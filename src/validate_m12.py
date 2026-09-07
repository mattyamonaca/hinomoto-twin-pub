"""Issue #21: M0 / M1 / M2 / M12 on the same denominator, coefficient sensitivity, and an independent municipal check.

Everything below was fixed before the numbers were produced (docs/VALIDATION_M12.md, section 2).
Part A  Held-out city cells (86 cities x age, 1,118 cells; out-of-fold by prefecture mod 5, exactly as experiment_models.py):
        weighted mean, equal-city mean, median, p90, max, max city worsening vs M0, absolute error of the shares
        >=300 / >=500 / >=700 万円, by city size class. Same cells and weights for every model.
Part B  Coefficient sensitivity around the production M12 (gamma=1.5, gamma2=1.0, beta=0): in-sample city TV and the change of
        the municipal distributions P(y|m,s,a) for neighbouring coefficients, by area type (市 / 町村 / 区).
Part C  Independent municipal check with the FY2023 市町村税課税状況等の調 (2022 income; not an input of any model; the M0 tax
        proxy is the FY2022 市区町村のすがた, so M0 is also run with beta=0 as the fair baseline):
        within-prefecture log deviation of the model mean paid-worker income vs the tax indicators, correlations by area
        type, and the direction consistency of the M12 - M0 change with the tax residual. Pre-registered support rule:
        M12 is "supported" if corr(model, t1) is not lower than M0(beta=0) by more than 0.01 in every area group and the
        direction-consistency correlation is positive with a bootstrap 95% interval excluding 0. The rule does not change
        the production model; it is reported.
Outputs: validation/validation_m12.json, validation_m12_areas.csv (per-municipality indicators), validation_m12_cells.csv.
"""
import json,time,hashlib
import numpy as np
import pandas as pd
from paths import SOURCES,REPORTS,CATALOG
from model_math import norm
import estimator as es
from experiment_models import GAMMAS,GAMMAS_IND,BETAS,ADOPT

PROD={'gamma_edu':1.5,'gamma_ind':1.0,'beta':0.}
NEIGHBOURS=[(1.0,1.0,0.),(2.0,1.0,0.),(1.5,0.5,0.),(1.5,1.5,0.),(1.5,1.0,0.3),(2.0,0.0,0.),(0.,2.0,0.3),(0.,0.,0.5),(0.,0.,0.)]
THRESH={'ge300':6,'ge500':8,'ge700':10}
MODELS={'M0':lambda k:k[0]==0. and k[1]==0.,'M0_notax':lambda k:k[0]==0. and k[1]==0. and k[2]==0.,'M1':lambda k:k[1]==0.,'M2':lambda k:k[0]==0.,'M12':lambda k:True}
MIDS=es.MIDS*1e4

def sha(p):
 p=CATALOG/p;return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def area_types(S,areas):
 pop=pd.read_csv(S/'census_population_tidy.csv.gz',dtype=str)[['area','type','name']].drop_duplicates().set_index('area')
 t=pop.reindex(areas).type.fillna('?').tolist();names=pop.reindex(areas).name.tolist()
 lab={'0':'ward','2':'city','3':'town_village'};return [lab.get(x,'other') for x in t],names

def part_a(inp,W,cp):
 h=inp['heldout'];w=h['weight'];codes=h['codes'];n=len(w);folds=h['pref']%5;ob=h['obs']
 tv={};loss={};pred={}
 for g in GAMMAS:
  te=es.education_tilt(inp,g)
  for gi in GAMMAS_IND:
   ti=es.industry_tilt(inp,gi) if gi else None;tilt=te if ti is None else (ti if te is None else te*ti)
   q,E=es.mixture(inp,W,cp,tilt);Xb=es.calibrate(inp,q,E)
   for b in BETAS:
    Xt=es.tax_project(inp,Xb,E,float(b));pr=es.city_predictions(inp,Xt);k=(g,gi,float(b))
    pred[k]=pr;tv[k]=.5*np.abs(pr-ob).sum(1);loss[k]=-np.sum(ob*np.log(np.maximum(pr,1e-15)),1)
 keys=list(tv);L=np.array([loss[k] for k in keys]);T=np.array([tv[k] for k in keys])
 def select(mask,allowed):
  cand=[i for i,k in enumerate(keys) if allowed(k)];j=cand[int(np.argmin([np.average(L[i][mask],weights=w[mask]) for i in cand]))];return keys[j],j
 cells=pd.DataFrame({'city':codes,'age':h['age']+1,'fold':folds,'weight':w})
 size=cells.groupby('city').weight.sum();cells['city_size_class']=cells.city.map(lambda c:'large_ge250k' if size[c]>=250000 else 'medium_175k_250k' if size[c]>=175000 else 'small_lt175k')   # terciles of known-income population
 out={};oof_pred={}
 for name,allowed in MODELS.items():
  cv=np.zeros(n);pp=np.zeros((n,16));chosen=[]
  for f in range(5):
   train=folds!=f;test=~train;k,j=select(train,allowed);cv[test]=T[j][test];pp[test]=pred[k][test];chosen.append([k[0],k[1],k[2]])
  cells['tv_oof_'+name]=cv;oof_pred[name]=pp
  d=pd.DataFrame({'tv':cv,'w':w,'city':codes,'cls':cells.city_size_class})
  res={'weighted_mean':float(np.average(cv,weights=w)),'equal_city_mean':float(d.groupby('city').tv.mean().mean()),'equal_cell_mean':float(cv.mean()),'median':float(np.median(cv)),'p90':float(np.quantile(cv,.9)),'max':float(cv.max()),'fold_selection':chosen}
  for t,i in THRESH.items():
   err=np.abs(pp[:,i:].sum(1)-ob[:,i:].sum(1));res['abs_error_share_'+t]=float(np.average(err,weights=w));cells[f'err_{t}_{name}']=err
  res['by_city_size_class']={c:float(np.average(f.tv,weights=f.w)) for c,f in d.groupby('cls')}
  out[name]=res
 for name in ('M1','M2','M12','M0'):
  base='M0_notax' if name=='M0' else 'M0'
  d=cells['tv_oof_'+name]-cells['tv_oof_'+base];city=cells.assign(d=d).groupby('city').d.mean()
  out[name]['vs_'+base]={'weighted_mean_change':float(np.average(d,weights=w)),'relative_improvement':float(1-out[name]['weighted_mean']/out[base]['weighted_mean']),'fraction_cells_improved':float((d<0).mean()),'max_city_mean_worsening':float(city.max()),'worst_city':str(city.idxmax()),'meets_pre_registered_rule':bool(1-out[name]['weighted_mean']/out[base]['weighted_mean']>=ADOPT['min_relative_tv_improvement'] and out[name]['median']<=out[base]['median'] and city.max()<=ADOPT['max_city_mean_worsening_tv'])}
 d=cells.tv_oof_M12-cells.tv_oof_M1;out['M12']['vs_M1']={'weighted_mean_change':float(np.average(d,weights=w)),'relative_improvement':float(1-out['M12']['weighted_mean']/out['M1']['weighted_mean']),'fraction_cells_improved':float((d<0).mean()),'max_city_mean_worsening':float(cells.assign(d=d).groupby('city').d.mean().max())}
 # in-sample production coefficients and neighbours (Part B, city side)
 sens={}
 for k in [(PROD['gamma_edu'],PROD['gamma_ind'],PROD['beta'])]+NEIGHBOURS:
  kk=(k[0],k[1],float(k[2]));sens[str(list(k))]={'in_sample_weighted_tv':float(np.average(tv[kk],weights=w)),'in_sample_median':float(np.median(tv[kk]))}
 return out,cells,sens

def municipal(inp,W,cp,g,gi,b):
 r=es.run(inp,g,b,W=W,cp=cp,gamma_industry=gi);return r['Xt'],r['E']

def part_b(inp,W,cp,types):
 X0,E=municipal(inp,W,cp,PROD['gamma_edu'],PROD['gamma_ind'],PROD['beta']);pop=E;ok=pop>0;typ=np.array(types)
 out={}
 for k in NEIGHBOURS:
  X1,_=municipal(inp,W,cp,*k);tvm=.5*np.abs(norm(X1)-norm(X0)).sum(-1)
  rec={'weighted_mean_tv':float(np.average(tvm[ok],weights=pop[ok])),'p90':float(np.quantile(tvm[ok],.9)),'max':float(tvm[ok].max())}
  for t in ('city','town_village','ward'):
   sel=ok&(typ==t)[:,None,None];rec['weighted_mean_tv_'+t]=float(np.average(tvm[sel],weights=pop[sel])) if sel.any() else None
   rec['p90_'+t]=float(np.quantile(tvm[sel],.9)) if sel.any() else None
  out[str(list(k))]=rec
 return out

def part_c(inp,W,cp,types,names,S):
 tax=pd.read_csv(S/'tax_status/tax_status_2023_tidy.csv',dtype={'area':str}).set_index('area')
 areas=inp['areas'];parent=inp['parent'];pref=inp['pref']
 unit=[a if a.startswith('131') else parent.get(a,a) for a in areas]   # designated-city wards -> city; Tokyo wards stay
 units=sorted(set(unit));uidx={u:i for i,u in enumerate(units)};agg=np.zeros((len(areas),len(units)));agg[np.arange(len(areas)),[uidx[u] for u in unit]]=1
 utype=[];uname=[]
 for u in units:
  i=[j for j,x in enumerate(unit) if x==u];utype.append('designated_city' if len(i)>1 or types[i[0]]=='ward' and not u.startswith('131') else ('tokyo_ward' if u.startswith('131') else types[i[0]]));uname.append(names[i[0]] if len(i)==1 else names[i[0]].split('市')[0]+'市')
 upref=np.array([pref[unit.index(u)] for u in units])
 have=np.array([u in tax.index for u in units]);tx=tax.reindex(units)
 t1=np.log(np.maximum(tx.taxable_income_thousand_yen,1)/np.maximum(tx.income_levy_taxpayers,1)).to_numpy()
 t2=np.log(np.maximum(tx.salary_income_levy_thousand_yen,1)/np.maximum(tx.salary_income_levy_payers,1)).to_numpy()
 t3=(tx.total_percapita_levy_only/np.maximum(tx.total_taxpayers,1)).to_numpy()
 wt=np.maximum(tx.income_levy_taxpayers.fillna(0).to_numpy(),0)
 def within_pref(x,w):
  out=np.full_like(x,np.nan,dtype=float)
  for p in np.unique(upref):
   s=(upref==p)&have&np.isfinite(x)
   if s.sum()<2:continue
   out[s]=x[s]-np.average(x[s],weights=np.maximum(w[s],1))
  return out
 T1=within_pref(t1,wt);T2=within_pref(t2,wt);T3=within_pref(t3,wt)
 configs={'M0':(0.,0.,0.5),'M0_notax':(0.,0.,0.),'M1':(2.0,0.,0.),'M2':(0.,2.0,0.3),'M12':(PROD['gamma_edu'],PROD['gamma_ind'],PROD['beta'])}
 defined=(agg.T@es.run(inp,0.,0.,W=W,cp=cp)['E'].reshape(len(areas),-1)).sum(1)>0;have=have&defined   # areas with no paid workers (e.g. 双葉町, 2020 population 0) have no defined distribution
 rows=pd.DataFrame({'unit':units,'name':uname,'type':utype,'prefecture':[inp['prefs'][p] for p in upref],'in_tax_table':have,'tax_t1_log_taxable_income_per_payer_dev':T1,'tax_t2_log_salary_levy_per_payer_dev':T2,'tax_t3_levy_only_share_dev':T3,'income_levy_taxpayers':wt})
 model={}
 for name,k in configs.items():
  X,E=municipal(inp,W,cp,*k);Xu=agg.T@X.reshape(len(areas),-1);Xu=Xu.reshape(len(units),2,13,16).sum((1,2));Eu=Xu.sum(-1)
  mean=np.log(np.maximum((Xu*MIDS).sum(-1),1)/np.maximum(Eu,1));low=Xu[:,:2].sum(-1)/np.maximum(Eu,1)
  model[name]={'m1':within_pref(mean,Eu),'m3':within_pref(low,Eu),'E':Eu}
  rows['model_m1_'+name]=model[name]['m1'];rows['model_m3_'+name]=model[name]['m3'];rows['paid_workers_'+name]=Eu
 def corr(x,y,sel):
  s=sel&np.isfinite(x)&np.isfinite(y)
  if s.sum()<5:return None
  return {'n':int(s.sum()),'pearson':float(np.corrcoef(x[s],y[s])[0,1]),'spearman':float(np.corrcoef(pd.Series(x[s]).rank().to_numpy(),pd.Series(y[s]).rank().to_numpy())[0,1])}
 groups={'all':have,'city':have&(np.array(utype)=='city'),'town_village':have&(np.array(utype)=='town_village'),'designated_city':have&(np.array(utype)=='designated_city'),'tokyo_ward':have&(np.array(utype)=='tokyo_ward')}
 res={'units':len(units),'units_compared':int(have.sum()),'units_excluded_no_paid_workers':int((~defined).sum()),'correlations':{}}
 for name in configs:
  res['correlations'][name]={g:{'m1_vs_t1':corr(model[name]['m1'],T1,s),'m1_vs_t2':corr(model[name]['m1'],T2,s),'m3_vs_t3':corr(model[name]['m3'],T3,s)} for g,s in groups.items()}
 # direction consistency: does the M12-M0 change point toward the tax residual?
 rng=np.random.default_rng(0);dc={}
 for name,base in (('M12','M0_notax'),('M12','M0'),('M1','M0_notax'),('M2','M0_notax'),('M12','M1')):
  d=model[name]['m1']-model[base]['m1'];resid=T1-model[base]['m1']
  for g,s in groups.items():
   sel=s&np.isfinite(d)&np.isfinite(resid)
   if sel.sum()<10:continue
   x=d[sel];y=resid[sel];c=float(np.corrcoef(x,y)[0,1])
   boots=[np.corrcoef(x[i],y[i])[0,1] for i in (rng.integers(0,len(x),len(x)) for _ in range(1000))]
   dc[f'{name}_minus_{base}:{g}']={'n':int(sel.sum()),'corr_change_vs_residual':c,'bootstrap_95':[float(np.quantile(boots,.025)),float(np.quantile(boots,.975))],'fraction_moved_toward_tax':float(np.mean(np.sign(x)==np.sign(y)))}
 res['direction_consistency']=dc
 c12=res['correlations']['M12'];c0=res['correlations']['M0_notax']
 not_worse=all(c12[g]['m1_vs_t1'] is None or c0[g]['m1_vs_t1'] is None or c12[g]['m1_vs_t1']['pearson']>=c0[g]['m1_vs_t1']['pearson']-0.01 for g in ('city','town_village','designated_city','tokyo_ward'))
 key='M12_minus_M0_notax:all';positive=key in dc and dc[key]['bootstrap_95'][0]>0
 res['pre_registered_support_rule']={'correlation_not_worse_than_M0_notax_by_group':bool(not_worse),'direction_consistency_positive_ci':bool(positive),'supported':bool(not_worse and positive)}
 return res,rows

def main():
 t0=time.time();S=SOURCES;inp=es.load_real_inputs(S);W=es.fit_status(inp);cp=es.status_income_shapes(inp)
 types,names=area_types(S,inp['areas'])
 out={'protocol':__doc__,'production':PROD,'adoption_rule':ADOPT,'inputs':{'catalog_manifest_sha256':sha('manifest.json'),'industry_manifest_sha256':sha('industry/manifest.json'),'education_manifest_sha256':sha('education/manifest.json'),'tax_status_manifest_sha256':sha('tax_status/manifest.json'),'production_json':json.loads((CATALOG/'production.json').read_text()) if (CATALOG/'production.json').exists() else None},'area_counts':{t:int(np.sum(np.array(types)==t)) for t in set(types)}}
 a,cells,sens=part_a(inp,W,cp);out['A_heldout_same_denominator']=a;out['B_city_in_sample_sensitivity']=sens;print('A done',round(time.time()-t0),flush=True)
 out['B_municipal_change_from_production']=part_b(inp,W,cp,types);print('B done',round(time.time()-t0),flush=True)
 if (S/'tax_status/tax_status_2023_tidy.csv').exists():
  c,rows=part_c(inp,W,cp,types,names,S);out['C_independent_tax_check']=c;rows.to_csv(REPORTS/'validation_m12_areas.csv',index=False)
 else:out['C_independent_tax_check']={'skipped':'sources/tax_status missing; run make fetch-tax-status'}
 out['dependence_on_prefecture_aggregates']='pref_target (ESS prefecture income shares) and ess_cat (prefecture status x income) include the 86 evaluation cities; seed_q for towns comes from the prefecture 表3-1 row; edu_rate for most municipalities is the prefecture education x labour table; ind_q is national. Held-out city cells are therefore not independent of the inputs.'
 out['elapsed_seconds']=round(time.time()-t0,1)
 (REPORTS/'validation_m12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=float));cells.to_csv(REPORTS/'validation_m12_cells.csv',index=False)
 print(json.dumps({k:{x:round(v[x],5) for x in ('weighted_mean','equal_city_mean','median','p90','max','abs_error_share_ge300','abs_error_share_ge500','abs_error_share_ge700')} for k,v in a.items()},indent=1))
 if 'C_independent_tax_check' in out and 'correlations' in out['C_independent_tax_check']:
  print(json.dumps({m:{g:(v['m1_vs_t1'] or {}).get('pearson') for g,v in c.items()} for m,c in out['C_independent_tax_check']['correlations'].items()},indent=1));print(json.dumps(out['C_independent_tax_check']['pre_registered_support_rule']))
if __name__=='__main__':main()
