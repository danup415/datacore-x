// Operator UI: KPI bar, hierarchy, layers, asset information panel, alarms,
// what-if workflow with before/after comparison, diagnostics & validation.
import { PRESETS } from '../scene/view.js';
import { fmt, healthColor, stateColor } from '../scene/util.js';
import { sparkline, lineChart } from './chart.js';

const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, html = '') => { const e = document.createElement(tag); Object.assign(e, attrs); if (html) e.innerHTML = html; return e; };
const hex = n => '#' + n.toString(16).padStart(6, '0');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const PRIO = { CRITICAL: '#ff3b30', HIGH: '#f0883e', MEDIUM: '#d29922', LOW: '#58a6ff' };

const COMMANDS = {
  pump: [['pump_start', 'Start'], ['pump_stop', 'Stop'], ['pump_changeover', 'Changeover →'], ['reset_trip', 'Reset trip'], ['maintenance_complete', 'Maintenance complete']],
  crah: [['crah_enable', 'Enable'], ['crah_disable', 'Disable'], ['reset_trip', 'Reset trip'], ['maintenance_complete', 'Maintenance complete']],
  chiller: [['chiller_lead', 'Make lead'], ['reset_trip', 'Reset trip'], ['maintenance_complete', 'Maintenance complete']],
  hx: [['maintenance_complete', 'Maintenance complete (CIP)']], tower: [['maintenance_complete', 'Maintenance complete']],
  battery: [['maintenance_complete', 'Replace / restore string']], rack: [['maintenance_complete', 'Clear rack issue']],
};

export class App {
  constructor({ registry, store, source, view, facility }) {
    Object.assign(this, { registry, store, source, view, facility });
    this.reg = new Map(registry.assets.map(a => [a.id, a]));
    this.selected = null;
    this.playback = null;
    this.cat = [];
    this.requests = [];
    this.results = new Map();
    this.fps = 0; this._fr = 0; this._ft = performance.now();
    this.checks = [];
  }

  current() {
    const s = this.store.snap;
    if (!this.playback) return s;
    const P = this.playback;
    const fr = P.frames[P.branch][P.i];
    return { ...s, seq: s?.seq, mode: 'SCENARIO', sim_time_s: fr.t, sim_clock: fr.clock, facility: fr.facility, assets: fr.assets,
      alarms: fr.alarms, faults_injected: fr.faults_injected,
      source: { ...(s?.source || {}), label: `What-if ${P.runId} · ${P.branch.toUpperCase()} branch · isolated instance (not live)` } };
  }

  init() {
    this.buildViews(); this.buildLayers(); this.buildTree(); this.buildTabs();
    this.renderAsset(null); this.renderWhatIf(); this.renderDiag();
    $('#role').onchange = e => { this.source.role = e.target.value; this.source.user = e.target.value + '1'; this.renderAsset(this.selected, true); this.renderWhatIf(); };
    this.source.role = $('#role').value; this.source.user = this.source.role + '1';
    $('#hm-h').oninput = e => { this.facility.heatmap.setHeight(+e.target.value); $('#hm-hv').textContent = +e.target.value < 0.1 ? 'floor' : (+e.target.value).toFixed(1) + ' m'; const s = this.current(); if (s) this.facility.updateSlow(s); };
    this.view.pickables = this.facility.pickables;
    this.view.onPick = id => this.select(id);
    this.view.onDouble = id => { if (id) { this.select(id); this.focus(id); } };
    const tip = $('#tooltip');
    this.view.onHover = (id, e) => {
      const s = this.current();
      if (!id || !s) { tip.style.display = 'none'; return; }
      const a = s.assets[id], d = this.reg.get(id);
      const r = this.view.renderer.domElement.getBoundingClientRect();
      tip.style.left = (e.clientX - r.left + 14) + 'px'; tip.style.top = (e.clientY - r.top + 10) + 'px';
      tip.style.display = 'block';
      let extra = '';
      if (d.type === 'rack' && a) extra = `<br>Inlet ${fmt(a.v.inlet_c, 1)} °C · Outlet ${fmt(a.v.outlet_c, 1)} °C<br>Power ${fmt(a.v.power_kw, 1)} kW · face velocity ≈ ${fmt((a.v.airflow_m3s ?? 0) / 1.2, 2)} m/s (derived)`;
      if (d.type === 'pipe' && a) extra = `<br>${fmt(a.v.flow_ls, 2)} L/s · ${fmt(a.v.temp_c, 1)} °C · ${fmt(a.v.velocity_ms, 2)} m/s`;
      tip.innerHTML = `<b>${esc(d.name)}</b> <span class="mut">${id}</span><br>${a ? `<span class="pill" style="background:${hex(stateColor(a.state))}">${a.state}</span>` : ''}${a?.health ? ` HI <b>${fmt(a.health.hi, 0)}</b> · ${esc(a.health.fault)}` : ''}${extra}`;
    };
    this.store.on((kind) => {
      if (kind === 'snapshot') this.onSnapshot();
      if (kind === 'link') this.renderLink();
      if (kind === 'log' && $('#tab-diag').classList.contains('on')) this.renderDiag();
    });
    const P = new URLSearchParams(location.search);
    if (P.get('embed') === '1') document.body.classList.add('embed');
    if (P.get('embed') === 'bare') document.body.classList.add('embed', 'bare');
    if (P.get('run')) this.openRun(P.get('run'), P.get('branch') || 'scenario');
    if (P.get('view') && PRESETS[P.get('view')]) this.view.goto(PRESETS[P.get('view')], 0);
    if (P.get('asset')) setTimeout(() => { this.select(P.get('asset')); this.focus(P.get('asset')); }, 300);
    addEventListener('message', ev => { if (ev.data?.type === 'dcx:select' && this.reg.has(ev.data.asset)) { this.select(ev.data.asset); this.focus(ev.data.asset); } });
    this.source.catalogue().then(c => { this.cat = c; this.renderWhatIf(); });
    if (this.source.kind === 'replay') this.renderReplayBar();
  }

  // ---------------------------------------------------------------------------
  buildViews() {
    const V = $('#views');
    const add = (txt, fn, id) => { const b = el('button', { textContent: txt, onclick: fn }); if (id) b.id = id; V.appendChild(b); return b; };
    add('Facility', () => this.preset('facility')); add('Data hall', () => this.preset('datahall'));
    add('Cold aisle', () => this.preset('coldaisle')); add('Chiller plant', () => this.preset('plant'));
    add('Electrical', () => this.preset('electrical')); add('Yard / roof', () => this.preset('yard'));
    add('Walkthrough', () => this.view.setWalk(true), 'btn-walk');
    add('Exit isolate', () => this.isolate(null), 'btn-uniso');
  }
  preset(p) { if (this.view.walking) this.view.setWalk(false); this.view.goto(PRESETS[p]); }

  buildLayers() {
    const L = $('#layers');
    const names = { building: 'Building', it: 'IT racks', cooling: 'Cooling plant', electrical: 'Electrical', piping: 'Chilled/condenser water', cables: 'Power flow (cables)', airflow: 'Airflow', heatmap: 'Thermal heatmap', zone: 'Aisle zones', indicators: 'Status / alarms', labels: 'Labels' };
    const defaults = { cables: false };
    for (const [k, v] of Object.entries(names)) {
      const on = defaults[k] ?? true;
      const lab = el('label', {}, `<input type="checkbox" ${on ? 'checked' : ''} data-l="${k}"> ${v}`);
      lab.querySelector('input').onchange = e => { this.facility.setLayer(k, e.target.checked); if (k === 'heatmap') $('#legend').style.opacity = e.target.checked ? 1 : 0.35; };
      L.appendChild(lab);
      this.facility.setLayer(k, on);
    }
    const gt = el('label', {}, `<input type="checkbox" id="gt-toggle"> <span class="mut">Injected faults (ground truth)</span>`);
    gt.querySelector('input').onchange = e => { this.facility.showInjected = e.target.checked; };
    L.appendChild(gt);
  }

  buildTree() {
    const kids = new Map();
    for (const a of this.registry.assets) { const p = a.parent ?? '__root'; if (!kids.has(p)) kids.set(p, []); kids.get(p).push(a); }
    this.treeRows = new Map();
    const mk = (a, depth) => {
      const li = el('li');
      const ch = kids.get(a.id) || [];
      const row = el('div', {}, `<span class="tw">${ch.length ? (depth < 2 ? '▾' : '▸') : ''}</span><span class="dot"></span>${esc(a.id)} <span class="mut small">${esc(a.type)}</span><span class="hi-chip"></span>`);
      row.onclick = e => { if (e.target.classList.contains('tw') && ch.length) { ul.style.display = ul.style.display === 'none' ? '' : 'none'; e.target.textContent = ul.style.display === 'none' ? '▸' : '▾'; return; } this.select(a.id); };
      row.ondblclick = () => { this.select(a.id); this.focus(a.id); };
      li.appendChild(row);
      const ul = el('ul');
      if (ch.length) { for (const c of ch) ul.appendChild(mk(c, depth + 1)); if (depth >= 2) ul.style.display = 'none'; li.appendChild(ul); }
      this.treeRows.set(a.id, row);
      return li;
    };
    const root = el('ul');
    for (const a of kids.get('__root') || []) root.appendChild(mk(a, 0));
    $('#tree').appendChild(root);
  }

  buildTabs() {
    for (const b of document.querySelectorAll('#tabs button')) b.onclick = () => this.tab(b.dataset.t);
  }
  tab(t) {
    for (const b of document.querySelectorAll('#tabs button')) b.classList.toggle('on', b.dataset.t === t);
    for (const x of document.querySelectorAll('.tab')) x.classList.toggle('on', x.id === 'tab-' + t);
    if (t === 'diag') this.renderDiag();
    if (t === 'alarms') this.renderAlarms();
    if (t === 'whatif') this.renderWhatIf();
  }

  // ---------------------------------------------------------------------------
  select(id) {
    this.selected = id;
    this.facility.select(id);
    for (const [k, r] of this.treeRows) r.classList.toggle('sel', k === id);
    if (id) { const r = this.treeRows.get(id); let p = r?.parentElement?.parentElement; while (p && p.tagName === 'UL') { p.style.display = ''; p = p.parentElement?.parentElement; } r?.scrollIntoView({ block: 'nearest' }); }
    this.renderAsset(id, true);
    this.tab('asset');
    if (window.parent !== window) window.parent.postMessage({ type: 'dcx:selected', asset: id }, '*');
  }
  focus(id) { if (this.view.walking) this.view.setWalk(false); this.view.focus(this.facility.assetCenter(id), this.facility.assetRadius(id)); }
  isolate(id) { this.facility.isolate(id); if (id) this.focus(id); $('#btn-uniso').classList.toggle('pri', !!id); }

  // ---------------------------------------------------------------------------
  onSnapshot() {
    const s = this.current();
    if (!s) return;
    this.renderTop(s);
    this.renderTreeStatus(s);
    this.updateAsset(s);
    if ($('#tab-alarms').classList.contains('on')) this.renderAlarms();
    if ($('#tab-diag').classList.contains('on')) this.renderDiag();
    this.renderAlarmCount();
    this.facility.updateSlow(s);
    $('#hm-n').textContent = `${this.facility.heatmap.nSensors} sensors`;
    if (this.source.kind === 'replay' && !this.playback) this.updateReplayBar();
  }

  renderTop(s) {
    const f = s.facility;
    const k = [['IT load', fmt(f.it_load_kw, 1), 'kW'], ['Facility', fmt(f.facility_power_kw, 1), 'kW'], ['PUE', fmt(f.pue, 3), ''],
      ['Cooling', fmt(f.cooling_power_kw, 1), 'kW'], ['CHWS/R', `${fmt(f.chws_c, 1)}/${fmt(f.chwr_c, 1)}`, '°C'],
      ['Max inlet', fmt(f.max_inlet_c, 1), '°C'], ['Wet-bulb', fmt(f.wetbulb_c, 1), '°C']];
    $('#kpis').innerHTML = k.map(([n, v, u], i) => `<div class="kpi"><b style="${i === 5 && f.max_inlet_c > 27 ? 'color:#ff7b72' : ''}${this.store.stale ? ';opacity:.45' : ''}">${v}</b><span>${n} ${u}</span></div>`).join('');
    const mode = this.playback ? 'scen' : (this.source.kind === 'replay' ? 'replay' : 'live');
    const b = $('#src-badge');
    b.className = 'badge ' + { live: 'b-live', replay: 'b-replay', scen: 'b-scen' }[mode];
    b.textContent = { live: 'LIVE · ' + (s.source?.type || ''), replay: 'RECORDED REPLAY', scen: 'WHAT-IF PLAYBACK' }[mode];
    $('#clock').innerHTML = `${esc((s.sim_clock || '').replace('T', ' '))} <span class="mut">t=${fmt(s.sim_time_s, 0)} s · seq ${s.seq ?? '—'}</span>`;
    $('#srcline').textContent = 'Data source: ' + (s.source?.label || '—');
    const ban = $('#banner');
    if (this.store.stale) { ban.className = 'stale'; ban.textContent = `⚠ COMMUNICATION ${this.store.link} — last update ${this.store.ageS.toFixed(0)} s ago · values shown are STALE`; }
    else if (this.playback) { ban.className = 'scen'; ban.textContent = `WHAT-IF PLAYBACK · ${this.playback.title} · ${this.playback.branch.toUpperCase()} · not live`; }
    else { ban.className = ''; }
  }
  renderLink() {
    const st = this.store.link;
    const c = { OK: '#3fb950', CONNECTING: '#d29922', STALE: '#d29922', LOST: '#f85149' }[st];
    $('#link').innerHTML = `<span class="dot" style="background:${c}"></span>${st} <span class="mut">${this.source.kind === 'live' ? (this.source.latencyMs != null ? this.source.latencyMs + ' ms' : '') : 'replay'}</span>`;
    const s = this.current(); if (s) this.renderTop(s);
  }
  renderTreeStatus(s) {
    for (const [id, row] of this.treeRows) {
      const a = s.assets[id];
      const dot = row.querySelector('.dot'), chip = row.querySelector('.hi-chip');
      if (a) { dot.style.background = this.store.stale ? '#6e7681' : hex(stateColor(a.state)); }
      else dot.style.background = 'transparent';
      if (a?.health) { chip.textContent = fmt(a.health.hi, 0); chip.style.background = hex(healthColor(a.health.hi)) + '33'; chip.style.color = hex(healthColor(a.health.hi)); }
    }
  }
  renderAlarmCount() {
    const s = this.current(); const n = (s.alarms || []).filter(a => a.state !== 'ACTIVE_ACK').length;
    const c = $('#al-cnt'); c.style.display = n ? '' : 'none'; c.textContent = n;
  }

  // ---------------------------------------------------------------------------
  renderAsset(id, rebuild = false) {
    const T = $('#tab-asset');
    if (!id) {
      T.innerHTML = `<div class="sec"><h4>No asset selected</h4><p class="mut">Click equipment in the 3D view or the hierarchy. Every value shown is taken from the current snapshot of the twin (or the selected what-if branch).</p>
        <div class="card small"><b>Facility summary</b><div id="fac-sum"></div></div></div>`;
      this._assetBuilt = null; this.updateAsset(this.current()); return;
    }
    if (!rebuild && this._assetBuilt === id) return;
    const d = this.reg.get(id);
    const crumbs = []; let p = d; while (p) { crumbs.unshift(p.id); p = this.reg.get(p.parent); }
    const pb = this.playback;
    const cmds = (COMMANDS[d.type] || []);
    T.innerHTML = `
      <div class="sec">
        <div class="small mut">${crumbs.map(c => `<a href="#" data-sel="${c}" style="color:#8b949e">${c}</a>`).join(' › ')}</div>
        <div class="row" style="justify-content:space-between;margin-top:4px"><div><div style="font-size:15px;font-weight:600">${esc(d.name)}</div><div class="mut mono small">${d.id} · ${d.type} · layer ${d.layer}</div></div><span id="a-state" class="pill">—</span></div>
        <div class="row" style="margin-top:8px"><button id="a-focus">Focus</button><button id="a-iso">Isolate &amp; inspect</button><button id="a-trend">Trend…</button></div>
        <div id="a-health"></div><div id="a-diag"></div>
      </div>
      <div class="sec"><h4>${pb ? 'Values — baseline vs scenario (this frame)' : 'Live data'}</h4><table id="a-tbl"><thead><tr>${pb ? '<th>Point</th><th class="num">Baseline</th><th class="num">Scenario</th><th class="num">Δ</th>' : '<th>Point</th><th class="num">Value</th><th>Unit</th><th>Trend</th>'}</tr></thead><tbody></tbody></table>
        <div id="a-chart" style="display:none"><canvas class="chartbox" id="a-cv"></canvas></div></div>
      ${cmds.length ? `<div class="sec"><h4>Supervisory commands</h4><div class="row" id="a-cmds"></div><div id="a-acks" class="small" style="margin-top:6px"></div><div class="small mut" style="margin-top:4px">Commands pass role checks, PLC interlocks and are confirmed only by process feedback.</div></div>` : ''}
      <details class="sec"><summary>Data-point mapping (registry → Ignition / OPC UA)</summary><table class="small mono">${d.tags.map(t => `<tr><td>${t.key}</td><td>${esc(t.path)}</td><td>${esc(t.opc_node)}</td></tr>`).join('')}</table></details>`;
    T.querySelectorAll('[data-sel]').forEach(a => a.onclick = e => { e.preventDefault(); this.select(a.dataset.sel); });
    $('#a-focus').onclick = () => this.focus(id);
    $('#a-iso').onclick = () => this.isolate(this.facility.isolated === id ? null : id);
    $('#a-trend').onclick = () => { const c = $('#a-chart'); c.style.display = c.style.display === 'none' ? '' : 'none'; this._trendKey = this._trendKey || d.tags[0]?.key; this.drawAssetTrend(); };
    const tb = T.querySelector('#a-tbl tbody');
    this._cells = new Map();
    for (const t of d.tags) {
      const tr = el('tr');
      tr.innerHTML = pb ? `<td>${esc(t.label)}</td><td class="num"></td><td class="num"></td><td class="num"></td>` : `<td>${esc(t.label)}</td><td class="num"></td><td class="mut">${esc(t.unit)}</td><td><canvas class="spk"></canvas></td>`;
      tr.style.cursor = 'pointer';
      tr.onclick = () => { this._trendKey = t.key; $('#a-chart').style.display = ''; this.drawAssetTrend(); };
      tb.appendChild(tr);
      this._cells.set(t.key, tr);
    }
    if (d.type === 'rack') {
      const tr = el('tr', {}, pb ? `<td>Face velocity (derived)</td><td class="num"></td><td class="num"></td><td></td>` : `<td>Face velocity <span class="mut">(derived = airflow / 1.2 m²)</span></td><td class="num"></td><td class="mut">m/s</td><td></td>`);
      tb.appendChild(tr); this._cells.set('_vel', tr);
    }
    if (cmds.length) {
      const C = $('#a-cmds');
      for (const [c, label] of cmds) {
        const b = el('button', { textContent: label });
        b.disabled = this.source.kind !== 'live' || !!pb || this.source.role === 'viewer';
        b.onclick = async () => {
          const body = { command: c, asset: id };
          if (c === 'pump_changeover') { const t = prompt('Changeover to which pump? (P-01 / P-02 / P-03)', id === 'P-03' ? 'P-01' : 'P-03'); if (!t) return; body.value = t; }
          if (c === 'maintenance_complete' && !confirm(`Record maintenance complete for ${id}? This clears its fault condition in the twin.`)) return;
          try { const r = await this.source.command(body); this.store.note(`Command ${r.id} ${r.command} → ${r.status}: ${r.reason}`); } catch (e) { alert(e.message); }
        };
        C.appendChild(b);
      }
      if (this.source.kind !== 'live') $('#a-acks').innerHTML = '<span class="mut">Commands are disabled in recorded replay / what-if playback.</span>';
    }
    this._assetBuilt = id;
    this.updateAsset(this.current());
  }

  updateAsset(s) {
    if (!s) return;
    const id = this.selected;
    if (!id) {
      const f = s.facility, box = $('#fac-sum');
      if (box) box.innerHTML = `<table class="small">${Object.entries(f).map(([k, v]) => `<tr><td>${k}</td><td class="num">${fmt(v, 2)}</td></tr>`).join('')}</table>`;
      return;
    }
    if (this._assetBuilt !== id) return;
    const a = s.assets[id], d = this.reg.get(id);
    const st = $('#a-state');
    if (a) { st.textContent = this.store.stale ? a.state + ' (STALE)' : a.state; st.style.background = hex(this.store.stale ? 0x6e7681 : stateColor(a.state)); }
    else { st.textContent = d.tags.length ? 'NO DATA' : 'STRUCTURE'; st.style.background = '#6e7681'; }
    const pb = this.playback;
    const base = pb ? pb.frames.baseline[pb.i]?.assets?.[id] : null, scen = pb ? pb.frames.scenario[pb.i]?.assets?.[id] : null;
    for (const t of d.tags) {
      const tr = this._cells?.get(t.key); if (!tr) continue;
      const td = tr.children;
      if (pb) {
        const vb = base?.v?.[t.key], vs = scen?.v?.[t.key];
        td[1].textContent = fmt(vb, t.decimals); td[2].textContent = fmt(vs, t.decimals);
        const dd = (vb != null && vs != null) ? vs - vb : null;
        td[3].textContent = dd == null ? '—' : (dd > 0 ? '+' : '') + dd.toFixed(t.decimals);
        td[3].style.color = dd == null || Math.abs(dd) < 10 ** -t.decimals ? '' : '#ffa657';
      } else {
        const v = a?.v?.[t.key], q = a?.q?.[t.key];
        td[1].textContent = q && q !== 'GOOD' ? `${q}` : fmt(v, t.decimals);
        td[1].className = 'num' + (q === 'BAD' ? ' q-bad' : '');
        td[1].style.opacity = this.store.stale ? 0.45 : 1;
        sparkline(td[3].firstChild, this.store.trend.get(`${id}|${t.key}`), { stale: this.store.stale });
      }
    }
    const vel = this._cells?.get('_vel');
    if (vel) {
      if (pb) { vel.children[1].textContent = fmt((base?.v?.airflow_m3s ?? 0) / 1.2, 2); vel.children[2].textContent = fmt((scen?.v?.airflow_m3s ?? 0) / 1.2, 2); }
      else vel.children[1].textContent = fmt((a?.v?.airflow_m3s ?? 0) / 1.2, 2);
    }
    const H = $('#a-health');
    const h = (pb ? scen : a)?.health;
    if (H) {
      if (h) {
        const col = hex(healthColor(h.hi));
        const rul = h.rul_h == null ? '<span class="mut">no degradation trend</span>' : `${fmt(h.rul_h, 2)} h <span class="mut">[${fmt(h.rul_lo_h, 2)} – ${fmt(h.rul_hi_h, 2)}]</span>`;
        const hb = pb ? base?.health : null;
        H.innerHTML = `<div class="hcard"><div class="hring" style="border:5px solid ${col};color:${col}">${fmt(h.hi, 0)}</div>
          <div><div><b>Equipment Health Index</b>${hb ? ` <span class="mut small">baseline ${fmt(hb.hi, 0)}</span>` : ''}</div>
          <div>Fault: <b style="color:${h.fault_code ? col : '#7ee787'}">${esc(h.fault)}</b> <span class="mut">p=${fmt(h.prob, 2)}</span></div>
          <div>RUL: ${rul} <span class="mut">conf ${fmt(h.confidence, 2)}</span></div>
          <div class="small" style="margin-top:3px">${esc(h.recommendation || '')}</div>
          ${h.note ? `<div class="small mut">${esc(h.note)}</div>` : ''}
          <div class="small mut" style="margin-top:3px">${esc(h.basis || '')}</div></div></div>`;
      } else H.innerHTML = '';
    }
    const D = $('#a-diag');
    const dg = (pb ? scen : a)?.diag;
    if (D) D.innerHTML = dg ? `<div class="card small"><b>Twin synchronisation</b> — measured inlet vs twin estimate<br>
      Estimate ${fmt(dg.twin_inlet_est_c, 2)} °C · residual <b style="color:${(dg.residual_k ?? 0) > 2 ? '#ffa657' : '#7ee787'}">${fmt(dg.residual_k, 2)} K</b> · ΔT ${fmt(dg.delta_t_k, 1)} K<br>
      Finding: <b>${esc(dg.finding)}</b> · model confidence ${fmt(dg.model_confidence, 2)}</div>` : '';
    const acks = $('#a-acks');
    if (acks && this.source.kind === 'live') {
      const list = (this.store.snap?.commands || []).filter(c => c.asset === id || (c.command === 'pump_changeover' && c.value === id)).slice(0, 5);
      acks.innerHTML = list.map(c => `<div class="mono"><span style="color:${{ EXECUTED: '#7ee787', ACCEPTED: '#d29922', REJECTED: '#ff7b72', TIMEOUT: '#ff7b72', RECEIVED: '#8b949e' }[c.status] || '#8b949e'}">${c.status}</span> ${c.command} <span class="mut">${esc(c.reason || '')}</span></div>`).join('') || '<span class="mut">No commands issued for this asset.</span>';
    }
    if ($('#a-chart') && $('#a-chart').style.display !== 'none') this.drawAssetTrend();
  }

  drawAssetTrend() {
    const id = this.selected, k = this._trendKey;
    if (!id || !k) return;
    const t = this.store.tagDef(id, k);
    const cv = $('#a-cv');
    if (this.playback) {
      const P = this.playback;
      const ser = b => P.frames[b].map(f => [f.t - P.frames.baseline[0].t, f.assets[id]?.v?.[k]]);
      lineChart(cv, [{ name: 'baseline', color: '#8b949e', pts: ser('baseline'), dash: [4, 3] }, { name: 'scenario', color: '#ffa657', pts: ser('scenario') }],
        { title: t?.label || k, unit: t?.unit, playhead: P.frames.baseline[P.i].t - P.frames.baseline[0].t });
    } else {
      const pts = this.store.trend.get(`${id}|${k}`) || [];
      const t0 = pts.length ? pts[0][0] : 0;
      lineChart(cv, [{ name: 'measured', color: '#58a6ff', pts: pts.map(([a, b]) => [a - t0, b]) }], { title: (t?.label || k) + ' — client buffer', unit: t?.unit });
    }
  }

  // ---------------------------------------------------------------------------
  renderAlarms() {
    const s = this.current(); const T = $('#tab-alarms');
    const al = s?.alarms || [];
    T.innerHTML = `<div class="sec"><h4>Active alarms (${al.length})</h4>${al.length ? '' : '<p class="mut">No active alarms.</p>'}<div id="al-list"></div>
      <p class="small mut">States follow ISA-18.2: ACTIVE_UNACK (blinking), ACTIVE_ACK, CLEARED_UNACK. Alarms are evaluated on measured values and intelligence outputs.</p></div>`;
    const L = $('#al-list');
    for (const a of al) {
      const d = el('div', { className: 'al' + (a.state !== 'ACTIVE_ACK' ? ' unack' : '') });
      d.style.borderColor = PRIO[a.priority];
      d.innerHTML = `<div class="row" style="justify-content:space-between"><b style="color:${PRIO[a.priority]}">${a.priority}</b><span class="mono small mut">t=${fmt(a.t_active, 0)} s · ${a.state}</span></div><div>${esc(a.text)}</div>`;
      d.onclick = () => { this.select(a.asset === 'DCX' ? null : a.asset); if (a.asset !== 'DCX') this.focus(a.asset); };
      if (a.state !== 'ACTIVE_ACK' && !this.playback) {
        const b = el('button', { textContent: 'Acknowledge' }); b.style.marginTop = '4px';
        b.disabled = this.source.role === 'viewer';
        b.onclick = async e => { e.stopPropagation(); try { await this.source.ackAlarm(a.id); this.store.note(`Alarm ${a.id} acknowledged`); } catch (er) { alert(er.message); } };
        d.appendChild(b);
      }
      L.appendChild(d);
    }
  }

  // ---------------------------------------------------------------------------
  renderWhatIf() {
    const T = $('#tab-whatif');
    if (!this.cat.length) { T.innerHTML = '<div class="sec mut">Loading scenario catalogue…</div>'; return; }
    const sel = this._wSel || this.cat[0].id;
    const sc = this.cat.find(c => c.id === sel);
    const replay = this.source.kind === 'replay';
    T.innerHTML = `<div class="sec"><h4>Scenario</h4>
      <select id="w-sel" style="width:100%">${this.cat.map(c => `<option value="${c.id}" ${c.id === sel ? 'selected' : ''}>${c.id} · ${esc(c.title)}</option>`).join('')}</select>
      <p class="small mut">${esc(sc.description)}</p>
      <table class="small" id="w-params">${Object.entries(sc.params).map(([k, p]) => `<tr><td>${k}</td><td>${p.type === 'enum' ? `<select data-k="${k}" ${replay ? 'disabled' : ''}>${p.options.map(o => `<option ${o === p.default ? 'selected' : ''}>${o}</option>`).join('')}</select>`
        : p.type === 'bool' ? `<input type="checkbox" data-k="${k}" ${p.default ? 'checked' : ''} ${replay ? 'disabled' : ''}>` : `<input type="number" data-k="${k}" value="${p.default}" min="${p.min}" max="${p.max}" step="any" style="width:80px" ${replay ? 'disabled' : ''}> <span class="mut">${p.unit} [${p.min}–${p.max}]</span>`}</td></tr>`).join('')}
      <tr><td>horizon_s</td><td><input type="number" id="w-h" value="1800" min="60" max="7200" style="width:80px" ${replay ? 'disabled' : ''}> <span class="mut">s</span></td></tr></table>
      ${replay ? '<p class="small mut">Replay mode: results are the recorded output of the isolated what-if executor with default parameters.</p>' : ''}
      <div class="row" style="margin-top:6px"><button class="pri" id="w-req" ${this.source.role === 'viewer' ? 'disabled' : ''}>Request scenario</button><span class="small mut">Requires operator approval before execution · runs in an isolated instance</span></div></div>
      <div class="sec"><h4>Requests &amp; runs</h4><div id="w-reqs"></div></div><div class="sec" id="w-res"></div>`;
    $('#w-sel').onchange = e => { this._wSel = e.target.value; this.renderWhatIf(); };
    $('#w-req').onclick = async () => {
      const params = {};
      for (const i of T.querySelectorAll('#w-params [data-k]')) params[i.dataset.k] = i.type === 'checkbox' ? i.checked : (i.tagName === 'SELECT' ? i.value : +i.value);
      try { const r = await this.source.requestScenario(sel, params, +$('#w-h').value); this.requests.unshift(r); this.store.note(`Scenario ${sel} requested (${r.request_id}) — pending approval`); this.renderRequests(); }
      catch (e) { alert(e.message); }
    };
    this.renderRequests();
    if (this._shownRun) this.renderResult(this._shownRun);
  }
  renderRequests() {
    const L = $('#w-reqs'); if (!L) return;
    L.innerHTML = this.requests.length ? '' : '<p class="mut small">No requests yet.</p>';
    for (const r of this.requests) {
      const d = el('div', { className: 'card small' });
      d.innerHTML = `<div class="row" style="justify-content:space-between"><b>${r.scenario_id} · ${esc(r.title)}</b><span class="mono">${r.status}</span></div>
        <div class="mono mut">${r.request_id}${r.run_id ? ' → ' + r.run_id : ''} · by ${esc(r.requested_by)}${r.approved_by ? ' · approved by ' + esc(r.approved_by) : ''}</div>
        <div class="mono mut">${esc(JSON.stringify(r.params))}</div><div class="row btns" style="margin-top:4px"></div><div class="prog"></div>`;
      const row = d.querySelector('.btns');
      if (r.status === 'PENDING_APPROVAL') {
        const ap = el('button', { className: 'pri', textContent: 'Approve & execute' });
        ap.disabled = this.source.role === 'viewer';
        ap.onclick = async () => {
          try { const x = await this.source.approve(r.request_id); r.status = 'APPROVED'; r.run_id = x.run_id; r.approved_by = this.source.user; this.renderRequests(); this.poll(r); }
          catch (e) { alert(e.message); }
        };
        const rj = el('button', { textContent: 'Reject' });
        rj.onclick = async () => { try { await this.source.reject(r.request_id); r.status = 'REJECTED'; this.renderRequests(); } catch (e) { alert(e.message); } };
        row.append(ap, rj);
      }
      if (r.run_id && this.results.has(r.run_id)) {
        const v = el('button', { textContent: 'Show results' }); v.onclick = () => this.renderResult(r.run_id); row.append(v);
      }
      L.appendChild(d);
    }
  }
  async poll(r) {
    const tick = async () => {
      try {
        const x = await this.source.run(r.run_id, false);
        r.status = x.status === 'COMPLETED' ? 'EXECUTED' : x.status;
        const card = [...document.querySelectorAll('#w-reqs .card')].find(c => c.textContent.includes(r.run_id));
        if (card) card.querySelector('.prog').innerHTML = `<div style="height:4px;background:#21262d;border-radius:2px;margin-top:4px"><div style="height:4px;width:${(x.progress || 0) * 100}%;background:#39d0ff;border-radius:2px"></div></div>`;
        if (x.status === 'COMPLETED') {
          const full = await this.source.run(r.run_id, true);
          this.results.set(r.run_id, { ...full.result, title: r.title, request: r });
          this.store.note(`What-if ${r.run_id} completed`);
          this.renderRequests(); this.renderResult(r.run_id); return;
        }
        if (x.status === 'FAILED') { this.store.note(`What-if ${r.run_id} failed: ${x.error}`); this.renderRequests(); return; }
      } catch (e) { this.store.note('poll error ' + e.message); }
      setTimeout(tick, 600);
    };
    tick();
  }
  renderResult(runId) {
    const R = this.results.get(runId); const box = $('#w-res'); if (!R || !box) return;
    this._shownRun = runId;
    const cmp = R.comparison.map(c => {
      const cls = c.worse === true ? 'worse' : c.worse === false ? 'better' : '';
      const f = v => typeof v === 'number' ? fmt(v, Math.abs(v) < 10 ? 2 : 1) : esc(v ?? '—');
      return `<tr><td>${esc(c.label)} <span class="mut">${esc(c.unit)}</span></td><td class="num">${f(c.baseline)}</td><td class="num">${f(c.scenario)}</td><td class="num ${cls}">${c.delta == null ? '' : (c.delta > 0 ? '+' : '') + f(c.delta)}</td></tr>`;
    }).join('');
    const sc = (R.state_changes_end || []).map(s => `<div class="mono small">${s.asset}: ${s.baseline} → <b>${s.scenario}</b></div>`).join('') || '<span class="mut small">No end-state changes.</span>';
    box.innerHTML = `<h4>Before / after — ${esc(R.title)} <span class="mono mut">${runId}</span></h4>
      <table class="small"><thead><tr><th>KPI (${(R.horizon_s / 60).toFixed(0)} min horizon)</th><th class="num">Baseline</th><th class="num">Scenario</th><th class="num">Δ</th></tr></thead><tbody>${cmp}</tbody></table>
      <h4 style="margin-top:8px">Operating-state changes at end of horizon</h4>${sc}
      <div class="row" style="margin-top:8px"><select id="w-metric"><option value="max_inlet_c">Max rack inlet</option><option value="facility_power_kw">Facility power</option><option value="pue">PUE</option><option value="cooling_power_kw">Cooling power</option><option value="chws_c">CHW supply</option><option value="it_load_kw">IT load</option><option value="worst_hi">Worst asset Health Index</option></select></div>
      <canvas class="chartbox" id="w-cv"></canvas>
      <div class="row" style="margin-top:6px"><button class="pri" id="w-3d">View scenario in 3D</button><button id="w-3db">View baseline in 3D</button>
      ${this.source.kind === 'live' ? `<button class="warn" id="w-apply" ${this.source.role !== 'engineer' ? 'disabled title="engineer role required"' : ''}>Apply to live twin</button>` : ''}</div>
      <p class="small mut">${esc(R.note || 'Computed by the backend isolated what-if executor from a deep copy of the live twin state at approval time.')}</p>`;
    const draw = () => {
      const m = $('#w-metric').value;
      const ser = br => R.frames[br].map(f => [f.t - R.frames.baseline[0].t, m === 'worst_hi' ? Math.min(...Object.values(f.assets).filter(a => a.health).map(a => a.health.hi)) : f.facility[m]]);
      lineChart($('#w-cv'), [{ name: 'baseline', color: '#8b949e', pts: ser('baseline'), dash: [4, 3] }, { name: 'scenario', color: '#ffa657', pts: ser('scenario') }],
        { title: $('#w-metric').selectedOptions[0].text, threshold: m === 'max_inlet_c' ? 27 : null, playhead: this.playback && this.playback.runId === runId ? R.frames.baseline[this.playback.i].t - R.frames.baseline[0].t : null });
    };
    $('#w-metric').onchange = draw; draw();
    this._drawRes = draw;
    $('#w-3d').onclick = () => this.enterPlayback(runId, 'scenario');
    $('#w-3db').onclick = () => this.enterPlayback(runId, 'baseline');
    const ap = $('#w-apply');
    if (ap) ap.onclick = async () => { if (!confirm('Apply this approved scenario to the LIVE twin? (Simulation only — injects the same faults into the running model.)')) return; try { await this.source.applyToLive(runId); this.store.note(`Scenario ${runId} applied to live twin`); } catch (e) { alert(e.message); } };
  }

  // Open a what-if run from the URL (?run=<id>&branch=scenario|baseline), e.g.
  // when the SCADA dashboard previews a scenario; waits for the run to finish.
  async openRun(runId, branch) {
    for (let k = 0; k < 600; k++) {
      try {
        const x = await this.source.run(runId, false);
        if (x.status === 'COMPLETED') {
          const full = await this.source.run(runId, true);
          this.results.set(runId, { ...full.result, title: x.title || runId });
          this.enterPlayback(runId, branch); return;
        }
        if (x.status === 'FAILED') { this.store.note(`What-if ${runId} failed`); return; }
      } catch (e) { this.store.note('openRun: ' + e.message); }
      await new Promise(r => setTimeout(r, 1000));
    }
  }
  enterPlayback(runId, branch) {
    const R = this.results.get(runId);
    this.playback = { runId, branch, frames: R.frames, i: 0, playing: true, title: R.title };
    if (this.view.walking) this.view.setWalk(false);
    const tl = $('#timeline'); tl.style.display = 'flex';
    const n = R.frames.baseline.length;
    tl.innerHTML = `<b class="small" style="color:#ffa657">WHAT-IF</b><button id="tl-play">❚❚</button><select id="tl-br"><option value="scenario">Scenario</option><option value="baseline">Baseline</option></select>
      <input type="range" id="tl-r" min="0" max="${n - 1}" value="0"><span class="mono small" id="tl-t"></span><button id="tl-exit">Return to live</button>`;
    $('#tl-br').value = branch;
    $('#tl-br').onchange = e => { this.playback.branch = e.target.value; this.renderAsset(this.selected, true); this.onSnapshot(); };
    $('#tl-r').oninput = e => { this.playback.i = +e.target.value; this.onSnapshot(); };
    $('#tl-play').onclick = () => { this.playback.playing = !this.playback.playing; $('#tl-play').textContent = this.playback.playing ? '❚❚' : '▶'; };
    $('#tl-exit').onclick = () => this.exitPlayback();
    this.renderAsset(this.selected, true);
    clearInterval(this._pbTimer);
    this._pbTimer = setInterval(() => {
      const P = this.playback; if (!P) return;
      if (P.playing) { P.i = (P.i + 1) % n; $('#tl-r').value = P.i; this.onSnapshot(); }
      const f = P.frames.baseline[P.i]; $('#tl-t').textContent = `+${((f.t - P.frames.baseline[0].t) / 60).toFixed(1)} min`;
      if (this._drawRes && this._shownRun === runId) this._drawRes();
    }, 400);
    this.store.note(`Entered what-if playback ${runId} (${branch})`);
    this.onSnapshot();
  }
  exitPlayback() {
    clearInterval(this._pbTimer); this.playback = null; $('#timeline').style.display = 'none';
    if (this.source.kind === 'replay') this.renderReplayBar();
    this.renderAsset(this.selected, true); this.onSnapshot();
  }

  renderReplayBar() {
    const tl = $('#timeline'); tl.style.display = 'flex';
    tl.innerHTML = `<b class="small" style="color:#d2a8ff">REPLAY</b><button id="rp-play">❚❚</button><input type="range" id="rp-r" min="0" max="${this.source.live.n - 1}" value="0"><span class="mono small" id="rp-t"></span>
      <select id="rp-fps"><option value="0.5">0.5 f/s</option><option value="1" selected>1 f/s</option><option value="2">2 f/s</option><option value="5">5 f/s</option></select>`;
    $('#rp-play').onclick = () => { this.source.playing = !this.source.playing; $('#rp-play').textContent = this.source.playing ? '❚❚' : '▶'; };
    $('#rp-r').oninput = e => { this.source.seek(+e.target.value); };
    $('#rp-fps').onchange = e => this.source.setFps(+e.target.value);
  }
  updateReplayBar() {
    const r = $('#rp-r'); if (!r) return;
    r.value = Math.max(0, this.source.i - 1);
    const s = this.store.snap; $('#rp-t').textContent = `t=${fmt(s.sim_time_s, 0)} s · ${(this.source.fps * (this.source.doc.live.t[1] - this.source.doc.live.t[0])).toFixed(0)}× real time`;
  }

  // ---------------------------------------------------------------------------
  tickFps() {
    this._fr++; const now = performance.now();
    if (now - this._ft > 1000) { this.fps = this._fr * 1000 / (now - this._ft); this._fr = 0; this._ft = now; }
  }
  renderDiag() {
    const T = $('#tab-diag'); const s = this.store.snap;
    const st = this.view.stats();
    const comm = s?.comm || {};
    const inj = (this.current()?.faults_injected || []);
    if (!this._diagBuilt) {
      T.innerHTML = `<div class="sec"><h4>Communication health</h4><table class="small" id="d-comm"></table>
        <div class="row" style="margin-top:6px"><button id="d-loss">Simulate link loss (8 s)</button><button id="d-cons">Consistency check (seq)</button></div><div id="d-cons-out" class="small mono"></div></div>
        <div class="sec"><h4>Rendering performance</h4><table class="small" id="d-perf"></table></div>
        <div class="sec"><h4>Validation self-test (8A-G)</h4><div class="row"><button class="pri" id="d-run">Run checks</button></div><div id="d-checks" class="chk"></div></div>
        <div class="sec"><h4>Injected faults — simulation ground truth</h4><div id="d-inj" class="small mono"></div><p class="small mut">Shown for validation only. The 3D fault highlight uses the intelligence layer's detected faults, not this list.</p></div>
        <div class="sec"><h4>Event log</h4><div id="d-log" class="small mono"></div></div>`;
      $('#d-loss').onclick = async () => { const how = await this.source.simulateCommLoss(8); this.store.note(`Link-loss test started (${how})`); };
      $('#d-cons').onclick = () => this.consistencyCheck();
      $('#d-run').onclick = () => this.runChecks();
      this._diagBuilt = true;
    }
    const rows = [['Link', this.store.link], ['Last update age', this.store.ageS.toFixed(1) + ' s'], ['Seq (latest)', s?.seq], ['Sequence gaps', this.store.seqGaps],
      ['Messages', this.store.msgCount], ['Reconnects', this.source.reconnects], ['Ping latency', this.source.latencyMs != null ? this.source.latencyMs + ' ms' : '—'],
      ['Source', s?.source?.type + ' · ' + (s?.source?.model || '') + ' ' + (s?.source?.model_version || '')], ['Registry', s?.source?.registry_version || this.registry.registry_version],
      ...Object.entries(comm).map(([k, v]) => ['Service: ' + k, v]), ['Sim speed', s?.runtime ? s.runtime.speed + '× · ' + s.runtime.publish_hz + ' Hz' : '—']];
    $('#d-comm').innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td class="num">${esc(v)}</td></tr>`).join('');
    $('#d-perf').innerHTML = [['FPS', this.fps.toFixed(0)], ['Draw calls', st.calls], ['Triangles', st.tris.toLocaleString()], ['Geometries', st.geos], ['Textures', st.tex], ['Pickable meshes', this.facility.pickables.length]]
      .map(([k, v]) => `<tr><td>${k}</td><td class="num">${v}</td></tr>`).join('');
    $('#d-inj').innerHTML = inj.length ? inj.map(f => `<div>${esc(f.fault_id)} · ${f.kind} @ ${f.asset} · sev ${fmt(f.severity_now, 2)} · ${f.stage}</div>`).join('') : '<span class="mut">none</span>';
    const ev = (s?.events || []).slice(-8).reverse().map(e => `<div>t=${e.t} ${esc(e.asset)} ${esc(e.kind)}: ${esc(e.text)}</div>`).join('');
    $('#d-log').innerHTML = this.store.log.slice(0, 12).map(l => `<div><span class="mut">${l.wall}</span> ${esc(l.text)}</div>`).join('') + (ev ? '<hr style="border-color:#222a33">' + ev : '');
  }
  async consistencyCheck() {
    const out = $('#d-cons-out');
    if (this.source.kind !== 'live') { out.textContent = 'Replay: single in-browser source — consistency check applies to live service.'; return; }
    try {
      const tags = await this.source.tags();
      const hist = await this.source.historian(tags.seq);
      let n = 0, bad = 0;
      for (const a of this.registry.assets) for (const t of a.tags) {
        n++;
        const tv = tags.tags[t.path]?.v, hv = hist.measured.assets[a.id]?.v?.[t.key];
        if (!(tv === hv || (tv == null && hv == null))) bad++;
      }
      const ws = this.store.snap;
      const hws = await this.source.historian(ws.seq);
      let wsBad = 0;
      for (const a of this.registry.assets) for (const t of a.tags) {
        const x = ws.assets[a.id]?.v?.[t.key], y = hws.measured.assets[a.id]?.v?.[t.key];
        if (!(x === y || (x == null && y == null))) wsBad++;
      }
      out.innerHTML = `seq ${tags.seq}: ${n} points · tag API vs historian mismatches: <b>${bad}</b> · 3D/WebSocket (seq ${ws.seq}) vs historian: <b>${wsBad}</b>`;
    } catch (e) { out.textContent = 'check failed: ' + e.message; }
  }

  async runChecks() {
    const out = [];
    const ok = (name, pass, info = '') => out.push({ name, pass, info });
    const s = this.store.snap;
    // 1 mapping
    let missing = [], unitless = 0;
    for (const a of this.registry.assets) {
      if (!a.tags.length) continue;
      if (!s.assets[a.id]) { missing.push(a.id); continue; }
      for (const t of a.tags) { if (!(t.key in s.assets[a.id].v)) missing.push(a.id + '.' + t.key); if (!t.unit) unitless++; }
    }
    const orphan = this.facility.pickables.filter(m => !this.reg.has(m.userData.assetId)).length;
    ok('G1 equipment-to-data mapping', !missing.length && !orphan, `${this.registry.assets.length} assets; missing ${missing.length}; orphan meshes ${orphan}; unit-less tags ${unitless}`);
    // 2 live update
    const seq0 = this.store.lastSeq, t0 = s.sim_time_s;
    await new Promise(r => setTimeout(r, Math.max(2500, this.store.expectedPeriodMs * 2.5)));
    ok('G2 live update of simulation values', this.store.lastSeq > seq0 && this.store.snap.sim_time_s !== t0, `seq ${seq0} → ${this.store.lastSeq}`);
    // 3 selection & drill-down
    const prev = this.selected; let selBad = 0;
    for (const a of this.registry.assets.filter(x => x.tags.length)) {
      this.select(a.id);
      const tr = this._cells.get(a.tags[0].key);
      const cur = this.current().assets[a.id]?.v?.[a.tags[0].key];
      if (!tr || (!this.playback && tr.children[1].textContent !== (this.current().assets[a.id]?.q?.[a.tags[0].key] && this.current().assets[a.id].q[a.tags[0].key] !== 'GOOD' ? this.current().assets[a.id].q[a.tags[0].key] : fmt(cur, a.tags[0].decimals)))) selBad++;
    }
    this.select(prev); this.tab('diag');
    ok('G3 equipment selection & drill-down', selBad === 0, `${selBad} panel/value mismatches`);
    // 4 fault highlighting
    const cs = this.current(); let hlBad = 0, nDet = 0;
    for (const [id, o] of this.facility.objs) {
      const a = cs.assets[id]; if (!a || !o.hl) continue;
      const exp = !!((a.health && a.health.fault_code && a.health.prob >= 0.5) || (a.diag && a.diag.finding !== 'Consistent with twin') || ['TRIPPED', 'NO_POWER', 'OUTPUT_OFF'].includes(a.state));
      if (exp) nDet++;
      if (exp !== o.hl.visible) hlBad++;
    }
    ok('G4 fault highlighting matches detected faults', hlBad === 0, `${nDet} highlighted; ${hlBad} mismatches`);
    // 5 heatmap
    ok('G5 thermal heatmap updates from sensors', this.facility.heatmap.nSensors >= 20 && this.facility.layers.heatmap.visible, `${this.facility.heatmap.nSensors} sensor points (layer ${this.facility.layers.heatmap.visible ? 'on' : 'off'})`);
    // 6 flow animation
    const off0 = this.facility.pipes.items.map(i => i.tex.offset.x);
    await new Promise(r => setTimeout(r, 600));
    const moved = this.facility.pipes.items.filter((i, k) => Math.abs(i.tex.offset.x - off0[k]) > 1e-4).length;
    ok('G6 airflow & fluid-flow animation driven by data', moved > 0 && this.facility.airflow.mesh.count > 0, `${moved}/${off0.length} pipe segments animating; ${this.facility.airflow.parts.length} air particles`);
    // 7 what-if sync
    if (this.playback) {
      const P = this.playback, fr = P.frames[P.branch][P.i];
      ok('G7 what-if scenario synchronisation', this.current().assets['R-01'].v.inlet_c === fr.assets['R-01'].v.inlet_c, `scene frame = ${P.branch}[${P.i}]`);
    } else ok('G7 what-if scenario synchronisation', null, 'open a what-if result in 3D, then re-run');
    // 8 command ack
    const cmds = s.commands || [];
    ok('G8 command acknowledgement', this.source.kind !== 'live' ? null : cmds.some(c => ['EXECUTED', 'REJECTED'].includes(c.status)), this.source.kind !== 'live' ? 'replay: commands disabled' : `${cmds.length} recent commands; ${cmds.filter(c => c.status === 'EXECUTED').length} confirmed by feedback`);
    // 9 comm loss
    const lossNote = this.store.log.find(l => l.text.startsWith('Link recovered'));
    ok('G9 communication loss & recovery', lossNote ? true : null, lossNote ? lossNote.text : 'press “Simulate link loss”, wait for recovery, re-run');
    // 10 performance
    ok('G10 performance with complete facility scene', this.fps >= 30, `${this.fps.toFixed(0)} FPS · ${this.view.stats().calls} draw calls · ${this.view.stats().tris.toLocaleString()} triangles`);
    this.checks = out;
    window.__dcxChecks = out;
    $('#d-checks').innerHTML = out.map(c => `<div><span class="${c.pass ? 'p' : c.pass === false ? 'f' : 'mut'}">${c.pass ? 'PASS' : c.pass === false ? 'FAIL' : 'N/A '}</span> ${esc(c.name)} <span class="mut">— ${esc(c.info)}</span></div>`).join('');
    return out;
  }
}
