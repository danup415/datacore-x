import * as THREE from 'three';

export const STATE_COLOR = {
  RUNNING: 0x3fb950, MONITORED: 0x3fb950, ENERGISED: 0x3fb950, DOUBLE_CONVERSION: 0x3fb950, FLOWING: 0x3fb950,
  ON_UTILITY: 0x3fb950, FLOAT: 0x3fb950, CHARGING: 0x56d4dd,
  STANDBY: 0x58a6ff, STOPPED: 0x8b949e, BYPASS: 0x8b949e, NO_FLOW: 0x8b949e, COOLDOWN: 0x58a6ff,
  STARTING: 0xd29922, ON_GENERATOR: 0xd29922, BATTERY: 0xd29922, DISCHARGING: 0xd29922,
  TRIPPED: 0xf85149, NO_POWER: 0xbc4c8f, DEAD_BUS: 0xf85149, OUTPUT_OFF: 0xf85149, 'DE-ENERGISED': 0xbc4c8f,
  UNKNOWN: 0x6e7681, STALE: 0x6e7681,
};
export const stateColor = s => STATE_COLOR[s] ?? 0x6e7681;

export function healthColor(hi) {
  if (hi === null || hi === undefined) return 0x6e7681;
  if (hi >= 80) return 0x3fb950;
  if (hi >= 60) return 0xa5c94a;
  if (hi >= 40) return 0xd29922;
  return 0xf85149;
}

// Perceptual-ish thermal ramp 16 -> 40 °C (blue, cyan, green, yellow, orange, red)
const STOPS = [[16, [0.13, 0.30, 0.85]], [20, [0.10, 0.65, 0.95]], [24, [0.20, 0.80, 0.45]],
  [28, [0.95, 0.85, 0.20]], [33, [0.98, 0.50, 0.12]], [40, [0.85, 0.12, 0.12]]];
export function tempRGB(t) {
  if (t === null || t === undefined || Number.isNaN(t)) return [0.35, 0.37, 0.4];
  if (t <= STOPS[0][0]) return STOPS[0][1];
  for (let i = 1; i < STOPS.length; i++) {
    if (t <= STOPS[i][0]) {
      const [t0, c0] = STOPS[i - 1], [t1, c1] = STOPS[i];
      const f = (t - t0) / (t1 - t0);
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return STOPS[STOPS.length - 1][1];
}
export const tempColor = t => new THREE.Color(...tempRGB(t));

export function fmt(v, d = 1) {
  if (v === null || v === undefined) return '—';
  if (typeof v !== 'number') return String(v);
  return v.toFixed(d);
}

export function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.15, ...opts });
}

let _stripeTex;
export function rackFaceTexture() {
  if (_stripeTex) return _stripeTex;
  const c = document.createElement('canvas'); c.width = 64; c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 64, 256);
  for (let i = 0; i < 42; i++) {
    const y = 6 + i * 5.9;
    g.fillStyle = i % 2 ? '#d8d8d8' : '#c4c4c4';
    g.fillRect(4, y, 56, 4.6);
    g.fillStyle = '#7a7a7a'; g.fillRect(48, y + 1.5, 3, 1.6);
  }
  _stripeTex = new THREE.CanvasTexture(c);
  _stripeTex.colorSpace = THREE.SRGBColorSpace;
  return _stripeTex;
}

let _grille;
export function grilleTexture() {
  if (_grille) return _grille;
  const c = document.createElement('canvas'); c.width = 128; c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#b9c0c7'; g.fillRect(0, 0, 128, 128);
  g.fillStyle = '#7d858d';
  for (let y = 4; y < 128; y += 8) g.fillRect(6, y, 116, 3);
  _grille = new THREE.CanvasTexture(c); _grille.colorSpace = THREE.SRGBColorSpace;
  return _grille;
}

let _tile;
export function floorTileTexture() {
  if (_tile) return _tile;
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#3a4048'; g.fillRect(0, 0, 64, 64);
  g.strokeStyle = '#2a2f35'; g.lineWidth = 3; g.strokeRect(0, 0, 64, 64);
  _tile = new THREE.CanvasTexture(c);
  _tile.wrapS = _tile.wrapT = THREE.RepeatWrapping;
  _tile.colorSpace = THREE.SRGBColorSpace;
  return _tile;
}

let _perf;
export function perfTileTexture() {
  if (_perf) return _perf;
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#5d6670'; g.fillRect(0, 0, 64, 64);
  g.fillStyle = '#2b3036';
  for (let y = 6; y < 60; y += 7) for (let x = 6; x < 60; x += 7) { g.beginPath(); g.arc(x, y, 2, 0, 7); g.fill(); }
  g.strokeStyle = '#2a2f35'; g.lineWidth = 3; g.strokeRect(0, 0, 64, 64);
  _perf = new THREE.CanvasTexture(c); _perf.wrapS = _perf.wrapT = THREE.RepeatWrapping; _perf.colorSpace = THREE.SRGBColorSpace;
  return _perf;
}

let _chev;
export function chevronTexture() {
  if (_chev) return _chev;
  const c = document.createElement('canvas'); c.width = 128; c.height = 32;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 128, 32);
  g.fillStyle = '#9aa3ad';
  for (let x = 0; x < 128; x += 32) {
    g.beginPath(); g.moveTo(x + 6, 4); g.lineTo(x + 20, 16); g.lineTo(x + 6, 28); g.lineTo(x + 12, 28); g.lineTo(x + 26, 16); g.lineTo(x + 12, 4); g.closePath(); g.fill();
  }
  _chev = new THREE.CanvasTexture(c);
  _chev.wrapS = _chev.wrapT = THREE.RepeatWrapping;
  _chev.colorSpace = THREE.SRGBColorSpace;
  return _chev;
}

export function bboxLines(obj, color) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3()).addScalar(0.08);
  const ctr = box.getCenter(new THREE.Vector3());
  const geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x, size.y, size.z));
  const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color, transparent: true, depthTest: false }));
  l.position.copy(ctr);
  l.renderOrder = 10;
  return l;
}
