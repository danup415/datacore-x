// DATACORE-X 3D digital twin — entry point.
// Data source selection: embedded recorded replay (standalone build) or the
// live integration service (WebSocket + REST) when served by the backend.
import { Store } from './data/store.js';
import { LiveSource } from './data/live.js';
import { ReplaySource } from './data/replay.js';
import { View } from './scene/view.js';
import { Facility } from './scene/facility.js';
import { App } from './ui/app.js';

async function boot() {
  const replayDoc = window.DCX_REPLAY || null;
  const registry = replayDoc ? replayDoc.registry : await LiveSource.loadRegistry('');
  const store = new Store(registry);
  const source = replayDoc ? new ReplaySource(store, replayDoc) : new LiveSource(store, '');
  store.sourceKind = source.kind;
  const view = new View(document.getElementById('viewport'));
  const facility = new Facility(registry, view.scene);
  const app = new App({ registry, store, source, view, facility });
  app.init();
  window.DCX = { app, store, source, view, facility };

  let last = performance.now();
  const loop = () => {
    const now = performance.now();
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    store.watchdog();
    const s = app.current();
    if (s) facility.update(s, store.stale ? 0 : dt, { stale: store.stale });
    facility.labelLOD(view.camera);
    view.update(dt);
    app.tickFps();
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  source.connect();
}

boot().catch(e => {
  document.body.innerHTML = `<pre style="color:#ff7b72;padding:20px">DATACORE-X failed to start: ${e.message}\n\nIf you opened index.html directly, start the backend (uvicorn datacorex.api:app) or use the standalone demo build.</pre>`;
  console.error(e);
});
