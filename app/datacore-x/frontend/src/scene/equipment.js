// Engineering-grade simplified equipment geometry.  Each builder returns
// { group, update(asset, dt) } where `asset` is the live snapshot entry for
// that registry asset.  Animated parts are driven ONLY by snapshot values.
import * as THREE from 'three';
import { mat, rackFaceTexture, grilleTexture, tempColor, stateColor } from './util.js';

const box = (w, h, d, m) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
const cyl = (r, h, m, seg = 24) => new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), m);

function fan(radius, blades = 5, color = 0x30363d) {
  const g = new THREE.Group();
  const m = mat(color, { metalness: 0.4 });
  const hub = cyl(radius * 0.18, 0.08, m);
  g.add(hub);
  for (let i = 0; i < blades; i++) {
    const b = box(radius * 0.85, 0.02, radius * 0.28, m);
    b.position.x = radius * 0.5;
    b.rotation.x = 0.35;
    const p = new THREE.Group(); p.add(b); p.rotation.y = (i / blades) * Math.PI * 2;
    g.add(p);
  }
  return g;
}

// ---------------------------------------------------------------------------
export function buildRack(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const body = box(w, h, d, mat(0x23272e, { roughness: 0.6 }));
  body.position.y = h / 2;
  g.add(body);
  const tex = rackFaceTexture();
  const front = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.92, h * 0.94), new THREE.MeshStandardMaterial({ map: tex, color: 0x4488ff, emissive: 0x112244, emissiveIntensity: 0.6, roughness: 0.5 }));
  front.position.set(0, h / 2, d / 2 + 0.004);
  const rear = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.92, h * 0.94), new THREE.MeshStandardMaterial({ map: tex, color: 0xff6633, emissive: 0x221108, emissiveIntensity: 0.6, roughness: 0.5 }));
  rear.position.set(0, h / 2, -d / 2 - 0.004); rear.rotation.y = Math.PI;
  g.add(front, rear);
  // utilisation bar on the front edge
  const barBg = box(0.04, h * 0.9, 0.02, mat(0x111418));
  barBg.position.set(w / 2 - 0.03, h / 2, d / 2 + 0.02);
  const bar = box(0.035, 1, 0.025, new THREE.MeshBasicMaterial({ color: 0x58a6ff }));
  bar.position.set(w / 2 - 0.03, 0, d / 2 + 0.025);
  g.add(barBg, bar);
  return {
    group: g, heightTop: h,
    update(asset) {
      const v = asset.v;
      front.material.color.copy(tempColor(v.inlet_c));
      front.material.emissive.copy(tempColor(v.inlet_c)).multiplyScalar(0.25);
      rear.material.color.copy(tempColor(v.outlet_c));
      rear.material.emissive.copy(tempColor(v.outlet_c)).multiplyScalar(0.25);
      const u = Math.max(0.02, Math.min(1, (v.cpu_util ?? 0) / 100));
      bar.scale.y = h * 0.9 * u;
      bar.position.y = h * 0.05 + (h * 0.9 * u) / 2;
      const off = asset.state !== 'RUNNING';
      if (off) { front.material.color.setHex(0x30343a); rear.material.color.setHex(0x30343a); front.material.emissive.setHex(0); rear.material.emissive.setHex(0); }
    },
  };
}

export function buildCRAH(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const body = box(w, h, d, mat(0xc9d1d9, { roughness: 0.5 }));
  body.position.y = h / 2;
  const gr = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.86, h * 0.6), new THREE.MeshStandardMaterial({ map: grilleTexture() }));
  gr.position.set(0, h * 0.62, d / 2 + 0.005);
  const panel = box(0.35, 0.22, 0.02, new THREE.MeshBasicMaterial({ color: 0x0d1117 }));
  panel.position.set(-w * 0.32, h * 0.18, d / 2 + 0.01);
  g.add(body, gr, panel);
  const fans = [];
  for (const x of [-w * 0.27, w * 0.27]) {
    const shroud = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.04, 8, 24), mat(0x6e7681));
    shroud.rotation.x = Math.PI / 2; shroud.position.set(x, h + 0.02, 0);
    const f = fan(0.34); f.position.set(x, h + 0.03, 0);
    g.add(shroud, f); fans.push(f);
  }
  const coil = box(w * 0.86, 0.06, 0.1, new THREE.MeshStandardMaterial({ color: 0x58a6ff, emissive: 0x0b2a55 }));
  coil.position.set(0, h * 0.32, d / 2 + 0.03);
  g.add(coil);
  return {
    group: g, heightTop: h + 0.1,
    update(asset, dt) {
      const s = (asset.v.fan_speed_pct ?? 0) / 100;
      for (const f of fans) f.rotation.y += dt * s * 18;
      coil.material.color.copy(tempColor(asset.v.supply_c));
      panel.material.color.setHex(stateColor(asset.state));
    },
  };
}

export function buildChiller(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const skid = box(w, 0.12, d, mat(0x30363d)); skid.position.y = 0.06;
  const evap = cyl(0.36, w * 0.85, mat(0x3b6ea8)); evap.rotation.z = Math.PI / 2; evap.position.set(0, 0.5, -d * 0.22);
  const cond = cyl(0.36, w * 0.85, mat(0xa86b3b)); cond.rotation.z = Math.PI / 2; cond.position.set(0, 0.5, d * 0.22);
  const comp = cyl(0.32, 0.7, mat(0x8b949e, { metalness: 0.5 })); comp.position.set(-w * 0.15, 1.25, 0);
  const comp2 = cyl(0.25, 0.5, mat(0x8b949e, { metalness: 0.5 })); comp2.rotation.z = Math.PI / 2; comp2.position.set(w * 0.12, 1.35, 0);
  const panel = box(0.6, 1.2, 0.3, mat(0xd0d7de)); panel.position.set(w * 0.42, 0.75, 0);
  const screen = box(0.32, 0.22, 0.02, new THREE.MeshBasicMaterial({ color: 0x3fb950 }));
  screen.position.set(w * 0.42, 1.05, 0.16);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 6, 24), new THREE.MeshBasicMaterial({ color: 0x58a6ff }));
  ring.position.copy(comp.position); ring.position.y += 0.37; ring.rotation.x = Math.PI / 2;
  g.add(skid, evap, cond, comp, comp2, panel, screen, ring);
  return {
    group: g, heightTop: h,
    update(asset, dt) {
      const run = asset.state === 'RUNNING';
      const plr = (asset.v.plr_pct ?? 0) / 100;
      ring.rotation.z += dt * (run ? 2 + 10 * plr : 0);
      ring.material.color.setHex(run ? 0x58a6ff : 0x30363d);
      screen.material.color.setHex(stateColor(asset.state));
      evap.material.color.copy(tempColor(asset.v.chws_c)).lerp(new THREE.Color(0x3b6ea8), 0.4);
      cond.material.color.copy(tempColor(asset.v.cwl_c)).lerp(new THREE.Color(0xa86b3b), 0.4);
    },
  };
}

export function buildPump(a) {
  const g = new THREE.Group();
  const base = box(1.3, 0.12, 0.55, mat(0x30363d)); base.position.y = 0.06;
  const motor = cyl(0.2, 0.6, mat(0x2f6feb)); motor.rotation.z = Math.PI / 2; motor.position.set(-0.3, 0.38, 0);
  const fins = cyl(0.21, 0.08, mat(0x1f4fb0)); fins.rotation.z = Math.PI / 2; fins.position.set(-0.62, 0.38, 0);
  const coupling = cyl(0.09, 0.2, mat(0xd29922)); coupling.rotation.z = Math.PI / 2; coupling.position.set(0.1, 0.38, 0);
  const volute = cyl(0.3, 0.22, mat(0x8b949e, { metalness: 0.6 })); volute.rotation.x = Math.PI / 2; volute.position.set(0.42, 0.42, 0);
  const notch = box(0.04, 0.2, 0.02, new THREE.MeshBasicMaterial({ color: 0x0d1117 }));
  const rotor = new THREE.Group(); rotor.add(notch); notch.position.y = 0.06;
  rotor.position.set(0.1, 0.38, 0.1); rotor.rotation.x = 0;
  const shaftDisc = cyl(0.1, 0.02, mat(0xf0f6fc)); shaftDisc.rotation.x = Math.PI / 2;
  const spin = new THREE.Group(); spin.add(shaftDisc); spin.add(rotor); spin.position.set(0, 0, 0);
  const disc = new THREE.Group(); disc.position.set(0.1, 0.38, 0.11); disc.add(shaftDisc.clone());
  const mark = box(0.02, 0.09, 0.02, new THREE.MeshBasicMaterial({ color: 0xf85149 })); mark.position.y = 0.045; mark.position.z = 0.012; disc.add(mark);
  const suction = cyl(0.07, 0.3, mat(0x8b949e)); suction.rotation.z = Math.PI / 2; suction.position.set(0.7, 0.42, 0);
  const disch = cyl(0.06, 0.3, mat(0x8b949e)); disch.position.set(0.42, 0.7, 0);
  g.add(base, motor, fins, coupling, volute, disc, suction, disch);
  return {
    group: g, heightTop: 0.95,
    update(asset, dt) {
      const n = (asset.v.speed_pct ?? 0) / 100;
      disc.rotation.z -= dt * n * 25;
      const vib = asset.v.vib_mms ?? 0;
      g.position.y = vib > 3 ? Math.sin(performance.now() / 18) * Math.min(0.012, vib * 0.0012) : 0;
      motor.material.color.setHex(asset.state === 'RUNNING' ? 0x2f6feb : (asset.state === 'TRIPPED' ? 0x8e2c2c : 0x3b4a66));
    },
  };
}

export function buildHX(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const frame = box(w, 0.1, d, mat(0x30363d)); frame.position.y = 0.05;
  const head = box(w, h, 0.08, mat(0x2f6feb)); head.position.set(0, h / 2, -d / 2 + 0.04);
  const tail = box(w, h, 0.08, mat(0x2f6feb)); tail.position.set(0, h / 2, d / 2 - 0.04);
  g.add(frame, head, tail);
  const plates = [];
  for (let i = 0; i < 14; i++) {
    const p = box(w * 0.86, h * 0.85, 0.035, mat(0xb1bac4, { metalness: 0.6 }));
    p.position.set(0, h / 2, -d / 2 + 0.14 + i * ((d - 0.28) / 13));
    g.add(p); plates.push(p);
  }
  return {
    group: g, heightTop: h,
    update(asset) {
      const on = asset.state === 'RUNNING';
      const c = tempColor(asset.v.chw_out_c);
      for (const p of plates) p.material.color.copy(on ? c.clone().lerp(new THREE.Color(0xb1bac4), 0.5) : new THREE.Color(0x6e7681));
    },
  };
}

export function buildTower(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const basin = box(w + 0.1, 0.35, d + 0.1, new THREE.MeshStandardMaterial({ color: 0x1f6feb, transparent: true, opacity: 0.85 }));
  basin.position.y = 0.175;
  const casing = box(w, h - 0.9, d, mat(0x8b949e, { transparent: true, opacity: 0.55 }));
  casing.position.y = 0.35 + (h - 0.9) / 2;
  const louv = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.9, 1.0), new THREE.MeshStandardMaterial({ map: grilleTexture(), side: THREE.DoubleSide }));
  louv.position.set(0, 0.9, d / 2 + 0.01);
  const deck = box(w, 0.08, d, mat(0x6e7681)); deck.position.y = h - 0.55;
  const stack = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 1.25, 0.55, 32, 1, true), mat(0x57606a, { side: THREE.DoubleSide }));
  stack.position.y = h - 0.25;
  const f = fan(1.05, 6); f.position.y = h - 0.35;
  const water = box(w * 0.92, h - 1.3, d * 0.92, new THREE.MeshStandardMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.0 }));
  water.position.y = 0.35 + (h - 1.3) / 2;
  g.add(basin, casing, louv, deck, stack, f, water);
  return {
    group: g, heightTop: h,
    update(asset, dt) {
      const s = (asset.v.fan_speed_pct ?? 0) / 100;
      f.rotation.y += dt * s * 9;
      water.material.opacity = asset.state === 'RUNNING' ? 0.18 + 0.15 * Math.min(1, (asset.v.heat_rej_kw ?? 0) / 150) : 0.0;
    },
  };
}

export function buildTransformer(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const tank = box(w * 0.7, h * 0.7, d * 0.7, mat(0x57606a)); tank.position.y = h * 0.35;
  g.add(tank);
  const finM = mat(0x6e7681);
  for (let i = 0; i < 9; i++) {
    for (const s of [-1, 1]) {
      const f = box(0.03, h * 0.55, d * 0.2, finM); f.position.set(-w * 0.3 + i * (w * 0.6 / 8), h * 0.33, s * (d * 0.45));
      g.add(f);
    }
  }
  const bushings = [];
  for (let i = 0; i < 3; i++) {
    const b = cyl(0.06, 0.45, mat(0xa0522d)); b.position.set(-0.4 + i * 0.4, h * 0.7 + 0.22, 0); g.add(b); bushings.push(b);
  }
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.08), new THREE.MeshBasicMaterial({ color: 0x3fb950 }));
  lamp.position.set(w * 0.36, h * 0.6, d * 0.36); g.add(lamp);
  return { group: g, heightTop: h, update(asset) { lamp.material.color.setHex(stateColor(asset.state)); } };
}

export function buildSwitchgear(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const n = 6; const cw = w / n;
  const lamps = [];
  for (let i = 0; i < n; i++) {
    const c = box(cw - 0.03, h, d, mat(0xd0d7de)); c.position.set(-w / 2 + cw / 2 + i * cw, h / 2, 0);
    const door = box(cw - 0.12, h * 0.4, 0.02, mat(0xaeb7c0)); door.position.set(c.position.x, h * 0.6, d / 2 + 0.01);
    const lamp = box(0.12, 0.06, 0.02, new THREE.MeshBasicMaterial({ color: 0x3fb950 })); lamp.position.set(c.position.x, h * 0.88, d / 2 + 0.02);
    g.add(c, door, lamp); lamps.push(lamp);
  }
  return {
    group: g, heightTop: h,
    update(asset) {
      const src = asset.v.source_code;
      lamps.forEach((l, i) => l.material.color.setHex(i === 0 ? (src === 1 ? 0x3fb950 : 0x30363d) : i === 1 ? (src === 2 ? 0xd29922 : 0x30363d) : (src ? 0x3fb950 : 0xf85149)));
    },
  };
}

export function buildGenerator(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const enc = box(w, h * 0.85, d, mat(0x2d6a4f)); enc.position.y = h * 0.425;
  const louv = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.3, h * 0.5), new THREE.MeshStandardMaterial({ map: grilleTexture() }));
  louv.position.set(w * 0.3, h * 0.45, d / 2 + 0.01);
  const stack = cyl(0.12, 0.9, mat(0x30363d)); stack.position.set(-w * 0.32, h * 0.85 + 0.45, 0);
  const smoke = new THREE.Mesh(new THREE.SphereGeometry(0.25, 12, 8), new THREE.MeshBasicMaterial({ color: 0x8b949e, transparent: true, opacity: 0 }));
  smoke.position.set(-w * 0.32, h * 0.85 + 1.05, 0);
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.08), new THREE.MeshBasicMaterial({ color: 0x8b949e }));
  lamp.position.set(-w * 0.4, h * 0.7, d / 2 + 0.05);
  g.add(enc, louv, stack, smoke, lamp);
  let ph = 0;
  return {
    group: g, heightTop: h + 0.9,
    update(asset, dt) {
      const run = asset.state === 'RUNNING' || asset.state === 'STARTING';
      ph += dt;
      smoke.material.opacity = run ? 0.25 + 0.15 * Math.sin(ph * 3) : 0;
      smoke.position.y = h * 0.85 + 1.05 + (run ? (ph % 1.5) * 0.4 : 0);
      lamp.material.color.setHex(stateColor(asset.state === 'STOPPED' ? 'STANDBY' : asset.state));
    },
  };
}

export function buildUPS(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const n = 3; const cw = w / n;
  for (let i = 0; i < n; i++) {
    const c = box(cw - 0.02, h, d, mat(0x24292f)); c.position.set(-w / 2 + cw / 2 + i * cw, h / 2, 0); g.add(c);
  }
  const screen = box(0.32, 0.2, 0.02, new THREE.MeshBasicMaterial({ color: 0x3fb950 })); screen.position.set(-w / 2 + cw / 2, h * 0.75, d / 2 + 0.01);
  const loadBg = box(0.06, h * 0.6, 0.02, new THREE.MeshBasicMaterial({ color: 0x0d1117 })); loadBg.position.set(0, h * 0.45, d / 2 + 0.01);
  const load = box(0.05, 1, 0.025, new THREE.MeshBasicMaterial({ color: 0x58a6ff })); load.position.set(0, 0, d / 2 + 0.015);
  g.add(screen, loadBg, load);
  return {
    group: g, heightTop: h,
    update(asset) {
      screen.material.color.setHex(stateColor(asset.state));
      const x = Math.max(0.01, Math.min(1, (asset.v.load_pct ?? 0) / 100));
      load.scale.y = h * 0.6 * x; load.position.y = h * 0.15 + (h * 0.6 * x) / 2;
      load.material.color.setHex(x > 0.8 ? 0xd29922 : 0x58a6ff);
    },
  };
}

export function buildBattery(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const frameM = mat(0x484f58);
  for (const x of [-w / 2 + 0.03, w / 2 - 0.03]) for (const z of [-d / 2 + 0.03, d / 2 - 0.03]) {
    const p = box(0.05, h, 0.05, frameM); p.position.set(x, h / 2, z); g.add(p);
  }
  const shelves = 4, per = 10;
  const blkGeo = new THREE.BoxGeometry(w / per - 0.03, h / shelves - 0.14, d * 0.7);
  const blkMat = new THREE.MeshStandardMaterial({ color: 0x30363d, roughness: 0.6 });
  const inst = new THREE.InstancedMesh(blkGeo, blkMat, shelves * per);
  const m4 = new THREE.Matrix4();
  for (let s = 0; s < shelves; s++) for (let i = 0; i < per; i++) {
    m4.makeTranslation(-w / 2 + (i + 0.5) * (w / per), (s + 0.5) * (h / shelves) - 0.02, 0);
    inst.setMatrixAt(s * per + i, m4);
  }
  for (let s = 0; s < shelves; s++) { const sh = box(w, 0.03, d, frameM); sh.position.y = s * (h / shelves); g.add(sh); }
  g.add(inst);
  const gaugeBg = box(w * 0.9, 0.08, 0.02, new THREE.MeshBasicMaterial({ color: 0x0d1117 })); gaugeBg.position.set(0, h + 0.08, d / 2);
  const gauge = box(1, 0.07, 0.025, new THREE.MeshBasicMaterial({ color: 0x3fb950 })); gauge.position.set(0, h + 0.08, d / 2 + 0.006);
  g.add(gaugeBg, gauge);
  const cols = [];
  for (let k = 0; k < shelves * per; k++) cols.push(new THREE.Color(0x30363d));
  return {
    group: g, heightTop: h + 0.15,
    update(asset) {
      const soc = Math.max(0, Math.min(1, (asset.v.soc_pct ?? 0) / 100));
      gauge.scale.x = w * 0.9 * Math.max(0.01, soc);
      gauge.position.x = -w * 0.45 + (w * 0.9 * soc) / 2;
      gauge.material.color.setHex(soc > 0.6 ? 0x3fb950 : soc > 0.3 ? 0xd29922 : 0xf85149);
      const tcol = tempColor(asset.v.temp_c).lerp(new THREE.Color(0x30363d), 0.65);
      for (let k = 0; k < shelves * per; k++) inst.setColorAt(k, tcol);
      if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
    },
  };
}

export function buildPDU(a) {
  const g = new THREE.Group();
  const [w, h, d] = a.size;
  const c = box(w, h, d, mat(0x30363d)); c.position.y = h / 2;
  const scr = box(0.3, 0.18, 0.02, new THREE.MeshBasicMaterial({ color: 0x3fb950 })); scr.position.set(0, h * 0.78, d / 2 + 0.01);
  const ph = [0, 1, 2].map(i => { const b = box(0.06, 1, 0.02, new THREE.MeshBasicMaterial({ color: 0x58a6ff })); b.position.set(-0.12 + i * 0.12, 0, d / 2 + 0.012); g.add(b); return b; });
  g.add(c, scr);
  return {
    group: g, heightTop: h,
    update(asset) {
      scr.material.color.setHex(stateColor(asset.state));
      const I = [asset.v.current_l1_a, asset.v.current_l2_a, asset.v.current_l3_a];
      ph.forEach((b, i) => { const x = Math.max(0.01, Math.min(1, (I[i] ?? 0) / 220)); b.scale.y = 0.8 * x; b.position.y = 0.3 + 0.4 * x; });
    },
  };
}

export const BUILDERS = {
  rack: buildRack, crah: buildCRAH, chiller: buildChiller, pump: buildPump, hx: buildHX, tower: buildTower,
  transformer: buildTransformer, switchgear: buildSwitchgear, generator: buildGenerator, ups: buildUPS,
  battery: buildBattery, pdu: buildPDU,
};
