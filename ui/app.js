(() => {
'use strict';

/* ------------------------------------------------------------------ *
 *  ShiftLogic dashboard
 *  - Puzzle tab: notes + the reference answer from the visible key.
 *  - Live run tab: real output from POST /api/solve (nothing simulated).
 *  - Scorecard tab: reads results.json produced by scripts/make_results.py.
 * ------------------------------------------------------------------ */

const BLOCKS = ['07:00', '09:00', '11:00', '13:00', '15:00'];
const KINDS = ['unique', 'ambiguous', 'inconsistent'];
const KIND_NAME = { unique: 'Unique', ambiguous: 'Ambiguous', inconsistent: 'Inconsistent' };
const BUDGETS = [['1x', 'up to 1 call'], ['3x', 'up to 3'], ['10x', 'up to 10']];
// Reference points quoted in CANDIDATE_BRIEF.md (measured by the task authors, not by this repo).
const BRIEF_REF = { granite: 0.0, frontier: 0.675 };

const S = {
  items: [], active: null, filter: 'all', query: '',
  tab: 'item', core: 0, budget: '1x', busy: false,
  api: { state: 'unknown', configured: false }, live: {}, results: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const csv = s => (s || '').split(',').map(x => x.trim()).filter(Boolean);
const norm = s => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const pct = v => (v * 100).toFixed(1) + '%';
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

/* ---------------- parsing ---------------- */
function parse(it) {
  if (it._p) return it._p;
  const rows = it.text.split('\n');
  const head = rows[0] || '';
  const staff = csv((head.match(/rota:\s*([^.]*)\./) || [])[1]);
  const holders = csv((head.match(/on a station are ([^;.]*)/) || [])[1]);
  const lines = rows.slice(1).map(s => s.trim()).filter(Boolean);
  const bay = (head.match(/Bay\s+\w+/) || [''])[0];
  return (it._p = { head, staff, holders, lines, bay });
}

function coreSets(it) { return it.conflict_line_sets || []; }

function coreLineIdx(it, set) {
  // A cited statement may omit a leading hedge, so match by containment either way.
  const { lines } = parse(it);
  const hit = new Set();
  set.forEach(stmt => {
    const t = norm(stmt);
    lines.forEach((l, i) => { const n = norm(l); if (n === t || n.endsWith(t) || n.includes(t)) hit.add(i); });
  });
  return hit;
}

function assignments(it) {
  if (it.case === 'unique') return [it.assignment || (it.assignments || [])[0] || {}];
  return it.assignments || [];
}

/* ---------------- small renderers ---------------- */
const stPill = st => st ? `<span class="pill st-${esc(st)}">${esc(st)}</span>` : `<span class="pill none">no station</span>`;

function boardHtml(a) {
  const by = {};
  Object.entries(a).forEach(([n, v]) => { by[v.block] = [n, v.station]; });
  return `<ol class="board">${BLOCKS.map(b => {
    const [n, st] = by[b] || [];
    return `<li><time>${b}</time><span class="who">${n ? esc(n) : '—'}</span>${n ? stPill(st) : ''}</li>`;
  }).join('')}</ol>`;
}

function matrixHtml(list) {
  const cell = (a, b) => { const e = Object.entries(a).find(([, v]) => v.block === b); return e ? { n: e[0], st: e[1].station || '' } : { n: '', st: '' }; };
  const body = BLOCKS.map(b => {
    const cells = list.map(a => cell(a, b));
    const vary = new Set(cells.map(c => c.n + '|' + c.st)).size > 1;
    return `<tr class="${vary ? 'vary' : ''}"><th scope="row">${b}</th>${cells.map(c =>
      `<td><span class="who">${esc(c.n || '—')}</span>${c.n ? stPill(c.st) : ''}</td>`).join('')}</tr>`;
  }).join('');
  const head = list.map((_, i) => `<th scope="col">Schedule ${i + 1}</th>`).join('');
  return `<table class="matrix"><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function variesHtml(list) {
  if (list.length < 2) return '';
  const names = Object.keys(list[0]);
  const out = [];
  names.forEach(n => {
    const blocks = new Set(list.map(a => a[n]?.block));
    const sts = new Set(list.map(a => a[n]?.station || ''));
    const what = [blocks.size > 1 && 'block', sts.size > 1 && 'station'].filter(Boolean);
    if (what.length) out.push(`<b>${esc(n)}</b> (${what.join(' + ')})`);
  });
  const fixed = names.length - out.length;
  return `<div class="varies">Varies across schedules: ${out.join(', ') || 'nothing'}. ${fixed ? `${plural(fixed, 'person')} fixed in every schedule.` : ''}</div>`;
}

/* ---------------- rail ---------------- */
function counts() { const c = { all: S.items.length }; KINDS.forEach(k => c[k] = S.items.filter(i => i.case === k).length); return c; }

function renderFilters() {
  const c = counts();
  $('#filters').innerHTML = ['all', ...KINDS].map(k =>
    `<button data-f="${k}" aria-pressed="${S.filter === k}">${k === 'all' ? 'All' : KIND_NAME[k]}<small>${c[k]}</small></button>`).join('');
}

function visible() {
  const q = S.query.trim().toLowerCase();
  return S.items.filter(i => (S.filter === 'all' || i.case === S.filter) && (!q || i.id.toLowerCase().includes(q) || i.text.toLowerCase().includes(q)));
}

function hintFor(i) {
  if (i.case === 'unique') return '1 schedule';
  if (i.case === 'ambiguous') return plural((i.assignments || []).length, 'schedule');
  return plural(coreSets(i).length, 'core set');
}

function renderRail() {
  const list = visible();
  const host = $('#item-list');
  if (!list.length) { host.innerHTML = '<div class="empty">No puzzles match.</div>'; return; }
  const groups = S.filter === 'all' ? KINDS : [S.filter];
  host.innerHTML = groups.map(k => {
    const rows = list.filter(i => i.case === k);
    if (!rows.length) return '';
    return `<div class="group-label">${KIND_NAME[k]}</div>` + rows.map(i =>
      `<button class="item" data-id="${esc(i.id)}" aria-current="${S.active && S.active.id === i.id}">
        <span class="dot ${i.case}"></span><span class="id">${esc(i.id)}</span>
        <span class="hint">${esc(hintFor(i))}</span>${S.live[i.id] ? '<span class="ran" title="Has a live run"></span>' : ''}
      </button>`).join('');
  }).join('');
  const cur = $('.item[aria-current="true"]', host);
  if (cur) cur.scrollIntoView({ block: 'nearest' });
}

/* ---------------- header ---------------- */
function renderHeader() {
  const it = S.active; if (!it) return;
  const p = parse(it);
  $('#item-id').textContent = it.id;
  const kb = $('#item-kind'); kb.className = `badge ${it.case}`; kb.textContent = KIND_NAME[it.case];
  $('#item-meta').innerHTML = [p.bay, plural(p.staff.length, 'person') + ' on the rota', plural(p.holders.length, 'station holder'), `${BLOCKS.length} blocks`]
    .filter(Boolean).map(t => `<span>${esc(t)}</span>`).join('<span>·</span>');
}

function renderBudget() {
  $('#budget').innerHTML = BUDGETS.map(([b, s]) =>
    `<button data-b="${b}" aria-pressed="${S.budget === b}" title="${esc(s)}">${b}</button>`).join('');
}

function renderApiState() {
  const el = $('#api-state');
  const m = { on: ['on', 'Model endpoint ready'], nokey: ['warn', 'Server running, no API key in .env'], off: ['warn', 'Static mode — start server.py to run live'], unknown: ['', 'Checking server…'] };
  const [cls, txt] = m[S.api.state] || m.unknown;
  el.className = 'api-state ' + cls;
  el.innerHTML = `<span class="dot"></span>${esc(txt)}`;
  const usable = S.api.state === 'on';
  $('#run-btn').disabled = !usable || S.busy;
  $('#custom-btn').disabled = !usable || S.busy;
  $('#run-btn').title = usable ? '' : txt;
}

/* ---------------- Puzzle tab ---------------- */
function renderItem() {
  const it = S.active; if (!it) return;
  const p = parse(it);
  const sets = coreSets(it);
  const coreIdx = it.case === 'inconsistent' ? Math.min(S.core, sets.length - 1) : -1;
  const hit = coreIdx >= 0 ? coreLineIdx(it, sets[coreIdx]) : new Set();

  const rota = p.staff.map(n => `<span class="chip ${p.holders.includes(n) ? 'holder' : ''}">${esc(n)}</span>`).join('');
  const lines = p.lines.map((l, i) =>
    `<li data-i="${i}" class="${hit.has(i) ? 'core' : ''}"><span class="n">${i + 1}</span><span>${esc(l)}</span></li>`).join('');

  let answer = '';
  if (it.case === 'unique') {
    answer = `<div class="card-h"><h3>Reference answer</h3><span class="sub">exactly one schedule fits</span></div>
      <div class="card-b">${boardHtml(assignments(it)[0])}</div>`;
  } else if (it.case === 'ambiguous') {
    const list = assignments(it);
    answer = `<div class="card-h"><h3>Reference answer</h3><span class="sub">${plural(list.length, 'schedule')} fit — all must be returned</span></div>
      <div class="card-b">${matrixHtml(list)}${variesHtml(list)}</div>`;
  } else {
    answer = `<div class="card-h"><h3>Reference answer</h3><span class="sub">notes contradict themselves</span></div>
      <div class="card-b">
        ${sets.length > 1 ? `<div class="cores" id="cores">${sets.map((s, i) => `<button data-c="${i}" aria-pressed="${i === coreIdx}">Core ${String.fromCharCode(65 + i)} · ${s.length}</button>`).join('')}</div>` : ''}
        <ul class="stmts">${sets[coreIdx].map(stmt => {
          const first = [...coreLineIdx(it, [stmt])][0];
          return `<li><button class="stmt" data-line="${first ?? ''}"><span class="ln">${first !== undefined ? 'L' + (first + 1) : ''}</span><span>${esc(stmt)}</span></button></li>`;
        }).join('')}</ul>
        <p class="note">These ${sets[coreIdx].length} statements cannot all hold together, and dropping any one of them leaves a schedule that works. ${sets.length > 1 ? 'Other minimal sets also exist; any one is a correct citation.' : ''}</p>
      </div>`;
  }

  $('#panel-item').innerHTML = `<div class="split">
    <section class="card"><div class="card-h"><h3>Shift notes</h3><span class="sub">${plural(p.lines.length, 'line')}</span></div>
      <div class="card-b">
        <div class="rota">${rota}</div>
        ${it.case === 'inconsistent' ? '<div class="legend"><span><i></i>in the selected conflict set</span></div>' : ''}
        <ol class="lines" id="lines">${lines}</ol>
      </div></section>
    <section class="card">${answer}</section>
  </div>`;
}

/* ---------------- Live tab ---------------- */
const STAGES = [
  ['Stage 1', 'Pre-filter', 'Reads the header, then drops lines that mention nobody and nothing on the rota.', false],
  ['Stage 2', 'Granite decompiler', 'The model turns each remaining line into a typed constraint, one call at 1×.', true],
  ['Stage 3', '720-world solver', 'Checks every block and station permutation. Counts survivors, or finds a minimal conflict.', false],
  ['Stage 4', 'Repair (3× / 10×)', 'If more than 4 worlds survive, re-asks the model about lines it skipped.', true],
];

function parseConstraint(str) {
  const m = /^(\w+)\((.*?)\)\s*←\s*'([\s\S]*)'$/.exec(str);
  if (!m) return { kind: '', args: str, src: '' };
  let args = m[2];
  if (/^BLOCK_/.test(m[1])) args = args.replace(/,\s*(\d)$/, (_, d) => ', ' + (BLOCKS[+d] || d)); // server stores block indices
  return { kind: m[1], args, src: m[3] };
}

function sieveHtml(steps) {
  const top = Math.log10(720);
  return `<div class="sieve">${steps.map(s => {
    const w = s.worlds_after;
    const width = w <= 0 ? 100 : Math.max(3, (Math.log10(w) / top) * 100);
    return `<div class="sv ${w === 0 ? 'zero' : w === 1 ? 'one' : ''}" title="${esc(s.source_line)}">
      <span class="i">${s.step}</span><span class="p">${esc(s.constraint)}</span>
      <span class="bar-t"><span style="width:${width}%"></span></span><span class="c">${w}</span></div>`;
  }).join('')}</div><p class="sub" style="margin-top:6px">Bars are log-scaled, 720 worlds at full width. Red means the last constraint left none.</p>`;
}

function stepHtml(st) {
  const d = st.details || {};
  const deterministic = /pre-filter|solver|verdict/i.test(st.title) && !/repair|consensus/i.test(st.title);
  let body = '';
  if (d.constraints_extracted) {
    body += `<div class="small-h">${plural(d.constraints_extracted.length, 'constraint')} extracted</div><ul class="cons">${d.constraints_extracted.map(parseConstraint).map(c =>
      `<li class="con"><span class="kind">${esc(c.kind || '—')}</span><span><span class="args">${esc(c.args)}</span>${c.src ? `<span class="src">${esc(c.src)}</span>` : ''}</span></li>`).join('')}</ul>`;
  }
  if (d.sample_noise && d.sample_noise.length) body += `<div class="small-h">Examples dropped as chatter</div>${d.sample_noise.map(n => `<div class="quote">${esc(n)}</div>`).join('')}`;
  if (d.newly_recovered && d.newly_recovered.length) body += `<div class="small-h">Recovered by repair</div><ul class="cons">${d.newly_recovered.map(r => `<li class="con"><span class="kind">+</span><span class="args">${esc(r)}</span></li>`).join('')}</ul>`;
  if (d.added_consensus && d.added_consensus.length) body += `<div class="small-h">Added from second sample</div><ul class="cons">${d.added_consensus.map(r => `<li class="con"><span class="kind">+</span><span class="args">${esc(r)}</span></li>`).join('')}</ul>`;
  if (d.elimination_steps && d.elimination_steps.length) body += `<div class="small-h">Worlds remaining after each constraint</div>${sieveHtml(d.elimination_steps)}`;
  return `<li class="step ${deterministic ? '' : 'model'}"><span class="num">${esc(st.step)}</span>
    <div class="card"><div class="card-b"><div class="step-h"><h4>${esc(st.title)}</h4>
      <span class="tag ${deterministic ? '' : 'model'}">${deterministic ? 'deterministic' : 'model call'}</span></div>
      <p>${esc(st.description)}</p>${body}</div></div></li>`;
}

function compare(it, data) {
  if (!data) return null;
  if (data.case !== it.case) return { cls: 'no', txt: `Declared ${data.case}; reference says ${it.case}` };
  const canon = a => Object.keys(a).sort().map(n => {
    const refStation = (assignments(it).flatMap(x => Object.entries(x)).find(([k, v]) => k === n && v.station) || [])[1];
    return `${n}|${a[n].block}|${refStation ? (a[n].station || '') : ''}`;
  }).join(';');
  if (it.case === 'unique') return canon(data.assignment || {}) === canon(assignments(it)[0]) ? { cls: 'yes', txt: 'Matches the reference schedule' } : { cls: 'no', txt: 'Schedule differs from the reference' };
  if (it.case === 'ambiguous') {
    const a = new Set((data.assignments || []).map(canon)), b = new Set(assignments(it).map(canon));
    const ok = a.size === b.size && [...a].every(x => b.has(x));
    return ok ? { cls: 'yes', txt: `Matches all ${b.size} reference schedules` } : { cls: 'no', txt: `Returned ${a.size}; reference has ${b.size}` };
  }
  const got = new Set((data.conflicts || []).map(norm));
  const exact = coreSets(it).some(s => s.length === got.size && s.every(x => got.has(norm(x))));
  return exact ? { cls: 'yes', txt: 'Cites one of the reference conflict sets' }
    : { cls: 'maybe', txt: 'Right kind; set is not one of the listed cores' };
}

function answerHtml(data, it, custom) {
  if (data.case === 'unique') return boardHtml(data.assignment || {});
  if (data.case === 'ambiguous') { const l = data.assignments || []; return matrixHtml(l) + variesHtml(l); }
  const c = data.conflicts || [];
  return c.length ? `<ul class="stmts">${c.map(x => {
    const at = custom ? undefined : [...coreLineIdx(it, [x])][0];
    return `<li><div class="stmt" style="cursor:default"><span class="ln">${at !== undefined ? 'L' + (at + 1) : ''}</span><span>${esc(x)}</span></div></li>`;
  }).join('')}</ul>` : '<p class="sub">No statements were cited.</p>';
}

function renderLive() {
  const it = S.active; if (!it) return;
  const host = $('#panel-live');
  const run = S.live[it.id];
  if (!run) {
    host.innerHTML = `<div class="stack"><section class="card"><div class="card-h"><h3>How a run works</h3></div>
      <div class="pipeline">${STAGES.map(([k, t, d, m]) => `<div class="pipe ${m ? 'model' : ''}"><div class="k">${k}${m ? ' · model' : ''}</div><h4>${t}</h4><p>${d}</p></div>`).join('')}</div>
      <p class="cta">Pick a budget in the top bar and press <b>Run on Granite</b>. Everything shown here comes back from the server for that run, including the extracted constraints and the world counts.</p></section></div>`;
    return;
  }
  const { data, budget, ms, custom } = run;
  const t = data.telemetry || {};
  const cmp = custom ? null : compare(it, data);
  host.innerHTML = `<div class="stack">
    <section class="card"><div class="verdict"><div>
      <h2>${esc(KIND_NAME[data.case] || data.case)}</h2>
      <div class="facts"><span>Budget <b>${esc(budget)}</b></span><span>Model calls <b>${esc(t.calls_used ?? '—')}</b> of ${esc(t.max_calls ?? '—')}</span><span>Surviving worlds <b>${esc(t.world_count ?? '—')}</b> of 720</span><span>Round trip <b>${(ms / 1000).toFixed(1)}s</b></span>${custom ? '<span><b>custom notes</b></span>' : ''}</div></div>
      ${cmp ? `<span class="cmp ${cmp.cls}">${esc(cmp.txt)}</span>` : ''}</div></section>
    <section class="card"><div class="card-h"><h3>Answer returned</h3></div><div class="card-b">${answerHtml(data, it, custom)}</div></section>
    <section><h3 style="font-size:14px;margin:4px 0 12px">What happened, step by step</h3>
      <ol class="steps">${(t.trace || []).map(stepHtml).join('')}</ol></section>
    <details class="raw"><summary>Raw response</summary><pre>${esc(JSON.stringify(data, null, 2))}</pre></details>
  </div>`;
}

/* ---------------- Scorecard tab ---------------- */
function renderScore() {
  const host = $('#panel-score');
  const r = S.results;
  if (!r || !r.runs || !Object.keys(r.runs).length) {
    host.innerHTML = `<div class="card empty-card"><h3>No measured results yet</h3>
      <p class="sub" style="font-size:13px">This page only shows numbers produced by <code>score.py</code> on real runs, so it stays empty until you generate them.</p>
      <pre>./run items.json --budget 1x  --out answers_1x.json
./run items.json --budget 3x  --out answers_3x.json
./run items.json --budget 10x --out answers_10x.json
python3 scripts/make_results.py answers_1x.json answers_3x.json answers_10x.json</pre>
      <p class="sub">Then reload. Granite and frontier reference points come from the task brief.</p></div>`;
    return;
  }
  const order = ['1x', '3x', '10x'].filter(b => r.runs[b]);
  const stat = (lab, v, ref, note) => `<div class="card stat ${ref ? 'ref' : ''}"><div class="lab">${esc(lab)}</div><div class="val">${pct(v)}</div><div class="meter"><span style="width:${Math.min(100, v * 100)}%"></span></div><div class="src">${esc(note)}</div></div>`;
  const cards = [stat('Granite 4.2 8B, no harness', BRIEF_REF.granite, true, 'from the task brief'), stat('Frontier model, no harness', BRIEF_REF.frontier, true, 'from the task brief')]
    .concat(order.map(b => stat(`ShiftLogic ${b}`, r.runs[b].macro_exact_match, false, `${r.runs[b].n_items} items · one run`)));
  const kindRows = order.map(b => { const k = r.runs[b].per_case_rate || {}; return `<tr><td><b>${b}</b></td><td>${pct(k.unique || 0)}</td><td>${pct(k.ambiguous || 0)}</td><td>${pct(k.inconsistent || 0)}</td><td><b>${pct(r.runs[b].macro_exact_match)}</b></td><td>${pct(r.runs[b].ambiguous_partial || 0)}</td><td>${pct(r.runs[b].inconsistent_label_only || 0)}</td></tr>`; }).join('');
  const conf = order.map(b => {
    const c = r.runs[b].confusion || {};
    const cols = [...KINDS, 'unparsed'];
    const cells = KINDS.map(t => `<div class="r">${KIND_NAME[t]}</div>` + cols.map(d => { const v = (c[t] || {})[d] || 0; return `<div class="v ${d === t ? 'diag' : v ? 'off' : ''}">${v}</div>`; }).join('')).join('');
    return `<div><div style="font-weight:600">${b}</div><div class="cm"><div class="h"></div>${cols.map(d => `<div class="h">${({ unique: 'Unique', ambiguous: 'Ambig.', inconsistent: 'Incons.', unparsed: 'Unparsed' })[d]}</div>`).join('')}${cells}</div></div>`;
  }).join('');
  host.innerHTML = `<div class="stack" style="max-width:1100px">
    <div class="score-grid">${cards.join('')}</div>
    <section class="card"><div class="card-h"><h3>Exact match by kind</h3><span class="sub">macro = mean of the three kinds</span></div><div class="card-b"><table class="tbl"><thead><tr><th>Budget</th><th>Unique</th><th>Ambiguous</th><th>Inconsistent</th><th>Macro</th><th>Ambig. partial</th><th>Label only</th></tr></thead><tbody>${kindRows}</tbody></table></div></section>
    <section class="card"><div class="card-h"><h3>Declared kind vs true kind</h3><span class="sub">rows are the true kind</span></div><div class="card-b conf">${conf}</div></section>
    ${r.generated ? `<p class="sub">Generated ${esc(r.generated)} from score.py.</p>` : ''}</div>`;
}

/* ---------------- state changes ---------------- */
function setTab(t) {
  S.tab = t;
  $$('.tabs [role="tab"]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
  ['item', 'live', 'score'].forEach(x => { $('#panel-' + x).hidden = x !== t; });
  if (t === 'live') renderLive();
  if (t === 'score') renderScore();
}

function select(id, keepTab) {
  const it = S.items.find(i => i.id === id); if (!it) return;
  S.active = it; S.core = 0;
  renderHeader(); renderItem(); renderRail();
  if (S.tab === 'live') renderLive();
  if (!keepTab && S.tab === 'score') setTab('item');
  $('#shell').classList.remove('rail-open');
  $('#panel-' + S.tab).scrollTop = 0;
}

function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || ''); el.textContent = msg;
  $('#toasts').appendChild(el); setTimeout(() => el.remove(), 6000);
}

function setBusy(b) {
  S.busy = b;
  $('#run-btn').classList.toggle('busy', b);
  $('#run-label').textContent = b ? `Running ${S.budget}…` : 'Run on Granite';
  renderApiState();
}

async function run(custom) {
  const it = S.active; if (!it || S.busy) return;
  setBusy(true);
  const t0 = performance.now();
  try {
    const res = await fetch('/api/solve', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: it.id, budget: S.budget, custom_text: custom || null }) });
    if (!res.ok) { let d = ''; try { d = (await res.json()).detail; } catch (_) {} throw new Error(d || `${res.status} ${res.statusText}`); }
    const data = await res.json();
    S.live[it.id] = { data, budget: S.budget, ms: performance.now() - t0, custom: !!custom };
    setTab('live'); renderRail();
  } catch (e) {
    toast(`Run failed: ${e.message}`, 'error');
  } finally { setBusy(false); }
}

async function probeApi() {
  try {
    const r = await fetch('/api/health', { cache: 'no-store' });
    const j = await r.json();
    S.api = { state: j.api_configured ? 'on' : 'nokey' };
  } catch (_) { S.api = { state: 'off' }; }
  renderApiState();
}

async function loadResults() {
  try {
    const r = await fetch('results.json', { cache: 'no-store' });
    const text = await r.text();
    S.results = JSON.parse(text);
  } catch (_) { S.results = null; }
  if (S.tab === 'score') renderScore();
}

function setTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
  try { t ? localStorage.setItem('sl-theme', t) : localStorage.removeItem('sl-theme'); } catch (_) {}
}

/* ---------------- wiring ---------------- */
function wire() {
  $('#filters').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.filter = b.dataset.f; renderFilters(); renderRail(); });
  $('#search').addEventListener('input', e => { S.query = e.target.value; renderRail(); });
  $('#item-list').addEventListener('click', e => { const b = e.target.closest('.item'); if (b) select(b.dataset.id, true); });
  $('#budget').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.budget = b.dataset.b; renderBudget(); });
  $('.tabs').addEventListener('click', e => { const b = e.target.closest('[role="tab"]'); if (b) setTab(b.dataset.tab); });
  $('#run-btn').addEventListener('click', () => run());
  $('#menu-btn').addEventListener('click', () => $('#shell').classList.toggle('rail-open'));
  $('#theme-btn').addEventListener('click', () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark' || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    setTheme(dark ? 'light' : 'dark');
  });
  $('#custom-btn').addEventListener('click', () => { $('#custom-text').value = S.active ? S.active.text : ''; $('#custom-dialog').showModal(); });
  $('#custom-dialog').addEventListener('close', () => { if ($('#custom-dialog').returnValue === 'go' && $('#custom-text').value.trim()) run($('#custom-text').value); });

  $('#panel-item').addEventListener('click', e => {
    const c = e.target.closest('[data-c]');
    if (c) { S.core = +c.dataset.c; renderItem(); return; }
    const s = e.target.closest('.stmt[data-line]');
    if (s && s.dataset.line !== '') {
      const li = $(`#lines li[data-i="${s.dataset.line}"]`);
      if (li) { li.scrollIntoView({ block: 'center', behavior: 'smooth' }); li.classList.remove('flash'); void li.offsetWidth; li.classList.add('flash'); }
    }
  });

  document.addEventListener('keydown', e => {
    if (e.target.closest('input,textarea,select,dialog')) return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const list = visible(); if (!list.length) return;
    const i = Math.max(0, list.findIndex(x => S.active && x.id === S.active.id));
    const n = list[Math.min(list.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (n) { e.preventDefault(); select(n.id, true); }
  });
}

async function init() {
  try { const t = localStorage.getItem('sl-theme'); if (t) setTheme(t); } catch (_) {}
  renderBudget(); renderApiState(); wire();
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    S.items = await res.json();
  } catch (e) {
    $('#panel-item').innerHTML = `<div class="card empty-card"><h3>Could not load data.json</h3><p class="sub">Serve the ui folder over HTTP (for example <code>python3 server.py</code>) rather than opening the file directly.</p></div>`;
    return;
  }
  renderFilters(); renderRail();
  if (S.items.length) select(S.items[0].id, true);
  probeApi(); loadResults();
}
init();
})();
