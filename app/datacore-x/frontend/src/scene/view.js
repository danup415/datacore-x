// Renderer, cameras, navigation (orbit/pan/zoom + first-person walkthrough),
// picking, hover and camera transitions.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PointerLockControls } from 'three/examples/jsm/controls/PointerLockControls.js';
import { CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

export const PRESETS = {
  facility: { pos: [-6, 26, 40], target: [15, 0, 10] },
  datahall: { pos: [7, 12.5, 18.5], target: [7, 0.8, 6] },
  coldaisle: { pos: [7.0, 2.3, 8.7], target: [7.0, 1.3, 5.2] },
  plant: { pos: [19, 9, 16], target: [21, 0.5, 5.5] },
  electrical: { pos: [7, 9, 26], target: [7, 0.5, 16] },
  yard: { pos: [26, 11, 32], target: [20, 0.5, 18] },
};

export class View {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0b0f14);
    this.scene.fog = new THREE.Fog(0x0b0f14, 60, 140);
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.05, 400);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'css2d';
    container.appendChild(this.labels.domElement);
    // lights
    this.scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x1a1f26, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-10, 30, 25); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -30, right: 30, top: 30, bottom: -30, near: 1, far: 90 });
    sun.target.position.set(15, 0, 10);
    this.scene.add(sun, sun.target);
    const fill = new THREE.PointLight(0x9ecbff, 20, 18); fill.position.set(7, 3.6, 6); this.scene.add(fill);
    // controls
    this.orbit = new OrbitControls(this.camera, this.renderer.domElement);
    this.orbit.enableDamping = true;
    this.orbit.dampingFactor = 0.08;
    this.orbit.maxPolarAngle = Math.PI * 0.495;
    this.orbit.minDistance = 0.6; this.orbit.maxDistance = 120;
    this.orbit.screenSpacePanning = true;
    this.walk = new PointerLockControls(this.camera, this.renderer.domElement);
    this.walking = false;
    this.keys = {};
    this.walkSpeed = 3.0;
    addEventListener('keydown', e => { if (!e.target.closest('input,select,textarea')) this.keys[e.code] = true; });
    addEventListener('keyup', e => { this.keys[e.code] = false; });
    this.walk.addEventListener('unlock', () => { if (this.walking) this.setWalk(false); });
    this.ray = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.tween = null;
    this.pickables = [];
    this.onPick = () => {};
    this.onDouble = () => {};
    this.onHover = () => {};
    this._down = null;
    const el = this.renderer.domElement;
    el.addEventListener('pointerdown', e => { this._down = [e.clientX, e.clientY]; });
    el.addEventListener('pointerup', e => {
      if (this.walking || !this._down) return;
      const moved = Math.hypot(e.clientX - this._down[0], e.clientY - this._down[1]);
      if (moved < 5 && e.button === 0) this.onPick(this.pick(e));
    });
    el.addEventListener('dblclick', e => { if (!this.walking) this.onDouble(this.pick(e)); });
    el.addEventListener('pointermove', e => { if (!this.walking) this.onHover(this.pick(e), e); });
    this.resize();
    addEventListener('resize', () => this.resize());
    // also follow the container itself (embedded iframes / grid layouts settle after init)
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => this.resize()).observe(this.container);
    this.goto(PRESETS.facility, 0);
  }
  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.camera.aspect = w / Math.max(1, h); this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h); this.labels.setSize(w, h);
  }
  pick(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.mouse, this.camera);
    const hits = this.ray.intersectObjects(this.pickables.filter(o => this._visible(o)), false);
    return hits.length ? hits[0].object.userData.assetId : null;
  }
  _visible(o) { while (o) { if (!o.visible) return false; o = o.parent; } return true; }
  goto(p, ms = 900) {
    const from = { pos: this.camera.position.clone(), target: this.orbit.target.clone() };
    const to = { pos: new THREE.Vector3(...p.pos), target: new THREE.Vector3(...p.target) };
    if (!ms) { this.camera.position.copy(to.pos); this.orbit.target.copy(to.target); this.orbit.update(); return; }
    this.tween = { from, to, t0: performance.now(), ms };
  }
  focus(center, radius) {
    const dir = this.camera.position.clone().sub(this.orbit.target).normalize();
    if (dir.y < 0.25) dir.y = 0.35;
    dir.normalize();
    const dist = Math.max(2.2, radius * 2.1);
    const pos = center.clone().add(dir.multiplyScalar(dist));
    this.goto({ pos: pos.toArray(), target: center.toArray() });
  }
  setWalk(on) {
    this.walking = on;
    if (on) {
      this.orbit.enabled = false;
      const t = this.orbit.target;
      this.camera.position.set(1.2, 0.6 + 1.7, 6.0);
      this.camera.lookAt(t.x, 1.6, t.z);
      this.camera.lookAt(13, 2.0, 6.0);
      this.walk.lock();
    } else {
      this.walk.unlock();
      this.orbit.enabled = true;
      const d = new THREE.Vector3(); this.camera.getWorldDirection(d);
      this.orbit.target.copy(this.camera.position).add(d.multiplyScalar(4));
    }
  }
  update(dt) {
    if (this.tween) {
      const { from, to, t0, ms } = this.tween;
      let f = Math.min(1, (performance.now() - t0) / ms);
      f = f < 0.5 ? 4 * f * f * f : 1 - (-2 * f + 2) ** 3 / 2;
      this.camera.position.lerpVectors(from.pos, to.pos, f);
      this.orbit.target.lerpVectors(from.target, to.target, f);
      if (f >= 1) this.tween = null;
    }
    if (this.walking) {
      const k = this.keys, s = this.walkSpeed * dt * (k.ShiftLeft ? 2.2 : 1);
      if (k.KeyW || k.ArrowUp) this.walk.moveForward(s);
      if (k.KeyS || k.ArrowDown) this.walk.moveForward(-s);
      if (k.KeyA || k.ArrowLeft) this.walk.moveRight(-s);
      if (k.KeyD || k.ArrowRight) this.walk.moveRight(s);
      if (k.KeyE) this.camera.position.y += s; if (k.KeyQ) this.camera.position.y -= s;
      const p = this.camera.position;
      const inHall = p.x > 0 && p.x < 14 && p.z > 0 && p.z < 12;
      p.y = Math.max(inHall ? 1.0 : 0.6, Math.min(30, p.y));
    } else this.orbit.update();
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }
  stats() { const i = this.renderer.info; return { calls: i.render.calls, tris: i.render.triangles, geos: i.memory.geometries, tex: i.memory.textures }; }
}
