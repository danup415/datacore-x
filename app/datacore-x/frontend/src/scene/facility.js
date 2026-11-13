// Facility scene assembly from the asset registry: building shell, equipment,
// zones, flows, heatmap, status/health/alarm indicators, labels, highlight and
// isolation.  Nothing is placed that is not in the registry.
import * as THREE from 'three';
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import { BUILDERS } from './equipment.js';
import { Pipes, Cables, Airflow } from './flows.js';
import { Heatmap } from './heatmap.js';
import { bboxLines, floorTileTexture, perfTileTexture, healthColor, stateColor, fmt, mat } from './util.js';

const LAYERS = ['building', 'it', 'cooling', 'electrical', 'piping', 'cables', 'airflow', 'heatmap', 'zone', 'indicators', 'labels'];

const PRIMARY = {
  rack: a => `${fmt(a.v.inlet_c, 1)}°C in`, crah: a => `${fmt(a.v.fan_speed_pct, 0)}% fan`,
  chiller: a => `${fmt(a.v.load_kw, 0)} kW · COP ${fmt(a.v.cop, 1)}`, pump: a => `${fmt(a.v.flow_ls, 2)} L/s`,
  hx: a => `${fmt(a.v.duty_kw, 0)} kW`, tower: a => `${fmt(a.v.leaving_c, 1)}°C`,
  transformer: a => `${fmt(a.v.load_pct, 0)}%`, switchgear: a => ['DEAD', 'UTILITY', 'GENERATOR'][a.v.source_code ?? 0] ?? '—',
  generator: a => `${fmt(a.v.power_kw, 0)} kW`, ups: a => `${fmt(a.v.load_pct, 0)}% ${a.state === 'BATTERY' ? '⚡BATT' : ''}`,
  battery: a => `SoC ${fmt(a.v.soc_pct, 0)}%`, pdu: a => `${fmt(a.v.load_kw, 1)} kW`,
};

function alarmSprite() {
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff'; g.beginPath(); g.moveTo(32, 4); g.lineTo(62, 58); g.lineTo(2, 58); g.closePath(); g.fill();
  g.fillStyle = '#0d1117'; g.font = 'bold 40px sans-serif'; g.textAlign = 'center'; g.fillText('!', 32, 54);
  const t = new THREE.CanvasTexture(c);
  return new THREE.Sprite(new THREE.SpriteMaterial({ map: t, color: 0xf85149, depthTest: false, transparent: true }));
}
const PRIO_COL = { CRITICAL: 0xf85149, HIGH: 0xf0883e, MEDIUM: 0xd29922, LOW: 0x58a6ff };

export class Facility {
  constructor(registry, scene) {
    this.registry = registry;
    this.reg = new Map(registry.assets.map(a => [a.id, a]));
    this.root = new THREE.Group();
    scene.add(this.root);
    this.layers = {};
    for (const l of LAYERS) { const g = new THREE.Group(); g.name = l; this.layers[l] = g; this.root.add(g); }
    this.objs = new Map(); // id -> {def, group, ctrl, light, ring, alarm, label, hl, sel}
    this.pickables = [];
    this.labelsOn = true;
    this.isolated = null;
    this.selected = null;
    this.showInjected = false;
    this._buildBuilding();
    this._buildAssets();
    this.pipes = new Pipes(registry, this.layers.piping);
    this.cables = new Cables(registry, this.layers.cables);
    this.airflow = new Airflow(registry, this.layers.airflow);
    this.heatmap = new Heatmap(registry, this.layers.heatmap);
    for (const m of this.pipes.pickables()) this.pickables.push(m);
    this.hotspots = new Map();
    this.t = 0;
  }

  // ------------------------------------------------------------------
  _buildBuilding() {
    const L = this.layers.building;
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(90, 70), mat(0x10151b, { roughness: 1 }));
    ground.rotation.x = -Math.PI / 2; ground.position.set(16, -0.02, 11); ground.receiveShadow = true;
    L.add(ground);
    const grid = new THREE.GridHelper(90, 90, 0x1b222b, 0x161c23); grid.position.set(16, -0.01, 11); L.add(grid);
    const slab = (id, color, y = 0.05) => {
      const a = this.reg.get(id);
      const m = new THREE.Mesh(new THREE.BoxGeometry(a.size[0], 0.1, a.size[2]), mat(color, { roughness: 0.95 }));
      m.position.set(a.pos[0], y, a.pos[2]); m.receiveShadow = true; L.add(m); return m;
    };
    slab('PR-01', 0x2b3138); slab('ER-01', 0x2b3138); slab('YARD-01', 0x353b42, 0.02); slab('ROOF-01', 0x3b4249);
    // raised floor in data hall
    const dh = this.reg.get('DH-01');
    const ft = floorTileTexture().clone(); ft.needsUpdate = true; ft.repeat.set(dh.size[0] / 0.6, dh.size[2] / 0.6);
    const rf = new THREE.Mesh(new THREE.BoxGeometry(dh.size[0], 0.6, dh.size[2]),
      [mat(0x2b3138), mat(0x2b3138), new THREE.MeshStandardMaterial({ map: ft, transparent: true, opacity: 0.82, roughness: 0.9 }), mat(0x2b3138), mat(0x2b3138), mat(0x2b3138)]);
    rf.position.set(dh.pos[0], 0.3, dh.pos[2]); rf.receiveShadow = true;
    L.add(rf);
    this.raisedFloor = rf;
    const pt = perfTileTexture().clone(); pt.needsUpdate = true; pt.repeat.set(3.4 / 0.6, 1.6 / 0.6);
    const perf = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.6), new THREE.MeshStandardMaterial({ map: pt }));
    perf.rotation.x = -Math.PI / 2; perf.position.set(7.0, 0.605, 6.0); L.add(perf);
    // walls (translucent shells + edges)
    for (const id of ['DH-01', 'PR-01', 'ER-01']) {
      const a = this.reg.get(id);
      const geo = new THREE.BoxGeometry(a.size[0], a.size[1], a.size[2]);
      const shell = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x8aa4c8, transparent: true, opacity: 0.035, depthWrite: false, side: THREE.BackSide }));
      shell.position.set(a.pos[0], a.size[1] / 2, a.pos[2]);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x3d4b5c }));
      edges.position.copy(shell.position);
      L.add(shell, edges);
      const div = document.createElement('div'); div.className = 'room-lbl'; div.textContent = a.name;
      const lbl = new CSS2DObject(div); lbl.position.set(a.pos[0] - a.size[0] / 2 + 1.2, a.size[1] + 0.2, a.pos[2] - a.size[2] / 2 + 0.3);
      this.layers.labels.add(lbl);
    }
    for (const id of ['YARD-01', 'ROOF-01']) {
      const a = this.reg.get(id);
      const div = document.createElement('div'); div.className = 'room-lbl'; div.textContent = a.name;
      const lbl = new CSS2DObject(div); lbl.position.set(a.pos[0], 0.4, a.pos[2] + a.size[2] / 2 - 0.4);
      this.layers.labels.add(lbl);
    }
  }

  _buildZones() {
    const Z = this.layers.zone;
    const glass = new THREE.MeshStandardMaterial({ color: 0x79c0ff, transparent: true, opacity: 0.16, roughness: 0.1, metalness: 0.1, depthWrite: false, side: THREE.DoubleSide });
    const ca = this.reg.get('ZONE-CA');
    const g = new THREE.Group();
    const y0 = ca.pos[1], top = y0 + ca.size[1];
    const roof = new THREE.Mesh(new THREE.PlaneGeometry(ca.size[0], ca.size[2]), glass); roof.rotation.x = -Math.PI / 2; roof.position.set(ca.pos[0], top, ca.pos[2]);
    const d1 = new THREE.Mesh(new THREE.PlaneGeometry(ca.size[2], ca.size[1]), glass); d1.rotation.y = Math.PI / 2; d1.position.set(ca.pos[0] - ca.size[0] / 2, y0 + ca.size[1] / 2, ca.pos[2]);
    const d2 = d1.clone(); d2.position.x = ca.pos[0] + ca.size[0] / 2;
    for (const m of [roof, d1, d2]) { m.userData.assetId = 'ZONE-CA'; g.add(m); this.pickables.push(m); }
    const fr = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(...ca.size)), new THREE.LineBasicMaterial({ color: 0x58a6ff }));
    fr.position.set(ca.pos[0], y0 + ca.size[1] / 2, ca.pos[2]); g.add(fr);
    Z.add(g);
    const ha = new THREE.Group();
    const hm = new THREE.MeshBasicMaterial({ color: 0xf85149, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide });
    for (const z of [3.5, 8.5]) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 1.0), hm); p.rotation.x = -Math.PI / 2; p.position.set(7.0, 0.62, z);
      p.userData.assetId = 'ZONE-HA'; ha.add(p); this.pickables.push(p);
    }
    Z.add(ha);
    this.objs.set('ZONE-CA', { def: ca, group: g, ctrl: { update() {} }, top: top });
    this.objs.set('ZONE-HA', { def: this.reg.get('ZONE-HA'), group: ha, ctrl: { update() {} }, top: 0.9 });
    this.zoneHa = hm; this.zoneGlass = glass;
  }

  _buildAssets() {
    this._buildZones();
    for (const a of this.registry.assets) {
      const B = BUILDERS[a.type];
      if (!B) continue;
      const ctrl = B(a);
      const g = ctrl.group;
      g.position.set(...a.pos);
      g.rotation.y = (a.rot_y_deg || 0) * Math.PI / 180;
      g.traverse(o => { if (o.isMesh) { o.userData.assetId = a.id; o.castShadow = true; this.pickables.push(o); } });
      const layer = this.layers[a.layer] || this.layers.cooling;
      layer.add(g);
      const top = a.pos[1] + (ctrl.heightTop ?? a.size[1]);
      // status light + health ring
      const light = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), new THREE.MeshBasicMaterial({ color: 0x6e7681 }));
      light.position.set(a.pos[0], top + 0.25, a.pos[2]);
      this.layers.indicators.add(light);
      let ring = null;
      if (a.has_health) {
        ring = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.035, 8, 24), new THREE.MeshBasicMaterial({ color: 0x3fb950 }));
        ring.position.copy(light.position);
        this.layers.indicators.add(ring);
      }
      const alarm = alarmSprite(); alarm.scale.set(0.45, 0.45, 1); alarm.position.set(a.pos[0], top + 0.75, a.pos[2]); alarm.visible = false;
      this.layers.indicators.add(alarm);
      const div = document.createElement('div'); div.className = 'lbl';
      div.innerHTML = `<b>${a.id}</b><span></span>`;
      div.dataset.asset = a.id;
      const label = new CSS2DObject(div); label.position.set(a.pos[0], top + 0.45, a.pos[2]);
      this.layers.labels.add(label);
      const hl = bboxLines(g, 0xf85149); hl.scale.multiplyScalar(1.03); hl.visible = false; this.root.add(hl);
      const sel = bboxLines(g, 0x39d0ff); sel.visible = false; this.root.add(sel);
      const gt = bboxLines(g, 0xbc8cff); gt.visible = false; gt.scale.multiplyScalar(1.07); this.root.add(gt);
      this.objs.set(a.id, { def: a, group: g, ctrl, light, ring, alarm, label, div, hl, sel, gt, top });
    }
    // hotspot marker ring per rack (shown when measured inlet > 27 °C)
    this.hotspotMarkers = new Map();
    for (const a of this.registry.assets.filter(x => x.type === 'rack')) {
      const f = a.rot_y_deg === 0 ? 1 : -1;
      const m = new THREE.Mesh(new THREE.RingGeometry(0.25, 0.36, 24), new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false }));
      m.position.set(a.pos[0], a.pos[1] + 1.2, a.pos[2] + f * 0.62); m.visible = false;
      this.layers.indicators.add(m);
      this.hotspotMarkers.set(a.id, m);
    }
  }

  // ------------------------------------------------------------------
  setLayer(name, on) {
    if (name === 'labels') { this.labelsOn = on; this.layers.labels.visible = on; for (const o of this.objs.values()) if (o.label) o.label.visible = on; return; }
    if (this.layers[name]) this.layers[name].visible = on;
  }
  layerNames() { return LAYERS; }

  select(id) {
    if (this.selected && this.objs.get(this.selected)?.sel) this.objs.get(this.selected).sel.visible = false;
    this.selected = id;
    const o = id && this.objs.get(id);
    if (o?.sel) { o.sel.visible = true; }
  }
  isolate(id) {
    this.isolated = id;
    const keep = new Set();
    if (id) {
      keep.add(id);
      for (const a of this.registry.assets) if (a.parent === id) keep.add(a.id);
    }
    for (const [aid, o] of this.objs) {
      const vis = !id || keep.has(aid);
      o.group.visible = vis;
      if (o.light) o.light.visible = vis;
      if (o.ring) o.ring.visible = vis;
      if (o.label) o.label.visible = vis && this.labelsOn;
    }
    const flowLayers = ['piping', 'cables', 'airflow', 'heatmap'];
    if (id) {
      if (!this._preIso) this._preIso = Object.fromEntries(flowLayers.map(l => [l, this.layers[l].visible]));
      const isPipe = this.reg.get(id)?.type === 'pipe';
      this.layers.piping.visible = isPipe;
      for (const m of this.pipes.items) m.mesh.visible = !isPipe || m.asset.id === id;
      this.layers.cables.visible = false; this.layers.airflow.visible = false; this.layers.heatmap.visible = false;
    } else if (this._preIso) {
      for (const l of flowLayers) this.layers[l].visible = this._preIso[l];
      for (const m of this.pipes.items) m.mesh.visible = true;
      this._preIso = null;
    }
    this.raisedFloor.material[2].opacity = id ? 0.25 : 0.82;
  }
  assetCenter(id) {
    const o = this.objs.get(id);
    if (o) return new THREE.Box3().setFromObject(o.group).getCenter(new THREE.Vector3());
    const a = this.reg.get(id);
    if (a?.type === 'pipe') { const p = a.paths[2] || a.paths[0]; return new THREE.Vector3(...p[Math.floor(p.length / 2)]); }
    if (a) return new THREE.Vector3(a.pos[0], a.pos[1] + a.size[1] / 2, a.pos[2]);
    return new THREE.Vector3(13, 0, 10);
  }
  assetRadius(id) {
    const o = this.objs.get(id);
    if (o) { const s = new THREE.Box3().setFromObject(o.group).getSize(new THREE.Vector3()); return Math.max(s.x, s.y, s.z); }
    const a = this.reg.get(id);
    return a ? Math.max(...a.size, 4) : 20;
  }

  // ------------------------------------------------------------------
  update(snap, dt, { stale = false } = {}) {
    this.t += dt;
    const blink = (Math.sin(this.t * 6) + 1) / 2;
    const alarmBy = new Map();
    for (const al of snap.alarms || []) {
      const cur = alarmBy.get(al.asset);
      const rank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 }[al.priority];
      if (!cur || rank > cur.rank) alarmBy.set(al.asset, { rank, al, unacked: al.state !== 'ACTIVE_ACK' });
      else if (al.state !== 'ACTIVE_ACK') cur.unacked = true;
    }
    const injected = new Set((snap.faults_injected || []).filter(f => f.severity_now > 0).map(f => f.asset));
    for (const [id, o] of this.objs) {
      const a = snap.assets[id];
      if (!a) continue;
      o.ctrl.update(a, dt, snap);
      if (o.light) o.light.material.color.setHex(stale ? 0x6e7681 : stateColor(a.state));
      if (o.ring) o.ring.material.color.setHex(stale ? 0x6e7681 : healthColor(a.health?.hi));
      const al = alarmBy.get(id);
      if (o.alarm) {
        o.alarm.visible = !!al;
        if (al) { o.alarm.material.color.setHex(PRIO_COL[al.al.priority]); o.alarm.material.opacity = al.unacked ? 0.35 + 0.65 * blink : 1; }
      }
      // detected-fault highlight (intelligence output, not ground truth)
      const det = a.health && a.health.fault_code && (a.health.prob ?? 0) >= 0.5;
      const diagFault = a.diag && a.diag.finding && a.diag.finding !== 'Consistent with twin';
      if (o.hl) {
        o.hl.visible = !!(det || diagFault || a.state === 'TRIPPED' || a.state === 'NO_POWER' || a.state === 'OUTPUT_OFF');
        if (o.hl.visible) { o.hl.material.color.setHex((a.health?.hi ?? 100) < 40 || a.state === 'TRIPPED' ? 0xf85149 : 0xf0883e); o.hl.material.opacity = 0.4 + 0.6 * blink; }
      }
      if (o.gt) o.gt.visible = this.showInjected && injected.has(id);
      if (o.div && this.labelsOn) {
        const pf = PRIMARY[o.def.type];
        o.div.querySelector('span').textContent = pf ? pf(a) : '';
        o.div.classList.toggle('stale', stale);
        o.div.classList.toggle('alarm', !!al);
        o.div.classList.toggle('sel', this.selected === id);
      }
    }
    for (const [id, m] of this.hotspotMarkers) {
      const t = snap.assets[id]?.v?.inlet_c;
      m.visible = t != null && t > 27;
      if (m.visible) { const s = 1 + 0.25 * blink; m.scale.set(s, s, s); m.material.opacity = 0.5 + 0.5 * blink; }
    }
    if (this.zoneHa) {
      const tha = snap.assets['ZONE-HA']?.v?.temp_c ?? 34;
      this.zoneHa.opacity = 0.06 + Math.min(0.3, Math.max(0, (tha - 30) / 30));
    }
    if (this.layers.piping.visible) this.pipes.update(snap, dt);
    if (this.layers.cables.visible) this.cables.update(snap, dt);
    if (this.layers.airflow.visible) this.airflow.update(snap, dt);
  }
  labelLOD(camera) {
    if (!this.labelsOn) return;
    const p = camera.position;
    for (const o of this.objs.values()) if (o.ring) o.ring.quaternion.copy(camera.quaternion);
    for (const o of this.objs.values()) {
      if (!o.label || !o.group.visible) continue;
      const small = o.def.type === 'rack' || o.def.type === 'pdu' || o.def.type === 'battery' || o.def.type === 'ups';
      const d = p.distanceTo(o.label.position);
      o.label.visible = this.selected === o.def.id || !small || d < 13;
    }
  }
  updateSlow(snap) { if (this.layers.heatmap.visible) this.heatmap.update(snap); }
}
