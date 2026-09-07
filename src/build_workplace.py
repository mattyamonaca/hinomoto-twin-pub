"""Stage C (issue #24): experimental residence x workplace x industry distribution for all municipalities.

Inputs (sources/workplace, 2020 census 従業地・通学地集計, both sexes, 15歳以上就業者):
  od_pairs_tidy            OD[o,d]      table 3: employed residents of o working in d (d = leaf municipality or UNK)
  industry_commute_tidy    R[o,c,g]     table 8: residents of o in industry g by commuting category c
                           W[d,c,g]     table 8: workers in d in industry g by where they live (category c)
Categories c: 0 own municipality (自市区町村, incl. 自宅 and 従業市区町村「不詳・外国」), 1 other ward of the same designated
city (自市内他区), 2 other municipality of the same prefecture, 3 other prefecture. Residents with unknown workplace
(従業地「不詳」) are kept aside as U[o,g] = table 8 column 従業地「不詳」; the census counts them at the residence in
workplace-based totals, so they are removed from W before fitting.

Model: X[o,d,g] on the pairs published in table 3, fitted by IPF (KL projection of a seed) to three margin families:
  sum_g X[o,d,g] = OD[o,d]                       (every pair)
  sum_{d in category c of o} X[o,d,g] = R[o,c,g]   (residence side, per category)
  sum_{o in category c of d} X[o,d,g] = W[d,c,g]   (workplace side, per category)
The seed is OD[o,d] x (residence share of g within category) x (workplace share of g within category), normalised per
pair. Only the split of a category across its specific municipalities is estimated; every published margin is kept.
The ODI tables 9/10 (large cities) are never used here; verify_workplace.py evaluates against them.

Output: data/workplace_c.npz (pair list + X, unknown-workplace counts, margin errors) and validation/workplace_c_build.json.
"""
from paths import SOURCES,OUTPUT,REPORTS
import json,time,sys
import numpy as np
import pandas as pd

G=[f'G{i:02}' for i in range(1,21)];CAT=['own','in_city','in_pref','other_pref']
MODEL_VERSION='C-0.1'

def category(o,d,parent):
 """Commuting category of pair (o,d) in the census sense; parent maps a ward to its designated-city code."""
 if o==d:return 0
 if parent.get(o) is not None and parent.get(o)==parent.get(d):return 1
 if o[:2]==d[:2]:return 2
 return 3

def load_inputs(sources_dir=None,output_dir=None):
 S=(sources_dir or SOURCES)/'workplace';O=output_dir or OUTPUT
 areas=pd.read_csv(S/'workplace_areas.csv',dtype=str).area.tolist();ix={a:i for i,a in enumerate(areas)}
 pm=pd.read_csv(O/'parent_mapping.csv',dtype=str);parent=dict(zip(pm.area,pm.parent_code))
 od=pd.read_csv(S/'od_pairs_tidy.csv.gz',dtype={'origin':str,'dest':str})
 t8=pd.read_csv(S/'industry_commute_tidy.csv.gz',dtype={'area':str,'status':str,'industry':str});t8=t8[(t8.status=='0')&(t8.industry!='G00')]
 A=len(areas);R=np.zeros((A,4,20));W=np.zeros((A,4,20));U=np.zeros((A,20))
 ai=t8.area.map(ix).to_numpy();gi=t8.industry.map({g:i for i,g in enumerate(G)}).to_numpy()
 R[ai,0,gi]=t8.own.to_numpy()+t8.unknown_muni.to_numpy();R[ai,1,gi]=t8.other_in_city.to_numpy();R[ai,2,gi]=t8.other_in_pref.to_numpy();R[ai,3,gi]=t8.other_pref.to_numpy()
 U[ai,gi]=t8.unknown_dest.to_numpy()
 W[ai,0,gi]=t8.wp_total.to_numpy()-t8.wp_from_other.to_numpy()-t8.unknown_dest.to_numpy();W[ai,1,gi]=t8.wp_in_city.to_numpy();W[ai,2,gi]=t8.wp_in_pref.to_numpy();W[ai,3,gi]=t8.wp_other_pref.to_numpy()
 known=od[od.dest!='UNK'];oi=known.origin.map(ix).to_numpy();di=known.dest.map(ix).to_numpy();v=known.employed.to_numpy(float)
 ci=np.array([category(o,d,parent) for o,d in zip(known.origin,known.dest)])
 unk=od[od.dest=='UNK'].set_index('origin').employed.reindex(areas).fillna(0).to_numpy()
 return {'areas':areas,'parent':parent,'oi':oi,'di':di,'ci':ci,'od':v,'R':R,'W':W,'U':U,'od_unknown':unk}

def seed(x):
 """OD x residence-category industry share x workplace-category industry share, normalised per pair."""
 oi,di,ci=x['oi'],x['di'],x['ci']
 r=x['R'][oi,ci];r=r/np.maximum(r.sum(1,keepdims=True),1e-12)
 w=x['W'][di,ci];w=w/np.maximum(w.sum(1,keepdims=True),1e-12)
 s=r*w;bad=s.sum(1)<=0
 s[bad]=r[bad]                              # a workplace with no published workers in any industry of the category: residence share only
 bad2=s.sum(1)<=0;s[bad2]=1./20
 return x['od'][:,None]*s/s.sum(1,keepdims=True)

def ipf(x,X,iters=200,tol=0.5,verbose=False):
 """Cyclic scaling to the three margin families; returns X and the history of max absolute errors (persons)."""
 oi,di,ci,od,R,W=x['oi'],x['di'],x['ci'],x['od'],x['R'],x['W'];A=R.shape[0]
 ro=oi*4+ci;wd=di*4+ci;hist=[]
 def margins(X):
  m1=np.abs(X.sum(1)-od).max()
  s=np.zeros((A*4,20));np.add.at(s,ro,X);m2=np.abs(s-R.reshape(A*4,20)).max()
  t=np.zeros((A*4,20));np.add.at(t,wd,X);m3=np.abs(t-W.reshape(A*4,20)).max()
  return float(m1),float(m2),float(m3)
 for it in range(iters):
  s=np.zeros((A*4,20));np.add.at(s,ro,X);f=np.divide(R.reshape(A*4,20),s,out=np.ones_like(s),where=s>0);X*=f[ro]
  t=np.zeros((A*4,20));np.add.at(t,wd,X);f=np.divide(W.reshape(A*4,20),t,out=np.ones_like(t),where=t>0);X*=f[wd]
  p=X.sum(1);X*=np.divide(od,p,out=np.ones_like(p),where=p>0)[:,None]
  if it%5==4 or it==iters-1:
   e=margins(X);hist.append((it+1,)+e)
   if verbose:print(it+1,e,flush=True)
   if max(e)<tol:break
 return X,hist

def build(sources_dir=None,output_dir=None,reports_dir=None,iters=1500,tol=0.1):
 t0=time.time();x=load_inputs(sources_dir,output_dir);X0=seed(x)
 # consistency of the inputs before fitting (all from the same census; differences would be parsing errors)
 A=len(x['areas']);tot_o=np.bincount(x['oi'],weights=x['od'],minlength=A);tot_d=np.bincount(x['di'],weights=x['od'],minlength=A)
 chk={'residence_total_vs_table8_max_abs':float(np.abs(tot_o-x['R'].sum((1,2))).max()),'workplace_total_vs_table8_max_abs':float(np.abs(tot_d-x['W'].sum((1,2))).max()),'unknown_workplace_table3_vs_table8_max_abs':float(np.abs(x['od_unknown']-x['U'].sum(1)).max())}
 X,hist=ipf(x,X0.copy(),iters,tol,verbose=True)
 e=hist[-1];ind_tv=None
 out=output_dir or OUTPUT;rep=reports_dir or REPORTS
 np.savez_compressed(out/'workplace_c.npz',areas=np.array(x['areas']),origin=x['oi'].astype(np.int32),dest=x['di'].astype(np.int32),category=x['ci'].astype(np.int8),x=X.astype(np.float32),seed=X0.astype(np.float32),unknown_workplace=x['U'].astype(np.float32),industry_codes=np.array(G),categories=np.array(CAT),model_version=MODEL_VERSION,stage='C')
 report={'model_version':MODEL_VERSION,'pairs':int(len(x['od'])),'areas':A,'employed_known_workplace':float(x['od'].sum()),'employed_unknown_workplace':float(x['U'].sum()),'input_consistency':chk,'ipf':{'iterations':e[0],'max_abs_error_persons':{'pair':e[1],'residence_category_industry':e[2],'workplace_category_industry':e[3]},'history':hist,'converged':bool(max(e[1:])<tol),'tolerance_persons':tol},'seed_vs_fit_tv_weighted':float((0.5*np.abs(X/np.maximum(X.sum(1,keepdims=True),1e-12)-X0/np.maximum(X0.sum(1,keepdims=True),1e-12)).sum(1)*x['od']).sum()/x['od'].sum()),'nonnegative':bool((X>=0).all()),'elapsed_seconds':round(time.time()-t0,1),'file_bytes':int((out/'workplace_c.npz').stat().st_size)}
 (rep/'workplace_c_build.json').write_text(json.dumps(report,ensure_ascii=False,indent=1));print(json.dumps({k:v for k,v in report.items() if k!='ipf'},ensure_ascii=False));print('ipf',report['ipf']['max_abs_error_persons'],'iterations',e[0])
 return report

if __name__=='__main__':build()
