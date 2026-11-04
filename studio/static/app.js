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
const fmtSize = b => b > 1 << 20 ? (b / (1 << 20)).toFixed(1) + ' MB' : Math.round(b / 1024) + ' KB';
const COLORS = ['#3399ff', '#ff8c1a', '#2fb84f', '#c84ad0', '#e0b600', '#14b8c4', '#ff4d5e', '#7a6cff'];
const CMP_COLORS = { auto: '#00a2ff', classic: '#ff7a00', vision: '#d100d1', sam3: '#00b050' };

// ------------------------------------------------------------ icone (stile Vista, piccole)
const I = {
  folder: '<svg class="ico" viewBox="0 0 16 16"><defs><linearGradient id="fg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff2b0"/><stop offset="1" stop-color="#e8b33c"/></linearGradient></defs><path d="M1 4h5l1.5 1.5H15v8.5H1z" fill="url(#fg)" stroke="#b07d16"/><path d="M1.5 7h13.5" stroke="#fff" opacity=".7"/></svg>',
  pics: '<svg class="ico" viewBox="0 0 16 16"><rect x="1.5" y="2.5" width="13" height="11" rx="1" fill="#e9f4ff" stroke="#3a6ea5"/><path d="M3 12l3.5-4 2.5 3 2-2 2.5 3z" fill="#2fa84f"/><circle cx="11" cy="5.5" r="1.4" fill="#ffc83d"/></svg>',
  cut: '<svg class="ico" viewBox="0 0 16 16"><circle cx="4" cy="12" r="2.3" fill="none" stroke="#c03030" stroke-width="1.4"/><circle cx="12" cy="12" r="2.3" fill="none" stroke="#c03030" stroke-width="1.4"/><path d="M5.5 10.5L12 2M10.5 10.5L4 2" stroke="#555" stroke-width="1.3"/></svg>',
  warn: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 1.5l7 12.5H1z" fill="#ffd34d" stroke="#b58500"/><path d="M8 6v4" stroke="#333" stroke-width="1.6"/><circle cx="8" cy="12" r=".9" fill="#333"/></svg>',
  inbox: '<svg class="ico" viewBox="0 0 16 16"><path d="M1.5 9l2-6h9l2 6v4.5h-13z" fill="#dfeefe" stroke="#3a6ea5"/><path d="M1.5 9h4l1 2h3l1-2h4" fill="none" stroke="#3a6ea5"/></svg>',
  jobs: '<svg class="ico" viewBox="0 0 16 16"><rect x="1.5" y="3" width="13" height="10" rx="1" fill="#fff" stroke="#566d86"/><rect x="3" y="5" width="7" height="2" fill="#36b51a"/><rect x="3" y="9" width="10" height="2" fill="#9fd88f"/></svg>',
  scanner: '<svg class="ico" viewBox="0 0 16 16"><rect x="1" y="6" width="14" height="6" rx="1.5" fill="#d9e3ee" stroke="#4a5c70"/><rect x="2" y="4" width="12" height="2.5" rx="1" fill="#9fb5cc" stroke="#4a5c70"/><rect x="3" y="9" width="6" height="1" fill="#33aaff"/><circle cx="12.5" cy="9.5" r=".9" fill="#5be35b"/></svg>',
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
  compare: null, hist: [], fut: [], open: new Set(['originals']), jobs: [], chat: null,
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
      h('div', { class: 'mi' + (it.disabled ? ' disabled' : ''), onclick: () => { closeMenu(); it.do && it.do(); } },
        it.check ? h('span', { class: 'ck' }, '✓') : null, it.label, it.kbd ? h('span', { class: 'kbd' }, it.kbd) : null)));
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
      '-', { label: 'Fit', disabled: !ed, kbd: '⌘0', do: fit }, { label: 'Actual pixels', disabled: !ed, kbd: '⌘1', do: actual },
      '-', { label: 'Reset pane sizes', do: () => { store('navw', ''); store('sidew', ''); applyPaneSizes(); } },
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
    node('Settings', I.gear, 'v:settings', { onclick: settingsDialog }),
  ));
}

// ------------------------------------------------------------ viste
async function go(view) {
  if (S.view === 'editor' && view !== 'editor') leaveEditor();
  S.view = view;
  renderCmdbar(); renderNav(); renderNavbar();
  if (view === 'gallery') renderGallery();
  if (view === 'jobs') renderJobs();
  if (view === 'scanners') renderScanners();
  if (view === 'scripts') renderScripts();
  renderSide();
}
async function openDir(rel) {
  S.dir = rel; S.sel.clear(); S.anchor = null;
  S.open.add(rel.split('/')[0]);
  S.items = await api.get('list', { dir: rel }).catch(e => (status(e.message), []));
  go('gallery');
}
const crumbs = (...parts) => h('div', { class: 'crumbs' }, ...parts);
const visibleItems = () => S.items.filter(i => !i.dir && (!S.filter || i.name.toLowerCase().includes(S.filter.toLowerCase())));
function selectAll() { visibleItems().forEach(i => S.sel.add(i.rel)); }

function renderGallery() {
  const main = $('#main'); main.innerHTML = '';
  const items = visibleItems();
  const grid = h('div', { class: 'gallery', tabindex: 0 });
  const sub = S.items.filter(i => i.dir && (!S.filter || i.name.toLowerCase().includes(S.filter.toLowerCase())));
  sub.forEach(c => grid.append(h('div', { class: 'thumb', title: c.name, ondblclick: () => openDir(c.rel), onclick: () => openDir(c.rel) },
    h('div', { class: 'pic', html: I.folder.replace('class="ico"', 'width="96" height="96"') }), h('div', { class: 'cap' }, `${c.name} (${c.count})`))));
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
      h('div', { class: 'pic' }, h('img', { src: `/api/thumb?${qs({ rel: it.rel, size: 256 })}&m=${it.mtime}`, loading: 'lazy', draggable: 'false' })),
      h('div', { class: 'cap' }, it.name));
    grid.append(el);
  });
  const t = S.tree.flatMap(n => [n, ...n.children]).find(n => n.rel === S.dir);
  main.append(crumbs(h('b', {}, S.dir.split('/').join(' ▸ ')), h('span', { class: 'sub' }, `${items.length} item${items.length !== 1 ? 's' : ''}${S.sel.size ? `, ${S.sel.size} selected` : ''}`)), grid);
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
      h('div', {}, h('div', { class: 'rn' }, e.name), h('div', { class: 'rd' }, e.available ? e.note : (e.id === 'sam3' ? 'Needs ~/sam3.pt (the file DigitalSreeni Image Annotator uses).' : 'Not available.')))));
  }
  const e = S.engines.find(x => x.id === S.engine);
  for (const p of e?.params || []) {
    const v = S.params[p.id] ?? p.default;
    const inp = p.type === 'bool' ? h('input', { type: 'checkbox', checked: !!v, onchange: ev => S.params[p.id] = ev.target.checked })
      : h('input', { type: p.type === 'number' ? 'number' : 'text', step: p.step, value: v, class: 'f', oninput: ev => S.params[p.id] = p.type === 'number' ? +ev.target.value : ev.target.value });
    box.append(h('div', { class: 'row' }, h('label', {}, p.label), inp));
  }
  return box;
}
const engParams = () => { const e = S.engines.find(x => x.id === S.engine); const o = {}; for (const p of e?.params || []) o[p.id] = S.params[p.id] ?? p.default; return o; };

function sideGallery(side) {
  const sel = S.items.filter(i => S.sel.has(i.rel));
  if (sel.length === 1) {
    const it = sel[0];
    side.append(group('Info',
      h('div', { style: { textAlign: 'center', margin: '4px 0 8px' } }, h('img', { src: `/api/thumb?${qs({ rel: it.rel, size: 256 })}&m=${it.mtime}`, style: { maxWidth: '100%', maxHeight: '220px', boxShadow: '0 1px 4px rgba(0,0,0,.35)' } })),
      h('div', { class: 'row' }, h('label', {}, 'Name'), h('div', { class: 'f' }, it.name)),
      h('div', { class: 'row' }, h('label', {}, 'Size'), h('div', { class: 'f' }, fmtSize(it.size))),
      h('div', { class: 'row' }, h('label', {}, 'Date'), h('div', { class: 'f' }, new Date(it.mtime * 1000).toLocaleString())),
      h('div', { class: 'row' }, h('label', {}, 'Status'), h('div', { class: 'f' }, it.done ? (it.done === 'ok' ? 'Cut by the agent' : it.done === 'studio' ? 'Exported from the studio' : 'Failed, needs a look') : 'Not cut yet')),
      h('div', { class: 'btns' }, h('button', { class: 'btn default', onclick: () => openScan(it.rel) }, 'Open'), h('button', { class: 'btn', onclick: () => api.post('open', { what: 'finder', rel: it.rel }) }, 'Show in Finder'))));
  } else {
    side.append(group('Folder', h('div', { class: 'muted' }, sel.length ? `${sel.length} scans selected.` : 'Select scans (⌘-click, ⇧-click) to run a batch, or double-click one to open it.')));
  }
  side.append(group('Engine', engineChooser()),
    group('Batch',
      h('div', { class: 'btns' },
        h('button', { class: 'btn', disabled: !sel.length, onclick: () => batch(false) }, 'Detect'),
        h('button', { class: 'btn default', disabled: !sel.length, onclick: () => batch(true) }, 'Detect + export'),
        h('button', { class: 'btn', disabled: !sel.some(i => i.sheets), onclick: () => exportMany(sel.filter(i => i.sheets).map(i => i.rel)) }, 'Export edited')),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Batches run in the background; see Jobs. Existing cutouts are never overwritten: changed ones are moved to studio-data/replaced.')));
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
    list.append(h('div', { class: 'sheet' + (S.selSheet === s.id ? ' sel' : ''), onclick: () => { S.selSheet = s.id; renderSide(); draw(); } },
      h('input', { type: 'checkbox', checked: s.on !== false, title: 'Export this sheet', onclick: e => e.stopPropagation(), onchange: e => commit(() => { s.on = e.target.checked; }) }),
      h('span', { class: 'dot', style: { background: COLORS[i % COLORS.length] } }),
      h('div', { class: 'nm', title: name || '' }, (name ? name.split('/').pop() : 'not exported') , h('small', {}, `${s.engine || 'manual'}${sheetEdited(s) ? ' · edited' : ''}${s.holes?.length ? ` · ${s.holes.length} hole(s)` : ''}`)),
      h('div', {}, h('button', { class: 'btn small', title: 'Preview the cutout', onclick: e => { e.stopPropagation(); cutoutDialog(s); } }, '👁'))));
  });
  if (!st?.sheets.length) list.append(h('div', { class: 'muted' }, 'No sheets yet. Press Detect, or draw one with the polygon or box tool.'));
  const sel = st?.sheets.find(s => s.id === S.selSheet);
  side.append(group('Sheets', list, sel ? h('div', { style: { marginTop: '6px' } },
    h('div', { class: 'row' }, h('label', {}, 'Label'), h('input', { type: 'text', class: 'f', value: sel.label || '', placeholder: 'used by {label} in names',
      onchange: e => commit(() => { sel.label = e.target.value; }) })),
    h('div', { class: 'btns' },
      h('button', { class: 'btn small', disabled: !sheetEdited(sel) || !sel.poly0, onclick: () => commit(() => { sel.poly = JSON.parse(JSON.stringify(sel.poly0)); sel.ops = []; }) }, 'Undo all edits'),
      h('button', { class: 'btn small', onclick: () => commit(() => { st.sheets = st.sheets.filter(x => x !== sel); S.selSheet = null; }) }, 'Remove'))) : null));
  side.append(group('Save',
    h('div', { class: 'small muted' }, 'Names follow the template in Settings: ', h('code', {}, S.settings.template)),
    h('div', { class: 'btns' },
      h('button', { class: 'btn default', disabled: !st?.sheets.some(s => s.on !== false), onclick: doExport }, 'Export'),
      h('button', { class: 'btn', onclick: () => api.post('open', { what: 'finder', rel: S.rel }) }, 'Original in Finder')),
    st?.exported ? h('div', { class: 'small', style: { marginTop: '6px', color: '#2d7a2d' } }, '✓ Exported ' + new Date(st.exported * 1000).toLocaleString()) : null));
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
  S.rel = rel; S.selSheet = null; S.compare = null; S.hist = []; S.fut = []; V.tile = V.mtile = null;
  const parts = rel.split('/'); if (parts.length >= 3) S.dir = parts.slice(0, -1).join('/');
  S.view = 'editor';
  renderCmdbar(); renderNav(); renderNavbar();
  const main = $('#main'); main.innerHTML = '';
  const tools = [['select', I.t_select, 'Select (V)'], ['hand', I.t_hand, 'Pan (H, or hold Space)'], ['points', I.t_points, 'Edit points (A): drag; double-click an edge adds, ⌥-click removes'],
    ['poly', I.t_poly, 'New sheet by polygon (P): click points, Enter to close'], ['rect', I.t_rect, 'Rectangle (M): add or cut a rectangle'], ['lasso', I.t_lasso_add, 'Lasso (L; K = lasso in Cut mode)'],
    ['wand', I.t_wand, 'Magic wand (W): click a colour, like Photoshop'], ['brush', I.t_brush_add, 'Brush (B; E = eraser)'], ['box', I.t_box, 'Detect inside a box (R) with the chosen engine']];
  const tb = h('div', { class: 'toolbox' }, tools.map(([id, ic, tip]) => h('div', { class: 'tool' + (S.tool === id ? ' on' : ''), 'data-tool': id, title: tip, onclick: () => setTool(id) }, svg(ic))),
    h('hr'),
    h('div', { class: 'modes', title: 'What lasso, rectangle, wand and brush do. X swaps, hold ⌥ for the other one.' },
      h('div', { class: 'mode' + (S.mode === 'add' ? ' on' : ''), 'data-mode': 'add', onclick: () => setMode('add') }, '＋'),
      h('div', { class: 'mode' + (S.mode === 'sub' ? ' on' : ''), 'data-mode': 'sub', onclick: () => setMode('sub') }, '－')),
    h('div', { class: 'opt', id: 'modename' }, S.mode === 'add' ? 'Add' : 'Cut'),
    h('hr'), h('div', { class: 'opt' }, 'Brush'), h('input', { type: 'range', min: 0.2, max: 10, step: 0.1, value: S.brushMM, title: 'Brush size in mm ([ and ])', oninput: e => { S.brushMM = +e.target.value; $('#bsz').textContent = S.brushMM.toFixed(1) + ' mm'; } }),
    h('div', { class: 'opt', id: 'bsz' }, S.brushMM.toFixed(1) + ' mm'),
    h('hr'), h('div', { class: 'opt' }, 'Wand'), h('input', { type: 'range', min: 1, max: 80, step: 1, value: S.wandTol, title: 'Tolerance, like Photoshop (the automatic cut uses about 13-15)', oninput: e => { S.wandTol = +e.target.value; $('#wtol').textContent = 'tol ' + S.wandTol; } }),
    h('div', { class: 'opt', id: 'wtol' }, 'tol ' + S.wandTol),
    h('label', { class: 'opt', title: 'Only touching pixels (off: the same colour anywhere)' }, h('input', { type: 'checkbox', checked: S.wandContig, onchange: e => S.wandContig = e.target.checked }), ' contig.'),
    h('hr'),
    h('label', { class: 'opt', title: 'Darken what will be cut away (O)' }, h('input', { type: 'checkbox', id: 'cutview', checked: S.showCut, onchange: e => { S.showCut = e.target.checked; requestTile(); draw(); } }), h('br'), 'Cut view'));
  const stage = h('div', { class: 'stage bg-' + S.bg });
  cv = h('canvas'); hud = h('div', { class: 'hud' }); busyEl = h('div', { class: 'busy' }, h('div', { style: { width: '220px', background: '#fff', padding: '12px', border: '1px solid #9bb', borderRadius: '4px', boxShadow: '0 3px 12px rgba(0,0,0,.25)' } }, h('div', { id: 'busymsg', style: { marginBottom: '6px' } }, 'Working…'), h('div', { class: 'progress marquee' }, h('i'))));
  stage.append(cv, hud, busyEl);
  main.append(crumbs(h('b', {}, parts.slice(0, -1).join(' ▸ ')), ' ▸ ', parts.at(-1), h('span', { class: 'sub', id: 'edsub' }, '')), h('div', { class: 'editor' }, tb, stage));
  ctx = cv.getContext('2d');
  bindCanvas(stage);
  new ResizeObserver(() => { resize(); draw(); }).observe(stage);
  $('#title').textContent = `${parts.at(-1)} - Scan Studio`;
  try {
    const [info, st] = await Promise.all([api.get('info', { rel }), api.get('state', { rel })]);
    if (S.rel !== rel) return;
    S.info = info; setState(st);
    const im = new Image(); im.src = `/api/preview?${qs({ rel })}`; await im.decode();
    if (S.rel !== rel) return;
    V.img = im; V.pScale = im.naturalWidth / info.w;
    resize(); fit(); renderSide(); renderCmdbar();
    // alla prima apertura solo il taglio automatico (veloce); SAM e gli altri motori solo con Detect
    if (!st.sheets.length && !st.engine) detect(null, 'auto');
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
function setMode(m) { S.mode = m; $$('.toolbox .mode').forEach(el => el.classList.toggle('on', el.dataset.mode === m)); const n = $('#modename'); if (n) n.textContent = m === 'add' ? 'Add' : 'Cut'; }
function setBg(b) { S.bg = b; store('bg', b); const st = $('.stage'); if (st) st.className = 'stage bg-' + b; renderCmdbar(); }
function setTool(t) { S.tool = t; S.poly = null; $$('.toolbox .tool').forEach(el => el.classList.toggle('on', el.dataset.tool === t)); cv && (cv.style.cursor = cursorFor(t)); draw(); }
const cursorFor = t => ({ hand: 'grab', select: 'default', points: 'default', box: 'crosshair', poly: 'crosshair', rect: 'crosshair', lasso: 'crosshair', wand: 'crosshair', brush: 'none' })[t];

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
  // la scansione con un'ombra, come una foto in Photo Gallery
  const [ix, iy] = toScr(0, 0), iw = S.info.w * V.s, ih = S.info.h * V.s;
  c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 8; c.shadowOffsetY = 2; c.fillStyle = '#fff'; c.fillRect(ix, iy, iw, ih); c.restore();
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
    const col = COLORS[i % COLORS.length], sel = s.id === S.selSheet, off = s.on === false;
    c.save();
    c.beginPath(); polyPath(c, s.poly);
    if (off) c.setLineDash([4, 4]);
    c.lineWidth = sel ? 3.5 : 2.5; c.strokeStyle = 'rgba(255,255,255,.85)'; c.stroke();
    c.lineWidth = sel ? 2 : 1.25; c.strokeStyle = off ? '#888' : col; c.stroke();
    if (sel) { c.fillStyle = col + '14'; c.fill(); }
    for (const o of s.ops) {
      c.beginPath(); c.strokeStyle = c.fillStyle = o.op === 'add' ? 'rgba(40,170,60,.35)' : 'rgba(220,40,40,.35)';
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
    if (sel && (S.tool === 'points')) {
      c.fillStyle = '#fff'; c.strokeStyle = '#000'; c.lineWidth = 1;
      s.poly.forEach((q, k) => { const [x, y] = toScr(...q); const hot = drag?.vertex === k || hoverV === k; c.fillStyle = hot ? col : '#fff'; c.fillRect(x - 3.5, y - 3.5, 7, 7); c.strokeRect(x - 3.5, y - 3.5, 7, 7); });
    }
    c.restore();
  });
  // disegno in corso
  if (S.poly?.length) { c.save(); c.beginPath(); const [x, y] = toScr(...S.poly[0]); c.moveTo(x, y); S.poly.forEach(p => c.lineTo(...toScr(...p))); if (mouse) c.lineTo(...toScr(...mouse)); c.strokeStyle = '#000'; c.setLineDash([4, 3]); c.lineWidth = 1.2; c.stroke(); S.poly.forEach(p => { const [a, b] = toScr(...p); c.fillStyle = '#fff'; c.fillRect(a - 3, b - 3, 6, 6); c.strokeRect(a - 3, b - 3, 6, 6); }); c.restore(); }
  if (drag?.lasso) { c.save(); c.beginPath(); polyPath(c, drag.lasso); c.fillStyle = drag.add ? 'rgba(40,170,60,.2)' : 'rgba(220,40,40,.2)'; c.fill(); c.setLineDash([4, 3]); c.strokeStyle = '#000'; c.stroke(); c.restore(); }
  if (drag?.stroke) { c.save(); c.beginPath(); c.lineCap = c.lineJoin = 'round'; c.lineWidth = 2 * drag.r * V.s; c.strokeStyle = drag.add ? 'rgba(40,170,60,.45)' : 'rgba(220,40,40,.45)'; const [x, y] = toScr(...drag.stroke[0]); c.moveTo(x, y); drag.stroke.forEach(p => c.lineTo(...toScr(...p))); c.stroke(); c.restore(); }
  if (drag?.rect) { c.save(); const [a, b] = toScr(drag.rect[0], drag.rect[1]), [e, f] = toScr(drag.rect[2], drag.rect[3]); c.setLineDash([4, 3]); c.strokeStyle = '#000'; c.strokeRect(a, b, e - a, f - b); c.fillStyle = drag.add ? 'rgba(40,170,60,.2)' : 'rgba(220,40,40,.2)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (drag?.box) { c.save(); const [a, b] = toScr(drag.box[0], drag.box[1]), [e, f] = toScr(drag.box[2], drag.box[3]); c.setLineDash([5, 3]); c.strokeStyle = '#000'; c.strokeRect(a, b, e - a, f - b); c.fillStyle = 'rgba(51,153,255,.12)'; c.fillRect(a, b, e - a, f - b); c.restore(); }
  if (mouse && S.tool === 'brush') { const [x, y] = toScr(...mouse); c.beginPath(); c.arc(x, y, Math.max(2, brushR() * V.s), 0, 7); c.strokeStyle = '#000'; c.lineWidth = 1; c.stroke(); c.strokeStyle = '#fff'; c.setLineDash([3, 3]); c.stroke(); }
  hud.textContent = `${Math.round(V.s * V.dpr * 100)}%` + (mouse ? ` · ${Math.round(mouse[0])}, ${Math.round(mouse[1])} px · ${(mouse[0] / S.info.ppm).toFixed(1)}, ${(mouse[1] / S.info.ppm).toFixed(1)} mm` : '');
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
    if (tool === 'select') {
      const s = sheetAt(pt); S.selSheet = s?.id || null; renderSide(); draw();
      if (!s) drag = { pan: [sx - V.ox, sy - V.oy] };
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
    const add = (S.mode === 'add') !== e.altKey;
    if (tool === 'lasso') { drag = { lasso: [rnd(pt)], add }; return; }
    if (tool === 'rect') { drag = { rect: [...pt, ...pt], add }; return; }
    if (tool === 'brush') { drag = { stroke: [rnd(pt)], r: brushR(), add }; draw(); return; }
    if (tool === 'wand') { wandAt(pt, add); return; }
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
    if (S.tool === 'points') { const s = S.st?.sheets.find(x => x.id === S.selSheet); const k = s ? nearestVertex(s, sx, sy) : -1; if (k !== hoverV) { hoverV = k; } cv.style.cursor = k >= 0 ? (e.altKey ? 'not-allowed' : 'move') : 'default'; }
    draw();
  });
  const up = e => {
    const d = drag; drag = null; cv.style.cursor = cursorFor(spaceDown ? 'hand' : S.tool);
    if (!d) return;
    if (d.vertex != null) { afterEdit(); return; }
    if (d.lasso && d.lasso.length > 2) applyRegion({ kind: 'poly', pts: d.lasso }, d.add);
    if (d.stroke) applyRegion({ kind: 'stroke', pts: d.stroke, r: d.r }, d.add);
    if (d.rect) {
      const [a, b, c2, d2] = [Math.min(d.rect[0], d.rect[2]), Math.min(d.rect[1], d.rect[3]), Math.max(d.rect[0], d.rect[2]), Math.max(d.rect[1], d.rect[3])].map(Math.round);
      if ((c2 - a) * V.s > 3 && (d2 - b) * V.s > 3) applyRegion({ kind: 'poly', pts: [[a, b], [c2, b], [c2, d2], [a, d2]] }, d.add);
    }
    if (d.box) {
      const b = [Math.min(d.box[0], d.box[2]), Math.min(d.box[1], d.box[3]), Math.max(d.box[0], d.box[2]), Math.max(d.box[1], d.box[3])].map(Math.round);
      if ((b[2] - b[0]) * V.s > 8 && (b[3] - b[1]) * V.s > 8) detect(b);
    }
    draw();
  };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('pointerleave', () => { mouse = null; draw(); });
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
    const mouseWheel = e.deltaMode === 1 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
    if (e.ctrlKey || e.metaKey || mouseWheel) zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025)), sx, sy);
    else { V.ox -= e.deltaX; V.oy -= e.deltaY; viewChanged(); }
  }, { passive: false });
}
function applyRegion(op, add) {
  const ob = bbox(op.pts).map((v, i) => v + (i < 2 ? -1 : 1) * (op.r || 0));
  const sheets = S.st.sheets;
  let targets = S.selSheet ? sheets.filter(s => s.id === S.selSheet) : sheets.filter(s => overlaps(bbox(s.poly), ob));
  if (add && !targets.length) {
    if (op.kind === 'poly') { commit(() => { const s = { id: newId(), src: null, engine: 'manual', poly0: null, poly: op.pts, ops: [], on: true, label: '', holes: [] }; sheets.push(s); S.selSheet = s.id; }); }
    else status('Brush: select a sheet first (or draw a new one with the lasso or polygon)');
    return;
  }
  if (!targets.length) return status('Nothing there to cut away');
  if (add && targets.length > 1) targets = targets.slice(0, 1);
  commit(() => targets.forEach(s => s.ops.push({ op: add ? 'add' : 'sub', ...op })));
}
async function wandAt(pt, add) {
  if (pt[0] < 0 || pt[1] < 0 || pt[0] >= S.info.w || pt[1] >= S.info.h) return;
  status('Magic wand…', true);
  let op;
  try { op = await api.post('wand', { rel: S.rel, x: Math.round(pt[0]), y: Math.round(pt[1]), tol: S.wandTol, contig: S.wandContig }); }
  catch (e) { return status('Wand: ' + e.message); }
  status(`Wand: ${(op.area / S.info.ppm / S.info.ppm / 100).toFixed(1)} cm² selected, tolerance ${op.tol}`);
  op.op = add ? 'add' : 'sub';
  const sheets = S.st.sheets;
  let targets = S.selSheet ? sheets.filter(s => s.id === S.selSheet) : sheets.filter(s => inside(op.seed, s.poly));
  if (!targets.length && !add) targets = sheets.filter(s => overlaps(bbox(s.poly), [op.pts[0][0], op.pts[0][1], op.pts[1][0], op.pts[1][1]]));
  if (!targets.length) {
    if (!add) return status('Nothing there to cut away');
    // un foglio nuovo fatto solo dalla bacchetta (es. un disegno cliccato sul coperchio)
    const outline = op.outline.reduce((a, p) => area(p) > area(a) ? p : a, op.outline[0]);
    return commit(() => { const s = { id: newId(), src: null, base: 'ops', engine: 'wand', poly0: null, poly: outline, ops: [op], on: true, label: '', holes: [] }; sheets.push(s); S.selSheet = s.id; });
  }
  commit(() => targets.slice(0, add ? 1 : targets.length).forEach(s => s.ops.push(op)));
}
function closePoly() {
  const p = S.poly; S.poly = null;
  if (p && p.length >= 3) commit(() => { const s = { id: newId(), src: null, engine: 'manual', poly0: null, poly: p, ops: [], on: true, label: '', holes: [] }; S.st.sheets.push(s); S.selSheet = s.id; });
  draw();
}
document.addEventListener('keydown', e => {
  if (e.target.closest('input, textarea, select')) return;
  const k = e.key, mod = e.metaKey || e.ctrlKey;
  if (mod && k === ',') { e.preventDefault(); return settingsDialog(); }
  if (S.view === 'gallery') {
    if (mod && k === 'a') { e.preventDefault(); selectAll(); renderGallery(); renderSide(); renderCmdbar(); }
    if (k === 'Enter' && S.sel.size) openScan([...S.sel][0]);
    if (k === 'ArrowRight') step(1); if (k === 'ArrowLeft') step(-1);
    return;
  }
  if (S.view !== 'editor') return;
  if (k === ' ') { if (!spaceDown) { spaceDown = true; cv.style.cursor = 'grab'; } e.preventDefault(); return; }
  if (mod && k.toLowerCase() === 'z') { e.preventDefault(); return e.shiftKey ? redo() : undo(); }
  if (mod && k === 's') { e.preventDefault(); return doExport(); }
  if (mod && k === '0') { e.preventDefault(); return fit(); }
  if (mod && k === '1') { e.preventDefault(); return actual(); }
  if (mod) return;
  const tools = { v: 'select', h: 'hand', a: 'points', p: 'poly', m: 'rect', l: 'lasso', k: 'lasso', w: 'wand', b: 'brush', e: 'brush', r: 'box' };
  const kl = k.toLowerCase();
  if (kl === 'x') return setMode(S.mode === 'add' ? 'sub' : 'add');
  if (tools[kl]) { if ('lb'.includes(kl)) setMode('add'); if ('ke'.includes(kl)) setMode('sub'); return setTool(tools[kl]); }
  if (k === 'Escape') { if (S.poly) { S.poly = null; draw(); } else if (openMenu) closeMenu(); else if ($('.dlg-back')) $('.dlg-back').remove(); else if (S.selSheet) { S.selSheet = null; renderSide(); draw(); } else go('gallery'); return; }
  if (k === 'Enter' && S.poly) return closePoly();
  if (k === '+' || k === '=') return zoomBy(1.4);
  if (k === '-') return zoomBy(1 / 1.4);
  if (k === '[' || k === ']') { S.brushMM = Math.max(0.2, Math.min(10, S.brushMM * (k === ']' ? 1.25 : 0.8))); $('#bsz') && ($('#bsz').textContent = S.brushMM.toFixed(1) + ' mm'); return draw(); }
  if (k === 'c') return toggleCompare();
  if (k === 'o') { S.showCut = !S.showCut; const cb = $('#cutview'); if (cb) cb.checked = S.showCut; requestTile(); return draw(); }
  if (k === 'Tab') { e.preventDefault(); const sh = S.st.sheets; if (!sh.length) return; const i = sh.findIndex(s => s.id === S.selSheet); S.selSheet = sh[(i + (e.shiftKey ? -1 : 1) + sh.length) % sh.length].id; renderSide(); return draw(); }
  if ((k === 'Delete' || k === 'Backspace') && S.selSheet) { const s = S.st.sheets.find(x => x.id === S.selSheet); commit(() => { if (s.src) s.on = !(s.on !== false); else { S.st.sheets = S.st.sheets.filter(x => x !== s); S.selSheet = null; } }); return; }
  if (k === 'ArrowRight') return step(1);
  if (k === 'ArrowLeft') return step(-1);
});
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
async function detect(box, engine) {
  if (!S.rel) return;
  await flushSave();
  engine = engine || S.engine;
  const eng = S.engines.find(e => e.id === engine);
  if (!eng?.available) return status(`${eng?.name || engine} is not available`);
  const many = Array.isArray(box);
  if (!many && S.st.sheets.some(sheetEdited) && !confirm('Detecting again replaces the sheets and your edits on them. Continue?')) return;
  busy(true, `${eng.name}${many ? ' (inside the box)' : ''}…` + (engine === 'sam3' && !S.samLoaded ? ' loading the model the first time (~10 s)' : ''));
  try {
    if (!many) pushHist();
    const r = await api.post('detect', { rel: S.rel, engine, params: engine === S.engine ? engParams() : {}, box: many ? box : null, replace: !many });
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
async function doExport() {
  if (S.view !== 'editor' || !S.st?.sheets.length) return;
  await flushSave();
  busy(true, 'Saving the cutouts…');
  try {
    const r = await api.post('export', { rel: S.rel });
    const moved = r.written.find(w => w.status === 'moved');
    if (moved) { S.rel = moved.rel; S.dir = moved.rel.split('/').slice(0, -1).join('/'); }
    const st = await api.get('state', { rel: S.rel }); setState(st);
    const list = r.written.map(w => `${w.status === 'identical' ? '= ' : w.status === 'moved' ? '→ ' : '✓ '}${w.path.replace(S.root + '/', '')}${w.moved_old ? '   (old one moved aside)' : ''}${w.status === 'moved' ? '   (the cutout you started from, kept)' : ''}`).join('\n');
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
    h('div', { class: 'titlebar' }, h('div', { class: 'title' }, title), h('div', { class: 'caption' }, h('span', { class: 'close', onclick: () => back.remove() }, '✕'))),
    h('div', { class: 'content', style: { display: 'flex', flexDirection: 'column' } },
      instr ? h('div', { class: 'main-instr' }, instr) : null, h('div', { class: 'inner', style: { flex: 1, overflow: 'auto' } }, body),
      h('div', { class: 'foot' }, (buttons || [['OK', () => true, true]]).map(([l, fn, def]) => h('button', { class: 'btn' + (def ? ' default' : ''), onclick: async () => { if ((await fn()) !== false) back.remove(); } }, l)))));
  back.append(d); document.body.append(back);
  return back;
}
const alertDialog = (title, body) => dialog('Scan Studio', title, typeof body === 'string' ? h('div', {}, body) : body);

function cutoutDialog(s) {
  let full = false;
  const img = h('img', { style: { display: 'block', margin: 'auto', maxWidth: '100%' } });
  const info = h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Rendering…');
  const box = h('div', { class: 'checker', style: { overflow: 'auto', maxHeight: '68vh', minHeight: '200px', border: '1px solid #ccc', cursor: 'zoom-in' } }, img);
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
    field('compare_engines', 'Compare', h('input', { type: 'text', value: (s.compare_engines || []).join(', ') }), 'Engines shown by Compare, e.g. classic, vision, sam3'),
    field('claude_tools', 'Claude may use', h('input', { type: 'text', value: s.claude_tools }), 'Passed to claude --allowedTools.'),
  );
  dialog('Settings', 'Scan Studio settings', body, [['OK', async () => {
    const bf = {}; f.batch_folders.value.split('\n').forEach(l => { const m = l.split('='); if (m.length >= 2 && m[0].trim()) bf[m[0].trim()] = m.slice(1).join('=').trim(); });
    S.settings = await api.post('settings', { out_root: f.out_root.value.trim() || 'cut', template: f.template.value.trim() || '{batch}/{stem}{sheet}', batch_folders: bf,
      eagle: f.eagle.checked, eagle_folder: f.eagle_folder.value.trim(), compare_engines: f.compare_engines.value.split(',').map(x => x.trim()).filter(Boolean), claude_tools: f.claude_tools.value.trim() });
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
  main.append(crumbs(h('b', {}, 'Jobs'), h('span', { class: 'sub' }, 'Batches, exports and Claude requests run here, one after another.')),
    h('div', { style: { flex: 1, overflow: 'auto' } }, S.jobs.length ? t : h('div', { class: 'empty' }, 'No jobs yet. Select scans in a folder and use Batch.')));
}

// ------------------------------------------------------------ scanner e script
async function renderScanners() {
  const main = $('#main'); main.innerHTML = '';
  const list = await api.get('scanners').catch(() => []);
  const card = s => h('div', { style: { display: 'flex', gap: '14px', alignItems: 'center', padding: '12px', border: '1px solid #d5dfe9', borderRadius: '4px', background: 'linear-gradient(#fff,#f3f7fb)', marginBottom: '8px' } },
    h('div', { html: I.scanner.replace('class="ico"', 'width="48" height="48"') }),
    h('div', { style: { flex: 1 } }, h('div', { style: { fontSize: '14px', color: '#1e3287' } }, s.name), h('div', { class: 'small muted' }, s.uri), h('div', { class: 'small muted' }, 'Driverless (eSCL over USB).')),
    h('div', { class: 'btns' }, h('button', { class: 'btn', onclick: () => api.post('open', { what: 'canon' }) }, 'IJ Scan Utility'), h('button', { class: 'btn', onclick: () => api.post('open', { what: 'imagecapture' }) }, 'Image Capture')));
  main.append(crumbs(h('b', {}, 'Scanners')), h('div', { style: { padding: '14px', overflow: 'auto' } },
    list.length ? list.map(card) : h('div', { class: 'muted' }, 'No scanner known to macOS right now. Plug in the Canon LiDE 400 and switch it on.'),
    h('div', { class: 'group', style: { margin: '16px 0 0', maxWidth: '640px' } }, h('div', { class: 'gh' }, 'How scans get here'),
      h('div', {}, 'Scan with Image Capture or IJ Scan Utility into ', h('b', {}, '~/Scans/inbox'), '. The agent moves each scan to originals/ and cuts it; open it here to check or fix the edges.'),
      h('div', { class: 'btns' }, h('button', { class: 'btn', onclick: () => api.post('open', { what: 'kick' }).then(() => status('Agent started')) }, 'Run the agent now'))),
    h('div', { class: 'group', style: { margin: '16px 0 0', maxWidth: '640px' } }, h('div', { class: 'gh' }, 'Coming next (milestone 2)'),
      h('div', { class: 'muted' }, 'Driving the scanner from here: preview scan of the whole bed, drag the scan area, DPI and colour mode, several scanners side by side, scanning straight into a batch.'))));
}
function renderScripts() {
  const main = $('#main'); main.innerHTML = '';
  const scripts = S.engines.filter(e => e.kind === 'script');
  main.append(crumbs(h('b', {}, 'Scripts'), h('span', { class: 'sub' }, '.scancut/scripts/')), h('div', { style: { padding: '14px', overflow: 'auto', maxWidth: '760px' } },
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
    const log = h('div', { class: 'chatlog' }, h('div', { class: 'muted small' }, 'Claude Code runs headless in .scancut and can read this scan, its edit state and the studio API. Try: "why is the left edge of sheet b ragged?" or "detect all scans in sketchbook with classic and export them".'));
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
      h('div', { class: 'titlebar' }, h('svg', {}), h('div', { class: 'title' }, 'Ask Claude'), h('div', { class: 'caption' }, h('span', { class: 'close', onclick: toggleChat }, '✕'))),
      h('div', { class: 'content', style: { display: 'flex', flexDirection: 'column' } }, log,
        h('div', { class: 'chatin' }, inp, h('div', { style: { display: 'flex', flexDirection: 'column', gap: '4px' } }, h('button', { class: 'btn default', onclick: send }, 'Send'), h('label', { class: 'small' }, cont, ' continue')))));
    d.append(box);
    setTimeout(() => inp.focus(), 0);
  }
}

// ------------------------------------------------------------ finestra (pywebview senza cornice)
$$('.caption [data-win]').forEach(el => el.addEventListener('click', () => {
  const a = window.pywebview?.api; const w = el.dataset.win;
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

// ------------------------------------------------------------ avvio
(async function init() {
  renderCmdbar(); renderNavbar();
  const [t, engines, settings] = await Promise.all([api.get('tree'), api.get('engines'), api.get('settings')]);
  S.root = t.root; S.tree = t.tree; S.engines = engines; S.settings = settings;
  renderNav();
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash) { S.dir = hash.split('/').slice(0, -1).join('/'); S.items = await api.get('list', { dir: S.dir }).catch(() => []); openScan(hash); }
  else openDir('originals');
  pollJobs();
  setInterval(async () => { const t = await api.get('tree').catch(() => null); if (t && JSON.stringify(t.tree) !== JSON.stringify(S.tree)) { S.tree = t.tree; renderNav(); if (S.view === 'gallery') refreshItems(); } }, 5000);
})();
