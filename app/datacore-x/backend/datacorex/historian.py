"""Historian: persists every published snapshot (measured) and the matching
ground truth, keyed by the same ``seq``.  SQLite by default; the schema is
plain SQL so the PostgreSQL deployment in the blueprint uses the same tables
(set ``DCX_HISTORIAN`` to a file path; a Postgres writer can subscribe to the
same snapshot stream).  An in-memory ring buffer serves fast trend queries."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from pathlib import Path


class Historian:
    def __init__(self, path: str | None = None, ring: int = 7200):
        self.path = path or ":memory:"
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(
                """CREATE TABLE IF NOT EXISTS measured(seq INTEGER PRIMARY KEY, sim_time REAL, wall_ts REAL,
                                                     source TEXT, snap TEXT);
                   CREATE TABLE IF NOT EXISTS truth(seq INTEGER PRIMARY KEY, sim_time REAL, data TEXT);
                   CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, wall_ts REAL, rec TEXT);
                   CREATE INDEX IF NOT EXISTS ix_measured_t ON measured(sim_time);""")
        self.ring = deque(maxlen=ring)
        self.ok = True
        self._pending = []

    def write(self, snap: dict, truth: dict | None):
        flat = {aid: a.get("v", {}) for aid, a in snap["assets"].items()}
        flat["_facility"] = snap["facility"]
        hi = {aid: a["health"]["hi"] for aid, a in snap["assets"].items() if "health" in a}
        self.ring.append((snap["sim_time_s"], snap["seq"], flat, hi))
        self._pending.append((snap["seq"], snap["sim_time_s"], snap["wall_ts"], snap["source"]["id"],
                              json.dumps(snap, separators=(",", ":")),
                              json.dumps(truth, separators=(",", ":")) if truth is not None else None))
        if len(self._pending) >= 5:
            self.flush()

    def flush(self):
        if not self._pending:
            return
        try:
            with self.lock:
                self.db.executemany("INSERT OR REPLACE INTO measured VALUES (?,?,?,?,?)",
                                    [p[:5] for p in self._pending])
                self.db.executemany("INSERT OR REPLACE INTO truth VALUES (?,?,?)",
                                    [(p[0], p[1], p[5]) for p in self._pending if p[5] is not None])
                self.db.commit()
            self.ok = True
        except sqlite3.Error:
            self.ok = False
        self._pending = []

    def get(self, seq: int) -> dict | None:
        self.flush()
        with self.lock:
            row = self.db.execute("SELECT snap FROM measured WHERE seq=?", (seq,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_truth(self, seq: int) -> dict | None:
        self.flush()
        with self.lock:
            row = self.db.execute("SELECT data FROM truth WHERE seq=?", (seq,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def trend(self, asset: str, key: str, seconds: float = 900, max_points: int = 600):
        if not self.ring:
            return []
        t_end = self.ring[-1][0]
        pts = []
        for t, seq, flat, hi in self.ring:
            if t < t_end - seconds:
                continue
            v = hi.get(asset) if key == "health_hi" else flat.get(asset, {}).get(key)
            if v is not None:
                pts.append((t, v))
        if len(pts) > max_points:
            step = len(pts) / max_points
            pts = [pts[int(i * step)] for i in range(max_points)]
        return pts

    def log_command(self, rec: dict):
        try:
            with self.lock:
                self.db.execute("INSERT OR REPLACE INTO commands VALUES (?,?,?)",
                                (rec["id"], rec["received_wall"], json.dumps(rec)))
                self.db.commit()
        except sqlite3.Error:
            self.ok = False
