"""Compare M0 (current model) with M1 (education composition re-estimates municipal income) on the held-out city tables.

Protocol (fixed before looking at results; see docs/EXPERIMENT_M12.md):
  * Parameters: M0 selects beta (tax tilt); M1 selects (gamma, beta). Selection minimises population-weighted
    cross entropy on the training folds only. Folds = prefecture code mod 5, identical to refine_tax.py.
  * Evaluation: TV distance on the test folds (out-of-fold), reported weighted and unweighted, with median, p90,
    max, the fraction of cells improved, and the worst per-city / per-prefecture change.
  * Adoption rule (pre-registered): M1 replaces M0 only if the out-of-fold weighted TV improves by at least 1%
    relative AND the unweighted median does not worsen AND no city worsens by more than 0.02 TV on average.
    Otherwise M0 stays the production default.
Outputs: validation/experiment_m1.json, experiment_m1_grid.csv, experiment_m1_cells.csv.
"""
import json,time
import numpy as np
import pandas as pd
from paths import SOURCES,REPORTS
import estimator as es

GAMMAS=[0.,0.25,0.5,0.75,1.,1.5,2.,2.5,3.,4.]
BETAS=np.round(np.arange(0,2.01,0.1),2)
ADOPT={'min_relative_tv_improvement':0.01,'median_must_not_worsen':True,'max_city_mean_worsening_tv':0.02}

def summarize(tv,w,codes):
 df=pd.DataFrame({'tv':tv,'w':w,'city':codes})
 return {'weighted_mean':float(np.average(tv,weights=w)),'unweighted_mean':float(tv.mean()),'median':float(np.median(tv)),'p90':float(np.quantile(tv,.9)),'max':float(tv.max()),'city_mean_max':float(df.groupby('city').tv.mean().max())}

def main():
 t0=time.time();inp=es.load_real_inputs(SOURCES);h=inp['heldout'];w=h['weight'];codes=h['codes'];n=len(w)
 W=es.fit_status(inp);cp=es.status_income_shapes(inp)
 folds=h['pref']%5
 tv={};loss={};grid=[]
 for g in GAMMAS:
  q,E=es.mixture(inp,W,cp,es.education_tilt(inp,g));Xb=es.calibrate(inp,q,E)
  for b in BETAS:
   Xt=es.tax_project(inp,Xb,E,float(b));m=es.city_metrics(inp,Xt);tv[(g,b)]=m['tv'];loss[(g,b)]=m['loss']
   grid.append({'gamma':g,'beta':float(b),'weighted_tv':float(np.average(m['tv'],weights=w)),'weighted_ce':float(np.average(m['loss'],weights=w))})
  print(f'gamma={g} done {time.time()-t0:.0f}s',flush=True)
 keys=list(tv.keys());L=np.array([loss[k] for k in keys]);T=np.array([tv[k] for k in keys])
 def select(mask,allowed):
  cand=[i for i,k in enumerate(keys) if allowed(k)]
  j=cand[int(np.argmin([np.average(L[i][mask],weights=w[mask]) for i in cand]))];return keys[j],j
 models={'M0':lambda k:k[0]==0.,'M1':lambda k:True,'M0_notax':lambda k:k[0]==0. and k[1]==0.,'M1_notax':lambda k:k[1]==0.}
 out={'protocol':__doc__,'adoption_rule':ADOPT,'cells':int(n),'cities':len(set(codes)),'folds':5,'grid':{'gamma':GAMMAS,'beta':[float(b) for b in BETAS]},'models':{}}
 cells=pd.DataFrame({'city':codes,'age':h['age']+1,'prefecture':[inp['prefs'][p] for p in h['pref']],'fold':folds,'weight':w})
 for name,allowed in models.items():
  cv=np.zeros(n);chosen=[]
  for f in range(5):
   train=folds!=f;test=~train;k,j=select(train,allowed);cv[test]=T[j][test];chosen.append({'fold':f,'gamma':k[0],'beta':float(k[1]),'test_cells':int(test.sum())})
  kfull,jfull=select(np.ones(n,bool),allowed)
  out['models'][name]={'out_of_fold':summarize(cv,w,codes),'fold_selection':chosen,'full_fit':{'gamma':kfull[0],'beta':float(kfull[1]),'in_sample':summarize(T[jfull],w,codes)}}
  cells['tv_oof_'+name]=cv
 # paired comparison M1 vs M0 (out of fold)
 d=cells.tv_oof_M1-cells.tv_oof_M0
 city=cells.assign(d=d).groupby('city').d.mean();pref=cells.assign(d=d).groupby('prefecture').d.mean()
 comp={'weighted_mean_change':float(np.average(d,weights=w)),'fraction_cells_improved':float((d<0).mean()),'max_cell_worsening':float(d.max()),'max_city_mean_worsening':float(city.max()),'worst_city':str(city.idxmax()),'max_prefecture_mean_worsening':float(pref.max()),'worst_prefecture':str(pref.idxmax()),'by_age_mean_change':{int(a):float(v) for a,v in cells.assign(d=d).groupby('age').d.mean().items()}}
 m0=out['models']['M0']['out_of_fold'];m1=out['models']['M1']['out_of_fold']
 rel=1-m1['weighted_mean']/m0['weighted_mean']
 adopt=rel>=ADOPT['min_relative_tv_improvement'] and m1['median']<=m0['median'] and comp['max_city_mean_worsening']<=ADOPT['max_city_mean_worsening_tv']
 comp['relative_weighted_tv_improvement']=float(rel);comp['adopt_M1']=bool(adopt)
 comp['decision']=('M1 meets the pre-registered rule' if adopt else 'M1 does not meet the pre-registered rule; M0 remains the production default')
 out['comparison_M1_vs_M0']=comp
 # effect size on education-level distributions (not validated; sensitivity between models)
 gsel=out['models']['M1']['full_fit']['gamma'];bsel=out['models']['M1']['full_fit']['beta'];b0=out['models']['M0']['full_fit']['beta']
 r0=es.run(inp,0.,b0,W=W,cp=cp);r1=es.run(inp,gsel,bsel,W=W,cp=cp)
 pop=inp['N'];den=pop.sum();tvm=.5*np.abs(es.norm(r1['counts_by_sex'])-es.norm(r0['counts_by_sex'])).sum(-1)
 out['municipal_distribution_change_M1_vs_M0']={'gamma':gsel,'beta_M1':bsel,'beta_M0':b0,'weighted_mean_tv_area_sex_age':float(np.average(tvm[pop>0],weights=pop[pop>0])),'p90':float(np.quantile(tvm[pop>0],.9)),'max':float(tvm[pop>0].max()),'note':'Change in P(income|area,sex,age) between the two models; unvalidated where no city table exists.'}
 e0=es.allocate_education(inp,r0['counts_by_sex']);e1=es.allocate_education(inp,r1['counts_by_sex'])
 R=inp['edu_share']*pop[...,None];tve=.5*np.abs(es.norm(e1)-es.norm(e0)).sum(-1);ok=R>0
 out['education_distribution_change_M1_vs_M0']={'weighted_mean_tv':float(np.average(tve[ok],weights=R[ok])),'p90':float(np.quantile(tve[ok],.9))}
 out['notes']=['City tables are not used to construct either model, but they are part of the prefecture totals; this is not a fully independent evaluation.','Weights are survey-expanded known-income counts, not sample sizes; unweighted statistics are reported alongside.','TV is half the L1 distance between 16-bin income shares of known-income workers by age; sex- and education-specific accuracy is not measured here.']
 out['elapsed_seconds']=round(time.time()-t0,1)
 (REPORTS/'experiment_m1.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 pd.DataFrame(grid).to_csv(REPORTS/'experiment_m1_grid.csv',index=False);cells.to_csv(REPORTS/'experiment_m1_cells.csv',index=False)
 print(json.dumps({k:v['out_of_fold'] for k,v in out['models'].items()},indent=1));print(json.dumps(comp,ensure_ascii=False,indent=1))
if __name__=='__main__':main()
