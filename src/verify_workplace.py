"""Verify the stage-C residence x workplace x industry fit and evaluate it on the ODI tables that were not used.

Checks (data/workplace_c.npz against sources/workplace):
  margins per pair / residence category x industry / workplace category x industry, non-negativity, normalisation of
  P(workplace | residence, industry), no duplicate pairs across ward/city levels, every code is a 2020 leaf.
Held-out evaluations (tables 9 and 10 list, for large cities and wards only, the specific municipality x industry):
  1. table 9 (residence side): P(d | o, g) for observed (o, g) cells, TV of the model against the observed row, compared
     with 'independent' P(d | o) (industry ignored), 'category' (OD x residence-category industry shares: the
     information in tables 3+8 on the residence side only, no IPF), 'gravity' (OD x workplace industry mix) and 'seed'.
  2. table 10 (workplace side): P(o | d, g) for large-city workplaces against the same candidates.
  3. sensitivity: refit with residence-side margins only, and from a flat seed.
Acceptance criteria are pre-registered in docs/WORKPLACE_C.md (section 4) and applied here; exit code 1 on failure.
Outputs: validation/workplace_c_verification.json, validation/workplace_c_heldout.csv
"""
import json,sys
import numpy as np
import pandas as pd
from paths import SOURCES,OUTPUT,REPORTS
import build_workplace as bw

G=bw.G

def checks(d,x,tol=0.5):
 X=d['x'].astype(float);oi=d['origin'];di=d['dest'];ci=d['category'];A=len(d['areas'])
 res={'nonnegative':bool((X>=-1e-6).all())}
 res['pair_margin_max_abs']=float(np.abs(X.sum(1)-x['od']).max())
 s=np.zeros((A*4,20));np.add.at(s,oi*4+ci,X);res['residence_margin_max_abs']=float(np.abs(s-x['R'].reshape(A*4,20)).max())
 t=np.zeros((A*4,20));np.add.at(t,di*4+ci,X);res['workplace_margin_max_abs']=float(np.abs(t-x['W'].reshape(A*4,20)).max())
 tot=np.bincount(oi,weights=X.sum(1),minlength=A)+d['unknown_workplace'].sum(1);res['residence_total_incl_unknown_vs_table8_max_abs']=float(np.abs(tot-(x['R'].sum((1,2))+x['U'].sum(1))).max())
 res['duplicate_pairs']=int(len(oi)-len(set(zip(oi.tolist(),di.tolist()))))
 leaf=set(x['areas']);res['all_codes_are_2020_leaves']=bool(all(a in leaf for a in d['areas']))
 res['passed']=bool(res['nonnegative'] and max(res['pair_margin_max_abs'],res['residence_margin_max_abs'],res['workplace_margin_max_abs'])<tol and res['duplicate_pairs']==0 and res['all_codes_are_2020_leaves'])
 return res

def heldout_rows(table,obs_df,key_col,other_col,keys_idx,other_idx,models,ix,min_cell):
 """For each observed key area and industry: TV between the observed conditional over the other side and each candidate."""
 rows=[];A=len(ix)
 groups={}
 for p,k in enumerate(keys_idx):groups.setdefault(k,[]).append(p)
 for k,ps in groups.items():ps.sort()
 for key,sub in obs_df.groupby(key_col):
  if key not in ix or ix[key] not in groups:continue
  ps=np.array(groups[ix[key]]);other=other_idx[ps];pos=np.full(A,-1);pos[other]=np.arange(len(ps))
  j=sub[other_col].map(ix).to_numpy();ok=j>=0;j=j[ok];obs=sub[G].to_numpy(float)[ok];slot=pos[j];inside=slot>=0
  full=np.zeros((len(ps),20));np.add.at(full,slot[inside],obs[inside]);outside=obs[~inside].sum(0)   # observed flows to places absent from the OD pair list
  tot=full.sum(0)+outside
  for gi in range(20):
   if tot[gi]<min_cell:continue
   ob=full[:,gi]/tot[gi];row={'table':table,'area':key,'industry':G[gi],'weight':float(tot[gi]),'observed_outside_pairs_share':float(outside[gi]/tot[gi])}
   for name,M in models.items():
    m=M[ps,gi];m=m/m.sum() if m.sum()>0 else m;row['tv_'+name]=float(.5*np.abs(m-ob).sum()+.5*outside[gi]/tot[gi])
   rows.append(row)
 return rows

def ipf_residence_only(x,Xs,d,iters=60):
 A=len(x['areas']);ro=d['origin']*4+d['category'];od=x['od']
 for it in range(iters):
  s=np.zeros((A*4,20));np.add.at(s,ro,Xs);f=np.divide(x['R'].reshape(A*4,20),s,out=np.ones_like(s),where=s>0);Xs*=f[ro]
  p=Xs.sum(1);Xs*=np.divide(od,p,out=np.ones_like(p),where=p>0)[:,None]
 return Xs

def evaluate(output_dir=None,sources_dir=None,reports_dir=None,min_cell=100):
 OUT=output_dir or OUTPUT;SRC=sources_dir or SOURCES;REP=reports_dir or REPORTS
 d=np.load(OUT/'workplace_c.npz');x=bw.load_inputs(SRC,OUT);areas=list(d['areas']);ix={a:i for i,a in enumerate(areas)}
 res={'model_version':str(d['model_version']),'checks':checks(d,x)}
 X=d['x'].astype(float);S=d['seed'].astype(float);oi=d['origin'];di=d['dest'];ci=d['category'];od=x['od'];A=len(areas)
 indep=od[:,None]*(x['R'].sum(1)/np.maximum(x['R'].sum((1,2)),1e-12))[oi]
 wshare=x['W'].sum(1);wshare=wshare/np.maximum(wshare.sum(1,keepdims=True),1e-12);grav=od[:,None]*wshare[di]
 rc=x['R'][oi,ci];rc=rc/np.maximum(rc.sum(1,keepdims=True),1e-12);catb=od[:,None]*rc
 models={'model':X,'seed':S,'independent':indep,'gravity':grav,'category':catb}
 t9=pd.read_csv(SRC/'workplace/odi_residence_tidy.csv.gz',dtype={'origin':str,'dest':str});t9=t9[t9.dest!='UNK']
 t10=pd.read_csv(SRC/'workplace/odi_workplace_tidy.csv.gz',dtype={'workplace':str,'origin':str});t10=t10[t10.origin!='UNK']
 rows=heldout_rows('9',t9,'origin','dest',oi,di,models,ix,min_cell)+heldout_rows('10',t10,'workplace','origin',di,oi,models,ix,min_cell)
 df=pd.DataFrame(rows);df.to_csv(REP/'workplace_c_heldout.csv',index=False)
 def summ(sub):
  w=sub.weight.to_numpy();return {c:{'weighted_mean':float(np.average(sub[c],weights=w)),'equal_mean':float(sub[c].mean()),'median':float(sub[c].median()),'p90':float(sub[c].quantile(.9)),'max':float(sub[c].max())} for c in sub.columns if c.startswith('tv_')}
 for t,name in [('9','heldout_9_workplace_given_residence_industry'),('10','heldout_10_residence_given_workplace_industry')]:
  h=df[df.table==t]
  if not len(h):continue
  s=summ(h);worse=h[h.tv_model>h.tv_independent+1e-12]
  res[name]={'areas':int(h.area.nunique()),'cells':len(h),'min_cell_persons':min_cell,**s,'share_of_cells_model_worse_than_independent':float(len(worse)/len(h)),'max_worsening_vs_independent':float((h.tv_model-h.tv_independent).max()),'relative_improvement_vs_independent_weighted':float(1-s['tv_model']['weighted_mean']/s['tv_independent']['weighted_mean']),'relative_improvement_vs_category_weighted':float(1-s['tv_model']['weighted_mean']/s['tv_category']['weighted_mean']),'observed_outside_pairs_share_weighted':float(np.average(h.observed_outside_pairs_share,weights=h.weight))}
 # sensitivity variants evaluated on table 9
 variants={'residence_side_only':ipf_residence_only(x,S.copy(),d),'flat_seed':bw.ipf(x,(od[:,None]*np.full((1,20),1/20)).copy(),iters=200,tol=0.5)[0]}
 sens={}
 for name,Xv in variants.items():
  r9=pd.DataFrame(heldout_rows('9',t9,'origin','dest',oi,di,{'v':Xv},ix,min_cell))
  sens[name]={'tv_weighted_mean_table9':float(np.average(r9.tv_v,weights=r9.weight)),'tv_vs_model_weighted':float((0.5*np.abs(Xv/np.maximum(Xv.sum(1,keepdims=True),1e-12)-X/np.maximum(X.sum(1,keepdims=True),1e-12)).sum(1)*od).sum()/od.sum())}
 res['sensitivity']=sens
 P=X/np.maximum(X.sum(1,keepdims=True),1e-12);Q=indep/np.maximum(indep.sum(1,keepdims=True),1e-12)
 res['association_tv_model_vs_independent_weighted']=float((0.5*np.abs(P-Q).sum(1)*od).sum()/od.sum())
 h=res.get('heldout_9_workplace_given_residence_industry',{})
 acc={'margins_within_0.5_persons':res['checks']['passed'],'heldout9_model_beats_independent_by_10pct':bool(h and h['relative_improvement_vs_independent_weighted']>=0.10),'heldout9_model_not_worse_than_category_baseline':bool(h and h['tv_model']['weighted_mean']<=h['tv_category']['weighted_mean']+1e-9),'heldout9_max_worsening_vs_independent_le_0.10':bool(h and h['max_worsening_vs_independent']<=0.10),'artifact_under_50mb':bool((OUT/'workplace_c.npz').stat().st_size<50e6)}
 res['acceptance']=acc;res['passed']=bool(all(acc.values()))
 (REP/'workplace_c_verification.json').write_text(json.dumps(res,ensure_ascii=False,indent=1));print(json.dumps(res,ensure_ascii=False,indent=1))
 return res

def main():
 res=evaluate()
 if not res['passed']:print('Workplace stage-C verification FAILED; see validation/workplace_c_verification.json',file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
