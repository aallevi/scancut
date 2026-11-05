// Scan Studio — interfaccia. Coordinate dei contorni: pixel della scansione a piena risoluzione.
'use strict';

// ------------------------------------------------------------ utilita'
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}
const svg = s => h('span', { html: s, style: { display: 'contents' } });
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const qs = o => new URLSearchParams(o).toString();
const api = {
  async get(p, q) {
    const r = await fetch(`/api/${p}${q ? '?' + qs(q) : ''}`);
    const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j;
  },
  async post(p, body) {
    const r = await fetch(`/api/${p}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Studio': '1' }, body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || r.status); e.status = r.status; e.body = j; throw e; }
    return j;
  },
};
function store(k, v) { try { if (v === undefined) return localStorage.getItem('studio.' + k); localStorage.setItem('studio.' + k, v); } catch (e) { return null; } }
const PREV_V = 2;      // alzare quando cambia il formato delle anteprime (2: PNG con trasparenza)
const bgCss = () => ({ white: '#fff', grey: '#8a8d91', dark: '#262a30', checker: 'repeating-conic-gradient(#e6e6e6 0% 25%, #fbfbfb 0% 50%) 0 0 / 16px 16px' }[S.bg] || 'linear-gradient(#eef4fb, #d6e4f3)');
const fmtSize = b => b > 1 << 20 ? (b / (1 << 20)).toFixed(1) + ' MB' : Math.round(b / 1024) + ' KB';
const COLORS = ['#3399ff', '#ff8c1a', '#2fb84f', '#c84ad0', '#e0b600', '#14b8c4', '#ff4d5e', '#7a6cff'];
const CMP_COLORS = { auto: '#00a2ff', classic: '#ff7a00', vision: '#d100d1', sam3: '#00b050' };

// ------------------------------------------------------------ icone (stile Vista, piccole)
const I = {
  addon: '<svg class="ico" viewBox="0 0 16 16"><defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d9f0ff"/><stop offset="1" stop-color="#5aa7e6"/></linearGradient></defs><path d="M2 5.5h3.2a1.6 1.6 0 1 1 3.2 0H11.5v3a1.6 1.6 0 1 1 0 3.2V14.5H2z" fill="url(#ag)" stroke="#2f6aa8"/></svg>',
  folder: '<svg class="ico" viewBox="0 0 16 16"><defs><linearGradient id="vfb" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fde49a"/><stop offset="1" stop-color="#e6b74f"/></linearGradient><linearGradient id="vff" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff0b8"/><stop offset="1" stop-color="#ecc160"/></linearGradient></defs><path d="M6 2.5h2.5l.7.8h3.8v11.2H6z" fill="url(#vfb)" stroke="#b8862a" stroke-width=".8" stroke-linejoin="round"/><path d="M3 4l3.5-1.6v12.4L3 15z" fill="url(#vff)" stroke="#b8862a" stroke-width=".8" stroke-linejoin="round"/><rect x="10.3" y="11" width="1.8" height="2.4" fill="#fff"/></svg>',
  folderBig: '<svg class="ico" viewBox="0 0 64 64"><defs><linearGradient id="vfB" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fde6a2"/><stop offset="1" stop-color="#ecc163"/></linearGradient><linearGradient id="vfF" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff1bd"/><stop offset=".6" stop-color="#f8da82"/><stop offset="1" stop-color="#eabf5e"/></linearGradient><linearGradient id="vfS" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5c4313" stop-opacity=".35"/><stop offset="1" stop-color="#5c4313" stop-opacity="0"/></linearGradient><radialGradient id="vfG" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#000" stop-opacity=".25"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient><clipPath id="vfC"><path d="M16 9.5h33.6v49.6l-33.6 2z"/></clipPath></defs><ellipse cx="38" cy="60.5" rx="25" ry="2.4" fill="url(#vfG)"/><path d="M15 7.6q0-1.6 1.6-1.6h7.6l2 2.2h22.6q2 0 2 2V42h2.4q1 0 1 1v15.4q0 1-1 1.1l-36.6 2q-1.6.1-1.6-1.5z" fill="url(#vfB)" stroke="#c4952f" stroke-width=".8" stroke-linejoin="round"/><path d="M50.8 10.5V41.6" stroke="#b07f22" stroke-width="1" opacity=".55"/><g clip-path="url(#vfC)"><!--pages--><rect x="28" y="6" width="9" height="56" fill="url(#vfS)"/></g><rect x="52.2" y="46.5" width="2.2" height="9.5" rx=".4" fill="#fff" stroke="#d4c49e" stroke-width=".4"/><rect x="52.5" y="53" width="1.6" height="1.8" fill="#3d8fe0"/><path d="M14.2 8.4l13.6 5q1.2.4 1.2 1.6V39.5l-2.4 2.6v20.6q0 1.1-1.1.8L15 60.6q-.8-.2-.8-1.1z" fill="url(#vfF)" stroke="#c4952f" stroke-width=".8" stroke-linejoin="round"/><path d="M15.4 9.6v50" stroke="#e2b553" stroke-width=".5"/><path d="M16.3 10v50" stroke="#fff" stroke-width=".5" opacity=".6"/><path d="M15 9.2l12.7 4.7" stroke="#fff" stroke-width=".9" opacity=".85"/></svg>',
  pics: '<svg class="ico" viewBox="0 0 16 16"><rect x="1.5" y="2.5" width="13" height="11" rx="1" fill="#e9f4ff" stroke="#3a6ea5"/><path d="M3 12l3.5-4 2.5 3 2-2 2.5 3z" fill="#2fa84f"/><circle cx="11" cy="5.5" r="1.4" fill="#ffc83d"/></svg>',
  cut: '<svg class="ico" viewBox="0 0 16 16"><circle cx="4" cy="12" r="2.3" fill="none" stroke="#c03030" stroke-width="1.4"/><circle cx="12" cy="12" r="2.3" fill="none" stroke="#c03030" stroke-width="1.4"/><path d="M5.5 10.5L12 2M10.5 10.5L4 2" stroke="#555" stroke-width="1.3"/></svg>',
  warn: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 1.5l7 12.5H1z" fill="#ffd34d" stroke="#b58500"/><path d="M8 6v4" stroke="#333" stroke-width="1.6"/><circle cx="8" cy="12" r=".9" fill="#333"/></svg>',
  inbox: '<svg class="ico" viewBox="0 0 16 16"><path d="M1.5 9l2-6h9l2 6v4.5h-13z" fill="#dfeefe" stroke="#3a6ea5"/><path d="M1.5 9h4l1 2h3l1-2h4" fill="none" stroke="#3a6ea5"/></svg>',
  jobs: '<svg class="ico" viewBox="0 0 16 16"><rect x="1.5" y="3" width="13" height="10" rx="1" fill="#fff" stroke="#566d86"/><rect x="3" y="5" width="7" height="2" fill="#36b51a"/><rect x="3" y="9" width="10" height="2" fill="#9fd88f"/></svg>',
  scanner: '<img class="ico" src="scanner-icon.png" alt="">',
  script: '<svg class="ico" viewBox="0 0 16 16"><path d="M3 1.5h7l3 3v10H3z" fill="#fff" stroke="#566d86"/><path d="M5 7l-1.5 1.5L5 10M8 7l1.5 1.5L8 10" stroke="#2a72c9" fill="none"/></svg>',
  gear: '<svg class="ico" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5" fill="#cfd8e3" stroke="#56677a" stroke-width="2" stroke-dasharray="2 1.4"/><circle cx="8" cy="8" r="2" fill="#fff" stroke="#56677a"/></svg>',
  claude: '<svg viewBox="0 0 16 16"><path d="M8 1l1.6 4.6L14 4l-3 3.6L15 9l-4.6.6L11 15 8 11.2 5 15l.6-5.4L1 9l4-1.4L2 4l4.4 1.6z" fill="#e8835a" stroke="#fff" stroke-width=".6"/></svg>',
  // strumenti
  t_select: '<svg viewBox="0 0 16 16"><path d="M3 1.5v12l3-3 2 4.5 2-1-2-4.3h4.2z" fill="#fff" stroke="#000"/></svg>',
  t_points: '<svg viewBox="0 0 16 16"><path d="M2 12L6 3l8 4-5 7z" fill="none" stroke="#1f6fd0" stroke-width="1.2"/><rect x="0.5" y="10.5" width="3" height="3" fill="#fff" stroke="#000"/><rect x="4.5" y="1.5" width="3" height="3" fill="#fff" stroke="#000"/><rect x="12.5" y="5.5" width="3" height="3" fill="#1f6fd0" stroke="#000"/><rect x="7.5" y="12.5" width="3" height="3" fill="#fff" stroke="#000"/></svg>',
  t_lasso_add: '<svg viewBox="0 0 16 16"><path d="M8 2C3 2 1.5 5 2.5 7s5 2.5 8 1.5S14 4 8 2z" fill="#d6f5d6" stroke="#1e8a1e" stroke-dasharray="2 1"/><path d="M4 8c-1 2 0 4 2 5" fill="none" stroke="#333"/><path d="M11 10v5M8.5 12.5h5" stroke="#1e8a1e" stroke-width="1.8"/></svg>',
  t_lasso_sub: '<svg viewBox="0 0 16 16"><path d="M8 2C3 2 1.5 5 2.5 7s5 2.5 8 1.5S14 4 8 2z" fill="#fde0e0" stroke="#c22" stroke-dasharray="2 1"/><path d="M4 8c-1 2 0 4 2 5" fill="none" stroke="#333"/><path d="M8.5 12.5h5" stroke="#c22" stroke-width="1.8"/></svg>',
  t_brush_add: '<svg viewBox="0 0 16 16"><path d="M13.5 1.5L7 8l1.5 1.5L15 3z" fill="#c8a165" stroke="#6b4b18"/><path d="M6.5 8.5c-2 0-3 1.5-3 3 0 1-1 2-2.5 2.5 3 .5 6-.5 7-3z" fill="#2fb84f" stroke="#1a6b2c"/></svg>',
  t_brush_sub: '<svg viewBox="0 0 16 16"><path d="M9 2l5 5-6.5 6.5H4.5L2 11z" fill="#f7b6c2" stroke="#9b3048"/><path d="M5.5 7.5l5 5" stroke="#9b3048"/><path d="M4.5 13.5H14" stroke="#555"/></svg>',
  t_poly: '<svg viewBox="0 0 16 16"><path d="M2 13L4 3l7 1 3 6-5 4z" fill="#dbeeff" stroke="#1f6fd0"/><circle cx="2" cy="13" r="1.3" fill="#000"/><circle cx="4" cy="3" r="1.3" fill="#000"/><circle cx="11" cy="4" r="1.3" fill="#000"/></svg>',
  t_box: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" fill="none" stroke="#000" stroke-dasharray="2 1.2"/><path d="M8 5.5l.9 1.8 2 .3-1.4 1.4.3 2L8 10.1 6.2 11l.3-2-1.4-1.4 2-.3z" fill="#ffb400" stroke="#9c6b00" stroke-width=".5"/></svg>',
  t_rect: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" fill="#dbeeff" stroke="#000" stroke-dasharray="2 1.2"/></svg>',
  t_wand: '<svg viewBox="0 0 16 16"><path d="M2 14L10 6" stroke="#444" stroke-width="2.2" stroke-linecap="round"/><path d="M2 14L8.5 7.5" stroke="#d9d9d9" stroke-width="1"/><path d="M12 1l.7 1.8L14.5 3l-1.6 1 .4 1.9L12 5l-1.3.9.4-1.9-1.6-1 1.8-.2z" fill="#ffd21f" stroke="#a87b00" stroke-width=".5"/><circle cx="14" cy="8" r=".8" fill="#ffd21f"/><circle cx="8" cy="2" r=".7" fill="#ffd21f"/></svg>',
  t_sam: '<svg viewBox="0 0 16 16"><path d="M8 1.5l1.2 3.3 3.3-1.2-1.2 3.3 3.2 1.1-3.2 1.1 1.2 3.3-3.3-1.2L8 14.5l-1.2-3.3-3.3 1.2 1.2-3.3L1.5 8l3.2-1.1-1.2-3.3 3.3 1.2z" fill="#7b5cff" stroke="#3b2a99" stroke-width=".6"/><circle cx="8" cy="8" r="2" fill="#fff"/></svg>',
  t_hand: '<svg viewBox="0 0 16 16"><path d="M5 14c-1.5-1.5-3-4-3-5s1-1 1.5-.5L5 10V3.5c0-1 1.5-1 1.5 0V8V2.5c0-1 1.5-1 1.5 0V8V3c0-1 1.5-1 1.5 0v5.5V5c0-1 1.5-1 1.5 0v5c0 2-1 4-2 4z" fill="#fff" stroke="#000" stroke-width=".9"/></svg>',
  // barra in basso
  prev: '<svg viewBox="0 0 18 18"><path d="M11.5 4L6 9l5.5 5z" fill="#fff"/></svg>',
  next: '<svg viewBox="0 0 18 18"><path d="M6.5 4L12 9l-5.5 5z" fill="#fff"/></svg>',
  orb_cut: '<svg viewBox="0 0 20 20"><path d="M4 15l3-3M16 15l-3-3" stroke="#fff" stroke-width="1.6"/><circle cx="4.5" cy="15.5" r="2.5" fill="none" stroke="#fff" stroke-width="1.6"/><circle cx="15.5" cy="15.5" r="2.5" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M7 12L14 2M13 12L6 2" stroke="#fff" stroke-width="1.6"/></svg>',
  orb_open: '<svg viewBox="0 0 20 20"><path d="M6 3l10 7-10 7z" fill="#fff"/></svg>',
  zin: '<svg viewBox="0 0 18 18"><circle cx="7.5" cy="7.5" r="5" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M11 11l5 5M5 7.5h5M7.5 5v5" stroke="#fff" stroke-width="1.6"/></svg>',
  zout: '<svg viewBox="0 0 18 18"><circle cx="7.5" cy="7.5" r="5" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M11 11l5 5M5 7.5h5" stroke="#fff" stroke-width="1.6"/></svg>',
  fit: '<svg viewBox="0 0 18 18"><path d="M2 6V2h4M12 2h4v4M16 12v4h-4M6 16H2v-4" fill="none" stroke="#fff" stroke-width="1.6"/></svg>',
  undo: '<svg viewBox="0 0 18 18"><path d="M6 4L2 8l4 4" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M2 8h9a4.5 4.5 0 010 9H8" fill="none" stroke="#fff" stroke-width="1.6"/></svg>',
  redo: '<svg viewBox="0 0 18 18"><path d="M12 4l4 4-4 4" fill="none" stroke="#fff" stroke-width="1.6"/><path d="M16 8H7a4.5 4.5 0 000 9h3" fill="none" stroke="#fff" stroke-width="1.6"/></svg>',
};

// ------------------------------------------------------------ stato
const S = {
  root: '', tree: [], dir: 'originals', items: [], sel: new Set(), anchor: null, filter: '',
  view: 'gallery', rel: null, info: null, st: null, names: {}, engines: [], settings: {},
  engine: 'auto', params: {}, tool: 'select', selSheet: null, brushMM: 1.5, showCut: true,
  mode: 'add', wandTol: 14, wandContig: true, bg: store('bg') || 'blue',
  loupe: store('loupe') === '1', densShut: store('densshut') === '1', loupeZoom: +(store('loupez') || 8), densR: +(store('densr') || 1), histLog: false, sam: null,
  compare: null, hist: [], fut: [], open: new Set(['originals']), jobs: [], chat: null,
};

S._primary = null; S.selSet = new Set();
Object.defineProperty(S, 'selSheet', { get() { return S._primary; }, set(v) { S._primary = v; S.selSet = new Set(v ? [v] : []); } });
const isSel = id => S.selSet.has(id);
const selSheets = () => (S.st?.sheets || []).filter(s => S.selSet.has(s.id));
function toggleSel(id) {
  if (S.selSet.has(id)) { S.selSet.delete(id); S._primary = [...S.selSet].pop() || null; }
  else { S.selSet.add(id); S._primary = id; }
}
function selectIds(ids, add) {
  if (!add) S.selSet = new Set();
  ids.forEach(i => S.selSet.add(i));
  S._primary = ids.length ? ids[ids.length - 1] : ([...S.selSet].pop() || null);
}

// ------------------------------------------------------------ (i): spiegazioni
let tipEl = null;
function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } }
function info(text) {
  const b = h('span', { class: 'info', tabindex: 0, 'aria-label': 'More information' }, 'i');
  const show = () => {
    hideTip();
    const r = b.getBoundingClientRect();
    tipEl = h('div', { class: 'balloon' }, h('div', { class: 'bt' }, h('span', { class: 'info big' }, 'i'), ' ', text));
    document.body.append(tipEl);
    const w = tipEl.offsetWidth, hgt = tipEl.offsetHeight;
    const left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - 28));
    const below = r.bottom + hgt + 14 < window.innerHeight;
    tipEl.style.left = left + 'px'; tipEl.style.top = (below ? r.bottom + 10 : r.top - hgt - 10) + 'px';
    tipEl.classList.add(below ? 'down' : 'up'); tipEl.style.setProperty('--ax', (r.left + r.width / 2 - left - 7) + 'px');
  };
  b.addEventListener('mouseenter', show); b.addEventListener('focus', show);
  b.addEventListener('mouseleave', hideTip); b.addEventListener('blur', hideTip);
  b.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); tipEl ? hideTip() : show(); });
  return b;
}
const TIPS = {
  brush: 'Brush size in millimetres on the paper (not screen pixels). In Add mode it paints sheet in, in Cut mode it erases. [ and ] change it.',
  wand: 'Magic wand tolerance, per colour channel, like Photoshop: a click selects every pixel within this many levels of the clicked colour. The automatic cut uses about 13-15. Raise it if the wand stops at shadows, lower it if it leaks into the paper.',
  contig: 'Contiguous: only pixels connected to the click. Off: the same colour anywhere on the scan (e.g. every bit of lid showing through holes).',
  cutview: 'Darkens what will be cut away. Zoomed in, it shows the exact final edge pixel by pixel, not the simplified outline. O toggles it.',
  modes: 'What lasso, rectangle and wand do, like Photoshop: □ New makes a separate sheet from the selection (e.g. only the ink: wand with contig. off, click a black line), + adds to the sheet, − cuts away, ∩ keeps only the overlap (e.g. only the ink inside this page). While clicking: ⇧ adds, ⌥ cuts, ⇧⌥ intersects. X swaps + and −.',
  hist: 'How many pixels have each lightness (grey) and each R, G, B value. The dashed line is the lid colour the automatic cut found. Read-only; click to switch linear/log.',
  template: 'How cutouts are named: {batch} {stem} {sheet} (" a", " b"…) {letter} {n} {label} {date} {engine}. A / makes subfolders.',
  densit: 'Values of the real scan pixel under the cursor (or the 3×3 / 5×5 average, View menu). "vs lid" is the colour distance the automatic cut measures; under the tolerance it counts as lid.',
};

// ------------------------------------------------------------ menu a tendina
let openMenu = null;
function closeMenu() { if (openMenu) { openMenu.el.remove(); openMenu.btn.classList.remove('open'); openMenu = null; } }
function menu(btn, items) {
  if (openMenu && openMenu.btn === btn) return closeMenu();
  closeMenu();
  const r = btn.getBoundingClientRect();
  const el = h('div', { class: 'menu', style: { left: r.left + 'px', top: r.bottom + 1 + 'px' } },
    items.map(it => it === '-' ? h('div', { class: 'sep' }) :
      h('div', { class: 'mi' + (it.disabled ? ' disabled' : ''), title: it.title || null, onclick: () => { closeMenu(); it.do && it.do(); } },
        it.check ? h('span', { class: 'ck' }, '✓') : null, it.label, it.kbd ? h('span', { class: 'kbd' }, it.kbd) : null,
        it.note ? h('div', { class: 'mnote' }, it.note) : null)));
  document.body.append(el);
  btn.classList.add('open');
  openMenu = { el, btn };
}
document.addEventListener('mousedown', e => { if (openMenu && !openMenu.el.contains(e.target) && !openMenu.btn.contains(e.target)) closeMenu(); });

// ------------------------------------------------------------ barra comandi
function cmd(label, onclick, opts = {}) {
  const b = h('div', { class: 'cmd' + (opts.disabled ? ' disabled' : ''), title: opts.title || null },
    opts.icon ? svg(opts.icon) : null, label, opts.menu ? h('span', { class: 'arrow' }, '▼') : null);
  b.addEventListener('click', () => opts.menu ? menu(b, opts.menu()) : onclick && onclick());
  return b;
}
function renderCmdbar() {
  const bar = $('#cmdbar'); bar.innerHTML = '';
  const ed = S.view === 'editor';
  const targets = () => ed ? [S.rel] : [...S.sel];
  bar.append(
    cmd('File', null, { menu: () => [
      { label: 'Show in Finder', do: () => api.post('open', { what: 'finder', rel: S.rel || [...S.sel][0] }) , disabled: !S.rel && !S.sel.size },
      { label: 'Open scans folder', do: () => api.post('open', { what: 'finder' }) },
      '-',
      { label: 'Settings…', do: settingsDialog, kbd: '⌘,' },
      { label: 'Reload', do: () => location.reload(), kbd: '⌘R' },
    ] }),
    cmd('Detect', null, { title: 'Find the sheets with an engine', menu: () => [
      ...S.engines.map(e => ({ label: e.name + (e.available ? '' : ' (not installed)'), check: S.engine === e.id, disabled: !e.available,
        do: () => { S.engine = e.id; renderSide(); if (ed) detect(); else if (S.sel.size) batch(false); } })),
      '-', { label: 'Compare engines', check: !!S.compare, disabled: !ed, do: toggleCompare, kbd: 'C' },
      { label: 'Unload SAM 3 (free memory)', disabled: !S.samLoaded, do: () => api.post('sam_unload').then(() => { S.samLoaded = false; status('SAM 3 unloaded'); }) },
    ] }),
    cmd('View', null, { menu: () => [
      ...[['blue', 'Light blue background'], ['white', 'White background'], ['grey', 'Grey background'], ['dark', 'Dark background'], ['checker', 'Checkerboard']].map(([b, l]) => ({ label: l, check: S.bg === b, do: () => setBg(b) })),
      '-', { label: 'Cut view', check: S.showCut, disabled: !ed, kbd: 'O', do: () => { S.showCut = !S.showCut; const cb = $('#cutview'); if (cb) cb.checked = S.showCut; requestTile(); draw(); } },
      { label: 'Compare engines', check: !!S.compare, disabled: !ed, kbd: 'C', do: toggleCompare },
      '-', { label: 'Loupe', check: S.loupe, kbd: 'G', do: () => { S.loupe = !S.loupe; store('loupe', S.loupe ? '1' : '0'); loupeDraw(); } },
      ...[4, 8, 16].map(z => ({ label: `   Loupe ${z}:1`, check: S.loupeZoom === z, do: () => { S.loupeZoom = z; store('loupez', z); } })),
      ...[[0, 'Densitometer: single pixel'], [1, 'Densitometer: 3×3 average'], [2, 'Densitometer: 5×5 average']].map(([r, l]) => ({ label: l, check: S.densR === r, do: () => { S.densR = r; store('densr', r); } })),
      '-', { label: 'Fit', disabled: !ed, kbd: '⌘0', do: fit }, { label: 'Actual pixels', disabled: !ed, kbd: '⌘1', do: actual },
      '-', { label: 'Reset pane sizes', do: () => { store('navw', ''); store('sidew', ''); applyPaneSizes(); } },
    ] }),
    cmd('SAM 3', null, { icon: I.t_sam, title: 'Meta Segment Anything 3: find objects by name', menu: () => {
      const sam = S.engines.find(e => e.id === 'sam3'), ok = sam?.available, p = samParams().prompt;
      if (!ok) return [{ label: 'SAM 3 is not installed', disabled: true }, { label: 'Add-ons…', do: () => go('addons'), note: 'Ultralytics and the model, two steps.' }];
      return [
        { label: `Prompt: “${p}”…`, do: samPromptDialog },
        ...samChoices().map(c => ({ label: '   ' + c.text, title: c.note, check: p === c.text, do: () => { S.params.prompt = c.text; renderSide(); status(c.note); } })),
        '-',
        { label: `Find every “${p}” (replace sheets)`, disabled: !ed, do: () => detect(null, 'sam3') },
        { label: `Find every “${p}” (add to sheets)`, disabled: !ed, do: () => detect(null, 'sam3', true) },
        { label: 'Click tool: pick objects', kbd: 'S', disabled: !ed, do: () => setTool('sam') },
        { label: 'Box tool: search inside a box', kbd: 'S + drag', disabled: !ed, do: () => setTool('sam') },
        '-',
        { label: S.samLoaded ? 'Unload SAM 3 (free 3.4 GB)' : 'SAM 3 not loaded (loads on first use)', disabled: !S.samLoaded, do: () => api.post('sam_unload').then(() => { S.samLoaded = false; status('SAM 3 unloaded'); }) },
      ];
    } }),
    cmd('Fix', null, { title: 'Corrections that change pixels: always a separate copy, never the original or the cutout', menu: () => [
      { label: 'About “fake pixels”…', do: fakePixelsDialog, note: 'Why these make extra copies and the rest of the studio never changes a pixel.' },
      '-',
      { label: 'Descreen (moiré on printed paper)', disabled: true, note: 'Coming. Notch filter on the image spectrum (FFT), like pro descreening. Saves a separate copy · fake pixels.' },
      { label: 'Levels and contrast', disabled: true, note: 'Coming. Curves on 16-bit data (48-bit scans via SANE). Saves a separate copy · fake pixels.' },
      { label: 'Noise and grain reduction', disabled: true, note: 'Coming. BM3D, a top-quality denoiser. Saves a separate copy · fake pixels.' },
      '-',
      { label: 'Dust and scratch removal', disabled: true, note: 'Not available: the LiDE 400 has no infrared channel, so dust cannot be told apart from ink. Software removal paints invented pixels over every speck.' },
    ] }),
    cmd('Export', () => ed ? doExport() : exportMany(targets()), { disabled: ed ? !S.st?.sheets.length : !S.sel.size, title: 'Save the cutouts (⌘S)' }),
    cmd('Batch', null, { menu: () => [
      { label: `Detect selected (${S.sel.size}) with ${engName(S.engine)}`, disabled: !S.sel.size, do: () => batch(false) },
      { label: `Detect and export selected (${S.sel.size})`, disabled: !S.sel.size, do: () => batch(true) },
      { label: 'Detect and export whole folder', do: () => { selectAll(); batch(true); } },
      '-', { label: 'Jobs…', do: () => go('jobs') },
    ] }),
    cmd('Scripts', null, { menu: () => [
      ...S.engines.filter(e => e.kind === 'script').map(e => ({ label: e.name, check: S.engine === e.id, do: () => { S.engine = e.id; renderSide(); } })),
      S.engines.some(e => e.kind === 'script') ? '-' : null,
      { label: 'Scripts folder…', do: () => go('scripts') },
    ].filter(Boolean) }),
    cmd('Scanner', null, { icon: I.scanner, menu: () => [
      { label: 'Canon IJ Scan Utility', do: () => api.post('open', { what: 'canon' }) },
      { label: 'Image Capture', do: () => api.post('open', { what: 'imagecapture' }) },
      { label: 'Run the scan agent now', do: () => api.post('open', { what: 'kick' }).then(() => status('Agent started')) },
      '-', { label: 'Scanners…', do: () => go('scanners') },
    ] }),
    h('div', { class: 'grow' }),
    cmd('Ask Claude', toggleChat, { icon: I.claude, title: 'Ask Claude about this scan, or give it a job' }),
    h('input', { class: 'search', placeholder: 'Search', value: S.filter, oninput: e => { S.filter = e.target.value; if (S.view === 'gallery') renderGallery(); } }),
  );
}
const engName = id => (S.engines.find(e => e.id === id) || { name: id }).name;

// ------------------------------------------------------------ albero a sinistra
const ICON_TOP = { originals: I.pics, cut: I.cut, failed: I.warn, inbox: I.inbox };
function renderNav() {
  const nav = $('#nav'); nav.innerHTML = '';
  const node = (label, icon, key, { count, kids, onclick, sel } = {}) => {
    const wrap = h('div', { class: S.open.has(key) ? 'open' : '' });
    const row = h('div', { class: 'node' + (sel ? ' sel' : ''), onclick, ondblclick: () => kids && toggle() },
      h('span', { class: 'tw', onclick: e => { e.stopPropagation(); toggle(); } }, kids?.length ? (S.open.has(key) ? '◢' : '▷') : ''),
      svg(icon), h('span', {}, label), count != null ? h('span', { class: 'count' }, count) : null);
    function toggle() { S.open.has(key) ? S.open.delete(key) : S.open.add(key); renderNav(); }
    wrap.append(row);
    if (kids?.length) wrap.append(h('div', { class: 'kids', style: { paddingLeft: '14px' } }, kids));
    return wrap;
  };
  const tree = h('div', { class: 'tree' });
  for (const t of S.tree) {
    const label = { originals: 'Originals', cut: 'Cutouts', failed: 'To check', inbox: 'Inbox' }[t.name];
    tree.append(node(label, ICON_TOP[t.name], t.rel, {
      count: t.count || null, sel: S.view === 'gallery' && S.dir === t.rel, onclick: () => openDir(t.rel),
      kids: t.children.map(c => node(c.name, I.folder, c.rel, { count: c.count, sel: (S.view === 'gallery' || S.view === 'editor') && S.dir === c.rel, onclick: () => openDir(c.rel) })),
    }));
  }
  nav.append(h('h4', {}, 'Scans'), tree, h('h4', {}, 'Studio'), h('div', { class: 'tree' },
    node('Jobs', I.jobs, 'v:jobs', { sel: S.view === 'jobs', onclick: () => go('jobs'), count: S.jobs.filter(j => j.status === 'running' || j.status === 'queued').length || null }),
    node('Scanners', I.scanner, 'v:scanners', { sel: S.view === 'scanners', onclick: () => go('scanners') }),
    node('Scripts', I.script, 'v:scripts', { sel: S.view === 'scripts', onclick: () => go('scripts') }),
    node('Add-ons', I.addon, 'v:addons', { sel: S.view === 'addons', onclick: () => go('addons') }),
    node('Settings', I.gear, 'v:settings', { onclick: settingsDialog }),
  ), S.version ? h('div', { class: 'small muted', style: { padding: '14px 10px 4px' } }, `Scan Studio ${S.version.replace('-', ' ')}`) : null);
}

// ------------------------------------------------------------ viste
async function go(view) {
  if (['jobs', 'scanners', 'scripts', 'addons'].includes(view)) remember('view:' + view);
  if (S.view === 'editor' && view !== 'editor') leaveEditor();
  S.view = view;
  renderCmdbar(); renderNav(); renderNavbar();
  if (view === 'gallery') renderGallery();
  if (view === 'jobs') renderJobs();
  if (view === 'scanners') renderScanners();
  if (view === 'scripts') renderScripts();
  if (view === 'addons') renderAddons();
  renderSide();
}
// motore e impostazioni dell'ultimo export della stessa serie: si riprendono entrando nella serie
// (una volta sola: se poi si sceglie un altro motore, resta quello)
async function useRemembered(rel) {
  const m = await api.get('remembered', { rel }).catch(() => null);
  if (!m || m.batch === S.memBatch) return;
  S.memBatch = m.batch;
  const e = m.engine && S.engines.find(x => x.id === m.engine);
  if (!e?.available) return;
  S.engine = e.id; Object.assign(S.params, m.params || {});
  status(`${m.batch}: ${e.name}${m.params?.prompt ? ` “${m.params.prompt}”` : ''}, as in your last export from this batch`);
  renderSide(); if (S.view === 'editor') renderOptions();
}
async function openDir(rel) {
  remember('dir:' + rel);
  if (/^originals\/[^/]+/.test(rel)) useRemembered(rel);
  S.dir = rel; S.sel.clear(); S.anchor = null;
  S.open.add(rel.split('/')[0]);
  S.items = await api.get('list', { dir: rel }).catch(e => (status(e.message), []));
  go('gallery');
}
const crumbs = (...parts) => h('div', { class: 'crumbs' }, ...parts);
const TOP_NAMES = { originals: 'Originals', cut: 'Cutouts', failed: 'To check', inbox: 'Inbox' };
S.navBack = []; S.navFwd = []; S._here = null; S._navigating = false;
function remember(target) {
  if (!S._navigating && S._here && S._here !== target) { S.navBack.push(S._here); if (S.navBack.length > 100) S.navBack.shift(); S.navFwd = []; }
  S._here = target;
}
async function goLoc(loc) {
  const [kind, ...rest] = loc.split(':'), arg = rest.join(':');
  S._navigating = true;
  try { if (kind === 'dir') await openDir(arg); else if (kind === 'scan') await openScan(arg); else await go(arg); }
  finally { S._navigating = false; }
}
async function navBack() { if (!S.navBack.length) return; S.navFwd.push(S._here); await goLoc(S.navBack.pop()); }
async function navFwd() { if (!S.navFwd.length) return; S.navBack.push(S._here); await goLoc(S.navFwd.pop()); }
function addressBar(dir, file, right) {
  // dir: 'originals/sketchbook' (o null per le pagine dello studio), file: nome della scansione aperta
  const box = h('div', { class: 'addr-field' });
  const chev = (prefix) => {
    const c = h('span', { class: 'addr-chev', title: 'Subfolders' }, '▸');
    c.addEventListener('click', async e => {
      e.stopPropagation();
      let items;
      if (prefix === '') items = S.tree.map(t => ({ label: TOP_NAMES[t.name] || t.name, rel: t.rel }));
      else items = (await api.get('list', { dir: prefix }).catch(() => [])).filter(i => i.dir).map(i => ({ label: `${i.name}  (${i.count})`, rel: i.rel }));
      menu(c, items.length ? items.map(i => ({ label: i.label, do: () => openDir(i.rel) })) : [{ label: 'No subfolders', disabled: true }]);
    });
    return c;
  };
  const seg = (label, onclick, cls) => h('span', { class: 'addr-seg' + (cls ? ' ' + cls : ''), onclick }, label);
  box.append(h('span', { class: 'addr-ico', html: I.pics }));
  if (dir == null) {
    box.append(seg('Studio', null, 'last'));
    if (right) box.append(h('span', { class: 'addr-chev dim' }, '▸'), seg(right, null, 'last'));
  } else {
    box.append(seg('Scans', () => openDir('originals')), chev(''));
    const parts = dir.split('/').filter(Boolean);
    parts.forEach((p, i) => {
      const prefix = parts.slice(0, i + 1).join('/'), last = i === parts.length - 1 && !file;
      box.append(seg(i === 0 ? (TOP_NAMES[p] || p) : p, last ? null : () => openDir(prefix), last ? 'last' : ''), chev(prefix));
    });
    if (file) box.append(seg(file, null, 'last'));
  }
  const nb = (dirn, en, fn, tip) => h('div', { class: 'addr-nav' + (en ? '' : ' off'), title: tip, onclick: fn }, svg(dirn < 0 ? I.prev : I.next));
  return h('div', { class: 'addr' },
    h('div', { class: 'addr-navs' }, nb(-1, S.navBack.length, navBack, 'Back (⌘[)'), nb(1, S.navFwd.length, navFwd, 'Forward (⌘])')),
    box, right && dir != null ? h('span', { class: 'sub' }, right) : null);
}
const visibleItems = () => S.items.filter(i => !i.dir && (!S.filter || i.name.toLowerCase().includes(S.filter.toLowerCase())));
function selectAll() { visibleItems().forEach(i => S.sel.add(i.rel)); }

// cartella grande con dentro le prime scansioni, infilate tra il dorso e l'aletta
function folderTile(peek = []) {
  const pages = peek.slice(0, 2).map((rel, k) => {
    const x = k ? 31.5 : 29.5, y = k ? 11 : 13.5, rot = k ? 4 : -1.5;
    const src = `/api/thumb?${qs({ rel, size: 256 })}&v=${PREV_V}`.replace(/&/g, '&amp;');
    return `<g transform="rotate(${rot} ${x + 8.5} ${y + 12.5})"><rect x="${x}" y="${y}" width="17" height="25" fill="#fff" stroke="#bdb6a6" stroke-width=".5"/>`
      + `<image href="${src}" x="${x + 1}" y="${y + 1}" width="15" height="23" preserveAspectRatio="xMidYMid slice"/></g>`;
  }).reverse().join('');
  return I.folderBig.replace('<!--pages-->', pages).replace('class="ico"', 'width="96" height="96"');
}

function renderGallery() {
  const main = $('#main'); main.innerHTML = '';
  const items = visibleItems();
  const grid = h('div', { class: 'gallery', tabindex: 0 });
  const sub = S.items.filter(i => i.dir && (!S.filter || i.name.toLowerCase().includes(S.filter.toLowerCase())));
  // le cartelle come i file: un clic seleziona, doppio clic (o Invio) apre
  sub.forEach(c => grid.append(h('div', { class: 'thumb' + (S.selDir === c.rel ? ' sel' : ''), title: c.name, ondblclick: () => { S.selDir = null; openDir(c.rel); },
    onclick: () => { S.selDir = c.rel; S.sel.clear(); renderGallery(); renderSide(); renderCmdbar(); } },
    h('div', { class: 'pic', html: folderTile(c.peek) }), h('div', { class: 'cap' }, `${c.name} (${c.count})`))));
  if (!items.length && !sub.length) grid.append(h('div', { class: 'empty' }, S.items.length ? 'No scans match the search.' : 'This folder is empty.'));
  items.forEach((it, idx) => {
    const badges = [];
    if (it.done === 'ok') badges.push(h('span', { class: 'badge ok', title: 'Cut by the agent' }, 'cut'));
    if (it.done === 'studio') badges.push(h('span', { class: 'badge studio', title: 'Exported from the studio' }, 'studio'));
    if (it.done === 'failed' || S.dir.startsWith('failed')) badges.push(h('span', { class: 'badge fail' }, 'check'));
    if (it.sheets != null && !it.exported) badges.push(h('span', { class: 'badge edit', title: 'Edited, not exported yet' }, `${it.sheets} ✎`));
    const el = h('div', { class: 'thumb' + (S.sel.has(it.rel) ? ' sel' : ''), title: it.name,
      onclick: e => clickItem(e, it, idx, items), ondblclick: () => openScan(it.rel) },
      h('div', { class: 'badges' }, badges),
      h('div', { class: 'pic' }, h('img', { src: `/api/thumb?${qs({ rel: it.rel, size: 256 })}&m=${it.mtime}&v=${PREV_V}`, loading: 'lazy', draggable: 'false', style: /\.png$/i.test(it.name) ? { background: bgCss() } : null })),
      h('div', { class: 'cap' }, it.name));
    grid.append(el);
  });
  const t = S.tree.flatMap(n => [n, ...n.children]).find(n => n.rel === S.dir);
  main.append(addressBar(S.dir, null, `${items.length} item${items.length !== 1 ? 's' : ''}${S.sel.size ? `, ${S.sel.size} selected` : ''}`), grid);
}
function clickItem(e, it, idx, items) {
  if (e.shiftKey && S.anchor != null) {
    const a = items.findIndex(i => i.rel === S.anchor);
    const [lo, hi] = [Math.min(a, idx), Math.max(a, idx)];
    if (!e.metaKey) S.sel.clear();
    items.slice(lo, hi + 1).forEach(i => S.sel.add(i.rel));
  } else if (e.metaKey || e.ctrlKey) {
    S.sel.has(it.rel) ? S.sel.delete(it.rel) : S.sel.add(it.rel); S.anchor = it.rel;
  } else { S.sel = new Set([it.rel]); S.anchor = it.rel; }
  S.selDir = null;
  renderGallery(); renderSide(); renderCmdbar();
}

// ------------------------------------------------------------ pannello a destra
function renderSide() {
  const side = $('#side'); side.innerHTML = '';
  side.style.display = $('#split2').style.display = ['gallery', 'editor'].includes(S.view) ? '' : 'none';
  if (S.view === 'gallery') return sideGallery(side);
  if (S.view === 'editor') return sideEditor(side);
}
function group(title, ...kids) { return h('div', { class: 'group' }, h('div', { class: 'gh' }, title), ...kids); }
function engineChooser() {
  const box = h('div');
  for (const e of S.engines) {
    box.append(h('label', { class: 'radio' + (e.available ? '' : ' dis'), title: e.note },
      h('input', { type: 'radio', name: 'eng', checked: S.engine === e.id, disabled: !e.available, onchange: () => { S.engine = e.id; renderSide(); } }),
      h('div', {}, h('div', { class: 'rn' }, e.name), h('div', { class: 'rd' }, e.available ? e.note : (e.id === 'sam3' || e.id === 'vision' ? 'Not installed: see Add-ons.' : 'Not available.')))));
  }
  const e = S.engines.find(x => x.id === S.engine);
  for (const p of e?.params || []) {
    const v = S.params[p.id] ?? p.default;
    let inp;
    if (p.type === 'bool') inp = h('input', { type: 'checkbox', checked: !!v, onchange: ev => S.params[p.id] = ev.target.checked });
    else if (p.choices) {
      const free = p.id === 'prompt';      // la frase di SAM si puo' anche scrivere a mano
      inp = h('select', { class: 'f', onchange: ev => { if (ev.target.value === '__other') { samPromptDialog(); ev.target.value = v; } else { S.params[p.id] = ev.target.value; renderSide(); } } },
        p.choices.map(c => h('option', { value: c.text, selected: c.text === v, title: c.note }, c.text)),
        p.choices.some(c => c.text === v) ? null : h('option', { value: v, selected: true }, v),
        free ? h('option', { value: '__other' }, 'Other…') : null);
    } else inp = h('input', { type: p.type === 'number' ? 'number' : 'text', step: p.step, value: v, class: 'f', oninput: ev => S.params[p.id] = p.type === 'number' ? +ev.target.value : ev.target.value });
    box.append(h('div', { class: 'row' }, h('label', {}, p.label), inp, p.hint ? info(p.hint) : null));
    const ch = p.choices?.find(c => c.text === v);
    if (ch) box.append(h('div', { class: 'small muted', style: { margin: '-2px 0 4px 76px' } }, ch.note));
  }
  return box;
}
function samParams() {
  const e = S.engines.find(x => x.id === 'sam3'); const o = {};
  for (const p of e?.params || []) o[p.id] = S.params[p.id] ?? p.default;
  return o;
}
const samChoices = () => (S.engines.find(e => e.id === 'sam3')?.params || []).find(p => p.id === 'prompt')?.choices || [];
const samHint = id => (S.engines.find(e => e.id === 'sam3')?.params || []).find(p => p.id === id)?.hint;
function samPromptDialog() {
  const p = samParams();
  const f = {
    prompt: h('input', { type: 'text', value: p.prompt, list: 'samlist' }),
    threshold: h('input', { type: 'number', step: 0.05, min: 0.05, max: 0.95, value: p.threshold }),
    hires: h('input', { type: 'checkbox', checked: p.hires }),
    refine: h('input', { type: 'checkbox', checked: p.refine }),
  };
  const row = (l, el, hint, tip) => h('div', { class: 'row', style: { alignItems: 'flex-start' } }, h('label', { style: { width: '130px', paddingTop: '3px' } }, l), h('div', { class: 'f' }, el, hint ? h('div', { class: 'small muted' }, hint) : null), tip ? info(tip) : null);
  dialog('SAM 3', 'What should SAM 3 look for?', h('div', { style: { width: '520px' } },
    h('datalist', { id: 'samlist' }, samChoices().map(c => h('option', { value: c.text }, c.note))),
    h('div', { class: 'small muted', style: { margin: '0 0 8px' } }, 'Tested on your kind of scans:'),
    h('div', { class: 'chips' }, samChoices().map(c => h('span', { class: 'chip', title: c.note, onclick: () => { f.prompt.value = c.text; } }, c.text))),
    row('Prompt', f.prompt, null, samHint('prompt')),
    row('Score', f.threshold, null, samHint('threshold')),
    row('Second pass', f.hires, null, samHint('hires')),
    row('Edge from real pixels', f.refine, null, samHint('refine'))),
    [['OK', () => { S.params.prompt = f.prompt.value.trim() || 'sheet of paper'; S.params.threshold = +f.threshold.value || 0.4; S.params.hires = f.hires.checked; S.params.refine = f.refine.checked; renderSide(); renderCmdbar(); }, true], ['Cancel', () => true]]);
}
const engParams = () => { const e = S.engines.find(x => x.id === S.engine); const o = {}; for (const p of e?.params || []) o[p.id] = S.params[p.id] ?? p.default; return o; };

function sideGallery(side) {
  const sel = S.items.filter(i => S.sel.has(i.rel));
  if (sel.length === 1) {
    const it = sel[0];
    side.append(group('Info',
      h('div', { style: { textAlign: 'center', margin: '4px 0 8px' } }, h('img', { src: `/api/thumb?${qs({ rel: it.rel, size: 256 })}&m=${it.mtime}&v=${PREV_V}`, style: { maxWidth: '100%', maxHeight: '220px', boxShadow: '0 1px 4px rgba(0,0,0,.35)' } })),
      h('div', { class: 'row' }, h('label', {}, 'Name'), h('div', { class: 'f' }, it.name)),
      h('div', { class: 'row' }, h('label', {}, 'Size'), h('div', { class: 'f' }, fmtSize(it.size))),
      h('div', { class: 'row' }, h('label', {}, 'Date'), h('div', { class: 'f' }, new Date(it.mtime * 1000).toLocaleString())),
      h('div', { class: 'row' }, h('label', {}, 'Status'), h('div', { class: 'f' }, it.done ? (it.done === 'ok' ? 'Cut by the agent' : it.done === 'studio' ? 'Exported from the studio' : 'Failed, needs a look') : 'Not cut yet')),
      h('div', { class: 'btns' }, h('button', { class: 'btn default', onclick: () => openScan(it.rel) }, 'Open'), h('button', { class: 'btn', onclick: () => api.post('open', { what: 'finder', rel: it.rel }) }, 'Show in Finder'))));
  } else {
    side.append(group('Folder', h('div', { class: 'muted' }, sel.length ? `${sel.length} scans selected.` : 'Select scans (⌘-click, ⇧-click) to run a batch, or double-click one to open it.')));
  }
  const inCut = S.dir.startsWith('cut'), inFail = S.dir.startsWith('failed');
  if (inCut) side.append(group('Cutouts',
    h('div', { class: 'btns' },
      h('button', { class: 'btn small', disabled: !sel.length, title: 'Rotate left, lossless', onclick: () => cutoutAction('rotate', sel, -90) }, '⟲ 90°'),
      h('button', { class: 'btn small', disabled: !sel.length, title: 'Rotate right, lossless', onclick: () => cutoutAction('rotate', sel, 90) }, '⟳ 90°'),
      h('button', { class: 'btn small', disabled: !sel.length, onclick: () => cutoutAction('ocr', sel) }, 'Text (OCR)'),
      h('button', { class: 'btn small', disabled: sel.length < 2, title: 'One TIFF with a page per selected cutout, in name order', onclick: () => cutoutAction('merge', sel) }, 'Merge into multipage TIFF'),
      h('button', { class: 'btn small', disabled: !sel.length, onclick: () => cutoutAction('trash', sel) }, 'Move to Trash'),
      info('Rotation moves pixels, never resamples; the previous file is kept in studio-data/replaced and the metadata (true size) is carried over. Text (OCR): Apple Vision reads any writing on the cutout and stores it in the file description (XMP, IPTC, EXIF), pixels untouched. Trash: the Mac Trash, so you can put files back.')),
    h('div', { class: 'small muted', style: { marginTop: '4px' } }, sel.length ? `${sel.length} selected` : 'Select cutouts (⌘-click, ⇧-click, ⌘A).')));
  if (inFail) side.append(group('To check',
    h('div', { class: 'small muted' }, 'Scans land here when the agent could not cut them, or Apple Vision cut them with an odd shape. Open one, fix it, export; then mark it checked.'),
    h('div', { class: 'btns' }, h('button', { class: 'btn default', disabled: !sel.length, onclick: () => markChecked(sel.map(i => i.rel)) }, '✓ Mark as checked'),
      info('Removes it from To check. The scan itself stays in originals/; nothing is deleted.'))));
  side.append(group('Engine', engineChooser()),
    group('Batch',
      h('div', { class: 'btns' },
        h('button', { class: 'btn', disabled: !sel.length, onclick: () => batch(false) }, 'Detect'),
        h('button', { class: 'btn default', disabled: !sel.length, onclick: () => batch(true) }, 'Detect + export'),
        h('button', { class: 'btn', disabled: !sel.some(i => i.sheets), onclick: () => exportMany(sel.filter(i => i.sheets).map(i => i.rel)) }, 'Export edited')),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Batches run in the background; see Jobs. Existing cutouts are never overwritten: changed ones are moved to studio-data/replaced.')));
}

let histData = null, histKey = '';
async function loadHist(hc, sel) {
  const key = `${S.rel}|${sel?.id || ''}|${S.st?.version || 0}`;
  if (key !== histKey) {
    histKey = key; histData = null;
    histData = await api.get('histogram', { rel: S.rel, ...(sel ? { id: sel.id } : {}) }).catch(() => null);
  }
  drawHist(hc);
}
function drawHist(hc) {
  const c = hc.getContext('2d'), W = hc.width, H = hc.height;
  c.clearRect(0, 0, W, H); c.fillStyle = '#fff'; c.fillRect(0, 0, W, H);
  if (!histData) return;
  const f = v => S.histLog ? Math.log1p(v) : v;
  const mx = Math.max(...['l', 'r', 'g', 'b'].map(k => Math.max(...histData[k].slice(1, 255).map(f))));
  const path = (arr, close) => { c.beginPath(); c.moveTo(0, H); arr.forEach((v, i) => c.lineTo(i / 255 * W, H - 6 - f(v) / mx * (H - 12))); if (close) { c.lineTo(W, H); c.closePath(); } };
  path(histData.l, true); c.fillStyle = 'rgba(80,90,105,.35)'; c.fill();
  [['r', 'rgba(220,40,40,.8)'], ['g', 'rgba(30,160,60,.8)'], ['b', 'rgba(40,90,220,.8)']].forEach(([k, col]) => { path(histData[k]); c.strokeStyle = col; c.lineWidth = 1.5; c.stroke(); });
  const x = histData.bg_l / 255 * W; c.setLineDash([5, 4]); c.strokeStyle = '#b07d16'; c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke(); c.setLineDash([]);
  c.fillStyle = '#555'; c.font = '20px "Segoe UI", Tahoma'; c.fillText(S.histLog ? 'log' : 'linear', W - 70, 24);
}
async function cutoutAction(action, items, deg) {
  const rels = items.map(i => i.rel).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  if (action === 'trash') {
    const ok = await choose('Move to Trash', `Move ${rels.length} cutout(s) to the Trash?`, rels.map(r => r.split('/').pop()).join(', ') + '. You can put them back from the Trash.', [['yes', 'Move to Trash', true], [null, 'Cancel']]);
    if (!ok) return;
  }
  status({ rotate: 'Rotating…', ocr: 'Reading text…', trash: 'Moving to Trash…', merge: 'Merging…' }[action], true);
  try {
    const r = await api.post('cutouts', { action, rels, deg });
    if (action === 'ocr') alertDialog('Text found', h('pre', { class: 'log' }, r.done.map(d => `${d.rel.split('/').pop()}:\n${d.text || '(no text)'}\n`).join('\n')));
    status(action === 'merge' ? `Merged into ${r.done[0]}` : `${r.done.length} cutout(s) ${{ rotate: 'rotated', ocr: 'read', trash: 'moved to the Trash' }[action]}`);
  } catch (e) { alertDialog('Cutouts', e.message); }
  S.sel.clear(); await refreshItems(); renderSide();
}
async function rotateOpenFile(deg) {
  await flushSave();
  status('Rotating…', true);
  try { await api.post('cutouts', { action: 'rotate', rels: [S.rel], deg }); status(`Rotated ${deg > 0 ? 'right' : 'left'} 90°`); openScan(S.rel); }
  catch (e) { alertDialog('Rotate', e.message); }
}
async function markChecked(rels) {
  const r = await api.post('checked', { rels });
  status(`${r.done.length} scan(s) marked as checked`);
  S.sel.clear(); await refreshItems(); const t = await api.get('tree'); S.tree = t.tree; renderNav(); renderSide();
}
function sheetEdited(s) { return s.ops.length || JSON.stringify(s.poly) !== JSON.stringify(s.poly0); }
function sideEditor(side) {
  if (!S.info) return;
  const st = S.st;
  side.append(group('Engine', engineChooser(), h('div', { class: 'btns' },
    h('button', { class: 'btn default', onclick: detect }, 'Detect'),
    h('button', { class: 'btn', onclick: toggleCompare }, S.compare ? 'Hide compare' : 'Compare'))));
  if (S.compare) {
    side.append(group('Compare', ...Object.entries(S.compare).map(([e, r]) => h('div', { class: 'row' },
      h('span', { class: 'dot', style: { width: '12px', height: '3px', background: CMP_COLORS[e] || '#888' } }),
      h('div', { class: 'f' }, engName(e), h('span', { class: 'muted small' }, r.error ? ' — ' + r.error : ` — ${r.polys.length} sheet(s), ${r.seconds}s`)),
      r.error ? null : h('button', { class: 'btn small', onclick: () => { S.engine = e; detect(); } }, 'Use')))));
  }
  const list = h('div');
  (st?.sheets || []).forEach((s, i) => {
    const name = S.names[s.id];
    list.append(h('div', { class: 'sheet' + (isSel(s.id) ? ' sel' : ''), oncontextmenu: e => { e.preventDefault(); soloSheet(s.id); }, onclick: e => {
      if (e.altKey) { soloSheet(s.id); renderSide(); draw(); return; }
      if (e.metaKey) toggleSel(s.id);
      else if (e.shiftKey && S._primary) { const ids = st.sheets.map(x => x.id), a = ids.indexOf(S._primary), b = ids.indexOf(s.id); selectIds(ids.slice(Math.min(a, b), Math.max(a, b) + 1), true); S._primary = s.id; }
      else S.selSheet = s.id;
      renderSide(); draw();
    } },
      h('input', { type: 'checkbox', checked: s.on !== false, title: 'Export this sheet · ⌃-click or ⌥-click: only this one',
        onclick: e => { e.stopPropagation(); if (e.ctrlKey) e.preventDefault(); else if (e.altKey) { e.preventDefault(); soloSheet(s.id); } },
        oncontextmenu: e => { e.preventDefault(); e.stopPropagation(); soloSheet(s.id); },
        onchange: e => commit(() => { s.on = e.target.checked; }) }),
      h('span', { class: 'dot', style: { background: COLORS[i % COLORS.length] } }),
      h('div', { class: 'nm', title: name || '' }, (name ? name.split('/').pop() : 'not exported') , h('small', {}, `${s.engine || 'manual'}${sheetEdited(s) ? ' · edited' : ''}${s.holes?.length ? ` · ${s.holes.length} hole(s)` : ''}${s.rot ? ` · ⟳ ${s.rot}°` : ''}${s.ocr ? ' · text' : ''}`)),
      h('div', {}, h('button', { class: 'btn small', title: 'Preview the cutout', onclick: e => { e.stopPropagation(); cutoutDialog(s); } }, '👁'))));
  });
  if (!st?.sheets.length) list.append(h('div', { class: 'muted' }, 'No sheets yet. Press Detect, or draw one with the polygon or box tool.'));
  const many = selSheets();
  const sel = many.length > 1 ? null : st?.sheets.find(s => s.id === S.selSheet);
  if (many.length > 1) list.append(h('div', { class: 'multi' },
    h('div', { class: 'mh' }, `${many.length} sheets selected`),
    h('div', { class: 'btns' },
      h('button', { class: 'btn small', title: 'Rotate 90° left, lossless', onclick: () => rotateSheets(many, -90) }, '⟲ 90°'),
      h('button', { class: 'btn small', title: 'Rotate 90° right, lossless', onclick: () => rotateSheets(many, 90) }, '⟳ 90°'),
      h('button', { class: 'btn small', onclick: () => commit(() => many.forEach(x => x.on = true)) }, 'Export on'),
      h('button', { class: 'btn small', onclick: () => commit(() => many.forEach(x => x.on = false)) }, 'Export off'),
      h('button', { class: 'btn small', title: 'Make one sheet out of these (each keeps its exact edge)', onclick: mergeSelected }, 'Merge into one'),
      h('button', { class: 'btn small', disabled: !many.some(x => sheetEdited(x) && x.poly0), onclick: () => commit(() => many.forEach(x => { if (x.poly0) { x.poly = JSON.parse(JSON.stringify(x.poly0)); x.ops = []; } })) }, 'Undo their edits'),
      h('button', { class: 'btn small', onclick: () => ocrSheets(many) }, 'Text (OCR)'),
      h('button', { class: 'btn small', onclick: deleteSelected }, 'Delete')),
    h('div', { class: 'row' }, h('label', {}, 'Label all'), h('input', { type: 'text', class: 'f', placeholder: 'same label on each', onchange: e => commit(() => many.forEach(x => x.label = e.target.value)) })),
    h('div', { class: 'small muted' }, 'Lasso, rectangle, wand and brush in Cut mode act on all of them. ⌘-click toggles, ⇧-click adds a range, drag on empty space to box-select, ⌘A selects all. ⌃-click (or ⌥-click) one sheet: only that one is exported.')));
  side.append(group('Sheets', list, sel ? h('div', { style: { marginTop: '6px' } },
    h('div', { class: 'row' }, h('label', {}, 'Label'), h('input', { type: 'text', class: 'f', value: sel.label || '', placeholder: 'used by {label} in names',
      onchange: e => commit(() => { sel.label = e.target.value; }) })),
    h('div', { class: 'btns' },
      h('button', { class: 'btn small', title: 'Rotate 90° left, lossless', onclick: () => rotateSheets([sel], -90) }, '⟲ 90°'),
      h('button', { class: 'btn small', title: 'Rotate 90° right, lossless', onclick: () => rotateSheets([sel], 90) }, '⟳ 90°'),
      info('Turns the cutout by 90° at export: pixels are moved, never resampled, so nothing is lost.'),
      h('button', { class: 'btn small', disabled: !sheetEdited(sel) || !sel.poly0, onclick: () => commit(() => { sel.poly = JSON.parse(JSON.stringify(sel.poly0)); sel.ops = []; }) }, 'Undo all edits'),
      h('button', { class: 'btn small', onclick: () => ocrSheets([sel]) }, 'Text (OCR)'),
      h('button', { class: 'btn small', onclick: deleteSelected }, 'Delete')),
    sel.ocr !== undefined ? h('div', { style: { marginTop: '6px' } },
      h('div', { class: 'small muted' }, 'Text found (edit if needed; saved in the file description at export):'),
      h('textarea', { rows: Math.min(8, Math.max(2, (sel.ocr || '').split('\n').length + 1)), style: { width: '100%' }, placeholder: '(no text found)',
        onchange: e => commit(() => { sel.ocr = e.target.value; }) }, sel.ocr || '')) : null) : null,
    (st?.history || []).length ? h('div', { class: 'row', style: { marginTop: '6px' } }, h('label', {}, 'Earlier'),
      h('select', { class: 'f', onchange: e => { if (e.target.value !== '') restoreVersion(+e.target.value); } },
        h('option', { value: '' }, `${st.history.length} earlier version(s)…`),
        st.history.map((v, i) => h('option', { value: i }, `${new Date(v.time * 1000).toLocaleString()} · ${v.engine || 'manual'} · ${v.sheets.length} sheet(s)`))),
      info('Every time Detect replaces the sheets, the previous ones are kept here (the last 15). Sheets you made by hand are never replaced by Detect.')) : null));
  side.append(group('Save',
    h('div', { class: 'small muted' }, 'Names follow the template in Settings: ', h('code', {}, S.settings.template), ' ', info(TIPS.template)),
    h('div', { class: 'small muted' }, `Format: ${S.settings.export_format === 'jxl' ? 'JPEG XL lossless' : 'PNG'} · a different cutout with a name already taken ${S.settings.export_existing === 'replace' ? 'replaces it (old one kept in studio-data/replaced)' : 'gets a new number, the old one stays'}. Change in Settings.`),
    h('div', { class: 'btns' },
      h('button', { class: 'btn default', disabled: !st?.sheets.some(s => s.on !== false), onclick: () => doExport() }, 'Export'),
      h('button', { class: 'btn', disabled: !st?.sheets.some(s => s.on !== false), title: 'The same cutouts in a subfolder, e.g. to keep an odd but interesting cut next to the normal one', onclick: () => doExport(S.settings.export_subfolder || 'extra') }, `To ${S.settings.export_subfolder || 'extra'}/`),
      h('button', { class: 'btn', onclick: () => api.post('open', { what: 'finder', rel: S.rel }) }, 'Original in Finder'),
      S.rel.startsWith('failed/') ? h('button', { class: 'btn', onclick: () => markChecked([S.rel]) }, '✓ Checked') : null),
    // un ritaglio gia' salvato aperto qui: girare il file stesso (senza perdita)
    S.rel.startsWith('cut/') && /\.(png|jxl)$/i.test(S.rel) ? h('div', { class: 'row', style: { marginTop: '6px' } }, h('label', {}, 'This file'),
      h('button', { class: 'btn small', title: 'Rotate this cutout file left, lossless', onclick: () => rotateOpenFile(-90) }, '⟲ 90°'),
      h('button', { class: 'btn small', title: 'Rotate this cutout file right, lossless', onclick: () => rotateOpenFile(90) }, '⟳ 90°'),
      info('Rotates the saved file itself (pixels moved, never resampled). The previous version is kept in studio-data/replaced; metadata and true size carry over.')) : null,
    st?.exported ? h('div', { class: 'small', style: { marginTop: '6px', color: '#2d7a2d' } }, '✓ Exported ' + new Date(st.exported * 1000).toLocaleString()) : null));
  const hc = h('canvas', { class: 'hist', width: 540, height: 180, title: 'Click: linear / log scale', onclick: () => { S.histLog = !S.histLog; drawHist(hc); } });
  side.append(group(h('span', {}, 'Histogram' + (sel ? ' — selected sheet' : ' — whole scan'), ' ', info(TIPS.hist)), hc, h('div', { class: 'small muted' }, 'Read-only. Grey: lightness; lines: R G B; dashed: the lid colour the cut found.')));
  loadHist(hc, sel);
  side.append(group('Scan', h('div', { class: 'small muted' }, `${S.info.w} × ${S.info.h} px · ${S.info.dpi} dpi · ${S.info.mm[0]} × ${S.info.mm[1]} mm`)));
}

// ------------------------------------------------------------ barra in basso
function renderNavbar() {
  const nb = $('#navbar'); nb.innerHTML = '';
  const ed = S.view === 'editor';
  const btn = (icon, title, fn) => h('div', { class: 'nb', title, onclick: fn }, svg(icon));
  nb.append(
    h('div', { class: 'left' }, h('span', { class: 'status', id: 'status' }, ''), h('div', { class: 'progress', id: 'jobbar', style: { width: '90px', display: 'none' } }, h('i', { style: { width: '0%' } }))),
    h('div', { class: 'pair' }, btn(I.prev, 'Previous scan (←)', () => step(-1)), btn(I.next, 'Next scan (→)', () => step(1))),
    h('div', { class: 'orb', title: ed ? 'Export the cutouts (⌘S)' : 'Open the selected scan', onclick: () => ed ? doExport() : S.sel.size && openScan([...S.sel][0]) }, svg(ed ? I.orb_cut : I.orb_open)),
    h('div', { class: 'pair' }, btn(I.undo, 'Undo (⌘Z)', undo), btn(I.redo, 'Redo (⇧⌘Z)', redo)),
    ed ? h('div', { class: 'right' }, btn(I.zout, 'Zoom out (−)', () => zoomBy(1 / 1.4)),
      h('input', { type: 'range', class: 'zoom', id: 'zoom', min: -60, max: 60, value: 0, oninput: e => zoomTo(e.target.value) }),
      btn(I.zin, 'Zoom in (+)', () => zoomBy(1.4)), btn(I.fit, 'Fit (⌘0) · actual pixels (⌘1)', fit)) : '',
  );
  updateJobBar();
}
let statusTimer;
function status(msg, sticky) { const el = $('#status'); if (!el) return; el.textContent = msg; clearTimeout(statusTimer); if (!sticky) statusTimer = setTimeout(() => el.textContent = '', 6000); }
function step(d) {
  const items = visibleItems(); if (!items.length) return;
  const cur = S.view === 'editor' ? S.rel : (S.anchor || null);
  let i = items.findIndex(x => x.rel === cur); i = Math.max(0, Math.min(items.length - 1, (i < 0 ? 0 : i + d)));
  if (S.view === 'editor') openScan(items[i].rel); else { S.sel = new Set([items[i].rel]); S.anchor = items[i].rel; renderGallery(); renderSide(); }
}

// ------------------------------------------------------------ editor
const V = { s: 1, ox: 0, oy: 0, img: null, pScale: 1, tile: null, mtile: null, dpr: 1, cw: 0, ch: 0 };
let cv, ctx, hud, busyEl;

async function openScan(rel) {
  if (S.view === 'editor' && S.rel !== rel) await flushSave();
  remember('scan:' + rel);
  useRemembered(rel);
  S.rel = rel; S.selSheet = null; S.compare = null; S.hist = []; S.fut = []; V.tile = V.mtile = null;
  const parts = rel.split('/'); if (parts.length >= 2) S.dir = parts.slice(0, -1).join('/');
  S.view = 'editor';
  renderCmdbar(); renderNav(); renderNavbar();
  const main = $('#main'); main.innerHTML = '';
  const tools = [['select', I.t_select, 'Select (V)'], ['hand', I.t_hand, 'Pan (H, or hold Space)'], ['points', I.t_points, 'Edit points (A): drag; double-click an edge adds, ⌥-click removes'],
    ['poly', I.t_poly, 'New sheet by polygon (P): click points, Enter to close'], ['rect', I.t_rect, 'Rectangle (M): add or cut a rectangle'], ['lasso', I.t_lasso_add, 'Lasso (L; K = lasso in Cut mode)'],
    ['wand', I.t_wand, 'Magic Wand (W): click a colour to select it, like Photoshop. Options appear in the bar above the scan'], ['brush', I.t_brush_add, 'Brush (B; E = eraser)'], ['box', I.t_box, 'Detect inside a box (R) with the chosen engine'],
    ['sam', I.t_sam, 'SAM 3 (S): click the object the prompt names (⌥-click excludes), or drag a box. Enter starts a new object.']];
  const tb = h('div', { class: 'toolbox' }, tools.map(([id, ic, tip]) => h('div', { class: 'tool' + (S.tool === id ? ' on' : ''), 'data-tool': id, title: tip, onclick: () => setTool(id) }, svg(ic))),
    h('hr'),
    h('label', { class: 'opt', title: 'Darken what will be cut away (O)' }, h('input', { type: 'checkbox', id: 'cutview', checked: S.showCut, onchange: e => { S.showCut = e.target.checked; requestTile(); draw(); } }), h('br'), 'Cut view ', info(TIPS.cutview)));
  const optbar = h('div', { class: 'optbar', id: 'optbar' });
  const stage = h('div', { class: 'stage bg-' + S.bg });
  cv = h('canvas'); hud = h('div', { class: 'hud' }); busyEl = h('div', { class: 'busy' }, h('div', { style: { width: '220px', background: '#fff', padding: '12px', border: '1px solid #9bb', borderRadius: '4px', boxShadow: '0 3px 12px rgba(0,0,0,.25)' } }, h('div', { id: 'busymsg', style: { marginBottom: '6px' } }, 'Working…'), h('div', { class: 'progress marquee' }, h('i'))));
  const loupe = h('canvas', { class: 'loupe', id: 'loupe', width: 360, height: 360 });
  const dens = h('div', { class: 'dens', id: 'dens' });
  // come le finestrelle di Vista: un clic sulla barra del titolo la chiude e la riapre
  dens.addEventListener('click', e => { if (!e.target.closest('.dh')) return; S.densShut = !S.densShut; store('densshut', S.densShut ? '1' : ''); dens.classList.toggle('collapsed', S.densShut); const t = dens.querySelector('.dtog'); if (t) t.textContent = S.densShut ? '▾' : '▴'; if (measAt) measure(measAt.pt, measAt.sx, measAt.sy); });
  stage.append(cv, hud, dens, loupe, busyEl);
  main.append(addressBar(parts.slice(0, -1).join('/'), parts.at(-1)), optbar, h('div', { class: 'editor' }, tb, stage));
  renderOptions();
  ctx = cv.getContext('2d');
  bindCanvas(stage);
  new ResizeObserver(() => { resize(); draw(); }).observe(stage);
  $('#title').textContent = `${parts.at(-1)} - Scan Studio`;
  try {
    const [info, st] = await Promise.all([api.get('info', { rel }), api.get('state', { rel })]);
    if (S.rel !== rel) return;
    S.info = info; setState(st);
    const im = new Image(); im.src = `/api/preview?${qs({ rel })}&v=${PREV_V}`; await im.decode();
    if (S.rel !== rel) return;
    V.img = im; V.pScale = im.naturalWidth / info.w;
    resize(); fit(); renderSide(); renderCmdbar();
    // alla prima apertura solo il taglio automatico (veloce); SAM e gli altri motori solo con Detect
    if (!st.sheets.length) status('No sheets yet: choose an engine and press Detect (or draw one).');
  } catch (e) {
    // il file non c'e' piu' (spostato dall'agente o cancellato): si torna alla cartella
    if (S.rel !== rel) return;
    const gone = /No such file|not found|FileNotFound/i.test(e.message);
    S.rel = null; S.info = null; S.st = null; $('#title').textContent = 'Scan Studio';
    await openDir(S.dir || 'originals');
    alertDialog(gone ? 'This scan is no longer there' : 'Could not open this scan',
      gone ? `${parts.at(-1)} was moved or deleted (the agent moves new scans from the inbox to originals/). The folder has been refreshed.` : e.message);
  }
}
function leaveEditor() { flushSave(); $('#title').textContent = 'Scan Studio'; }
function setState(st) { S.names = st.names || {}; delete st.names; S.st = st; }
const MODE_NAMES = { new: 'New selection', add: 'Add', sub: 'Subtract', int: 'Intersect' };
// le icone dei modi come in Photoshop: un quadrato, due uniti, uno meno l'altro, la parte comune
const MODE_ICONS = {
  new: '<svg viewBox="0 0 22 16"><rect x="5" y="2.5" width="12" height="11" fill="#cfe6fb" stroke="#24548a"/></svg>',
  add: '<svg viewBox="0 0 22 16"><path d="M2.5 2.5h9v4h8v8h-9v-4h-8z" fill="#b9e6b4" stroke="#1d6b2a"/></svg>',
  sub: '<svg viewBox="0 0 22 16"><path d="M2.5 2.5h9v4h-1v4h-8z" fill="#cfe6fb" stroke="#24548a"/><rect x="10.5" y="6.5" width="9" height="8" fill="#fff" stroke="#b03030" stroke-dasharray="2 1.2"/></svg>',
  int: '<svg viewBox="0 0 22 16"><rect x="2.5" y="2.5" width="9" height="8" fill="#fff" stroke="#6b52c9" stroke-dasharray="2 1.2"/><rect x="10.5" y="6.5" width="9" height="8" fill="#fff" stroke="#6b52c9" stroke-dasharray="2 1.2"/><rect x="10.5" y="6.5" width="1" height="4" fill="#c9bdf5" stroke="#3b2a99"/></svg>',
};
const MODE_HINTS = {
  new: 'makes a new, separate sheet from what you select (e.g. only the ink: turn Contiguous off and click a black line)',
  add: 'adds what you select to the sheet',
  sub: 'cuts what you select away from the sheet',
  int: 'keeps only the part of the sheet that is also in your selection (e.g. only the ink inside this page)',
};
function setMode(m) { S.mode = m; renderOptions(); }
function modeGroup() {
  return h('div', { class: 'og' }, h('span', { class: 'ol' }, 'Mode'),
    h('div', { class: 'segs' }, ['new', 'add', 'sub', 'int'].map(m => h('div', { class: 'seg' + (S.mode === m ? ' on' : ''), title: MODE_NAMES[m] + ': ' + MODE_HINTS[m] + ({ add: ' (hold ⇧)', sub: ' (hold ⌥)', int: ' (hold ⇧⌥)' }[m] || ''), onclick: () => setMode(m) },
      svg(MODE_ICONS[m]), h('span', {}, MODE_NAMES[m])))));
}
function numSlider(label, val, min, max, step, unit, onv, tip) {
  const num = h('input', { type: 'number', class: 'onum', min, max, step, value: val });
  const rng = h('input', { type: 'range', class: 'orng', min, max, step, value: val });
  rng.oninput = () => { num.value = rng.value; onv(+rng.value); };
  num.onchange = () => { const v = Math.max(min, Math.min(max, +num.value || min)); num.value = v; rng.value = v; onv(v); };
  return h('div', { class: 'og' }, h('span', { class: 'ol' }, label), rng, num, unit ? h('span', { class: 'ou' }, unit) : null, tip ? info(tip) : null);
}
const TOOL_TITLES = { select: 'Select', hand: 'Pan', points: 'Edit points', poly: 'Polygon', rect: 'Rectangle selection', lasso: 'Lasso selection', wand: 'Magic Wand', brush: 'Brush', box: 'Detect in a box', sam: 'SAM 3' };
function renderOptions() {
  const bar = $('#optbar'); if (!bar) return;
  bar.innerHTML = '';
  const t = S.tool;
  const hint = txt => h('div', { class: 'ohint' }, txt);
  const icon = (S.tool && I['t_' + (t === 'lasso' ? 'lasso_add' : t === 'brush' ? 'brush_add' : t)]) || '';
  bar.append(h('div', { class: 'otool' }, svg(icon), h('b', {}, TOOL_TITLES[t] || t)));
  if (t === 'wand') {
    bar.append(modeGroup(),
      numSlider('Tolerance', S.wandTol, 1, 120, 1, '', v => { S.wandTol = v; }, TIPS.wand),
      h('label', { class: 'og' }, h('input', { type: 'checkbox', checked: S.wandContig, onchange: e => { S.wandContig = e.target.checked; renderOptions(); } }), ' Contiguous', info(TIPS.contig)),
      hint(`Click a colour on the scan. ${MODE_NAMES[S.mode]} ${MODE_HINTS[S.mode]}.${S.wandContig ? '' : ' Contiguous is off: every pixel of that colour on the whole scan.'}`));
  } else if (t === 'lasso' || t === 'rect') {
    bar.append(modeGroup(), hint(`${t === 'rect' ? 'Drag a rectangle' : 'Drag around an area'}. ${MODE_NAMES[S.mode]} ${MODE_HINTS[S.mode]}.`));
  } else if (t === 'brush') {
    bar.append(h('div', { class: 'og' }, h('span', { class: 'ol' }, 'Paint'),
        h('div', { class: 'segs' }, [['add', 'Add'], ['sub', 'Erase']].map(([m, l]) => h('div', { class: 'seg' + ((S.mode === m || (m === 'add' && S.mode !== 'sub')) ? ' on' : ''), onclick: () => setMode(m) }, svg(MODE_ICONS[m]), h('span', {}, l))))),
      numSlider('Size', S.brushMM, 0.2, 20, 0.1, 'mm', v => { S.brushMM = v; draw(); }, TIPS.brush),
      hint(S.mode === 'sub' ? 'Paint over what should become transparent.' : 'Paint over paper the cut missed. [ and ] change the size.'));
  } else if (t === 'select') bar.append(hint('Click a sheet to select it. ⇧ or ⌘ click adds more; drag on empty space to select with a box; ⌃-click: export only that one; Delete removes.'));
  else if (t === 'hand') bar.append(hint('Drag to move around. Also: hold Space with any tool, or scroll with two fingers.'));
  else if (t === 'points') bar.append(hint('Drag the points of the selected sheet. Double-click an edge to add a point, ⌥-click a point to remove it.'));
  else if (t === 'poly') bar.append(hint('Click the corners of a new sheet; Enter (or double-click) closes it, Esc cancels.'));
  else if (t === 'box') bar.append(h('div', { class: 'og' }, h('span', { class: 'ol' }, 'Engine'), h('b', {}, engName(S.engine))), hint('Drag a box: the chosen engine looks for sheets only inside it, and adds them.'));
  else if (t === 'sam') bar.append(h('div', { class: 'og' }, h('span', { class: 'ol' }, 'Prompt'), h('b', {}, '“' + samParams().prompt + '”'), h('button', { class: 'btn small', onclick: samPromptDialog }, 'Change…')),
      hint('Click the object SAM 3 should pick (⌥-click excludes one), or drag a box to search inside it. Enter starts a new object.'));
}
function setBg(b) { S.bg = b; store('bg', b); const st = $('.stage'); if (st) st.className = 'stage bg-' + b; renderCmdbar(); if (S.view === 'gallery') renderGallery(); draw(); }
function setTool(t) { S.tool = t; S.poly = null; S.sam = null; renderOptions(); $$('.toolbox .tool').forEach(el => el.classList.toggle('on', el.dataset.tool === t)); cv && (cv.style.cursor = cursorFor(t)); draw(); }
const cursorFor = t => ({ hand: 'grab', select: 'default', points: 'default', box: 'crosshair', poly: 'crosshair', rect: 'crosshair', lasso: 'crosshair', wand: 'crosshair', brush: 'none', sam: 'crosshair' })[t];

function resize() {
  const r = cv.parentElement.getBoundingClientRect();
  V.dpr = window.devicePixelRatio || 1; V.cw = r.width; V.ch = r.height;
  cv.width = Math.round(r.width * V.dpr); cv.height = Math.round(r.height * V.dpr);
}
function fit() {
  if (!S.info) return;
  const m = 24, s = Math.min((V.cw - 2 * m) / S.info.w, (V.ch - 2 * m) / S.info.h);
  V.s = s; V.ox = (V.cw - S.info.w * s) / 2; V.oy = (V.ch - S.info.h * s) / 2; viewChanged();
}
function zoomAt(f, sx, sy) {
  const ns = Math.max(0.01, Math.min(16, V.s * f)); f = ns / V.s;
  V.ox = sx - (sx - V.ox) * f; V.oy = sy - (sy - V.oy) * f; V.s = ns; viewChanged();
}
const zoomBy = f => zoomAt(f, V.cw / 2, V.ch / 2);
function zoomTo(v) { const fitS = Math.min((V.cw - 48) / S.info.w, (V.ch - 48) / S.info.h); zoomAt(fitS * Math.pow(2, v / 10) / V.s, V.cw / 2, V.ch / 2); }
function actual() { zoomAt(1 / V.dpr / V.s, V.cw / 2, V.ch / 2); }
function viewChanged() {
  const z = $('#zoom'); if (z && S.info) { const fitS = Math.min((V.cw - 48) / S.info.w, (V.ch - 48) / S.info.h); z.value = Math.round(10 * Math.log2(V.s / fitS)); }
  requestTile(); draw();
}
const toImg = (sx, sy) => [(sx - V.ox) / V.s, (sy - V.oy) / V.s];
const toScr = (x, y) => [x * V.s + V.ox, y * V.s + V.oy];

// pezzi a piena risoluzione quando l'anteprima non basta (zoom sui bordi)
let tileTimer, tileSeq = 0;
function requestTile() {
  clearTimeout(tileTimer);
  tileTimer = setTimeout(async () => {
    if (!S.info) return;
    const zoomed = V.s * V.dpr > V.pScale * 1.05;
    const [x0, y0] = toImg(0, 0), [x1, y1] = toImg(V.cw, V.ch);
    const box = { x: Math.max(0, Math.floor(x0)), y: Math.max(0, Math.floor(y0)) };
    box.w = Math.min(S.info.w, Math.ceil(x1)) - box.x; box.h = Math.min(S.info.h, Math.ceil(y1)) - box.y;
    if (box.w <= 0 || box.h <= 0) return;
    const out = Math.round(box.w * V.s * V.dpr), seq = ++tileSeq, rel = S.rel;
    const get = async (path, extra) => {
      const r = await fetch(`/api/${path}?${qs({ rel, ...box, out, ...extra })}`);
      if (!r.ok) return null;
      const b = (r.headers.get('X-Box') || '').split(',').map(Number);
      return { bmp: await createImageBitmap(await r.blob()), box: b, rel };
    };
    const [t, m] = await Promise.all([zoomed ? get('tile') : null, S.showCut && S.st?.sheets.length ? get('masktile', { v: S.st.version }) : null]);
    if (seq !== tileSeq || rel !== S.rel) return;
    V.tile = t; V.mtile = m; draw();
  }, 140);
}

// ------------------------------------------------------------ disegno
function polyPath(c, pts) { if (!pts?.length) return; const [x, y] = toScr(...pts[0]); c.moveTo(x, y); for (let i = 1; i < pts.length; i++) c.lineTo(...toScr(...pts[i])); c.closePath(); }
function draw() {
  if (!ctx || !S.info) return;
  const c = ctx; c.setTransform(V.dpr, 0, 0, V.dpr, 0, 0); c.clearRect(0, 0, V.cw, V.ch);
  // lo sfondo scelto si dipinge nel canvas: nella finestra trasparente dell'app i pixel
  // trasparenti del canvas mostrerebbero il vetro scuro dietro la finestra, non lo sfondo
  c.fillStyle = bgPaint(c); c.fillRect(0, 0, V.cw, V.ch);
  // la scansione con un'ombra, come una foto in Photo Gallery
  const [ix, iy] = toScr(0, 0), iw = S.info.w * V.s, ih = S.info.h * V.s;
  // una scansione su un foglio bianco con l'ombra; un ritaglio trasparente direttamente sullo sfondo scelto
  if (!S.info.alpha) { c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 8; c.shadowOffsetY = 2; c.fillStyle = '#fff'; c.fillRect(ix, iy, iw, ih); c.restore(); }
  else { c.save(); c.setLineDash([4, 4]); c.strokeStyle = 'rgba(60,90,130,.45)'; c.strokeRect(ix - .5, iy - .5, iw + 1, ih + 1); c.restore(); }
  c.imageSmoothingEnabled = V.s * V.dpr < V.pScale * 2;
  if (V.img) c.drawImage(V.img, ix, iy, iw, ih);
  const tileOk = t => t && t.rel === S.rel && t.box.length === 4;
  if (tileOk(V.tile)) { c.imageSmoothingEnabled = false; const [a, b] = toScr(V.tile.box[0], V.tile.box[1]); c.drawImage(V.tile.bmp, a, b, (V.tile.box[2] - V.tile.box[0]) * V.s, (V.tile.box[3] - V.tile.box[1]) * V.s); }
  const sheets = S.st?.sheets || [];
  // cio' che verra' tolto: scurito. Da vicino la maschera vera, da lontano i contorni
  const covers = t => { const [a, b] = toImg(0, 0), [e, f] = toImg(V.cw, V.ch); return t.box[0] <= Math.max(0, a) + 1 && t.box[1] <= Math.max(0, b) + 1 && t.box[2] >= Math.min(S.info.w, e) - 1 && t.box[3] >= Math.min(S.info.h, f) - 1; };
  if (S.showCut && sheets.length) {
    if (tileOk(V.mtile) && covers(V.mtile)) {
      c.imageSmoothingEnabled = false; const [a, b] = toScr(V.mtile.box[0], V.mtile.box[1]);
      c.drawImage(V.mtile.bmp, a, b, (V.mtile.box[2] - V.mtile.box[0]) * V.s, (V.mtile.box[3] - V.mtile.box[1]) * V.s);
    } else {
      c.save(); c.beginPath(); c.rect(ix, iy, iw, ih);
      sheets.filter(s => s.on !== false).forEach(s => polyPath(c, s.poly));
      c.fillStyle = 'rgba(20,30,45,.42)'; c.fill('evenodd'); c.restore();
    }
  }
  if (S.compare) for (const [e, r] of Object.entries(S.compare)) {
    if (!r.polys) continue;
    c.save(); c.setLineDash([6, 4]); c.lineWidth = 1.5; c.strokeStyle = CMP_COLORS[e] || '#888';
    r.polys.forEach(p => { c.beginPath(); polyPath(c, p); c.stroke(); }); c.restore();
  }
  sheets.forEach((s, i) => {
    const col = COLORS[i % COLORS.length], sel = isSel(s.id), off = s.on === false;
    c.save();
    c.beginPath(); polyPath(c, s.poly);
    if (off) c.setLineDash([4, 4]);
    c.lineWidth = sel ? 3.5 : 2.5; c.strokeStyle = 'rgba(255,255,255,.85)'; c.stroke();
    c.lineWidth = sel ? 2 : 1.25; c.strokeStyle = off ? '#888' : col; c.stroke();
    if (sel) { c.fillStyle = col + '14'; c.fill(); }
    for (const o of s.ops) {
      c.beginPath(); c.strokeStyle = c.fillStyle = o.op === 'add' ? 'rgba(40,170,60,.35)' : o.op === 'int' ? 'rgba(40,110,230,.30)' : 'rgba(220,40,40,.35)';
      if (o.kind === 'wand') { (o.outline || []).forEach(p => polyPath(c, p)); c.fill('evenodd'); const [x, y] = toScr(...o.seed); c.fillStyle = o.op === 'add' ? '#1e8a1e' : '#c22'; c.fillRect(x - 3, y - 3, 6, 6); }
      else if (o.kind === 'stroke') { c.lineWidth = Math.max(1, 2 * o.r * V.s); c.lineCap = c.lineJoin = 'round'; const [x, y] = toScr(...o.pts[0]); c.moveTo(x, y); o.pts.forEach(p => c.lineTo(...toScr(...p))); c.stroke(); }
      else { polyPath(c, o.pts); c.fill(); }
    }
    c.setLineDash([3, 2]); c.lineWidth = 1; c.strokeStyle = col;
    (s.holes || []).forEach(hp => { c.beginPath(); polyPath(c, hp); c.stroke(); });
    c.setLineDash([]);
    // etichetta: la lettera del foglio
    const p = s.poly.reduce((a, q) => (q[1] < a[1] || (q[1] === a[1] && q[0] < a[0])) ? q : a, s.poly[0]);
    if (p) {
      const [lx, ly] = toScr(...p), L = sheets.filter(x => x.on !== false).length > 1 ? 'abcdefghijklmnopqrstuvwxyz'[sheets.filter(x => x.on !== false).indexOf(s)] || '' : '';
      const txt = (off ? '(off) ' : '') + (L || '') + (s.label ? ' ' + s.label : '') + (sheetEdited(s) ? ' ✎' : '');
      if (txt.trim()) { c.font = '600 11px "Segoe UI", Tahoma, sans-serif'; const w = c.measureText(txt).width + 10;
        c.fillStyle = off ? '#888' : col; c.beginPath(); c.roundRect(lx, ly - 20, w, 16, 3); c.fill(); c.fillStyle = '#fff'; c.fillText(txt, lx + 5, ly - 8); }
    }
    if (s.id === S.selSheet && S.selSet.size === 1 && (S.tool === 'points')) {
      c.fillStyle = '#fff'; c.strokeStyle = '#000'; c.lineWidth = 1;
      s.poly.forEach((q, k) => { const [x, y] = toScr(...q); const hot = drag?.vertex === k || hoverV === k; c.fillStyle = hot ? col : '#fff'; c.fillRect(x - 3.5, y - 3.5, 7, 7); c.strokeRect(x - 3.5, y - 3.5, 7, 7); });
    }
    c.restore();
  });
  // disegno in corso
  if (S.poly?.length) { c.save(); c.beginPath(); const [x, y] = toScr(...S.poly[0]); c.moveTo(x, y); S.poly.forEach(p => c.lineTo(...toScr(...p))); if (mouse) c.lineTo(...toScr(...mouse)); c.strokeStyle = '#000'; c.setLineDash([4, 3]); c.lineWidth = 1.2; c.stroke(); S.poly.forEach(p => { const [a, b] = toScr(...p); c.fillStyle = '#fff'; c.fillRect(a - 3, b - 3, 6, 6); c.strokeRect(a - 3, b - 3, 6, 6); }); c.restore(); }
  if (drag?.lasso) { c.save(); c.beginPath(); polyPath(c, drag.lasso); c.fillStyle = drag.add ? 'rgba(40,170,60,.2)' : 'rgba(220,40,40,.2)'; c.fill(); c.setLineDash([4, 3]); c.strokeStyle = '#000'; c.stroke(); c.restore(); }
  if (drag?.stroke) { c.save(); c.beginPath(); c.lineCap = c.lineJoin = 'round'; c.lineWidth = 2 * drag.r * V.s; c.strokeStyle = drag.add ? 'rgba(40,170,60,.45)' : 'rgba(220,40,40,.45)'; const [x, y] = toScr(...drag.stroke[0]); c.moveTo(x, y); drag.stroke.forEach(p => c.lineTo(...toScr(...p))); c.stroke(); c.restore(); }
  if (drag?.sambox && Math.abs(drag.sambox[2] - drag.sambox[0]) * V.s > 8) { c.save(); const [a, b] = toScr(drag.sambox[0], drag.sambox[1]), [e, f] = toScr(drag.sambox[2], drag.sambox[3]); c.setLineDash([5, 3]); c.strokeStyle = '#5b3fd9'; c.lineWidth = 1.5; c.strokeRect(a, b, e - a, f - b); c.fillStyle = 'rgba(123,92,255,.12)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (S.sam?.points.length) { c.save(); S.sam.points.forEach((q, i) => { const [x, y] = toScr(...q); c.beginPath(); c.arc(x, y, 6, 0, 7); c.fillStyle = S.sam.labels[i] ? '#2fb84f' : '#e03a3a'; c.fill(); c.lineWidth = 2; c.strokeStyle = '#fff'; c.stroke(); c.fillStyle = '#fff'; c.font = 'bold 10px sans-serif'; c.fillText(S.sam.labels[i] ? '+' : '–', x - 3, y + 3.5); }); c.restore(); }
  if (drag?.marq) { c.save(); const [a, b] = toScr(drag.marq[0], drag.marq[1]), [e, f] = toScr(drag.marq[2], drag.marq[3]); c.setLineDash([3, 3]); c.strokeStyle = '#3399ff'; c.strokeRect(a, b, e - a, f - b); c.fillStyle = 'rgba(51,153,255,.12)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (drag?.rect) { c.save(); const [a, b] = toScr(drag.rect[0], drag.rect[1]), [e, f] = toScr(drag.rect[2], drag.rect[3]); c.setLineDash([4, 3]); c.strokeStyle = '#000'; c.strokeRect(a, b, e - a, f - b); c.fillStyle = drag.add ? 'rgba(40,170,60,.2)' : 'rgba(220,40,40,.2)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (drag?.box) { c.save(); const [a, b] = toScr(drag.box[0], drag.box[1]), [e, f] = toScr(drag.box[2], drag.box[3]); c.setLineDash([5, 3]); c.strokeStyle = '#000'; c.strokeRect(a, b, e - a, f - b); c.fillStyle = 'rgba(51,153,255,.12)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (mouse && S.tool === 'brush') { const [x, y] = toScr(...mouse); c.beginPath(); c.arc(x, y, Math.max(2, brushR() * V.s), 0, 7); c.strokeStyle = '#000'; c.lineWidth = 1; c.stroke(); c.strokeStyle = '#fff'; c.setLineDash([3, 3]); c.stroke(); }
  const ss = S.selSet.size === 1 ? sheets.find(s => s.id === S.selSheet) : null;
  let info = S.selSet.size > 1 ? ` · ${S.selSet.size} sheets selected` : '';
  if (ss) { const b = bbox(ss.poly), w = b[2] - b[0], hh = b[3] - b[1]; info = ` · sheet ≈ ${(w / S.info.ppm).toFixed(0)} × ${(hh / S.info.ppm).toFixed(0)} mm · ${Math.round(w)} × ${Math.round(hh)} px · ${(w * hh * 4 / 1048576).toFixed(1)} MB RGBA`; }
  hud.textContent = `${Math.round(V.s * V.dpr * 100)}%` + (mouse ? ` · ${Math.round(mouse[0])}, ${Math.round(mouse[1])} px · ${(mouse[0] / S.info.ppm).toFixed(1)}, ${(mouse[1] / S.info.ppm).toFixed(1)} mm` : '') + info;
}
let checkerPat = null;
function bgPaint(c) {
  if (S.bg === 'white') return '#fff';
  if (S.bg === 'grey') return '#8a8d91';
  if (S.bg === 'dark') return '#262a30';
  if (S.bg === 'checker') {
    if (!checkerPat) { const t = document.createElement('canvas'); t.width = t.height = 16; const k = t.getContext('2d');
      k.fillStyle = '#fbfbfb'; k.fillRect(0, 0, 16, 16); k.fillStyle = '#e6e6e6'; k.fillRect(0, 0, 8, 8); k.fillRect(8, 8, 8, 8); checkerPat = c.createPattern(t, 'repeat'); }
    return checkerPat;
  }
  const g = c.createLinearGradient(0, 0, 0, V.ch); g.addColorStop(0, '#eef4fb'); g.addColorStop(1, '#d6e4f3'); return g;
}
const brushR = () => S.brushMM * S.info.ppm / 2;

// ------------------------------------------------------------ geometria
function inside(pt, poly) {
  let ins = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) ins = !ins;
  }
  return ins;
}
const area = p => Math.abs(p.reduce((a, q, i) => { const r = p[(i + 1) % p.length]; return a + q[0] * r[1] - r[0] * q[1]; }, 0) / 2);
function sheetAt(pt) {
  const hit = (S.st?.sheets || []).filter(s => inside(pt, s.poly));
  return hit.sort((a, b) => area(a.poly) - area(b.poly))[0];
}
function nearestVertex(s, sx, sy, r = 7) {
  let best = -1, bd = r * r;
  s.poly.forEach((q, k) => { const [x, y] = toScr(...q); const d = (x - sx) ** 2 + (y - sy) ** 2; if (d < bd) { bd = d; best = k; } });
  return best;
}
function nearestEdge(s, pt) {
  let best = -1, bd = Infinity, proj = null;
  for (let i = 0; i < s.poly.length; i++) {
    const a = s.poly[i], b = s.poly[(i + 1) % s.poly.length];
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L));
    const p = [a[0] + t * dx, a[1] + t * dy], d = (p[0] - pt[0]) ** 2 + (p[1] - pt[1]) ** 2;
    if (d < bd) { bd = d; best = i; proj = p; }
  }
  return { i: best, d: Math.sqrt(bd) * V.s, p: proj };
}
const bbox = p => p.reduce((b, q) => [Math.min(b[0], q[0]), Math.min(b[1], q[1]), Math.max(b[2], q[0]), Math.max(b[3], q[1])], [Infinity, Infinity, -Infinity, -Infinity]);
const overlaps = (a, b) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];
const rnd = p => [Math.round(p[0]), Math.round(p[1])];
function newId() { return 's' + (Math.max(0, ...(S.st.sheets.map(s => +s.id.slice(1) || 0))) + 1); }

// ------------------------------------------------------------ mouse e tastiera
let drag = null, mouse = null, hoverV = -1, spaceDown = false;
function bindCanvas(stage) {
  cv.style.cursor = cursorFor(S.tool);
  cv.addEventListener('pointerdown', e => {
    cv.setPointerCapture(e.pointerId);
    const r = cv.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top, pt = toImg(sx, sy);
    const tool = spaceDown || e.button === 1 ? 'hand' : S.tool;
    if (tool === 'hand') { drag = { pan: [sx - V.ox, sy - V.oy] }; cv.style.cursor = 'grabbing'; return; }
    if (e.ctrlKey && e.button === 0) return;           // ⌃-clic: ci pensa il menu contestuale (solo)
    if (tool === 'select') {
      const s = sheetAt(pt), mod = e.shiftKey || e.metaKey;
      if (s) { if (mod) toggleSel(s.id); else if (!isSel(s.id)) S.selSheet = s.id; else S._primary = s.id; renderSide(); draw(); return; }
      // sul vuoto: riquadro di selezione (lo spostamento resta con Spazio, H o due dita)
      drag = { marq: [...pt, ...pt], add: mod };
      return;
    }
    if (tool === 'points') {
      let s = S.st.sheets.find(x => x.id === S.selSheet);
      let k = s ? nearestVertex(s, sx, sy) : -1;
      if (k < 0) { const t = sheetAt(pt); if (t && t !== s) { S.selSheet = t.id; renderSide(); draw(); return; } }
      if (s && k >= 0) {
        if (e.altKey) { if (s.poly.length > 3) commit(() => s.poly.splice(k, 1)); return; }
        pushHist(); drag = { vertex: k, sheet: s };
        return;
      }
      if (!s) drag = { pan: [sx - V.ox, sy - V.oy] };
      return;
    }
    if (tool === 'poly') { S.poly = S.poly || []; S.poly.push(rnd(pt)); draw(); return; }
    const mode = e.shiftKey && e.altKey ? 'int' : e.shiftKey ? 'add' : e.altKey ? (S.mode === 'sub' ? 'add' : 'sub') : S.mode;
    const add = mode === 'add' || mode === 'new';
    if (tool === 'lasso') { drag = { lasso: [rnd(pt)], add, mode }; return; }
    if (tool === 'rect') { drag = { rect: [...pt, ...pt], add, mode }; return; }
    if (tool === 'brush') { drag = { stroke: [rnd(pt)], r: brushR(), add, mode: mode === 'new' || mode === 'int' ? 'add' : mode }; draw(); return; }
    if (tool === 'wand') { wandAt(pt, mode); return; }
    if (tool === 'sam') { drag = { sambox: [...pt, ...pt], add, start: [sx, sy] }; return; }
    if (tool === 'box') { drag = { box: [...pt, ...pt] }; return; }
  });
  cv.addEventListener('pointermove', e => {
    const r = cv.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top, pt = toImg(sx, sy);
    mouse = pt;
    if (drag?.pan) { V.ox = sx - drag.pan[0]; V.oy = sy - drag.pan[1]; viewChanged(); return; }
    if (drag?.vertex != null) { drag.sheet.poly[drag.vertex] = rnd(pt); draw(); return; }
    if (drag?.lasso) { const l = drag.lasso.at(-1); if (Math.hypot(pt[0] - l[0], pt[1] - l[1]) * V.s > 2) drag.lasso.push(rnd(pt)); draw(); return; }
    if (drag?.stroke) { const l = drag.stroke.at(-1); if (Math.hypot(pt[0] - l[0], pt[1] - l[1]) * V.s > 1.5) drag.stroke.push(rnd(pt)); draw(); return; }
    if (drag?.box) { drag.box[2] = pt[0]; drag.box[3] = pt[1]; draw(); return; }
    if (drag?.rect) { drag.rect[2] = pt[0]; drag.rect[3] = pt[1]; draw(); return; }
    if (drag?.marq) { drag.marq[2] = pt[0]; drag.marq[3] = pt[1]; draw(); return; }
    if (drag?.sambox) { drag.sambox[2] = pt[0]; drag.sambox[3] = pt[1]; draw(); return; }
    measure(pt, sx, sy);
    if (S.tool === 'points') { const s = S.st?.sheets.find(x => x.id === S.selSheet); const k = s ? nearestVertex(s, sx, sy) : -1; if (k !== hoverV) { hoverV = k; } cv.style.cursor = k >= 0 ? (e.altKey ? 'not-allowed' : 'move') : 'default'; }
    draw();
  });
  const up = e => {
    const d = drag; drag = null; cv.style.cursor = cursorFor(spaceDown ? 'hand' : S.tool);
    if (!d) return;
    if (d.vertex != null) { afterEdit(); return; }
    if (d.lasso && d.lasso.length > 2) applyRegion({ kind: 'poly', pts: d.lasso }, d.mode);
    if (d.stroke) applyRegion({ kind: 'stroke', pts: d.stroke, r: d.r }, d.mode);
    if (d.marq) {
      const b = [Math.min(d.marq[0], d.marq[2]), Math.min(d.marq[1], d.marq[3]), Math.max(d.marq[0], d.marq[2]), Math.max(d.marq[1], d.marq[3])];
      if ((b[2] - b[0]) * V.s < 4 && (b[3] - b[1]) * V.s < 4) { if (!d.add) S.selSheet = null; }
      else selectIds(S.st.sheets.filter(s => overlaps(bbox(s.poly), b)).map(s => s.id), d.add);
      renderSide();
    }
    if (d.sambox) {
      const b = [Math.min(d.sambox[0], d.sambox[2]), Math.min(d.sambox[1], d.sambox[3]), Math.max(d.sambox[0], d.sambox[2]), Math.max(d.sambox[1], d.sambox[3])].map(Math.round);
      if ((b[2] - b[0]) * V.s > 8 && (b[3] - b[1]) * V.s > 8) detect(b, 'sam3');
      else samClick([Math.round(d.sambox[0]), Math.round(d.sambox[1])], d.add);
    }
    if (d.rect) {
      const [a, b, c2, d2] = [Math.min(d.rect[0], d.rect[2]), Math.min(d.rect[1], d.rect[3]), Math.max(d.rect[0], d.rect[2]), Math.max(d.rect[1], d.rect[3])].map(Math.round);
      if ((c2 - a) * V.s > 3 && (d2 - b) * V.s > 3) applyRegion({ kind: 'poly', pts: [[a, b], [c2, b], [c2, d2], [a, d2]] }, d.mode);
    }
    if (d.box) {
      const b = [Math.min(d.box[0], d.box[2]), Math.min(d.box[1], d.box[3]), Math.max(d.box[0], d.box[2]), Math.max(d.box[1], d.box[3])].map(Math.round);
      if ((b[2] - b[0]) * V.s > 8 && (b[3] - b[1]) * V.s > 8) detect(b);
    }
    draw();
  };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('contextmenu', e => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), s = sheetAt(toImg(e.clientX - r.left, e.clientY - r.top));
    if (s) { soloSheet(s.id); renderSide(); draw(); }
  });
  cv.addEventListener('pointerleave', () => { mouse = null; draw(); $('#dens').style.display = 'none'; $('#loupe').style.display = 'none'; });
  cv.addEventListener('dblclick', e => {
    const r = cv.getBoundingClientRect(), pt = toImg(e.clientX - r.left, e.clientY - r.top);
    if (S.tool === 'poly') { S.poly?.pop(); closePoly(); return; }
    if (S.tool === 'points') {
      const s = S.st.sheets.find(x => x.id === S.selSheet); if (!s) return;
      const ne = nearestEdge(s, pt); if (ne.d < 8) commit(() => s.poly.splice(ne.i + 1, 0, rnd(ne.p)));
      return;
    }
    if (S.tool === 'select') { const s = sheetAt(pt); if (s) cutoutDialog(s); }
  });
  cv.addEventListener('wheel', e => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
    // pizzico (arriva come ctrl+rotella) o ⌘+rotella: zoom. Tutto il resto (due dita, anche veloci) sposta
    if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025)), sx, sy);
    else { V.ox -= e.deltaX; V.oy -= e.deltaY; viewChanged(); }
  }, { passive: false });
}
// densitometro: i valori veri del pixel (scansione a piena risoluzione), come li vede il taglio
let measTimer = null, measAt = null, loupeImg = null;
function measure(pt, sx, sy) {
  measAt = { pt, sx, sy };
  loupePlace();
  if (measTimer) return;
  measTimer = setTimeout(async () => {
    measTimer = null;
    const m = measAt; if (!m || !S.rel) return;
    const [x, y] = m.pt.map(Math.floor), rel = S.rel;
    const reqs = [api.get('pixel', { rel, x, y, r: S.densR }).catch(() => null)];
    if (S.loupe) { const half = Math.round(180 / S.loupeZoom / 2); reqs.push(fetch(`/api/tile?${qs({ rel, x: x - half, y: y - half, w: 2 * half + 1, h: 2 * half + 1, out: (2 * half + 1) * S.loupeZoom })}`).then(async r => r.ok ? { bmp: await createImageBitmap(await r.blob()), box: r.headers.get('X-Box').split(',').map(Number), x, y } : null)); }
    const [px, lo] = await Promise.all(reqs);
    if (rel !== S.rel) return;
    if (lo) { loupeImg = lo; loupeDraw(); }
    const el = $('#dens'); if (!el || !px || px.x == null) return;
    const lid = px.is_bg ? '<b style="color:#8a5a00">lid</b>' : '<b style="color:#1e6b2c">paper / ink</b>';
    el.classList.toggle('collapsed', S.densShut);
    el.innerHTML = `<div class="dh" title="${S.densShut ? 'Expand' : 'Collapse'}"><b>Densitometer</b><span>${S.densShut ? `${px.rgb.map(v => v.toFixed(0)).join(' · ')} · ${px.is_bg ? 'lid' : 'paper/ink'}` : (S.densR ? (2 * S.densR + 1) + '×' + (2 * S.densR + 1) + ' average' : 'single pixel')}</span><i class="dtog">${S.densShut ? '▾' : '▴'}</i></div>`
      + `<div class="dc">`
      + `<div><span>RGB</span>${px.rgb.map(v => v.toFixed(0)).join(' · ')}</div>`
      + `<div><span>L*a*b*</span>${px.lab.join(' · ')}</div>`
      + `<div><span>vs lid</span>${px.bg_dist} <small>(lid if &lt; ${px.bg_tol})</small> ${lid}</div>`
      + (px.alpha != null ? `<div><span>alpha</span>${px.alpha}</div>` : '')
      + `<div class="sw"><i style="background:rgb(${px.rgb.join(',')})"></i><i style="background:${labCss(px.bg_lab)}"></i><small>pixel · lid</small></div>`
      + `</div>`;
    el.style.display = 'block';
  }, 70);
}
function labCss(l) { return `lab(${l[0]}% ${l[1]} ${l[2]})`; }
function loupePlace() {
  const lo = $('#loupe'); if (!lo) return;
  if (!S.loupe || !measAt) { lo.style.display = 'none'; return; }
  lo.style.display = 'block';
  const W = cv.clientWidth, x = measAt.sx + 24 + 180 > W ? measAt.sx - 24 - 180 : measAt.sx + 24, y = Math.max(4, measAt.sy - 90);
  lo.style.left = x + 'px'; lo.style.top = y + 'px';
}
function loupeDraw() {
  const lo = $('#loupe'); if (!lo) return;
  loupePlace(); if (!S.loupe || !loupeImg) return;
  const c = lo.getContext('2d'), z = S.loupeZoom * 2, half = Math.round(180 / S.loupeZoom / 2);
  c.imageSmoothingEnabled = false; c.fillStyle = '#888'; c.fillRect(0, 0, 360, 360);
  const { bmp, box, x, y } = loupeImg;
  c.drawImage(bmp, (box[0] - (x - half)) * z, (box[1] - (y - half)) * z, (box[2] - box[0]) * z, (box[3] - box[1]) * z);
  // il pixel misurato al centro
  c.strokeStyle = '#000'; c.lineWidth = 2; c.strokeRect(half * z - 1, half * z - 1, z + 2, z + 2);
  c.strokeStyle = '#fff'; c.lineWidth = 1; c.strokeRect(half * z - 3, half * z - 3, z + 6, z + 6);
  c.fillStyle = 'rgba(0,0,0,.55)'; c.fillRect(0, 336, 360, 24); c.fillStyle = '#fff'; c.font = '12px "Segoe UI", Tahoma'; c.fillText(`${S.loupeZoom}:1 · real pixels · ${x}, ${y}`, 8, 352);
}
function newOpsSheet(op, outline, engine) {
  // un foglio nuovo fatto solo di questa selezione (es. il solo inchiostro: la carta resta trasparente)
  return { id: newId(), src: null, base: 'ops', engine, poly0: null, poly: outline, ops: [Object.assign({}, op, { op: 'add' })], on: true, label: '', holes: [] };
}
function applyRegion(op, mode) {
  const ob = bbox(op.pts).map((v, i) => v + (i < 2 ? -1 : 1) * (op.r || 0));
  const sheets = S.st.sheets;
  if (mode === 'new') {
    const outline = op.kind === 'poly' ? op.pts : [[ob[0], ob[1]], [ob[2], ob[1]], [ob[2], ob[3]], [ob[0], ob[3]]];
    return commit(() => { const s = op.kind === 'poly' ? { id: newId(), src: null, engine: 'manual', poly0: null, poly: op.pts, ops: [], on: true, label: '', holes: [] } : newOpsSheet(op, outline, 'brush'); sheets.push(s); S.selSheet = s.id; });
  }
  let targets = S.selSet.size ? sheets.filter(s => isSel(s.id) && (S.selSet.size === 1 || overlaps(bbox(s.poly), ob))) : sheets.filter(s => overlaps(bbox(s.poly), ob));
  if (mode === 'add' && !targets.length) {
    if (op.kind === 'poly') { commit(() => { const s = { id: newId(), src: null, engine: 'manual', poly0: null, poly: op.pts, ops: [], on: true, label: '', holes: [] }; sheets.push(s); S.selSheet = s.id; }); }
    else status('Brush: select a sheet first (or draw a new one with the lasso or polygon)');
    return;
  }
  if (!targets.length) return status(mode === 'int' ? 'Select the sheet to intersect with first' : 'Nothing there to cut away');
  if (mode === 'add' && targets.length > 1) targets = targets.slice(0, 1);
  commit(() => targets.forEach(s => s.ops.push({ op: mode, ...op })));
}
async function wandAt(pt, mode) {
  if (pt[0] < 0 || pt[1] < 0 || pt[0] >= S.info.w || pt[1] >= S.info.h) return;
  status('Magic wand…', true);
  let op;
  try { op = await api.post('wand', { rel: S.rel, x: Math.round(pt[0]), y: Math.round(pt[1]), tol: S.wandTol, contig: S.wandContig }); }
  catch (e) { return status('Wand: ' + e.message); }
  status(`Wand: ${(op.area / S.info.ppm / S.info.ppm / 100).toFixed(1)} cm² selected, tolerance ${op.tol}${op.contig ? '' : ', not contiguous'}`);
  const sheets = S.st.sheets;
  const outline = op.outline.reduce((a, p) => area(p) > area(a) ? p : a, op.outline[0]);
  if (mode === 'new') return commit(() => { const s = newOpsSheet(op, op.contig ? outline : [[op.pts[0][0], op.pts[0][1]], [op.pts[1][0], op.pts[0][1]], [op.pts[1][0], op.pts[1][1]], [op.pts[0][0], op.pts[1][1]]], 'wand'); sheets.push(s); S.selSheet = s.id; });
  op.op = mode;
  const wb = [op.pts[0][0], op.pts[0][1], op.pts[1][0], op.pts[1][1]];
  let targets = S.selSet.size ? sheets.filter(s => isSel(s.id) && (S.selSet.size === 1 || overlaps(bbox(s.poly), wb))) : sheets.filter(s => inside(op.seed, s.poly));
  if (!targets.length && mode !== 'add') targets = sheets.filter(s => overlaps(bbox(s.poly), wb));
  if (!targets.length) {
    if (mode !== 'add') return status(mode === 'int' ? 'Select the sheet to intersect with first' : 'Nothing there to cut away');
    // un foglio nuovo fatto solo dalla bacchetta (es. un disegno cliccato sul coperchio)
    return commit(() => { const s = newOpsSheet(op, outline, 'wand'); sheets.push(s); S.selSheet = s.id; });
  }
  commit(() => targets.slice(0, mode === 'add' ? 1 : targets.length).forEach(s => s.ops.push(op)));
}
async function samClick(pt, add) {
  const eng = S.engines.find(e => e.id === 'sam3');
  if (!eng?.available) return status('SAM 3 is not installed: see Add-ons');
  // i clic si sommano finche' non si preme Invio (o si cambia strumento): stesso oggetto
  if (!S.sam) S.sam = { points: [], labels: [], sheet: null };
  S.sam.points.push(pt); S.sam.labels.push(add ? 1 : 0); draw();
  const prm = Object.assign(samParams(), { points: S.sam.points, labels: S.sam.labels });
  if (!prm.prompt) prm.prompt = (S.engines.find(e => e.id === 'sam3').params.find(p => p.id === 'prompt') || {}).default;
  busy(true, 'SAM 3: “' + prm.prompt + '”' + (S.samLoaded ? '' : ' (loading the model, ~10 s)'));
  try {
    await flushSave();
    const before = new Set(S.st.sheets.map(s => s.id));
    const r = await api.post('detect', { rel: S.rel, engine: 'sam3', params: prm, replace: false });
    S.samLoaded = true;
    pushHist();
    const prev = S.sam.sheet;
    const fresh = r.state.sheets.filter(s => !before.has(s.id));
    r.state.sheets = r.state.sheets.filter(s => s.id !== prev);
    setState(r.state);
    S.sam.sheet = fresh[0]?.id || null;
    if (S.sam.sheet) S.selSheet = S.sam.sheet;
    status(fresh.length ? `SAM 3: object selected (${S.sam.points.length} click${S.sam.points.length > 1 ? 's' : ''}). Enter = done.` : `SAM 3 found no “${prm.prompt}” under the click. Try another prompt in the Engine panel.`);
    scheduleSave();
  } catch (e) { alertDialog('SAM 3 failed', e.message); }
  busy(false); renderSide(); draw();
}
function soloSheet(id) {
  const sh = S.st.sheets, me = sh.find(x => x.id === id); if (!me) return;
  const alreadySolo = me.on !== false && sh.every(x => x === me || x.on === false);
  commit(() => sh.forEach(x => { x.on = alreadySolo ? true : x === me; }));
  S.selSheet = id;
  status(alreadySolo ? 'All sheets on again' : 'Only this sheet will be exported (⌃-click it again to turn all back on)');
}
async function ocrSheets(list) {
  await flushSave();
  busy(true, 'Reading text (Apple Vision)…');
  try {
    const r = await api.post('ocr_sheets', { rel: S.rel, ids: list.map(x => x.id) });
    commit(() => list.forEach(x => { if (r[x.id] !== undefined) x.ocr = r[x.id]; }));
    const n = Object.values(r).filter(Boolean).length;
    status(n ? `Text found on ${n} sheet(s): it goes into the metadata at export` : 'No text found');
  } catch (e) { alertDialog('Text (OCR)', e.message); }
  busy(false); renderSide();
}
function deleteSelected() {
  const ids = new Set(S.selSet); if (!ids.size) return;
  commit(() => { S.st.sheets = S.st.sheets.filter(x => !ids.has(x.id)); S.selSheet = null; });
  status(`${ids.size} sheet${ids.size > 1 ? 's' : ''} deleted (⌘Z brings ${ids.size > 1 ? 'them' : 'it'} back)`);
}
function hull(pts) {
  // inviluppo convesso (solo per disegnare e cliccare il foglio unito; i pixel restano quelli dei pezzi)
  const p = pts.map(q => [q[0], q[1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cross(lo.at(-2), lo.at(-1), q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.slice().reverse()) { while (up.length >= 2 && cross(up.at(-2), up.at(-1), q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function mergeSelected() {
  const many = selSheets(); if (many.length < 2) return;
  const parts = JSON.parse(JSON.stringify(many));
  const all = parts.flatMap(x => x.poly.concat(...x.ops.map(o => o.pts || [])));
  const b = bbox(all);
  commit(() => {
    const first = S.st.sheets.indexOf(many[0]);
    const m = { id: newId(), src: null, base: 'ops', engine: 'merged', poly0: null, poly: hull(all), on: true, label: many[0].label || '',
      holes: parts.flatMap(x => x.holes || []), ops: [{ op: 'add', kind: 'sheets', sheets: parts, pts: [[b[0], b[1]], [b[2], b[3]]] }] };
    S.st.sheets = S.st.sheets.filter(x => !many.includes(x));
    S.st.sheets.splice(Math.min(first, S.st.sheets.length), 0, m);
    S.selSheet = m.id;
  });
  status(`${many.length} sheets merged into one`);
}
function closePoly() {
  const p = S.poly; S.poly = null;
  if (p && p.length >= 3) commit(() => { const s = { id: newId(), src: null, engine: 'manual', poly0: null, poly: p, ops: [], on: true, label: '', holes: [] }; S.st.sheets.push(s); S.selSheet = s.id; });
  draw();
}
document.addEventListener('keydown', e => {
  if (e.target.closest?.('input, textarea, select')) return;
  const k = e.key, mod = e.metaKey || e.ctrlKey;
  if (mod && k === ',') { e.preventDefault(); return settingsDialog(); }
  if ((mod && k === '[') || (e.altKey && k === 'ArrowLeft')) { e.preventDefault(); return navBack(); }
  if ((mod && k === ']') || (e.altKey && k === 'ArrowRight')) { e.preventDefault(); return navFwd(); }
  if (S.view === 'gallery') {
    if (mod && k === 'a') { e.preventDefault(); selectAll(); renderGallery(); renderSide(); renderCmdbar(); }
    if (k === 'Enter' && S.selDir) { const d = S.selDir; S.selDir = null; return openDir(d); }
    if (k === 'Enter' && S.sel.size) openScan([...S.sel][0]);
    if (k === 'ArrowRight') step(1); if (k === 'ArrowLeft') step(-1);
    return;
  }
  if (S.view === 'scanners' && k === ' ' && SC.spaceMode) { e.preventDefault(); return scanNextPage(); }
  if (S.view === 'scanners' && k === 'Escape' && SC.timed) return stopTimed();
  if (S.view === 'scanners' && (k === 'Delete' || k === 'Backspace') && SC.sel >= 0) { SC.areas.splice(SC.sel, 1); SC.sel = -1; drawBed(); renderScanSide(); return; }
  if (S.view !== 'editor') return;
  if (k === ' ') { if (!spaceDown) { spaceDown = true; cv.style.cursor = 'grab'; } e.preventDefault(); return; }
  if (mod && k.toLowerCase() === 'z') { e.preventDefault(); return e.shiftKey ? redo() : undo(); }
  if (mod && k === 's') { e.preventDefault(); return doExport(); }
  if (mod && k === '0') { e.preventDefault(); return fit(); }
  if (mod && k === '1') { e.preventDefault(); return actual(); }
  if (mod && k === 'a') { e.preventDefault(); selectIds(S.st.sheets.map(s => s.id)); renderSide(); return draw(); }
  if (mod) return;
  const tools = { v: 'select', h: 'hand', a: 'points', p: 'poly', m: 'rect', l: 'lasso', k: 'lasso', w: 'wand', b: 'brush', e: 'brush', r: 'box', s: 'sam' };
  if (k === 'g') { S.loupe = !S.loupe; store('loupe', S.loupe ? '1' : '0'); return loupeDraw(); }
  const kl = k.toLowerCase();
  if (kl === 'x') return setMode(S.mode === 'add' ? 'sub' : 'add');
  if (tools[kl]) { if ('lb'.includes(kl)) setMode('add'); if ('ke'.includes(kl)) setMode('sub'); return setTool(tools[kl]); }
  if (k === 'Escape') { if (S.sam) { S.sam = null; draw(); } else if (S.poly) { S.poly = null; draw(); } else if (openMenu) closeMenu(); else if ($('.dlg-back')) $('.dlg-back').remove(); else if (S.selSheet) { S.selSheet = null; renderSide(); draw(); } else go('gallery'); return; }
  if (k === 'Enter' && S.poly) return closePoly();
  if (k === 'Enter' && S.sam) { S.sam = null; status('SAM 3: next click starts a new object'); return draw(); }
  if (k === '+' || k === '=') return zoomBy(1.4);
  if (k === '-') return zoomBy(1 / 1.4);
  if (k === '[' || k === ']') { S.brushMM = Math.max(0.2, Math.min(10, S.brushMM * (k === ']' ? 1.25 : 0.8))); renderOptions(); return draw(); }
  if (k === 'c') return toggleCompare();
  if (k === 'o') { S.showCut = !S.showCut; const cb = $('#cutview'); if (cb) cb.checked = S.showCut; requestTile(); return draw(); }
  if (k === 'Tab') { e.preventDefault(); const sh = S.st.sheets; if (!sh.length) return; const i = sh.findIndex(s => s.id === S.selSheet); S.selSheet = sh[(i + (e.shiftKey ? -1 : 1) + sh.length) % sh.length].id; renderSide(); return draw(); }
  if ((k === 'Delete' || k === 'Backspace') && S.selSet.size) return deleteSelected();
  if (k === 'ArrowRight') return step(1);
  if (k === 'ArrowLeft') return step(-1);
});
document.addEventListener('mouseup', e => { if (e.button === 3) navBack(); if (e.button === 4) navFwd(); });
document.addEventListener('keyup', e => { if (e.key === ' ') { spaceDown = false; cv && (cv.style.cursor = cursorFor(S.tool)); } });

// ------------------------------------------------------------ storia e salvataggio
function pushHist() { S.hist.push(JSON.stringify(S.st.sheets)); if (S.hist.length > 80) S.hist.shift(); S.fut = []; }
function commit(fn) { pushHist(); fn(); afterEdit(); }
function afterEdit() { S.st.exported = false; scheduleSave(); renderSide(); draw(); }
function undo() { if (!S.hist.length || S.view !== 'editor') return; S.fut.push(JSON.stringify(S.st.sheets)); S.st.sheets = JSON.parse(S.hist.pop()); afterEdit(); }
function redo() { if (!S.fut.length || S.view !== 'editor') return; S.hist.push(JSON.stringify(S.st.sheets)); S.st.sheets = JSON.parse(S.fut.pop()); afterEdit(); }
let saveTimer = null, saving = Promise.resolve();
function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(save, 500); }
function save() {
  saveTimer = null;
  const st = S.st, rel = S.rel;
  saving = saving.then(async () => {
    try {
      const r = await api.post('state', { state: st });
      if (S.st === st) { st.version = r.version; }
      const fresh = await api.get('state', { rel }); if (S.rel === rel) { S.names = fresh.names || {}; renderSide(); }
      requestTile();
    } catch (e) {
      if (e.status === 409 && S.rel === rel) { status('Changed elsewhere (Claude or a job): reloaded'); setState(await api.get('state', { rel })); renderSide(); draw(); }
      else status('Could not save: ' + e.message);
    }
  });
  return saving;
}
async function flushSave() { if (saveTimer) { clearTimeout(saveTimer); save(); } await saving; }

// ------------------------------------------------------------ azioni
function busy(on, msg) { busyEl?.classList.toggle('on', on); const m = $('#busymsg'); if (m && msg) m.textContent = msg; }
async function detect(box, engine, add) {
  if (!S.rel) return;
  await flushSave();
  engine = engine || S.engine;
  const eng = S.engines.find(e => e.id === engine);
  if (!eng?.available) return status(`${eng?.name || engine} is not available`);
  const many = Array.isArray(box) || !!add;
  let addOnly = !!add;
  if (!many && S.st.sheets.some(s => s.src)) {
    const edited = S.st.sheets.filter(s => s.src && sheetEdited(s)).length;
    const choice = await choose('Detect', 'Keep the sheets you have?',
      `This scan already has ${S.st.sheets.length} sheet(s)${edited ? `, ${edited} with your edits` : ''}. Sheets you made by hand are always kept; detected ones can be kept too, or replaced (they stay in “Earlier” either way).`,
      [['keep', 'Keep them, add the new ones', true], ['replace', 'Replace them'], [null, 'Cancel']]);
    if (!choice) return;
    addOnly = choice === 'keep';
  }
  busy(true, `${eng.name}${many ? ' (inside the box)' : ''}…` + (engine === 'sam3' && !S.samLoaded ? ' loading the model the first time (~10 s)' : ''));
  try {
    pushHist();
    const r = await api.post('detect', { rel: S.rel, engine, params: engine === 'sam3' ? samParams() : engine === S.engine ? engParams() : {}, box: Array.isArray(box) ? box : null, replace: !many && !addOnly });
    if (engine === 'sam3') S.samLoaded = true;
    setState(r.state); const fresh = await api.get('state', { rel: S.rel }); S.names = fresh.names || {};
    status(`${eng.name}: ${r.state.sheets.length} sheet(s) in ${r.meta.seconds ?? 0}s`);
    V.mtile = null; requestTile();
  } catch (e) { status('Detect failed: ' + e.message); alertDialog('Detect failed', e.message); }
  busy(false); renderSide(); renderCmdbar(); draw(); refreshItems();
}
async function toggleCompare() {
  if (S.view !== 'editor') return;
  if (S.compare) { S.compare = null; renderSide(); renderCmdbar(); return draw(); }
  busy(true, 'Running the other engines…');
  try { S.compare = await api.post('compare', { rel: S.rel, engines: S.settings.compare_engines }); } catch (e) { status(e.message); }
  busy(false); renderSide(); renderCmdbar(); draw();
}
function rotateSheets(list, deg) {
  commit(() => list.forEach(x => { x.rot = (((x.rot || 0) + deg) % 360 + 360) % 360; }));
  status(`Rotated ${deg > 0 ? 'right' : 'left'} 90° (lossless, applied at export)`);
}
function restoreVersion(i) {
  const v = S.st.history[i]; if (!v) return;
  commit(() => {
    // lo stato di adesso va a sua volta nella storia: tornare indietro non perde niente
    S.st.history.splice(i, 1);
    S.st.history.unshift({ time: Date.now() / 1000, engine: S.st.engine, sheets: S.st.sheets });
    S.st.sheets = v.sheets; S.st.engine = v.engine; S.selSheet = null;
  });
  status('Earlier version restored (the current one is kept in the list)');
}
async function doExport(sub) {
  if (S.view !== 'editor' || !S.st?.sheets.length) return;
  await flushSave();
  busy(true, 'Saving the cutouts…');
  try {
    const r = await api.post('export', { rel: S.rel, subfolder: typeof sub === 'string' ? sub : null });
    const moved = r.written.find(w => w.status === 'moved');
    if (moved) { S.rel = moved.rel; S.dir = moved.rel.split('/').slice(0, -1).join('/'); }
    const st = await api.get('state', { rel: S.rel }); setState(st);
    const list = r.written.map(w => `${w.status === 'identical' ? '= ' : w.status === 'moved' ? '→ ' : '✓ '}${w.path.replace(S.root + '/', '')}${w.status === 'identical' ? '   (already there, identical)' : ''}${w.moved_old ? '   (old one moved aside)' : ''}${w.status === 'moved' ? '   (the cutout you started from, kept)' : ''}`).join('\n');
    status(`Exported ${r.written.filter(w => w.status === 'written').length} cutout(s)`);
    alertDialog('Cutouts saved', h('pre', { class: 'log' }, list || 'Nothing to save.'));
  } catch (e) { alertDialog('Export failed', e.message); }
  busy(false); renderSide(); refreshItems();
}
async function exportMany(rels) { if (!rels.length) return; await api.post('jobs', { kind: 'export', rels }); status(`Export of ${rels.length} scan(s) queued`); pollJobs(); }
async function batch(exp) {
  const rels = [...S.sel]; if (!rels.length) return;
  await api.post('jobs', { kind: 'batch', rels, engine: S.engine, params: engParams(), export: exp });
  status(`${rels.length} scan(s) queued with ${engName(S.engine)}`); pollJobs();
}
async function refreshItems() { if (!S.dir) return; S.items = await api.get('list', { dir: S.dir }).catch(() => S.items); if (S.view === 'gallery') renderGallery(); }

// ------------------------------------------------------------ dialoghi
function dialog(title, instr, body, buttons, opts = {}) {
  const back = h('div', { class: 'dlg-back', onmousedown: e => { if (e.target === back && !opts.modal) back.remove(); } });
  const d = h('div', { class: 'dlg', style: opts.style || {} },
    h('div', { class: 'titlebar' }, h('div', { class: 'title' }, h('span', {}, title)), h('div', { class: 'caption' }, h('span', { class: 'close', onclick: () => back.remove() }, '✕'))),
    h('div', { class: 'content', style: { display: 'flex', flexDirection: 'column' } },
      instr ? h('div', { class: 'main-instr' }, instr) : null, h('div', { class: 'inner', style: { flex: 1, overflow: 'auto' } }, body),
      h('div', { class: 'foot' }, (buttons || [['OK', () => true, true]]).map(([l, fn, def]) => h('button', { class: 'btn' + (def ? ' default' : ''), onclick: async () => { if ((await fn()) !== false) back.remove(); } }, l)))));
  back.append(d); document.body.append(back);
  return back;
}
// una domanda con piu' risposte, come le finestre di Vista: risolve con il valore del pulsante scelto
function choose(title, instr, text, buttons) {
  return new Promise(res => {
    const back = dialog(title, instr, h('div', { style: { maxWidth: '480px', lineHeight: 1.45 } }, text),
      buttons.map(([v, l, def]) => [l, () => { res(v); return true; }, def]), { modal: true });
    back.querySelector('.titlebar .close')?.addEventListener('click', () => res(null));
  });
}
const alertDialog = (title, body) => dialog('Scan Studio', title, typeof body === 'string' ? h('div', {}, body) : body);

function cutoutDialog(s) {
  let full = false;
  const img = h('img', { style: { display: 'block', margin: 'auto', maxWidth: '100%' } });
  const info = h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Rendering…');
  const box = h('div', { style: { background: bgCss(), overflow: 'auto', maxHeight: '68vh', minHeight: '200px', border: '1px solid #ccc', cursor: 'zoom-in' } }, img);
  const load = async () => {
    flushSave().then(() => {
      img.src = `/api/cutout?${qs({ rel: S.rel, id: s.id, max: full ? 100000 : 1400, v: S.st.version })}`;
      img.style.maxWidth = full ? 'none' : '100%'; box.style.cursor = full ? 'zoom-out' : 'zoom-in';
    });
  };
  img.onload = () => info.textContent = full ? 'Actual pixels. Click to fit.' : 'Exactly what will be saved (straightened, only transparency changed). Click for actual pixels.';
  img.onerror = () => info.textContent = 'Nothing to show (empty sheet?)';
  box.onclick = () => { full = !full; load(); };
  load();
  dialog('Cutout preview', S.names[s.id] || 'Cutout', h('div', {}, box, info), [['Close', () => true, true]], { style: { width: '760px' } });
}

function fakePixelsDialog() {
  dialog('Fix', 'Only real pixels, unless you ask', h('div', { style: { width: '520px', lineHeight: 1.5 } },
    h('p', {}, 'Everything else in Scan Studio only decides which pixels of your scan are kept: cutouts change transparency, never colour. The originals are never touched.'),
    h('p', {}, 'The Fix tools are different: they compute new pixel values (removing moiré, changing contrast, smoothing grain). That is what “fake pixels” means here. So they never overwrite anything: each one saves an extra copy next to the cutout, named after the fix, and the copy is marked in its file information.'),
    h('p', { class: 'muted' }, 'Dust removal is left out on purpose: without an infrared channel (the LiDE 400 has none) a speck of dust and a dot of ink look the same, and any software fix invents what is under the speck.')),
    [['OK', () => true, true]]);
}
async function settingsDialog() {
  const s = await api.get('settings');
  const f = {};
  const field = (id, label, el, hint) => { f[id] = el; return h('div', { class: 'row', style: { alignItems: 'flex-start' } }, h('label', { style: { width: '120px', paddingTop: '3px' } }, label), h('div', { class: 'f' }, el, hint ? h('div', { class: 'small muted' }, hint) : null)); };
  const body = h('div', { style: { width: '560px' } },
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '6px 0' } }, 'Where cutouts go'),
    field('out_root', 'Folder', h('input', { type: 'text', value: s.out_root }), 'Relative to ~/Scans, or a full path.'),
    field('template', 'Name template', h('input', { type: 'text', value: s.template }), '{batch} {stem} {sheet} (" a", " b"…) {letter} {n} {label} {date} {engine}. Use / for subfolders.'),
    field('batch_folders', 'Per batch', h('textarea', { rows: 3, placeholder: 'sketchbook = ~/Pictures/Sketchbook', value: Object.entries(s.batch_folders || {}).map(([k, v]) => `${k} = ${v}`).join('\n') }), 'One per line: batch = folder. Overrides the folder above.'),
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '12px 0 6px' } }, 'Eagle'),
    field('eagle', 'Add to Eagle', h('input', { type: 'checkbox', checked: s.eagle }), 'Also import each new cutout into Eagle (Eagle must be open).'),
    field('eagle_folder', 'Eagle folder id', h('input', { type: 'text', value: s.eagle_folder }), 'Optional.'),
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '12px 0 6px' } }, 'Engines and Claude'),
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '12px 0 6px' } }, 'Export'),
    field('export_format', 'Format', h('select', {}, [['png', 'PNG'], ['jxl', 'JPEG XL, lossless (smaller, keeps transparency)']].map(([v, l]) => h('option', { value: v, selected: s.export_format === v }, l))), 'JPEG XL is checked after writing: decoded back and compared pixel by pixel, else PNG is kept.'),
    field('ocr_on_export', 'Text (OCR)', h('input', { type: 'checkbox', checked: s.ocr_on_export }), 'Read any writing on each cutout with Apple Vision (on this Mac) and store it in the file description. Adds a few seconds per cutout.'),
    field('verify_jxl', 'Check JPEG XL', h('input', { type: 'checkbox', checked: s.verify_jxl }), 'Decode every JPEG XL back and compare it pixel by pixel (cjxl -d 0 is lossless by design; this only guards against a tool bug). Slower.'),
    field('keep_16bit', 'Keep 16 bits', h('input', { type: 'checkbox', checked: s.keep_16bit }), 'Cutouts of 48-bit colour or 16-bit grey scans keep all 16 bits per channel (PNG or JPEG XL). Off: 8-bit cutouts.'),
    field('export_existing', 'Name taken', h('select', {}, [['new_copy', 'Keep the old one, save the new one as “(2)”'], ['replace', 'Move the old one to studio-data/replaced']].map(([v, l]) => h('option', { value: v, selected: s.export_existing === v }, l))), 'Identical cutouts are never written twice.'),
    field('export_subfolder', 'Subfolder', h('input', { type: 'text', value: s.export_subfolder || 'extra' }), 'Used by the second export button (“To …/”).'),
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '12px 0 6px' } }, 'Colour calibration (IT8)'),
    field('it8_remind', 'Remind me', h('input', { type: 'checkbox', checked: s.it8_remind }), 'A reminder to recalibrate with the IT8.7/2 chart.'),
    field('it8_days', 'Every', h('input', { type: 'number', min: 7, max: 730, step: 1, value: s.it8_days || 90 }), 'days (90 = quarterly). ' + (s.it8_last ? 'Counting since ' + new Date(s.it8_last * 1000).toLocaleDateString() + '.' : '')),
    h('div', { class: 'btns', style: { margin: '0 0 6px 126px' } }, h('button', { class: 'btn small', onclick: async () => { S.settings = await api.post('settings', { it8_last: Date.now() / 1000, it8_snooze: 0 }); status('IT8 count restarted today'); } }, 'I calibrated today')),
    h('div', { class: 'gh', style: { color: '#1e3287', margin: '12px 0 6px' } }, 'Scan agent'),
    field('autocut', 'Cut automatically', h('input', { type: 'checkbox', checked: s.autocut }), 'On: new scans in the inbox are filed into originals/ and cut. Off: only filed; you cut them here when you want.'),
    field('compare_engines', 'Compare', h('input', { type: 'text', value: (s.compare_engines || []).join(', ') }), 'Engines shown by Compare, e.g. classic, vision, sam3'),
    field('claude_tools', 'Claude may use', h('input', { type: 'text', value: s.claude_tools }), 'Passed to claude --allowedTools.'),
  );
  dialog('Settings', 'Scan Studio settings', body, [['OK', async () => {
    const bf = {}; f.batch_folders.value.split('\n').forEach(l => { const m = l.split('='); if (m.length >= 2 && m[0].trim()) bf[m[0].trim()] = m.slice(1).join('=').trim(); });
    S.settings = await api.post('settings', { out_root: f.out_root.value.trim() || 'cut', template: f.template.value.trim() || '{batch}/{stem}{sheet}', batch_folders: bf,
      eagle: f.eagle.checked, eagle_folder: f.eagle_folder.value.trim(), export_format: f.export_format.value, export_existing: f.export_existing.value,
      export_subfolder: f.export_subfolder.value.trim() || 'extra', autocut: f.autocut.checked, verify_jxl: f.verify_jxl.checked, keep_16bit: f.keep_16bit.checked, ocr_on_export: f.ocr_on_export.checked,
      it8_remind: f.it8_remind.checked, it8_days: Math.max(7, +f.it8_days.value || 90), compare_engines: f.compare_engines.value.split(',').map(x => x.trim()).filter(Boolean), claude_tools: f.claude_tools.value.trim() });
    if (S.view === 'editor') { const st = await api.get('state', { rel: S.rel }); S.names = st.names || {}; renderSide(); }
  }, true], ['Cancel', () => true]]);
}

// ------------------------------------------------------------ lavori
let jobTimer = null;
async function pollJobs() {
  clearTimeout(jobTimer);
  S.jobs = await api.get('jobs').catch(() => S.jobs);
  updateJobBar();
  if (S.view === 'jobs') renderJobs();
  const active = S.jobs.some(j => j.status === 'running' || j.status === 'queued');
  if (active || S.view === 'jobs') jobTimer = setTimeout(pollJobs, active ? 900 : 3000);
  if (!active && S._wasActive) { refreshItems(); renderNav(); if (S.view === 'editor') { const st = await api.get('state', { rel: S.rel }); if (st.version !== S.st.version) { setState(st); renderSide(); draw(); } } }
  S._wasActive = active;
}
function updateJobBar() {
  const bar = $('#jobbar'); if (!bar) return;
  const j = S.jobs.find(x => x.status === 'running' && x.kind !== 'claude');
  bar.style.display = j ? '' : 'none';
  if (j) { bar.firstChild.style.width = Math.round(100 * j.done / j.total) + '%'; status(`${j.kind}: ${j.done}/${j.total}`, true); }
}
function renderJobs() {
  const main = $('#main'); main.innerHTML = '';
  const t = h('table', { class: 'table' }, h('tr', {}, h('th', {}, 'Job'), h('th', { style: { width: '150px' } }, 'Progress'), h('th', {}, 'Log'), h('th', {}, '')));
  for (const j of S.jobs) {
    const pct = Math.round(100 * j.done / j.total);
    t.append(h('tr', {}, h('td', {}, h('b', {}, j.kind), h('div', { class: 'small muted' }, new Date(j.created * 1000).toLocaleTimeString()), h('div', { class: 'small muted' }, j.args.engine || '')),
      h('td', {}, h('div', { class: 'progress' + (j.status === 'running' && j.kind === 'claude' ? ' marquee' : '') }, h('i', { style: { width: (j.status === 'done' ? 100 : pct) + '%' } })), h('div', { class: 'small muted' }, `${j.status} · ${j.done}/${j.total}`)),
      h('td', {}, h('div', { class: 'log', style: { maxHeight: '160px', overflow: 'auto' } }, j.log.slice(-60).join('\n'))),
      h('td', {}, ['running', 'queued'].includes(j.status) ? h('button', { class: 'btn small', onclick: () => api.post('cancel', { id: j.id }).then(pollJobs) }, 'Cancel') : null)));
  }
  main.append(addressBar(null, null, 'Jobs'),
    h('div', { style: { flex: 1, overflow: 'auto' } }, S.jobs.length ? t : h('div', { class: 'empty' }, 'No jobs yet. Select scans in a folder and use Batch.')));
}

// ------------------------------------------------------------ scanner e script
// ------------------------------------------------------------ scanner (SANE)
const SC = { devs: null, dev: null, opts: null, areas: [], sel: -1, img: null, job: null, pct: 0 };
const PRESETS = [['A4', 210, 297], ['A5', 148, 210], ['A5 landscape', 210, 148], ['Letter', 215.9, 279.4], ['10 × 15 cm', 100, 150], ['13 × 18 cm', 130, 180], ['A6', 105, 148]];
async function renderScanners() {
  const main = $('#main'); main.innerHTML = '';
  const bed = h('div', { class: 'bedwrap' }); const side = h('div', { class: 'scanside' });
  main.append(addressBar(null, null, 'Scanners'), h('div', { class: 'scanpage' }, bed, side));
  side.append(h('div', { class: 'group' }, h('div', { class: 'gh' }, 'Scanner'), h('div', { class: 'muted' }, 'Looking for scanners…')));
  if (!SC.devs) {
    const r = await api.get('scanners', SC.retry ? { refresh: 1 } : undefined).catch(e => ({ error: e.message, available: true, devices: [] }));
    SC.retry = true;
    // nel frattempo la pagina puo' essere stata ridisegnata: questa e' vecchia, non tocca niente
    if (S.view !== 'scanners' || !bed.isConnected) return;
    if (!r.available) {
      side.innerHTML = '';
      side.append(group('Scanner driver', h('div', {}, 'Scanning needs SANE, the open-source scanner driver (the only one that gives the LiDE 400 its 48-bit mode on the Mac).'),
        h('div', { class: 'btns' }, h('button', { class: 'btn default', onclick: async () => { const j = await api.post('jobs', { kind: 'install', what: 'sane' }); status('Installing SANE…'); const t = async () => { const x = await api.get('job', { id: j.id }); if (['queued', 'running'].includes(x.status)) return setTimeout(t, 1000); status(x.status === 'done' ? 'SANE installed' : 'SANE install failed: see Jobs'); SC.devs = null; renderScanners(); }; t(); } }, 'Install the scanner driver'),
          info('Runs “brew install sane-backends” (Homebrew must be installed). Takes a minute.'))));
      return;
    }
    SC.devs = r.devices || [];
    SC.dev = SC.devs.find(d => d.id === S.settings.scan_device) || SC.devs[0] || null;
    SC.res = S.settings.scan_res || 600; SC.mode = S.settings.scan_mode || 'Color'; SC.batch = S.settings.scan_batch || 'scan';
    loadPreview();
  }
  if (!bed.isConnected) return;
  bedCanvas(bed);
  renderScanSide(side);
}
function loadAreaPreview() {
  api.get('scanner_preview_area', { meta: 1 }).then(m => {
    if (!m.area) return;
    const im = new Image(); im.onload = () => { SC.zoom = { img: im, area: m.area }; drawBed(); }; im.src = '/api/scanner_preview_area?t=' + Date.now();
  }).catch(() => {});
}
function loadPreview() { const im = new Image(); im.onload = () => { SC.img = im; SC.zoom = null; drawBed(); }; im.onerror = () => { SC.img = null; drawBed(); }; im.src = '/api/scanner_preview?t=' + Date.now(); }
function renderScanSide(side) {
  side = side || $('.scanside'); if (!side) return; side.innerHTML = '';
  const o = SC.dev?.options || {};
  if (SC.dev && o.error) {
    side.append(group('Scanner', h('div', { style: { color: '#b03030' } }, `${SC.dev.name} is connected but not responding (${o.error}).`),
      h('div', { class: 'small', style: { margin: '6px 0' } }, 'This happens after a scan was cut off halfway. Unplug the scanner’s USB cable for about 10 seconds, plug it back in, then:'),
      h('button', { class: 'btn default', onclick: () => { SC.devs = null; renderScanners(); } }, 'Look again')));
    return;
  }
  if (!SC.devs.length) {
    side.append(group('Scanner', h('div', { class: 'muted' }, 'No scanner found. Plug in the LiDE 400, switch it on, then '), h('button', { class: 'btn', onclick: () => { SC.devs = null; renderScanners(); } }, 'Look again')));
    return;
  }
  const running = SC.job && ['queued', 'running'].includes(SC.job.status);
  side.append(group('Scanner',
    h('select', { onchange: e => { SC.dev = SC.devs.find(d => d.id === e.target.value); renderScanSide(); } }, SC.devs.map(d => h('option', { value: d.id, selected: d === SC.dev }, d.name))),
    h('div', { class: 'small muted', style: { marginTop: '4px' } }, `Bed ${o.width_mm?.toFixed(1)} × ${o.height_mm?.toFixed(1)} mm · up to ${Math.max(...(o.resolutions || [0]))} dpi · via SANE`),
    h('div', { class: 'btns' }, h('button', { class: 'btn', disabled: running, onclick: () => startScanJob('preview') }, 'Preview whole bed'), info('A quick 75 dpi scan of the whole bed (about 15 s), to see where your sheets are and draw the areas to scan.'))));
  const list = h('div');
  SC.areas.forEach((a, i) => {
    const ar = (a[4] && a[4].res) || SC.res, am = (a[4] && a[4].mode) || SC.mode;
    const px = [Math.round(a[2] / 25.4 * ar), Math.round(a[3] / 25.4 * ar)];
    const mb = px[0] * px[1] * (am.startsWith('Gray') || am.includes('gray') ? 1 : 3) * (am.includes('48') || am.includes('16') ? 2 : 1) / 1048576;
    const own = a[4] || {}, res = own.res || SC.res, mode = own.mode || SC.mode;
    list.append(h('div', { class: 'sheet' + (i === SC.sel ? ' sel' : ''), onclick: () => { SC.sel = i; drawBed(); renderScanSide(); } },
      h('span', { class: 'dot', style: { background: COLORS[i % COLORS.length] } }), h('span', {}),
      h('div', { class: 'nm' }, `${a[2].toFixed(0)} × ${a[3].toFixed(0)} mm`, h('small', {}, `${px[0]} × ${px[1]} px · ${mb.toFixed(0)} MB${a[4] ? ` · own: ${res} dpi, ${mode}` : ''}`)),
      h('button', { class: 'btn small', title: 'Remove this area', onclick: e => { e.stopPropagation(); SC.areas.splice(i, 1); SC.sel = -1; drawBed(); renderScanSide(); } }, '✕')));
  });
  if (!SC.areas.length) list.append(h('div', { class: 'muted small' }, 'No areas: the whole bed is scanned. Drag on the bed to draw an area, or add a format:'));
  const cur = SC.areas[SC.sel];
  if (cur) {
    const own = cur[4] || {};
    const setOwn = (k, v) => { const o = Object.assign({}, cur[4] || {}); if (v) o[k] = v; else delete o[k]; if (Object.keys(o).length) cur[4] = o; else cur.length = 4; renderScanSide(); };
    list.append(h('div', { class: 'multi' }, h('div', { class: 'mh' }, `Area ${SC.sel + 1}`),
      h('div', { class: 'row' }, h('label', {}, 'Resolution'), h('select', { class: 'f', onchange: e => setOwn('res', +e.target.value || null) },
        h('option', { value: '' }, `as below (${SC.res} dpi)`), (o.resolutions || []).map(r => h('option', { value: r, selected: own.res === r }, r + ' dpi')))),
      h('div', { class: 'row' }, h('label', {}, 'Colour'), h('select', { class: 'f', onchange: e => setOwn('mode', e.target.value || null) },
        h('option', { value: '' }, `as below (${SC.mode})`), (o.modes || []).filter(m => m !== 'Lineart').map(m => h('option', { value: m, selected: own.mode === m }, m)))),
      h('div', { class: 'btns' }, h('button', { class: 'btn small', disabled: running, onclick: () => startScanJob('preview', cur) }, 'Preview this area (300 dpi)'),
        info('A quick sharper look at just this area (a few seconds), drawn in place on the bed, to put the edges exactly where you want them.'))));
  }
  const sets = S.settings.frame_sets || {};
  side.append(group('Areas', list,
    h('div', { class: 'chips', style: { marginTop: '6px' } }, PRESETS.map(([n, w, hh]) => h('span', { class: 'chip', title: `Add a ${n} area at the top left of the bed`, onclick: () => addArea(w, hh) }, n))),
    h('div', { class: 'row' }, h('label', {}, 'Frame sets'),
      h('select', { class: 'f', onchange: e => { if (e.target.value) { SC.areas = JSON.parse(JSON.stringify(sets[e.target.value])); SC.sel = -1; drawBed(); renderScanSide(); } } },
        h('option', { value: '' }, Object.keys(sets).length ? 'Load…' : '(none saved)'), Object.keys(sets).map(k => h('option', { value: k }, k))),
      info('Saved groups of areas, e.g. "two A5 side by side". Draw the areas, then Save.')),
    h('div', { class: 'btns' },
      h('button', { class: 'btn small', disabled: !SC.areas.length, onclick: saveFrameSet }, 'Save areas as…'),
      h('button', { class: 'btn small', disabled: !SC.areas.length, onclick: () => { SC.areas = []; SC.sel = -1; drawBed(); renderScanSide(); } }, 'Clear'))));
  const deep = m => m.includes('48') || m.includes('16 bits');
  side.append(group('Settings',
    h('div', { class: 'row' }, h('label', {}, 'Resolution'), h('select', { class: 'f', onchange: e => { SC.res = +e.target.value; renderScanSide(); } },
      (o.resolutions || [300, 600]).map(r => h('option', { value: r, selected: r === SC.res }, r + ' dpi' + (r === 4800 ? ' (no extra detail, measured)' : r === 2400 ? ' (finest real detail)' : '')))),
      info('Only the resolutions the scanner itself offers, never upscaled. Measured on your LiDE 400 (1 cm of paper and pencil, 4 Nov 2026): 1200 shows clearly more than 600, 2400 adds a little fibre detail, 4800 adds nothing over 2400 (4× the file). Drawings: 600; fine pencil or texture: 1200; maximum real detail: 2400.')),
    h('div', { class: 'row' }, h('label', {}, 'Colour'), h('select', { class: 'f', onchange: e => { SC.mode = e.target.value; renderScanSide(); } },
      (o.modes || ['Color']).filter(m => m !== 'Lineart').map(m => h('option', { value: m, selected: m === SC.mode },
        ({ Color: 'Colour (24-bit)', Gray: 'Grey (8-bit)', '48 bits color': 'Colour 48-bit (16 per channel)', '16 bits gray': 'Grey 16-bit' })[m] || m))),
      info('48-bit colour and 16-bit grey keep 65,536 levels per channel instead of 256: smoother gradients and room for later corrections. Detection works on an 8-bit view; exported cutouts keep all 16 bits (16-bit PNG or JPEG XL). Files are twice as large.')),
    h('div', { class: 'row' }, h('label', {}, 'Batch'), h('input', { type: 'text', class: 'f', value: SC.batch, oninput: e => { SC.batch = e.target.value; nextName(); } }),
      info('Scans are named “<batch> <number>.tif” and go to the inbox; the agent moves them to originals/<batch>/ and cuts them, like your Image Capture scans.')),
    h('div', { class: 'small muted', id: 'nextname' }, '')));
  nextName();
  SC.every = SC.every || 15;
  side.append(group('Session',
    h('div', { class: 'small muted' }, 'For many pages by hand: put a page on the bed, scan, swap, repeat. Every scan gets the next number in the batch.'),
    h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!SC.spaceMode, onchange: e => { SC.spaceMode = e.target.checked; renderScanSide(); } }), ' Space bar scans the next page', info('Big-button mode: press Space (anywhere on this page) to scan the next page with the current areas and settings.')),
    SC.spaceMode ? h('div', { style: { textAlign: 'center', margin: '8px 0' } },
      h('div', { class: 'orb big', title: 'Scan the next page (Space)', onclick: scanNextPage }, svg(I.orb_cut)), h('div', { class: 'small muted' }, 'Space · next page')) : null,
    h('div', { class: 'row' }, h('label', {}, 'Every'), h('input', { type: 'number', min: 3, max: 600, step: 1, value: SC.every, class: 'f', onchange: e => { SC.every = Math.max(3, +e.target.value || 15); } }), h('span', { class: 'muted' }, 's'),
      SC.timed ? h('button', { class: 'btn', onclick: stopTimed }, 'Stop') : h('button', { class: 'btn', disabled: running, onclick: startTimed }, 'Start timed'),
      info('Timed scanning: a countdown with three beeps, then a scan, again and again, so you can swap pages without touching the Mac. Stop or Esc ends it.')),
    h('div', { class: 'small' }, `Pages this session: ${SC.pages || 0}`)));
  const pct = running ? Math.round(SC.job.pct || 0) : 0;
  side.append(group('Scan',
    h('div', { class: 'btns' }, h('button', { class: 'btn default', style: { minWidth: '140px', height: '28px' }, disabled: running, onclick: () => startScanJob('scan') },
      SC.areas.length > 1 ? `Scan ${SC.areas.length} areas` : 'Scan'),
      running ? h('button', { class: 'btn', onclick: () => api.post('cancel', { id: SC.job.id }) }, 'Cancel') : null),
    running ? h('div', { style: { marginTop: '8px' } }, h('div', { class: 'progress' }, h('i', { style: { width: pct + '%' } })), h('div', { class: 'small muted' }, (SC.job.kind === 'preview' ? 'Preview' : 'Scanning') + ` · ${pct}%`)) : null,
    SC.job?.status === 'done' && SC.job.kind === 'scan' ? h('div', { class: 'small', style: { color: '#2d7a2d', marginTop: '6px' } }, `✓ ${SC.job.done} scan(s) in the inbox; the agent is cutting them.`) : null,
    SC.job?.status === 'failed' ? h('div', { class: 'small', style: { color: '#b03030', marginTop: '6px' } }, SC.job.log.at(-1)) : null));
}
async function nextName() {
  const el = $('#nextname'); if (!el) return;
  const r = await api.get('next_scan_name', { batch: SC.batch || 'scan' }).catch(() => null);
  if (r) el.textContent = 'Next file: inbox/' + r.name;
}
function addArea(w, hh) {
  const o = SC.dev.options; w = Math.min(w, o.width_mm); hh = Math.min(hh, o.height_mm);
  SC.areas.push([0, 0, w, hh]); SC.sel = SC.areas.length - 1; drawBed(); renderScanSide();
}
function saveFrameSet() {
  const inp = h('input', { type: 'text', value: '', placeholder: 'e.g. two A5 side by side' });
  dialog('Frame sets', 'Save these areas', h('div', { style: { width: '380px' } }, inp), [['Save', async () => {
    const n = inp.value.trim(); if (!n) return false;
    const sets = Object.assign({}, S.settings.frame_sets || {}, { [n]: SC.areas });
    S.settings = await api.post('settings', { frame_sets: sets }); renderScanSide();
  }, true], ['Cancel', () => true]]);
  setTimeout(() => inp.focus(), 0);
}
async function startScanJob(kind, area) {
  if (!SC.dev) return;
  const body = kind === 'preview' ? { kind, dev: SC.dev.id, area: area ? area.slice(0, 4) : null } : { kind, dev: SC.dev.id, res: SC.res, mode: SC.mode, batch: SC.batch, areas: SC.areas, rels: SC.areas.length ? SC.areas : [0] };
  SC.job = await api.post('jobs', body).catch(e => (alertDialog('Scanner', e.message), null));
  if (!SC.job) return null;
  renderScanSide();
  return new Promise(resolve => {
    const tick = async () => {
      const j = await api.get('job', { id: SC.job.id }).catch(() => null); if (!j) return resolve(null);
      SC.job = j; if (S.view === 'scanners') renderScanSide();
      if (['queued', 'running'].includes(j.status)) return setTimeout(tick, 500);
      if (j.kind === 'preview' && j.status === 'done') { if (j.args.area) loadAreaPreview(); else loadPreview(); }
      if (j.kind === 'scan' && j.status === 'done') { SC.pages = (SC.pages || 0) + j.done; status(`${j.done} scan(s) in the inbox`); setTimeout(() => api.get('tree').then(t => { S.tree = t.tree; renderNav(); }), 1500); }
      resolve(j);
    };
    tick();
  });
}
// sessione pagina per pagina: Spazio per la prossima, o a tempo con il conto alla rovescia
let beepCtx = null;
function beep(f = 880, ms = 90) {
  try {
    beepCtx = beepCtx || new AudioContext();
    const o = beepCtx.createOscillator(), g = beepCtx.createGain();
    o.frequency.value = f; g.gain.value = 0.06; o.connect(g); g.connect(beepCtx.destination); o.start(); o.stop(beepCtx.currentTime + ms / 1000);
  } catch (e) {}
}
async function scanNextPage() {
  if (!SC.dev || (SC.job && ['queued', 'running'].includes(SC.job.status))) return;
  await startScanJob('scan');
}
async function startTimed() {
  SC.timed = true; renderScanSide();
  while (SC.timed && S.view === 'scanners') {
    for (let t = SC.every; t > 0 && SC.timed; t--) {
      SC.countdown = t; drawBed();
      if (t <= 3) beep(t === 1 ? 1320 : 880);
      await new Promise(r => setTimeout(r, 1000));
    }
    SC.countdown = 0; drawBed();
    if (!SC.timed) break;
    const j = await startScanJob('scan');
    if (!j || j.status !== 'done') { SC.timed = false; break; }
  }
  SC.timed = false; SC.countdown = 0; drawBed(); renderScanSide();
}
function stopTimed() { SC.timed = false; SC.countdown = 0; drawBed(); renderScanSide(); }
let bedcv, bedctx, bedV = { s: 1, ox: 0, oy: 0 }, bedDrag = null;
function bedCanvas(wrap) {
  bedcv = h('canvas'); wrap.append(bedcv); bedctx = bedcv.getContext('2d');
  new ResizeObserver(() => drawBed()).observe(wrap);
  const mm = e => { const r = bedcv.getBoundingClientRect(); return [(e.clientX - r.left - bedV.ox) / bedV.s, (e.clientY - r.top - bedV.oy) / bedV.s]; };
  const clampA = a => { const o = SC.dev.options; a[2] = Math.max(5, Math.min(a[2], o.width_mm)); a[3] = Math.max(5, Math.min(a[3], o.height_mm)); a[0] = Math.max(0, Math.min(a[0], o.width_mm - a[2])); a[1] = Math.max(0, Math.min(a[1], o.height_mm - a[3])); return a; };
  bedcv.addEventListener('pointerdown', e => {
    if (!SC.dev) return; bedcv.setPointerCapture(e.pointerId);
    const p = mm(e), tol = 6 / bedV.s;
    const sel = SC.areas[SC.sel];
    if (sel) {
      for (const [cx, cy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) if (Math.abs(p[0] - (sel[0] + cx * sel[2])) < tol && Math.abs(p[1] - (sel[1] + cy * sel[3])) < tol) { bedDrag = { resize: [cx, cy], start: sel.slice(), p }; return; }
    }
    const hit = SC.areas.map((a, i) => [a, i]).reverse().find(([a]) => p[0] >= a[0] && p[0] <= a[0] + a[2] && p[1] >= a[1] && p[1] <= a[1] + a[3]);
    if (hit) { SC.sel = hit[1]; bedDrag = { move: true, start: hit[0].slice(), p }; renderScanSide(); drawBed(); return; }
    bedDrag = { create: p }; SC.sel = -1;
  });
  bedcv.addEventListener('pointermove', e => {
    if (!bedDrag) return; const p = mm(e), o0 = bedDrag.p || bedDrag.create, d = [p[0] - o0[0], p[1] - o0[1]];
    if (bedDrag.create) bedDrag.box = [Math.min(p[0], o0[0]), Math.min(p[1], o0[1]), Math.abs(d[0]), Math.abs(d[1])];
    else if (bedDrag.move) { const a = SC.areas[SC.sel]; a[0] = bedDrag.start[0] + d[0]; a[1] = bedDrag.start[1] + d[1]; clampA(a); }
    else if (bedDrag.resize) {
      const a = SC.areas[SC.sel], s0 = bedDrag.start, [cx, cy] = bedDrag.resize;
      if (cx) a[2] = s0[2] + d[0]; else { a[0] = s0[0] + d[0]; a[2] = s0[2] - d[0]; }
      if (cy) a[3] = s0[3] + d[1]; else { a[1] = s0[1] + d[1]; a[3] = s0[3] - d[1]; }
      if (a[2] < 5) a[2] = 5; if (a[3] < 5) a[3] = 5; clampA(a);
    }
    drawBed();
  });
  bedcv.addEventListener('pointerup', () => {
    if (bedDrag?.box && bedDrag.box[2] > 5 && bedDrag.box[3] > 5) { SC.areas.push(clampA(bedDrag.box.map(v => Math.round(v * 10) / 10))); SC.sel = SC.areas.length - 1; }
    bedDrag = null; drawBed(); renderScanSide();
  });
}
function drawBed() {
  if (!bedcv || !SC.dev) return;
  const wrap = bedcv.parentElement, r = wrap.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  bedcv.width = r.width * dpr; bedcv.height = r.height * dpr; bedcv.style.width = r.width + 'px'; bedcv.style.height = r.height + 'px';
  const c = bedctx, o = SC.dev.options; c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.fillStyle = bgPaint(c); c.fillRect(0, 0, r.width, r.height);
  const m = 24; bedV.s = Math.min((r.width - 2 * m) / o.width_mm, (r.height - 2 * m) / o.height_mm);
  bedV.ox = (r.width - o.width_mm * bedV.s) / 2; bedV.oy = (r.height - o.height_mm * bedV.s) / 2;
  const X = v => bedV.ox + v * bedV.s, Y = v => bedV.oy + v * bedV.s;
  c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 10; c.shadowOffsetY = 2; c.fillStyle = '#f4f4f2'; c.fillRect(X(0), Y(0), o.width_mm * bedV.s, o.height_mm * bedV.s); c.restore();
  if (SC.img) c.drawImage(SC.img, X(0), Y(0), o.width_mm * bedV.s, o.height_mm * bedV.s);
  if (SC.zoom) { const z = SC.zoom.area; c.drawImage(SC.zoom.img, X(z[0]), Y(z[1]), z[2] * bedV.s, z[3] * bedV.s); }
  else { c.fillStyle = '#7a8796'; c.font = '13px "Segoe UI", Tahoma, sans-serif'; c.textAlign = 'center'; c.fillText('Press “Preview whole bed” to see what is on the scanner', X(o.width_mm / 2), Y(o.height_mm / 2)); c.textAlign = 'left'; }
  const areas = SC.areas;
  if (areas.length) { c.save(); c.beginPath(); c.rect(X(0), Y(0), o.width_mm * bedV.s, o.height_mm * bedV.s); areas.forEach(a => c.rect(X(a[0]), Y(a[1]), a[2] * bedV.s, a[3] * bedV.s)); c.fillStyle = 'rgba(20,30,45,.35)'; c.fill('evenodd'); c.restore(); }
  areas.forEach((a, i) => {
    const col = COLORS[i % COLORS.length];
    c.save(); c.lineWidth = i === SC.sel ? 2.5 : 1.5; c.strokeStyle = col; c.setLineDash(i === SC.sel ? [] : [6, 4]); c.strokeRect(X(a[0]), Y(a[1]), a[2] * bedV.s, a[3] * bedV.s); c.setLineDash([]);
    const label = `${i + 1} · ${a[2].toFixed(0)} × ${a[3].toFixed(0)} mm`; c.font = '600 11px "Segoe UI", Tahoma, sans-serif'; const w = c.measureText(label).width + 10;
    c.fillStyle = col; c.fillRect(X(a[0]), Y(a[1]) - 17, w, 16); c.fillStyle = '#fff'; c.fillText(label, X(a[0]) + 5, Y(a[1]) - 5);
    if (i === SC.sel) [[0, 0], [1, 0], [0, 1], [1, 1]].forEach(([cx, cy]) => { c.fillStyle = '#fff'; c.strokeStyle = '#000'; c.lineWidth = 1; c.fillRect(X(a[0] + cx * a[2]) - 4, Y(a[1] + cy * a[3]) - 4, 8, 8); c.strokeRect(X(a[0] + cx * a[2]) - 4, Y(a[1] + cy * a[3]) - 4, 8, 8); });
    c.restore();
  });
  if (SC.countdown) {
    const r2 = bedcv.parentElement.getBoundingClientRect(), cx = r2.width / 2, cy = r2.height / 2;
    c.save(); c.fillStyle = 'rgba(16,40,64,.55)'; c.beginPath(); c.roundRect(cx - 150, cy - 90, 300, 180, 14); c.fill();
    c.strokeStyle = 'rgba(255,255,255,.6)'; c.lineWidth = 2; c.stroke();
    c.fillStyle = '#fff'; c.textAlign = 'center'; c.font = '600 72px "Segoe UI", Tahoma, sans-serif'; c.fillText(String(SC.countdown), cx, cy + 20);
    c.font = '15px "Segoe UI", Tahoma, sans-serif'; c.fillText('next page · Esc stops', cx, cy + 62); c.restore();
  }
  if (bedDrag?.box) { const b = bedDrag.box; c.save(); c.setLineDash([4, 3]); c.strokeStyle = '#000'; c.strokeRect(X(b[0]), Y(b[1]), b[2] * bedV.s, b[3] * bedV.s); c.fillStyle = 'rgba(51,153,255,.15)'; c.fillRect(X(b[0]), Y(b[1]), b[2] * bedV.s, b[3] * bedV.s); c.restore(); }
}
// ------------------------------------------------------------ componenti aggiuntivi
const ADD = { list: null, jobs: {}, err: {}, token: '' };
async function renderAddons(refresh = true) {
  const main = $('#main');
  if (refresh || !ADD.list) ADD.list = await api.get('addons').catch(e => (status(e.message), []));
  if (S.view !== 'addons') return;
  main.innerHTML = '';
  const row = a => {
    const job = ADD.jobs[a.id];
    const pill = h('span', { class: 'pill ' + (a.ok ? 'ok' : 'no') }, a.ok ? (a.id === 'sam3' ? '✓ Found' : '✓ Installed') : 'Not installed');
    const btn = job ? h('button', { class: 'btn', disabled: true }, 'Installing…')
      : a.id === 'sam3' || (a.ok && a.id !== 'helpers') ? null
      : h('button', { class: 'btn' + (a.ok ? '' : ' default'), disabled: !!a.blocked, onclick: () => installAddon(a.id) }, a.ok ? 'Rebuild' : 'Install');
    return h('div', { class: 'addon' },
      h('div', { class: 'addon-main' },
        h('div', {}, h('b', {}, a.name), ' ', pill),
        h('div', {}, a.ok && a.path ? 'Meta’s segmentation model.' : a.line),
        a.path ? h('div', { class: 'small muted' }, a.path) : h('code', { class: 'small muted' }, a.cmd),
        a.blocked ? h('div', { class: 'small warn' }, a.blocked) : null,
        ADD.err[a.id] ? h('div', { class: 'small warn' }, ADD.err[a.id]) : null,
        a.id === 'sam3' && !a.ok ? h('div', { class: 'addon-steps' },
          h('div', {}, '1. ', h('a', { href: '#', onclick: e => { e.preventDefault(); api.post('open', { what: 'sam3page' }); } }, 'Request access on Hugging Face'), ' (free account; Meta approves it).'),
          h('div', {}, '2. ', h('a', { href: '#', onclick: e => { e.preventDefault(); api.post('open', { what: 'hftokens' }); } }, 'Create a read token'), ', paste it, download. Not stored.'),
          h('div', { class: 'row' }, h('input', { class: 'f', type: 'password', placeholder: 'hf_… (or leave empty after “hf auth login”)', value: ADD.token, oninput: e => { ADD.token = e.target.value; } }),
            job ? h('button', { class: 'btn', disabled: true }, 'Downloading…')
              : h('button', { class: 'btn default', onclick: () => installAddon('sam3', { token: ADD.token }) }, 'Download'))) : null),
      btn);
  };
  const groups = [['Tools', ADD.list.filter(a => !a.group)], ['SAM 3', ADD.list.filter(a => a.group === 'SAM 3')]];
  main.append(addressBar(null, null, 'Add-ons'), h('div', { style: { padding: '14px', overflow: 'auto', maxWidth: '780px' } },
    h('div', { class: 'muted', style: { marginBottom: '10px' } }, 'Optional. Cutting works without any of these.'),
    ...groups.map(([t, l], i) => h('div', { class: 'group', style: { margin: i ? '16px 0 0' : 0 } }, h('div', { class: 'gh' }, t), l.map(row)))));
}
async function installAddon(id, extra = {}) {
  delete ADD.err[id];
  const j = await api.post('jobs', { kind: 'install', what: id, ...extra });
  ADD.jobs[id] = j.id; renderAddons(false);
  for (;;) {
    await new Promise(r => setTimeout(r, 1000));
    const x = await api.get('job', { id: j.id });
    if (['queued', 'running'].includes(x.status)) continue;
    delete ADD.jobs[id];
    if (x.status !== 'done') ADD.err[id] = (x.log.filter(l => l.startsWith('ERROR')).pop() || 'Failed: see Jobs').replace(/^ERROR \w+: /, '');
    if (id === 'sam3' && x.status === 'done') ADD.token = '';
    S.engines = await api.get('engines');
    status(x.status === 'done' ? 'Installed' : 'Install failed');
    return renderAddons();
  }
}
function renderScripts() {
  const main = $('#main'); main.innerHTML = '';
  const scripts = S.engines.filter(e => e.kind === 'script');
  main.append(addressBar(null, null, 'Scripts'), h('div', { style: { padding: '14px', overflow: 'auto', maxWidth: '760px' } },
    h('div', { class: 'group', style: { margin: 0 } }, h('div', { class: 'gh' }, 'Your engines'),
      scripts.length ? scripts.map(e => h('div', { class: 'row' }, svg(I.script), h('b', {}, e.name), h('span', { class: 'muted' }, e.note))) : h('div', { class: 'muted' }, 'None yet.'),
      h('div', { class: 'btns' }, h('button', { class: 'btn', onclick: () => api.post('open', { what: 'scripts' }) }, 'Open scripts folder'), h('button', { class: 'btn', onclick: async () => { S.engines = await api.get('engines'); renderScripts(); } }, 'Refresh'))),
    h('div', { class: 'group', style: { margin: '16px 0 0' } }, h('div', { class: 'gh' }, 'Writing one'),
      h('div', {}, 'Each .py file in scripts/ becomes an engine. It needs one function:'),
      h('pre', { class: 'log', style: { background: '#f6f8fb', border: '1px solid #dde5ee', padding: '8px' } },
        "NAME = 'My cutter'\nNOTE = 'what it is good for'\n\ndef segment(rgb, ppm, params):\n    # rgb: HxWx3 uint8 scan, ppm: pixels per mm\n    # return a list of masks (HxW bool), one per sheet,\n    # or dicts {'mask': ..., 'holes': ...}\n    return [mask]"),
      h('div', { class: 'muted' }, 'It is reloaded on every run, so you can edit and press Detect again. See example_threshold.py.'))));
}

// ------------------------------------------------------------ Claude
function toggleChat() {
  const d = $('#drawer');
  if (d.classList.toggle('on') && !d.firstChild) {
    const log = h('div', { class: 'chatlog' }, h('div', { class: 'muted small' }, 'Claude Code runs headless in the project folder and can read this scan, its edit state and the studio API. Try: "why is the left edge of sheet b ragged?" or "detect all scans in sketchbook with classic and export them".'));
    const inp = h('textarea', { rows: 2, class: 'f', placeholder: 'Ask Claude…', onkeydown: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } } });
    const cont = h('input', { type: 'checkbox', checked: true, title: 'Continue the same conversation' });
    const send = async () => {
      const m = inp.value.trim(); if (!m) return; inp.value = '';
      log.append(h('div', { class: 'me' }, m));
      const out = h('div', { class: 'ai' }, h('div', { class: 'progress marquee', style: { width: '120px' } }, h('i')));
      log.append(out); log.scrollTop = 1e9;
      const j = await api.post('jobs', { kind: 'claude', message: m, rel: S.view === 'editor' ? S.rel : null, resume: cont.checked }).catch(e => ({ error: e.message }));
      if (j.error) { out.textContent = j.error; return; }
      pollJobs();
      const tick = async () => {
        const r = await api.get('job', { id: j.id }).catch(() => null); if (!r) return;
        out.innerHTML = '';
        r.log.forEach(l => out.append(h('div', { class: l.startsWith('⚙') ? 'tool' : '' }, l)));
        if (r.status === 'running' || r.status === 'queued') { out.append(h('div', { class: 'progress marquee', style: { width: '120px', marginTop: '4px' } }, h('i'))); setTimeout(tick, 800); }
        log.scrollTop = 1e9;
      };
      tick();
    };
    const box = h('div', { class: 'dlg' },
      h('div', { class: 'titlebar' }, h('svg', {}), h('div', { class: 'title' }, h('span', {}, 'Ask Claude')), h('div', { class: 'caption' }, h('span', { class: 'close', onclick: toggleChat }, '✕'))),
      h('div', { class: 'content', style: { display: 'flex', flexDirection: 'column' } }, log,
        h('div', { class: 'chatin' }, inp, h('div', { style: { display: 'flex', flexDirection: 'column', gap: '4px' } }, h('button', { class: 'btn default', onclick: send }, 'Send'), h('label', { class: 'small' }, cont, ' continue')))));
    d.append(box);
    setTimeout(() => inp.focus(), 0);
  }
}

// ------------------------------------------------------------ finestra (pywebview senza cornice)
// nell'app del Dock la finestra e' trasparente: fuori dalla cornice Vista non si disegna niente
if (window.__scanStudioApp || window.webkit?.messageHandlers?.studio) document.documentElement.classList.add('native');
$$('.caption [data-win]').forEach(el => el.addEventListener('click', () => {
  const a = window.pywebview?.api; const w = el.dataset.win;
  // nell'app del Dock (WebKit nativo): riduci nel Dock, ingrandisci, chiudi davvero
  const mac = window.webkit?.messageHandlers?.studio;
  if (mac) return mac.postMessage({ cmd: w });
  if (a) return a[w]?.();
  // in Chrome: ingrandisci = schermo intero, riduci = nascondi la finestra, chiudi = chiudi
  if (w === 'max') return document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
  if (w === 'min') return api.post('open', { what: 'hide' });
  if (w === 'close') { flushSave().finally(() => window.close()); }
}));

// ------------------------------------------------------------ pannelli ridimensionabili
function applyPaneSizes() {
  $('#nav').style.width = (+store('navw') || 210) + 'px';
  $('#side').style.width = (+store('sidew') || 290) + 'px';
}
function splitter(el, key, sign, min, max) {
  el.addEventListener('pointerdown', e => {
    el.setPointerCapture(e.pointerId); el.classList.add('on');
    const pane = $(key === 'navw' ? '#nav' : '#side'), w0 = pane.getBoundingClientRect().width, x0 = e.clientX;
    const move = ev => { const w = Math.max(min, Math.min(max, w0 + sign * (ev.clientX - x0))); pane.style.width = w + 'px'; store(key, Math.round(w)); };
    const up = () => { el.classList.remove('on'); el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
  });
  el.addEventListener('dblclick', () => { store(key, ''); applyPaneSizes(); });
}
applyPaneSizes();
splitter($('#split1'), 'navw', 1, 140, 480);
splitter($('#split2'), 'sidew', -1, 220, 620);

// ------------------------------------------------------------ promemoria IT8 (ogni 90 giorni, rimandabile)
async function it8Reminder() {
  const s = S.settings, day = 86400, now = Date.now() / 1000;
  if (!s.it8_remind) return;
  if (!s.it8_last) { S.settings = await api.post('settings', { it8_last: now }); return; }   // si comincia a contare oggi
  if (now < s.it8_last + (s.it8_days || 90) * day || now < (s.it8_snooze || 0)) return;
  const since = Math.round((now - s.it8_last) / day);
  const c = await choose('Colour calibration', 'Time to recalibrate the scanner colours?',
    `The last IT8 calibration (or the start of the count) was ${since} days ago. Scanner lamps and sensors drift slowly; recalibrating every ${s.it8_days || 90} days keeps colours accurate. You need the IT8.7/2 chart and about five minutes.`,
    [['snooze', 'Remind me in 2 weeks', true], ['done', 'I calibrated today'], ['off', 'Turn off reminders']]);
  if (c === 'snooze') S.settings = await api.post('settings', { it8_snooze: now + 14 * day });
  if (c === 'done') S.settings = await api.post('settings', { it8_last: now, it8_snooze: 0 });
  if (c === 'off') { S.settings = await api.post('settings', { it8_remind: false }); status('IT8 reminders off (Settings › Colour calibration)'); }
}

// ------------------------------------------------------------ avvio
(async function init() {
  renderCmdbar(); renderNavbar();
  const [t, engines, settings] = await Promise.all([api.get('tree'), api.get('engines'), api.get('settings')]);
  api.get('ping').then(p => { S.version = p.version; renderNav(); }).catch(() => {});
  S.root = t.root; S.tree = t.tree; S.engines = engines; S.settings = settings;
  renderNav();
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash) { S.dir = hash.split('/').slice(0, -1).join('/'); S.items = await api.get('list', { dir: S.dir }).catch(() => []); openScan(hash); }
  else openDir('originals');
  pollJobs();
  setTimeout(it8Reminder, 2500);
  setInterval(async () => { const t = await api.get('tree').catch(() => null); if (t && JSON.stringify(t.tree) !== JSON.stringify(S.tree)) { S.tree = t.tree; renderNav(); if (S.view === 'gallery') refreshItems(); } }, 5000);
})();
