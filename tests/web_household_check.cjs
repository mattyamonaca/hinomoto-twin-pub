/* Verify actual public-data household panels and the legacy-data fallback. */
const fs=require('fs'),path=require('path'),assert=require('assert');
const {JSDOM}=require('jsdom');
const site=path.resolve(process.argv[2]||'dist/site');
(async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(site,'index.html'),'utf8'),{runScripts:'dangerously',url:'http://localhost/',pretendToBeVisual:true,beforeParse(w){
  w.fetch=async u=>{const p=path.join(site,String(u).replace(/^http:\/\/localhost\//,''));if(!fs.existsSync(p))return {ok:false,status:404};const b=fs.readFileSync(p);return {ok:true,json:async()=>JSON.parse(b),arrayBuffer:async()=>b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)};};
  w.Element.prototype.scrollIntoView=function(){};
 }});
 await new Promise(r=>setTimeout(r,1500));const w=dom.window,H=w.__hinomoto;
 assert(H,'page did not initialize');
 for(const code of ['13103','47201','01555']){
  const data=JSON.parse(fs.readFileSync(path.join(site,'data/household',code+'.json')));
  assert.equal(data.constraints.version,'household-support-1');assert.equal(data.constraints.validation.violations,0);
  H.hhState.data[code]=data;H.renderHousehold(code);const p=w.document.getElementById('panel');
  assert(p.textContent.includes('世帯を作るときの制約と限界'));
  assert(p.textContent.includes('世帯主の配偶者は最大1人'));
  const rows=[0,1].flatMap(s=>[0,1,2].map(a=>data.by_sex_age[s*18+a])).filter(Boolean);
  const child=rows.reduce((t,r)=>t+r.n*r.is_child,0)/rows.reduce((t,r)=>t+r.n,0);
  assert(p.textContent.includes((child*100).toFixed(1)+'%'));
  assert(!p.textContent.includes('親と同居（続き柄「子」として）'));
  assert(!p.textContent.includes('NaN'));
 }
 const legacy=H.hhState.data['01555'];delete legacy.constraints;legacy.by_sex_age.filter(Boolean).forEach(r=>delete r.is_child);
 H.renderHousehold('01555');const text=w.document.getElementById('panel').textContent;
 assert(text.includes('制約を確認した記録がありません'));assert(text.includes('未収録'));assert(!text.includes('NaN'));
 console.log('3 household panels, constraint disclosure, child numerator and legacy fallback passed');process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
