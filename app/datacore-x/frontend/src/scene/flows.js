// Fluid, power and air flow visualisation.  All rates/directions/colours are
// derived from snapshot values (flows, velocities, powers, temperatures).
import * as THREE from 'three';
import { chevronTexture, tempColor } from './util.js';

function polyPath(pts) {
  const path = new THREE.CurvePath();
  for (let i = 0; i < pts.length - 1; i++) path.add(new THREE.LineCurve3(new THREE.Vector3(...pts[i]), new THREE.Vector3(...pts[i + 1])));
  return path;
}
const near = (p, q, r = 1.4) => Math.hypot(p[0] - q[0], p[2] - q[2]) < r;

// ---------------------------------------------------------------------------
export class Pipes {
  constructor(registry, layerGroup) {
    this.items = [];
    const reg = new Map(registry.assets.map(a => [a.id, a]));
    const bindables = registry.assets.filter(a => ['crah', 'pump', 'chiller', 'tower', 'hx'].includes(a.type));
    for (const a of registry.assets.filter(x => x.type === 'pipe')) {
      a.paths.forEach((pts, idx) => {
        const path = polyPath(pts);
        const len = path.getLength();
        const tex = chevronTexture().clone();
        tex.needsUpdate = true;
        tex.repeat.set(Math.max(1, len / 0.55), 1);
        const geo = new THREE.TubeGeometry(path, Math.max(8, Math.ceil(len * 4)), a.diameter_m / 2 + 0.01, 10, false);
        const m = new THREE.MeshStandardMaterial({ color: 0x58a6ff, map: tex, roughness: 0.45, metalness: 0.3, emissive: 0x000000 });
        const mesh = new THREE.Mesh(geo, m);
        mesh.userData.assetId = a.id;
        layerGroup.add(mesh);
        // bind branch flow to the equipment at either end (for proportional animation speed)
        let bind = null;
        for (const b of bindables) {
          const p = reg.get(b.id).pos;
          if (near(pts[pts.length - 1], p, 1.4) || near(pts[0], p, 1.4)) { bind = b; break; }
        }
        this.items.push({ asset: a, mesh, tex, len, bind });
      });
    }
  }
  pickables() { return this.items.map(i => i.mesh); }
  update(snap, dt) {
    for (const it of this.items) {
      const a = snap.assets[it.asset.id];
      if (!a) continue;
      const total = a.v.flow_ls ?? 0;
      let frac = 1;
      if (it.bind) {
        const b = snap.assets[it.bind.id];
        if (b) {
          if (it.bind.type === 'crah') frac = total > 0.05 ? (b.v.chw_flow_ls ?? 0) / total : 0;
          else if (it.bind.type === 'pump') frac = total > 0.05 ? (b.v.flow_ls ?? 0) / total : 0;
          else if (it.bind.type === 'chiller') frac = b.state === 'RUNNING' || b.state === 'STARTING' ? 1 : 0.05;
          else if (it.bind.type === 'tower') frac = b.state === 'RUNNING' ? 0.5 : 0;
        }
      }
      const vel = (a.v.velocity_ms ?? 0) * Math.min(1.5, frac);
      it.tex.offset.x -= dt * vel * 1.6 / 0.55;
      const base = { chw_supply: 0x1f6feb, chw_return: 0xdb6d28, condenser: 0x2ea043 }[it.asset.medium] ?? 0x8b949e;
      const c = new THREE.Color(base).lerp(tempColor(a.v.temp_c), 0.35);
      it.mesh.material.color.copy(c);
      it.mesh.material.emissive.copy(c).multiplyScalar(vel > 0.02 ? 0.18 : 0.0);
      if (vel <= 0.02) it.mesh.material.color.lerp(new THREE.Color(0x484f58), 0.6);
    }
  }
}

// ---------------------------------------------------------------------------
export class Cables {
  constructor(registry, layerGroup) {
    this.items = [];
    const reg = new Map(registry.assets.map(a => [a.id, a]));
    let k = 0;
    for (const [src, dst] of registry.electrical_links) {
      const A = reg.get(src), B = reg.get(dst);
      const top = a => [a.pos[0], a.pos[1] + a.size[1], a.pos[2]];
      const pa = top(A), pb = top(B);
      const yRun = (src.startsWith('PDU') ? 3.05 : 3.55) + (k % 6) * 0.035;
      const pts = [pa, [pa[0], yRun, pa[2]], [pb[0], yRun, pa[2]], [pb[0], yRun, pb[2]], pb];
      const clean = pts.filter((p, i) => i === 0 || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1], p[2] - pts[i - 1][2]) > 1e-3);
      const path = polyPath(clean);
      const len = path.getLength();
      const tex = chevronTexture().clone(); tex.needsUpdate = true; tex.repeat.set(Math.max(1, len / 0.4), 1);
      const geo = new THREE.TubeGeometry(path, Math.max(8, Math.ceil(len * 3)), 0.028, 6, false);
      const m = new THREE.MeshBasicMaterial({ color: 0xe3b341, map: tex, transparent: true, opacity: 0.9 });
      const mesh = new THREE.Mesh(geo, m);
      mesh.userData.assetId = src;
      layerGroup.add(mesh);
      this.items.push({ src, dst, mesh, tex });
      k++;
    }
  }
  power(snap, src, dst) {
    const v = (id, key) => snap.assets[id]?.v?.[key] ?? 0;
    if (src === 'TX-01') return v('TX-01', 'load_kva') * 0.95;
    if (src === 'GEN-01') return v('GEN-01', 'power_kw');
    if (src === 'SWG-01') {
      if (dst.startsWith('UPS')) return snap.assets[dst]?.state === 'DOUBLE_CONVERSION' ? v(dst, 'load_kw') + v(dst, 'losses_kw') : 0;
      return v(dst, 'power_kw') || v(dst, 'fan_kw');
    }
    if (src.startsWith('UPS') && dst.startsWith('BAT')) return -v(dst, 'current_a') * v(dst, 'voltage_v') / 1000; // + = charging
    if (src.startsWith('UPS')) return v(dst, 'load_kw');
    if (src.startsWith('PDU')) { const share = v(src, 'load_kw') / Math.max(1e-6, v('PDU-A', 'load_kw') + v('PDU-B', 'load_kw')); return v(dst, 'power_kw') * share; }
    return 0;
  }
  update(snap, dt) {
    for (const it of this.items) {
      const p = this.power(snap, it.src, it.dst);
      const mag = Math.abs(p);
      const speed = mag > 0.05 ? 0.6 + Math.min(2.5, mag / 40) : 0;
      it.tex.offset.x -= dt * speed * Math.sign(p || 1) / 0.4;
      it.mesh.material.color.setHex(mag > 0.05 ? (it.src.startsWith('UPS') && it.dst.startsWith('BAT') ? (p < 0 ? 0xf0883e : 0x56d4dd) : 0xe3b341) : 0x3d444d);
    }
  }
}

// ---------------------------------------------------------------------------
// Airflow: CRAH -> plenum -> tiles -> cold aisle -> rack -> hot aisle -> return
export class Airflow {
  constructor(registry, layerGroup) {
    this.reg = new Map(registry.assets.map(a => [a.id, a]));
    this.racks = registry.assets.filter(a => a.type === 'rack');
    this.crahs = registry.assets.filter(a => a.type === 'crah');
    this.plenumY = registry.airflow.plenum_y;
    this.returnY = registry.airflow.return_y;
    this.perRack = 22;
    this.perLoop = 10;
    const n = this.racks.length * (this.perRack + this.perLoop);
    const geo = new THREE.SphereGeometry(0.04, 6, 4);
    const m = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 });
    this.mesh = new THREE.InstancedMesh(geo, m, n);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.mesh.frustumCulled = false;
    layerGroup.add(this.mesh);
    this.parts = [];
    for (let r = 0; r < this.racks.length; r++) {
      for (let i = 0; i < this.perRack; i++) this.parts.push({ rack: r, loop: false, s: i / this.perRack + Math.random() * 0.02 });
      for (let i = 0; i < this.perLoop; i++) this.parts.push({ rack: r, loop: true, s: i / this.perLoop });
    }
    this.paths = new Map();
    this.tmp = new THREE.Matrix4();
    this.col = new THREE.Color();
    this.vec = new THREE.Vector3();
  }
  _path(rack, crah) {
    const key = rack.id + '|' + crah.id;
    if (this.paths.has(key)) return this.paths.get(key);
    const [x, y0, z] = rack.pos;
    const front = rack.rot_y_deg === 0 ? 1 : -1; // +z front for row A
    const zf = z + front * (rack.size[2] / 2), zr = z - front * (rack.size[2] / 2);
    const [cx, , cz] = crah.pos;
    const P = this.plenumY;
    const zt = 6.0;
    const pts = [
      [cx, 0.9, cz + Math.sign(6 - cz) * 0.5, 'sup'], [cx, P, cz + Math.sign(6 - cz) * 0.6, 'sup'],
      [x, P, zt, 'sup'], [x, y0 + 0.1, zt + front * 0.0, 'sup'], [x, y0 + 1.2, zf + front * 0.25, 'in'],
      [x, y0 + 1.2, zf, 'in'], [x, y0 + 1.2, zr, 'out'], [x, y0 + 1.5, zr - front * 0.6, 'out'],
      [x, this.returnY, zr - front * 1.2, 'ret'], [cx, crah.pos[1] + crah.size[1] + 0.25, cz, 'ret'],
    ];
    const vs = pts.map(p => new THREE.Vector3(p[0], p[1], p[2]));
    const segL = []; let L = 0;
    for (let i = 0; i < vs.length - 1; i++) { const l = vs[i].distanceTo(vs[i + 1]); segL.push(l); L += l; }
    const o = { vs, tags: pts.map(p => p[3]), segL, L };
    this.paths.set(key, o);
    return o;
  }
  _loop(rack) {
    const key = rack.id + '|loop';
    if (this.paths.has(key)) return this.paths.get(key);
    const [x, y0, z] = rack.pos;
    const front = rack.rot_y_deg === 0 ? 1 : -1;
    const zf = z + front * 0.6, zr = z - front * 0.6;
    const top = y0 + rack.size[1];
    const pts = [[x, top - 0.3, zr - front * 0.05, 'out'], [x, top + 0.15, zr, 'out'], [x, top + 0.15, zf, 'ret'],
      [x, top - 0.4, zf + front * 0.2, 'ret'], [x, top - 0.9, zf + front * 0.05, 'in']];
    const vs = pts.map(p => new THREE.Vector3(p[0], p[1], p[2]));
    const segL = []; let L = 0;
    for (let i = 0; i < vs.length - 1; i++) { const l = vs[i].distanceTo(vs[i + 1]); segL.push(l); L += l; }
    const o = { vs, tags: pts.map(p => p[3]), segL, L };
    this.paths.set(key, o);
    return o;
  }
  _sample(p, s, out) {
    let d = s * p.L;
    for (let i = 0; i < p.segL.length; i++) {
      if (d <= p.segL[i] || i === p.segL.length - 1) {
        const f = Math.min(1, d / p.segL[i]);
        out.copy(p.vs[i]).lerp(p.vs[i + 1], f);
        return p.tags[f < 0.5 ? i : i + 1];
      }
      d -= p.segL[i];
    }
    return 'sup';
  }
  chooseCrah(rack, snap) {
    const side = rack.pos[2] < 6 ? 'low' : 'high';
    const run = this.crahs.filter(c => snap.assets[c.id]?.state === 'RUNNING');
    const pref = run.filter(c => (c.pos[2] < 6 ? 'low' : 'high') === side);
    const pool = pref.length ? pref : run;
    if (!pool.length) return null;
    return pool.reduce((b, c) => (Math.abs(c.pos[0] - rack.pos[0]) < Math.abs(b.pos[0] - rack.pos[0]) ? c : b));
  }
  update(snap, dt) {
    const Tha = snap.assets['ZONE-HA']?.v?.temp_c;
    let k = 0;
    const chosen = this.racks.map(r => this.chooseCrah(r, snap));
    for (const p of this.parts) {
      const rack = this.racks[p.rack];
      const ra = snap.assets[rack.id];
      const crah = chosen[p.rack];
      let visible = !!ra && ra.state === 'RUNNING';
      let path;
      if (p.loop) {
        const res = ra?.diag?.residual_k ?? 0;
        visible = visible && res > 1.5 && (ra?.diag?.finding || '').includes('recirculation');
        path = this._loop(rack);
      } else {
        visible = visible && !!crah;
        path = crah ? this._path(rack, crah) : null;
      }
      if (!visible || !path) {
        this.tmp.makeScale(0, 0, 0); this.mesh.setMatrixAt(k, this.tmp); k++; continue;
      }
      const af = ra.v.airflow_m3s ?? 0.6;
      const vel = af / 1.2; // approx. face velocity (m/s) through 0.6 x 2.0 m rack face
      p.s = (p.s + dt * vel * 2.2 / path.L * (p.loop ? 0.6 : 1)) % 1;
      const tag = this._sample(path, p.s, this.vec);
      const T = tag === 'sup' ? (snap.assets[crah?.id]?.v?.supply_c ?? snap.assets['ZONE-CA']?.v?.temp_c)
        : tag === 'in' ? ra.v.inlet_c : tag === 'out' ? ra.v.outlet_c : Tha;
      this.col.copy(tempColor(T));
      if (p.loop) this.col.lerp(new THREE.Color(0xff7b00), 0.5);
      this.tmp.makeTranslation(this.vec.x, this.vec.y, this.vec.z);
      this.mesh.setMatrixAt(k, this.tmp);
      this.mesh.setColorAt(k, this.col);
      k++;
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }
}
