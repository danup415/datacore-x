// Thermal heatmap: inverse-distance-weighted interpolation of *measured*
// virtual-sensor temperatures on a horizontal plane in the data hall.
// This is a visual interpolation of sensor data, not a CFD field — the UI
// states that explicitly.
import * as THREE from 'three';
import { tempRGB } from './util.js';

export class Heatmap {
  constructor(registry, layerGroup) {
    const dh = registry.assets.find(a => a.id === 'DH-01');
    this.x0 = dh.pos[0] - dh.size[0] / 2; this.z0 = dh.pos[2] - dh.size[2] / 2;
    this.w = dh.size[0]; this.d = dh.size[2];
    this.res = 8; // px per metre
    this.cw = Math.round(this.w * this.res); this.ch = Math.round(this.d * this.res);
    this.canvas = document.createElement('canvas');
    this.canvas.width = this.cw; this.canvas.height = this.ch;
    this.ctx = this.canvas.getContext('2d');
    this.img = this.ctx.createImageData(this.cw, this.ch);
    this.tex = new THREE.CanvasTexture(this.canvas);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    this.tex.minFilter = THREE.LinearFilter;
    const m = new THREE.MeshBasicMaterial({ map: this.tex, transparent: true, opacity: 0.72, depthWrite: false, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(this.w, this.d), m);
    this.mesh.rotation.x = -Math.PI / 2;
    this.floorY = 0.6;
    this.height = 0.03; // drawing plane (sensor field is the ~1.2 m sensor layer)
    this.mesh.position.set(dh.pos[0], this.floorY + this.height, dh.pos[2]);
    this.mesh.renderOrder = 5;
    layerGroup.add(this.mesh);
    this.racks = registry.assets.filter(a => a.type === 'rack');
    this.crahs = registry.assets.filter(a => a.type === 'crah');
    this.nSensors = 0;
  }
  setHeight(h) { this.height = h; this.mesh.position.y = this.floorY + h; }
  points(snap) {
    const P = [];
    const A = snap.assets;
    const h = this.height;
    const wIn = 1;
    for (const r of this.racks) {
      const a = A[r.id]; if (!a) continue;
      const f = r.rot_y_deg === 0 ? 1 : -1;
      if (a.v.inlet_c != null) P.push([r.pos[0], r.pos[2] + f * 0.7, a.v.inlet_c, wIn]);
      if (a.v.outlet_c != null) P.push([r.pos[0], r.pos[2] - f * 0.75, a.v.outlet_c, 1]);
    }
    const ca = A['ZONE-CA']?.v?.temp_c, ha = A['ZONE-HA']?.v?.temp_c;
    if (ca != null) for (const x of [5.8, 7.0, 8.2]) P.push([x, 6.0, ca, wIn]);
    if (ha != null) for (const [x, z] of [[1.5, 3], [12.5, 3], [1.5, 9], [12.5, 9], [7, 2.2], [7, 9.8], [1.5, 6], [12.5, 6]]) P.push([x, z, ha, 0.8]);
    for (const c of this.crahs) {
      const a = A[c.id]; if (!a) continue;
      const toward = c.pos[2] < 6 ? 1 : -1;
      if (a.v.return_c != null) P.push([c.pos[0], c.pos[2] + toward * 0.6, a.v.return_c, 0.7]);
    }
    this.nSensors = P.length;
    return P;
  }
  update(snap) {
    const P = this.points(snap);
    const d = this.img.data;
    let k = 0;
    for (let j = 0; j < this.ch; j++) {
      const z = this.z0 + (j + 0.5) / this.res;
      for (let i = 0; i < this.cw; i++) {
        const x = this.x0 + (i + 0.5) / this.res;
        let ws = 0, ts = 0;
        for (const p of P) {
          const dd = (p[0] - x) ** 2 + (p[1] - z) ** 2 + 0.05;
          const w = p[3] / (dd * dd);
          ws += w; ts += w * p[2];
        }
        const T = ts / ws;
        const c = tempRGB(T);
        d[k++] = c[0] * 255; d[k++] = c[1] * 255; d[k++] = c[2] * 255; d[k++] = 255;
      }
    }
    this.ctx.putImageData(this.img, 0, 0);
    this.tex.needsUpdate = true;
  }
}
