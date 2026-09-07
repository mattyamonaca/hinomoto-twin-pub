/* Browser-side reproduction check for stage A (Issue #22).
   Loads site/index.html in jsdom with the assembled dataset (dist/site/data), recomputes the employment blocks in the
   page's own JavaScript and compares them cell by cell with the Python reference (validation/employment_web_reference.json).
   Usage: HINOMOTO_DATA_ROOT=... node tests/web_employment_check.cjs [dist/site] */
const fs = require('fs'), path = require('path');
const { JSDOM } = require('jsdom');
const site = path.resolve(process.argv[2] || 'dist/site');
const dataRoot = process.env.HINOMOTO_DATA_ROOT || path.resolve('..', 'hinomoto-twin-data');
const reference = JSON.parse(fs.readFileSync(path.join(dataRoot, 'validation', 'employment_web_reference.json'), 'utf8'));
const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
const CRITERIA = { max_abs_persons: 0.5, max_tv: 1e-4, all_ages_seconds: 2.0, margin_tv: 1e-5 };
(async () => {
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/', beforeParse(w){
    w.fetch = async (url) => { const rel = String(url).replace(/^http:\/\/localhost\//, ''); const f = path.join(site, rel); if (!fs.existsSync(f)) return { ok: false, status: 404 }; const buf = fs.readFileSync(f); return { ok: true, status: 200, json: async () => JSON.parse(buf.toString('utf8')), arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) }; };
    w.Element.prototype.scrollIntoView = function(){};
  } });
  const w = dom.window, d = w.document, errs = [];
  w.addEventListener('error', e => errs.push(e.message));
  await new Promise(r => setTimeout(r, 4000));
  const H = w.__hinomoto; if (!H) throw new Error('page hooks missing (data failed to load?)');
  const G = JSON.parse(fs.readFileSync(path.join(site, 'data', 'graph.json'), 'utf8'));
  const MI = {}; G.graph.munis.forEach((m, k) => { MI[m.c] = k; });
  // trigger loading of the municipal inputs, then wait
  H.empReady('m:13103'); await new Promise(r => setTimeout(r, 3000));
  const results = [];
  for (const s of reference.samples){
    const t0 = Date.now(), b = H.empBlock('m:' + s.code, s.sex, s.age), ms = Date.now() - t0;
    let maxAbs = 0, tvNum = 0, tot = 0;
    const cmp = (a, r) => { for (let i = 0; i < r.length; i++){ const dlt = Math.abs(a[i] - r[i]); maxAbs = Math.max(maxAbs, dlt); tvNum += dlt; tot += r[i]; } };
    cmp(b.paid, s.paid); cmp(b.fam, s.family); cmp(b.un, s.unemployed); cmp(b.ina, s.inactive);
    results.push({ code: s.code, sex: s.sex, age: s.age, persons: tot, max_abs_error_persons: maxAbs, tv: tot ? 0.5*tvNum/tot : 0, iterations_js: b.it, iterations_py: s.iterations, ms });
  }
  // timing: all ages, both sexes for one municipality (26 blocks)
  const t1 = Date.now(); for (let s = 0; s < 2; s++) for (let a = 0; a < 13; a++) H.empBlock('m:47201', s, a); const allAges = (Date.now() - t1)/1000;
  // margins preserved: summing the employment columns reproduces the 5-attribute income distribution
  H.setOpen('pref', true); H.setOpen('muni', true); H.setOpen('age', true); H.setOpen('edu', true); H.setOpen('inc', true); H.select('muni', '13103'); H.select('age', 4); H.select('edu', 3);
  const base = Array.from(H.incDist().p);
  H.setOpen('lab', true); H.setOpen('sta', true); H.setOpen('ind', true);
  const R = H.empCounts({ e: 3, lab: null, sta: null, ind: null }); const empP = Array.from(R.Y).map(v => R.total ? v/R.total : 0);
  let tvMargin = 0; for (let y = 0; y < 16; y++) tvMargin += Math.abs(empP[y] - base[y]); tvMargin *= 0.5;
  // a conditional query renders and is normalised
  H.select('lab', 0); H.select('sta', 0); H.select('ind', 7); const cond = H.incDist(); const sumP = Array.from(cond.p).reduce((a, b) => a + b, 0);
  const rows = d.querySelectorAll('#list-inc .row').length;
  // prefecture scope uses the aggregated block file
  H.skip('muni'); await new Promise(r => setTimeout(r, 3000)); const ready = H.empReady('p:13'); const Rp = H.empCounts({ e: null, lab: null, sta: null, ind: null });
  const passed = results.every(r => r.max_abs_error_persons <= CRITERIA.max_abs_persons && r.tv <= CRITERIA.max_tv) && allAges <= CRITERIA.all_ages_seconds && tvMargin <= CRITERIA.margin_tv && Math.abs(sumP - 1) < 1e-9 && rows === 16 && ready && Rp.total > 0 && errs.length === 0;
  const report = { passed, criteria: CRITERIA, model_version: G.graph.emp.version, dataset_version: G.dataset_version, samples: results, all_ages_one_municipality_seconds: allAges, margin_tv_vs_5_attribute_income: tvMargin, conditional_query: { condition: '港区 35-39 男 大学等 就業者 正規 情報通信業', population: cond.den, sum_p: sumP, p_500plus: cond.p.slice(8).reduce((a, b) => a + b, 0) }, prefecture_scope_ready: ready, prefecture_population: Rp.total, page_errors: errs };
  fs.writeFileSync(path.join(dataRoot, 'validation', 'employment_web_verification.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 1));
  if (!passed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
