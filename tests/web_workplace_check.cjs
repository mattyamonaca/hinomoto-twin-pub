/* Stage-C Explorer check (Issue #24): the workplace panel reproduces persona_v4 for sample conditions.
   Usage: HINOMOTO_DATA_ROOT=... node tests/web_workplace_check.cjs [dist/site] */
const fs = require('fs'), path = require('path');
const { JSDOM } = require('jsdom');
const site = path.resolve(process.argv[2] || 'dist/site');
const dataRoot = process.env.HINOMOTO_DATA_ROOT || path.resolve('..', 'hinomoto-twin-data');
const ref = JSON.parse(fs.readFileSync(path.join(dataRoot, 'validation', 'workplace_web_reference.json'), 'utf8'));
const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
const TOL = 1e-4;   /* counts are published rounded to 0.01 person; small denominators (towns x one industry) feel the rounding most */
(async () => {
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/', beforeParse(w){
    w.fetch = async (url) => { const rel = String(url).replace(/^http:\/\/localhost\//, ''); const f = path.join(site, rel); if (!fs.existsSync(f)) return { ok: false, status: 404 }; const buf = fs.readFileSync(f); return { ok: true, status: 200, json: async () => JSON.parse(buf.toString('utf8')), arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) }; };
    w.Element.prototype.scrollIntoView = function(){};
  } });
  const w = dom.window, d = w.document, errs = []; w.addEventListener('error', e => errs.push(e.message));
  await new Promise(r => setTimeout(r, 4000));
  const H = w.__hinomoto; if (!H) throw new Error('page hooks missing');
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const results = [];
  for (const c of ref.cases){
    H.wpState.mode = c.side; H.setOpen('pref', true); H.setOpen('muni', true); H.select('muni', c.code);
    if (c.industry){ H.setOpen('ind', true); H.select('ind', parseInt(c.industry.slice(1), 10)); } else if (H.S.ind !== null){ H.unplace('ind'); }
    let cond;
    if (c.mix){ H.setOpen('age', true); H.setOpen('sex', true); H.select('age', (c.mix.age - 15)/5 | 0); H.select('sex', c.mix.sex === 'male' ? 0 : 1); H.empReady('m:' + c.code); await wait(3000); cond = H.wpCondition(); }
    else { if (H.S.age !== null) H.unplace('age'); if (H.S.sex !== null) H.unplace('sex'); cond = H.wpCondition(); }
    H.wpReady(c.side, c.code); await wait(2500);
    const R = H.wpCompute(c.side, c.code, cond), r = c.result, list = c.side === 'residence' ? r.p_workplace : r.p_residence;
    const pj = {}; R.list.forEach(x => { pj[x.c] = x.n/R.tot; });
    let maxErr = 0; list.forEach(e => { maxErr = Math.max(maxErr, Math.abs((pj[e.municipality_code] || 0) - e.p)); });
    const cats = Object.values(r.p_by_commuting_category); let catErr = 0; cats.forEach((v, i) => { catErr = Math.max(catErr, Math.abs(v - R.cats[i])); });
    const unkErr = c.side === 'residence' ? Math.abs(R.unkShare - r.unknown_workplace_share_outside_distribution) : 0;
    results.push({ side: c.side, code: c.code, industry: c.industry, mix: !!c.mix, condition_kind: cond.kind, population_js: R.tot, population_py: r.model_population, max_abs_p_error: maxErr, category_error: catErr, unknown_share_error: unkErr, pop_error: Math.abs(R.tot - r.model_population) });
  }
  // the panel renders (residence side, Minato, all industries) and the toggle switches sides
  H.wpState.mode = 'residence'; if (H.S.ind !== null) H.unplace('ind'); if (H.S.age !== null) H.unplace('age'); if (H.S.sex !== null) H.unplace('sex'); H.select('muni', '13103'); H.S.focus = { dim: 'workplace', id: '13103' }; H.renderAll();
  const txt = d.getElementById('panel').textContent;
  const ok1 = txt.indexOf('勤務地の市区町村') >= 0 && txt.indexOf('分布の外数') >= 0;
  d.querySelector('.action[data-go="wpmode"][data-id="workplace"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true })); await wait(2500);
  const txt2 = d.getElementById('panel').textContent; const ok2 = txt2.indexOf('居住地の市区町村') >= 0;
  const passed = results.every(x => x.max_abs_p_error <= TOL && x.category_error <= TOL && x.unknown_share_error <= TOL && x.pop_error <= Math.max(0.5, 1e-5*x.population_py)) && ok1 && ok2 && errs.length === 0;
  const report = { passed, tolerance: TOL, model_version: ref.model_version, cases: results, panel_residence_ok: ok1, panel_workplace_ok: ok2, page_errors: errs };
  fs.writeFileSync(path.join(dataRoot, 'validation', 'workplace_web_verification.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 1)); if (!passed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
