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
  // review cases (PR #31): (a) M4 output labels carry only the applied conditions and the values are the page's own
  // conditional counts; (b) M1/M2 stage order matches build.py / estimator.run: mixture (not distributed) -> calibration
  // for M1, and M2 tilts the mixture before calibration (M1's calibrated array is a comparison baseline, not an input)
  H.setOpen('pref', true); H.setOpen('muni', true); H.setOpen('age', true); H.setOpen('sex', true); H.setOpen('lab', true); H.select('muni', '13103'); H.select('age', 4); H.select('sex', 0); if (H.S.edu !== null) H.unplace('edu'); H.select('lab', 1); H.empReady('m:13103'); await wait(2500);
  const rev = {};
  if (!noEmp && H.S.lab === 1){ H.derOpen('M4', null); d.querySelector('.fstep[data-step="3"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const t4 = txt();
    const R = H.empCounts({ e: null, lab: null, sta: null, ind: null }); const pj1 = (R.J[0]/R.total*100).toFixed(1) + '%', pj2 = (R.J[1]/R.total*100).toFixed(1) + '%';
    rev.m4_marginal_label_ok = t4.indexOf('P(就業者｜35～39歳・男)') >= 0 && t4.indexOf('P(就業者｜35～39歳・男・完全失業者)') < 0;
    rev.m4_marginal_value_ok = t4.indexOf('P(就業者｜35～39歳・男)' + pj1) >= 0;
    rev.m4_selected_condition_row_ok = t4.indexOf('P(完全失業者｜35～39歳・男)' + pj2) >= 0;
    rev.m4_income_undefined_marked = t4.indexOf('未定義') >= 0 || t4.indexOf('≥500万円｜35～39歳・男・完全失業者') >= 0;
    H.derBack(); }
  H.unplace('lab'); if (!noEmp){ H.setOpen('sta', true); H.setOpen('ind', true); H.select('sta', 0); H.select('ind', 7); H.derOpen('M4', null); d.querySelector('.fstep[data-step="3"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const t4b = txt();
  { const Rs = H.empCounts({ e: null, lab: null, sta: null, ind: null }); const Rg = H.empCounts({ e: null, lab: null, sta: 0, ind: null }); rev.m4_position_row_ok = t4b.indexOf('P(正規｜35～39歳・男)' + (Rs.K[0]/Rs.total*100).toFixed(1) + '%') >= 0; rev.m4_industry_row_ok = t4b.indexOf('P(情報通信業｜35～39歳・男・正規)' + (Rg.G[7]/Rg.total*100).toFixed(1) + '%') >= 0; rev.m4_income_row_conditioned = t4b.indexOf('≥500万円｜35～39歳・男・正規・情報通信業') >= 0; }
  H.derBack(); H.unplace('sta'); H.unplace('ind'); }
  const M1 = H.MODEL_DERIVATIONS.M1, M2 = H.MODEL_DERIVATIONS.M2;
  rev.m1_order_ok = M1.stages.map(x => x.kind).join('>') === 'input>process>estimate>process>output' && /混合/.test(M1.stages[2].title) && /校正/.test(M1.stages[3].title);
  H.derOpen('M1', null); d.querySelector('.fstep[data-step="2"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); rev.m1_mixture_marked_missing = txt().indexOf('この配布版には未収録') >= 0; H.derBack();
  rev.m2_order_ok = /傾き.*校正前/.test(M2.stages[1].title) && /公表構成への校正/.test(M2.stages[2].title) && /M1 の校正済み配列は入力ではなく/.test(M2.stages[0].plain);
  H.derOpen('M2', null); d.querySelector('.fstep[data-step="1"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); rev.m2_tilted_mixture_missing = txt().indexOf('この配布版には未収録') >= 0; d.querySelector('.fstep[data-step="2"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); rev.m2_compare_labelled_calibrated = txt().indexOf('校正後どうし') >= 0; H.derBack();
  const revOk = Object.values(rev).every(Boolean);
  // the M chip inside an item panel opens the derivation and back returns focus to the chip
  H.select('muni', '13103'); H.setOpen('inc', true); H.select('inc', 9); const chip = d.querySelector('#panel .sid[data-src="M2"]'); let chipOk = false;
  if (chip){ chip.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const opened = H.S.focus.dim === 'model' && H.S.focus.id === 'M2'; H.derBack(); chipOk = opened && H.S.focus.dim === 'inc' && d.activeElement === d.querySelector('#panel .sid[data-src="M2"]'); }
  // cycle guard: M4 -> M3 -> M2 -> M1 -> M4 unwinds instead of growing the stack
  H.derOpen('M4', null); H.derOpen('M3', null); H.derOpen('M2', null); H.derOpen('M1', null); const depthBefore = H.NAV.length; H.derOpen('M4', null); const cycleOk = H.NAV.length < depthBefore; while (H.NAV.length) H.derBack();
  // sources list has derivation buttons
  d.getElementById('srcbtn').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const srcBtns = d.querySelectorAll('#panel .action[data-go="model"]').length;
  // Issue #32: assumption registry integrity, assumption panel, per-stage literature, area-specific evaluation notes
  const A = H.ASSUMPTIONS, MA = H.MODEL_ASSUMPTIONS, LIT = H.MODEL_LITERATURE, asm = { missing_ids: [], bad_entries: [], unreferenced: [], lit_missing: [], m_level_literature_absent: true };
  const referenced = new Set();
  Object.keys(MA).forEach(m => { MA[m].forEach(id => { referenced.add(id); if (!A[id]) asm.missing_ids.push(m + ':' + id); }); H.MODEL_DERIVATIONS[m].stages.forEach((st, i) => { (st.asm || []).forEach(id => { referenced.add(id); if (!A[id]) asm.missing_ids.push(m + '/' + i + ':' + id); else if (MA[m].indexOf(id) < 0) asm.missing_ids.push(m + '/' + i + ' not in list:' + id); }); (st.lit || []).forEach(l => { if (!LIT[l.k]) asm.lit_missing.push(m + '/' + i + ':' + l.k); }); }); });
  Object.keys(A).forEach(id => { const a = A[id]; if (!['direct','indirect','none'].includes(a.cls) || !['published','heldout','synthetic','sensitivity'].every(k => a.methods[k] && ['done','not','na'].includes(a.methods[k].s) && a.methods[k].t) || !a.links.length || !a.text || !a.reason || !a.limits) asm.bad_entries.push(id); if (!referenced.has(id)) asm.unreferenced.push(id); });
  asm.shared_A04_in = Object.keys(MA).filter(m => MA[m].indexOf('A04') >= 0);
  asm.literature_stages = Object.keys(MA).map(m => m + ':' + H.MODEL_DERIVATIONS[m].stages.filter(st => st.lit && st.lit.length).length);
  // open M4, stage 2 (3-margin IPF), click A10, check the panel, go back
  H.select('muni', '13103'); H.derOpen('M4', null); d.querySelector('.fstep[data-step="2"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  const tM4 = txt(); asm.m_level_literature_absent = tM4.indexOf('手法の参考論文と適用範囲') < 0; asm.stage_literature_shown = tM4.indexOf('手法の参考文献（この工程）') >= 0 && tM4.indexOf('本実装との違い') >= 0;
  const before32 = snap(); const chipA = d.querySelector('#panel .asmchip[data-asm="A10"]'); asm.chip_present = !!chipA;
  if (chipA){ chipA.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); const tA = txt(); asm.panel_ok = H.S.focus.dim === 'assumption' && H.S.focus.id === 'A10' && d.querySelectorAll('#panel .vtab tbody tr').length === 4 && tA.indexOf('未検証') >= 0 && tA.indexOf('分類の規則') >= 0 && d.activeElement === d.querySelector('#panel .action[data-go="derback"]');
    H.derBack(); asm.back_ok = H.S.focus.dim === 'model' && H.S.focus.id === 'M4' && H.DER.open === 2 && d.activeElement === d.querySelector('#panel .asmchip[data-asm="A10"]'); asm.state_unchanged = snap() === before32; }
  // area-specific notes: A01 held-out row for 遠軽町 (not one of the 86 cities) vs 港区
  H.derBack(); H.select('muni', '01555'); H.asmOpen('A01', null); const tE = txt(); asm.town_marked_not_evaluated = tE.indexOf('評価対象外') >= 0 && tE.indexOf('遠軽町') >= 0; H.derBack();
  H.select('muni', '47201'); H.asmOpen('A01', null); const tK = txt(); asm.city_marked_included = tK.indexOf('86 都市に含まれる') >= 0 && tK.indexOf('那覇市') >= 0; H.derBack();
  H.asmOpen('A04', null); asm.old_version_flagged = txt().indexOf('旧版') >= 0; H.derBack();
  H.asmOpen('A05', null); asm.direct_has_limits = txt().indexOf('直接検証済み') >= 0 && txt().indexOf('保証しない') >= 0; H.derBack();
  // PR #33 review: (1) tax-check inclusion follows the actual evaluation units of validate_m12 (validation_m12_areas.csv)
  const csv = fs.readFileSync(path.resolve('docs/experiments/validation_m12_areas.csv'), 'utf8').split('\n').slice(1).filter(Boolean).map(l => l.split(',')); const units = {}; csv.forEach(r => { units[r[0]] = r[4] === 'True'; });
  const G2 = JSON.parse(fs.readFileSync(path.join(site, 'data', 'graph.json'), 'utf8')).graph; let taxMismatch = [];
  G2.munis.forEach(m => { const t = H.taxEvalStatus(m.c); if (m.c in units){ const want = units[m.c] ? 'included' : 'excluded'; if (t.s !== want) taxMismatch.push(m.c + ':' + t.s + '!=' + want); } else { if (t.s !== 'city_only' || !(m.pa in units)) taxMismatch.push(m.c + ':' + t.s + ' (not a unit, expected city_only)'); } });
  asm.tax_units_in_csv = Object.keys(units).length; asm.tax_rule_mismatches = taxMismatch.slice(0, 5); asm.tax_rule_ok = taxMismatch.length === 0;
  H.select('muni', '07546'); H.asmOpen('A05', null); const tF = txt(); asm.futaba_excluded = tF.indexOf('双葉町は評価対象外') >= 0 && tF.indexOf('有給就業者が 0') >= 0 && tF.indexOf('双葉町を含む') < 0; H.derBack();
  H.select('muni', '27102'); H.asmOpen('A05', null); const tW = txt(); asm.ward_city_only = tW.indexOf('都島区は個別に評価していない') >= 0 && tW.indexOf('大阪市の市計として評価') >= 0; H.derBack();
  H.select('muni', '27100'); H.asmOpen('A05', null); asm.designated_city_unit = txt().indexOf('市計として') >= 0; H.derBack();
  // (2) each synthetic experiment is described with its own areas / scenarios / seeds, matching the saved reports
  const EX = H.EXPERIMENTS; const rM12 = JSON.parse(fs.readFileSync(path.resolve('docs/experiments/synthetic_recovery_m12.json'), 'utf8')), rM1 = JSON.parse(fs.readFileSync(path.resolve('docs/experiments/synthetic_recovery.json'), 'utf8')), rA = JSON.parse(fs.readFileSync(path.resolve('docs/experiments/employment_a_synthetic.json'), 'utf8'));
  // design (cases = scenarios x repetitions) is checked against the structure of the saved reports, not only the counts
  const m12Seeds = rM12.seeds.length, m12Sc = Object.keys(rM12.scenarios).length;
  asm.exp_m12_ok = EX.synth_m12.scenarios === m12Sc && EX.synth_m12.seeds === m12Seeds && EX.synth_m12.cases === m12Sc*m12Seeds && EX.synth_m12.design.indexOf(m12Sc + ' シナリオ × ' + m12Seeds + ' seed') >= 0 && /6 都道府県 × 20 地域/.test(EX.synth_m12.areas);
  const m1Sc = Object.keys(rM1.scenarios).length, m1Seeds = rM1.scenarios[Object.keys(rM1.scenarios)[0]].M0.gamma_selected.length;   // one selected gamma per seed
  asm.exp_m1_ok = EX.synth_m1.scenarios === m1Sc && EX.synth_m1.seeds === m1Seeds && EX.synth_m1.cases === m1Sc*m1Seeds && /人工/.test(EX.synth_m1.areas);
  const aSc = Object.keys(rA.scenarios), aRandom = aSc.filter(k => /^random_seed_/.test(k)).length, aSingleRun = aSc.every(k => rA.scenarios[k].tv_joint && typeof rA.scenarios[k].tv_joint.weighted_mean === 'number');   // each case run once (no per-seed nesting)
  asm.exp_a_ok = EX.synth_a.scenarios === aSc.length && EX.synth_a.cases === aSc.length && EX.synth_a.seeds === 1 && aSingleRun && EX.synth_a.design.indexOf(aSc.length + ' ケースを各 1 回') >= 0 && EX.synth_a.design.indexOf(aRandom + ' ケース') >= 0 && !/8 シナリオ × 3 seed/.test(EX.synth_a.design) && new RegExp(rA.areas + ' 地域').test(EX.synth_a.areas) && /北海道・東京都/.test(EX.synth_a.areas);
  asm.exp_a_note_text = H.EXPERIMENTS.synth_a.design;
  H.asmOpen('A03', null); const tA3 = txt(); asm.a03_uses_m12_experiment = tA3.indexOf('M12 の仮想人口実験') >= 0 && tA3.indexOf('人工の 6 都道府県') >= 0 && tA3.indexOf('北海道・東京都') < 0; H.derBack();
  H.asmOpen('A06', null); const tA6 = txt(); asm.a06_uses_m1_experiment = tA6.indexOf('M1 の仮想人口実験') >= 0 && tA6.indexOf('北海道・東京都') < 0; H.derBack();
  H.asmOpen('A09', null); const tA9 = txt(); asm.a09_uses_stage_a_experiment = tA9.indexOf('段階A の未観測関連の実験') >= 0 && tA9.indexOf('北海道・東京都') >= 0 && tA9.indexOf('250 地域') >= 0 && tA9.indexOf('8 ケースを各 1 回') >= 0 && tA9.indexOf('8 シナリオ × 3 seed') < 0; H.derBack();
  // (3) A11 distinguishes the expected table (exact) from the integer sample (rounding / sampling errors), values from the saved report
  const rP = JSON.parse(fs.readFileSync(path.resolve('docs/experiments/household_b_population_13103.json'), 'utf8')).model;
  H.select('muni', '13103'); H.asmOpen('A11', null); const t11 = txt();
  asm.a11_integer_errors_shown = t11.indexOf('整数個票（抽出後）') >= 0 && t11.indexOf('±1 世帯') >= 0 && t11.indexOf('0.375') >= 0 && Math.abs(rP.households_per_family_type.max_abs_error - 1) < 1e-6 && Math.abs(rP.households_per_size_bin.max_abs_error - 2) < 1e-6 && Math.abs(rP.members_per_family_type.max_rel_error - 0.375) < 1e-3;
  asm.a11_heldout_versions_separated = t11.indexOf('整数個票からの集計') >= 0 && t11.indexOf('期待人数表からの計算値') >= 0 && Math.abs(rP.heldout_26_1_elderly_by_size.total_ratio - 1.05) < 0.005; H.derBack();
  const asmOk2 = asm.tax_rule_ok && asm.futaba_excluded && asm.ward_city_only && asm.designated_city_unit && asm.exp_m12_ok && asm.exp_m1_ok && asm.exp_a_ok && asm.a03_uses_m12_experiment && asm.a06_uses_m1_experiment && asm.a09_uses_stage_a_experiment && asm.a11_integer_errors_shown && asm.a11_heldout_versions_separated;
  const asmOk = asmOk2 && asm.missing_ids.length === 0 && asm.bad_entries.length === 0 && asm.unreferenced.length === 0 && asm.lit_missing.length === 0 && asm.m_level_literature_absent && asm.stage_literature_shown && asm.chip_present && asm.panel_ok && asm.back_ok && asm.state_unchanged && asm.town_marked_not_evaluated && asm.city_marked_included && asm.old_version_flagged && asm.direct_has_limits && asm.literature_stages.every(x => !/:0$/.test(x));
  const passed = checks.every(Boolean) && chipOk && cycleOk && srcBtns === 6 && revOk && asmOk && errs.length === 0;
  const report = { passed, no_emp_dataset: noEmp, assumptions: asm, assumptions_ok: asmOk, review_cases: rev, review_cases_ok: revOk, results, chip_back_focus_ok: chipOk, cycle_guard_ok: cycleOk, source_list_buttons: srcBtns, page_errors: errs };
  console.log(JSON.stringify(report, null, 1)); if (!passed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
