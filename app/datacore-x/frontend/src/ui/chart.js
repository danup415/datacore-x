// Minimal canvas charts (sparklines and baseline-vs-scenario line charts).

export function sparkline(canvas, pts, { color = '#58a6ff', stale = false } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 80, h = canvas.clientHeight || 18;
  if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  if (!pts || pts.length < 2) return;
  let lo = Infinity, hi = -Infinity;
  for (const [, v] of pts) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (hi - lo < 1e-9) { hi += 0.5; lo -= 0.5; }
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  g.strokeStyle = stale ? '#6e7681' : color; g.lineWidth = 1.3;
  g.beginPath();
  pts.forEach(([t, v], i) => {
    const x = ((t - t0) / Math.max(1e-9, t1 - t0)) * (w - 2) + 1;
    const y = h - 2 - ((v - lo) / (hi - lo)) * (h - 4);
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  });
  g.stroke();
}

export function lineChart(canvas, series, { title = '', unit = '', playhead = null, threshold = null } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 300, h = canvas.clientHeight || 150;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const L = 42, R = 8, T = 18, B = 20;
  let lo = Infinity, hi = -Infinity, t0 = Infinity, t1 = -Infinity;
  for (const s of series) for (const [t, v] of s.pts) { if (v == null) continue; lo = Math.min(lo, v); hi = Math.max(hi, v); t0 = Math.min(t0, t); t1 = Math.max(t1, t); }
  if (threshold != null) { lo = Math.min(lo, threshold); hi = Math.max(hi, threshold); }
  if (!isFinite(lo)) return;
  const pad = (hi - lo) * 0.08 || 0.5; lo -= pad; hi += pad;
  const X = t => L + ((t - t0) / Math.max(1e-9, t1 - t0)) * (w - L - R);
  const Y = v => T + (1 - (v - lo) / (hi - lo)) * (h - T - B);
  g.font = '10px ui-monospace, monospace'; g.fillStyle = '#8b949e'; g.strokeStyle = '#21262d'; g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4, y = Y(v);
    g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke();
    g.fillText(v.toFixed(Math.abs(hi - lo) < 5 ? 2 : 1), 2, y + 3);
  }
  g.fillText(`${((t1 - t0) / 60).toFixed(0)} min`, w - R - 40, h - 5);
  g.fillText('0', L, h - 5);
  g.fillStyle = '#c9d1d9'; g.font = '11px system-ui, sans-serif'; g.fillText(`${title}${unit ? ' (' + unit + ')' : ''}`, L, 12);
  if (threshold != null) { g.strokeStyle = '#f8514988'; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(L, Y(threshold)); g.lineTo(w - R, Y(threshold)); g.stroke(); g.setLineDash([]); }
  let lx = w - R - 8;
  for (const s of [...series].reverse()) {
    g.strokeStyle = s.color; g.lineWidth = s.width || 1.6; g.setLineDash(s.dash || []);
    g.beginPath(); let first = true;
    for (const [t, v] of s.pts) { if (v == null) continue; const x = X(t), y = Y(v); first ? g.moveTo(x, y) : g.lineTo(x, y); first = false; }
    g.stroke(); g.setLineDash([]);
    const tw = g.measureText(s.name).width;
    lx -= tw + 22;
    g.fillStyle = s.color; g.fillRect(lx, 7, 12, 3); g.fillStyle = '#c9d1d9'; g.fillText(s.name, lx + 15, 12);
  }
  if (playhead != null) { g.strokeStyle = '#f0f6fc'; g.lineWidth = 1; g.beginPath(); g.moveTo(X(playhead), T); g.lineTo(X(playhead), h - B); g.stroke(); }
}
