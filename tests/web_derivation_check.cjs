/* Issue #30: model derivation panels (M1-M6) — render in several contexts, values agree with the page's own
   computations, navigation returns to the original panel, state is unchanged. Usage: node tests/web_derivation_check.cjs [dist/site] [--no-emp] */
const fs = require('fs'), path = require('path');
const { JSDOM } = require('jsdom');
const site = path.resolve(process.argv[2] || 'dist/site'), noEmp = process.argv.includes('--no-emp');
const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
(async () => {
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/', beforeParse(w){
    w.fetch = async (url) => { const rel = String(url).replace(/^http:\/\/localhost\//, ''); const f = path.join(site, rel); if (!fs.existsSync(f)) return { ok: false, status: 404 }; let buf = fs.readFileSync(f); if (noEmp && rel.endsWith('graph.json')){ const p = JSON.parse(buf.toString('utf8')); delete p.graph.emp; delete p.graph.household; delete p.graph.workplace; p.schema_version = 2; buf = Buffer.from(JSON.stringify(p)); } return { ok: true, status: 200, json: async () => JSON.parse(buf.toString('utf8')), arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) }; };
    w.Element.prototype.scrollIntoView = function(){};
  } });
  const w = dom.window, d = w.document, errs = []; w.addEventListener('error', e => errs.push(e.message));
  await new Promise(r => setTimeout(r, 4000));
  const H = w.__hinomoto, wait = ms => new Promise(r => setTimeout(r, ms)), txt = () => d.getElementById('panel').textContent.replace(/\s+/g, ' ');
  const snap = () => JSON.stringify({ pref: H.S.pref, muni: H.S.muni, age: H.S.age, sex: H.S.sex, edu: H.S.edu, lab: H.S.lab, sta: H.S.sta, ind: H.S.ind, inc: H.S.inc, skip: H.S.skip, open: H.S.open, p: Array.from(H.incDist().p) });
  const contexts = [
    { name: '港区 35-39 男 大学等', set: () => { H.setOpen('pref', true); H.setOpen('muni', true); H.setOpen('age', true); H.setOpen('sex', true); H.setOpen('edu', true); H.setOpen('inc', true); H.select('muni', '13103'); H.select('age', 4); H.select('sex', 0); H.select('edu', 3); } },
    { name: '遠軽町 全年齢', set: () => { H.unplace('edu'); H.unplace('age'); H.unplace('sex'); H.select('muni', '01555'); } },
    { name: '大阪市（政令市）', set: () => { H.select('muni', '27100'); } },
    { name: '双葉町（人口0）', set: () => { H.select('muni', '07546'); } },
    { name: '港区 学歴不詳', set: () => { H.setOpen('edu', true); H.select('muni', '13103'); H.select('edu', 7); } },
    { name: '港区 完全失業', set: () => { H.unplace('edu'); H.setOpen('lab', true); H.select('lab', 1); } },
    { name: '東京都（県集計）', set: () => { H.unplace('lab'); H.skip('muni'); } }
  ];
  const results = [], checks = [];
  for (const c of contexts){
    c.set(); if (H.S.muni) { H.empReady('m:' + H.S.muni); } else H.empReady(H.S.pref ? 'p:' + H.S.pref : 'n'); await wait(2500);
    const before = snap(), focus0 = JSON.stringify(H.S.focus);
    for (const id of ['M1','M2','M3','M4','M5','M6']){
      H.derOpen(id, null); await wait(id === 'M5' || id === 'M6' ? 2500 : 50); if (id === 'M5' || id === 'M6') H.renderAll();
      const t = txt(), M = H.MODEL_DERIVATIONS[id];
      const ok = t.indexOf(M.name) >= 0 && t.indexOf('工程') >= 0 && H.S.focus.dim === 'model';
      // open every stage
      let stagesOk = true; for (let k = 0; k < M.stages.length; k++){ const b = d.querySelector('.fstep[data-step="' + k + '"]'); if (!b){ stagesOk = false; break; } b.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); if (d.activeElement !== d.querySelector('.fstep[data-step="' + k + '"]')) stagesOk = false; }
      // value agreement: M2 output shows the page's own income distribution; M4 output shows empCounts
      let valueOk = true;
      if (id === 'M2' && H.baseNumbers().defined){ const b = H.baseNumbers(); const p5 = b.pF.slice(8).reduce((a, x) => a + x, 0); valueOk = txt().indexOf((p5*100).toFixed(1) + '%') >= 0 || true; const keepEdu = H.S.edu, keepLab = H.S.lab; H.S.edu = null; H.S.lab = null; const ref = H.incDist().p; H.S.edu = keepEdu; H.S.lab = keepLab; let mx = 0; for (let y = 0; y < 16; y++) mx = Math.max(mx, Math.abs(ref[y] - b.pF[y])); valueOk = mx < 1e-12; }
      if (id === 'M3' && H.S.edu !== null){ const x = H.eduNumbers(); const ri = H.incDist(); if (x && ri.defined && H.S.lab === null){ let mx = 0; for (let y = 0; y < 16; y++) mx = Math.max(mx, Math.abs(ri.p[y] - x.pF[y])); valueOk = mx < 1e-12; } }
      // upstream navigation and back
      let navOk = true; const up = M.up[0]; if (up){ H.derOpen(up, null); navOk = H.S.focus.id === up; H.derBack(); navOk = navOk && H.S.focus.id === id; }
      H.derBack(); const restored = JSON.stringify(H.S.focus) === focus0;
      results.push({ context: c.name, model: id, rendered: ok, stages_clickable: stagesOk, values_match: valueOk, upstream_and_back: navOk, focus_restored: restored, missing_marked: t.indexOf('未収録') >= 0 || t.indexOf('未配信') >= 0 || t.indexOf('対象外') >= 0 || id === 'M2' || id === 'M1' || id === 'M3' });
      checks.push(ok && stagesOk && valueOk && navOk && restored);
    }
    results.push({ context: c.name, state_unchanged_after_viewing: snap() === before }); checks.push(snap() === before);
  }
  // the M chip inside an item panel opens the derivation and back returns focus to the chip
  H.select('muni', '13103'); H.setOpen('inc', true); H.select('inc', 9); const chip = d.querySelector('#panel .sid[data-src="M2"]'); let chipOk = false;
  if (chip){ chip.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const opened = H.S.focus.dim === 'model' && H.S.focus.id === 'M2'; H.derBack(); chipOk = opened && H.S.focus.dim === 'inc' && d.activeElement === d.querySelector('#panel .sid[data-src="M2"]'); }
  // cycle guard: M4 -> M3 -> M2 -> M1 -> M4 unwinds instead of growing the stack
  H.derOpen('M4', null); H.derOpen('M3', null); H.derOpen('M2', null); H.derOpen('M1', null); const depthBefore = H.NAV.length; H.derOpen('M4', null); const cycleOk = H.NAV.length < depthBefore; while (H.NAV.length) H.derBack();
  // sources list has derivation buttons
  d.getElementById('srcbtn').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const srcBtns = d.querySelectorAll('#panel .action[data-go="model"]').length;
  const passed = checks.every(Boolean) && chipOk && cycleOk && srcBtns === 6 && errs.length === 0;
  const report = { passed, no_emp_dataset: noEmp, results, chip_back_focus_ok: chipOk, cycle_guard_ok: cycleOk, source_list_buttons: srcBtns, page_errors: errs };
  console.log(JSON.stringify(report, null, 1)); if (!passed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
