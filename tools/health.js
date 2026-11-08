(async () => {
  // prova di salute dell'interfaccia: tools/snap "http://127.0.0.1:8799/" out.png 1400 880 60 tools/health.js
  // (server su una copia della radice). Ogni riga: secondi, PASS/FAIL, cosa.
  const R = window.__errs, T0 = Date.now(), ok = (c, m) => R.push(((Date.now() - T0) / 1000).toFixed(1) + (c ? ' PASS ' : ' FAIL ') + m), wait = ms => new Promise(r => setTimeout(r, ms));
  const until = async (f, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { if (f()) return true; await wait(100); } return false; };
  // la prima scansione degli originali e il primo ritaglio: solo su una COPIA della radice
  const firstIn = async (top, ok = () => true) => { for (const d of (await api.get('list', { dir: top })).filter(i => i.dir)) { const f = (await api.get('list', { dir: d.rel })).find(i => !i.dir && ok(i.rel)); if (f) return [d.rel, f.rel]; } return []; };
  // un taglio PNG (si gira senza perdita; un JPEG portato da fuori no)
  const [DIR, SCAN] = await firstIn('originals'), [, CUT] = await firstIn('cut', r => /\.png$/i.test(r));
  const img = async url => { const r = await fetch(url); const b = await createImageBitmap(await r.blob()); return [b.width, b.height]; };
  // mai sulle app vere (8765 Scan Studio, 8766 l'anteprima): detecta, taglia e gira file sul serio
  if (['8765', '8766'].includes(location.port)) { R.push('FAIL refused: run the health check on a scratch server (a copy of the scans), not on port ' + location.port); return; }
  try {
    // galleria e pagine dello studio
    await openDir(DIR); await wait(500);
    ok(S.view === 'gallery' && document.querySelectorAll('.thumb').length > 0, 'gallery shows scans');
    for (const v of ['jobs', 'scanners', 'scripts', 'addons']) { await go(v); await wait(700); ok(S.view === v && $('#main').children.length > 0, 'page ' + v); }
    ok(document.querySelectorAll('.addon').length >= 6, 'add-ons lists background models');
    // editor
    await openScan(SCAN); await until(() => S.info && V.img);
    ok(S.view === 'editor' && S.info.w > 0, 'editor opens scan');
    await api.post('detect', { rel: SCAN, engine: 'auto', params: {}, replace: true }); await openScan(SCAN); await until(() => S.st?.sheets.length);
    const n0 = S.st.sheets.length; ok(n0 > 0, `auto detect: ${n0} sheets`);
    // unita'
    S.engine = 'auto'; renderSide(); await wait(1500);
    ok([...document.querySelectorAll('.pu')].some(e => e.textContent.includes('× auto')), 'tolerance shows unit');
    ok(/Auto for this scan: [\d.]+/.test($('#side').textContent), 'tolerance shows real value');
    setTool('wand'); await wait(100); ok($('#optbar').textContent.includes('of 255'), 'wand unit');
    setTool('brush'); await wait(100); ok(/mm · \d+ px/.test($('#optbar').textContent), 'brush mm and px');
    setTool('select');
    // ruota il foglio: etichetta e ritaglio girati
    const sh = S.st.sheets[0]; selectIds([sh.id]);
    const [w0, h0] = await img(`/api/cutout?${qs({ rel: SCAN, id: sh.id, max: 400 })}`);
    rotateSheets([sh], 90); await flushSave();
    const [w1, h1] = await img(`/api/cutout?${qs({ rel: SCAN, id: sh.id, max: 400 })}&t=${Date.now()}`);
    ok(w1 === h0 && h1 === w0, `sheet rotate 90: cutout ${w0}x${h0} -> ${w1}x${h1}`);
    rotateSheets([sh], -90); await flushSave();
    // inverti e ritorna
    const ops0 = sh.ops.length; invertSelected(); await flushSave();
    ok(isInverted(S.st.sheets.find(x => x.id === sh.id)), 'invert on');
    const r = await fetch(`/api/masktile?${qs({ rel: SCAN, x: 0, y: 0, w: S.info.w, h: S.info.h, out: 200 })}`); ok(r.ok, 'mask of inverted sheet renders');
    invertSelected(); await flushSave();
    const back = S.st.sheets.find(x => x.id === sh.id);
    ok(!isInverted(back) && back.ops.length === ops0, 'invert again goes back exactly');
    invertSelected(); undo(); ok(!isInverted(S.st.sheets.find(x => x.id === sh.id)), 'undo of invert');
    // densitometro: resta, si chiude e si riapre senza il mouse sulla scansione
    measure([1500, 1500], 600, 300); await until(() => $('#dens').style.display === 'block');
    cv.dispatchEvent(new PointerEvent('pointerleave')); await wait(200);
    ok($('#dens').style.display === 'block', 'densitometer stays after leaving the scan');
    $('#dens .dh').click(); await wait(300); const shut = $('#dens').classList.contains('collapsed');
    $('#dens .dh').click(); await wait(300); ok(shut !== $('#dens').classList.contains('collapsed'), 'densitometer toggles');
    const d = $('#dens').getBoundingClientRect(), sp = $('#dens .dh span').getBoundingClientRect(); ok(sp.right <= d.right, 'densitometer text inside its frame');
    if (S.densShut) $('#dens .dh').click();
    // schede
    const nt = TABS.list.length; await newTab('scan:' + SCAN); ok(TABS.list.length === nt, 'same scan does not open twice');
    await newTab('dir:originals'); ok(TABS.list.length === nt + 1 && S.view === 'gallery', 'new tab');
    await switchTab(TABS.list.findIndex(t => t.loc === 'scan:' + SCAN)); await until(() => S.rel === SCAN && V.img);
    ok(S.view === 'editor' && S.rel === SCAN, 'switch back to scan tab');
    await closeTab(TABS.list.findIndex(t => t.loc === 'dir:originals')); ok(TABS.list.length === nt, 'close tab');
    // export
    await doExport(); await wait(300); ok(!!$('.dlg-back'), 'export dialog'); $('.dlg-back')?.remove();
    // ruota un ritaglio aperto: la selezione gira con l'immagine
    await openScan(CUT); await until(() => S.rel === CUT && V.img);
    await api.post('detect', { rel: CUT, engine: 'auto', params: {}, replace: true }); await openScan(CUT); await until(() => S.st?.sheets.length);
    const W = S.info.w, H = S.info.h, p = S.st.sheets[0].poly.map(q => q.slice());
    await rotateOpenFile(90); await until(() => S.info && S.info.w === H, 20000); await wait(800);
    ok(S.info.w === H && S.info.h === W, `cutout file rotated ${W}x${H} -> ${S.info.w}x${S.info.h}`);
    const p2 = S.st.sheets[0].poly, exp = p.map(([x, y]) => [H - y, x]);
    ok(JSON.stringify(p2) === JSON.stringify(exp), 'selection turned with the image');
    ok(V.img.naturalWidth / V.img.naturalHeight > 1 === (S.info.w > S.info.h), 'preview image is the rotated one');
    await rotateOpenFile(-90); await until(() => S.info && S.info.w === W, 20000);
    // alla fine: tutto cio' che deriva dalla libreria le corrisponde (tagli, testo nei tagli, pixel)
    const probs = await api.get('library/check', { deep: 1 }).catch(e => [{ kind: 'error', what: e.message }]);
    ok(!probs.length, 'library consistent (pixels included)' + (probs.length ? ': ' + probs.map(x => x.kind + ' ' + x.what).join('; ') : ''));
  } catch (e) { R.push('FAIL exception: ' + e.message + ' ' + (e.stack || '').split('\n')[1]); }
  R.push('DONE');
})(); 0;
