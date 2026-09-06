"""Soft municipal income-level adjustment. Taxable income is a proxy, never a wage mean target."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from build import norm,BASE,DATA,OUT,AGES

def main():
 d=np.load(OUT/'model_arrays.npz');areas=d['areas'].tolist();N=d['population'];C0=d['counts_by_sex'];X0=C0[...,1:];E=X0.sum(-1)
 tax=pd.read_csv(DATA/'tax_tidy.csv',dtype={'area':str}).set_index('area');geo=pd.read_csv(OUT/'municipalities.csv',dtype={'area':str});parents=pd.read_csv(OUT/'parent_mapping.csv',dtype={'parent_code':str,'area':str});parent=dict(zip(parents.area,parents.parent_code))
 ratios=[];sources=[]
 for m in areas:
  p=m[:2]+'000';src=m
  t=tax.loc[src] if src in tax.index else None
  if t is None or not np.isfinite(t.taxable_income_million_yen) or not t.income_taxpayers>0:
   src=parent.get(m,p);t=tax.loc[src]
  if not np.isfinite(t.taxable_income_million_yen) or not t.income_taxpayers>0:src=p;t=tax.loc[p]
  pmean=tax.loc[p,'taxable_income_million_yen']/tax.loc[p,'income_taxpayers'];r=np.log(t.taxable_income_million_yen/t.income_taxpayers/pmean)
  ratios.append(r);sources.append(src)
 feature=np.clip(ratios,-.5,.5)
 # Midpoints define a monotone tilt score only; no within-bin income values or mean are claimed.
 mids=np.array([25,75,125,175,225,275,350,450,550,650,750,850,950,1125,1375,1750.])
 score=np.log(mids/300)
 groups={p:np.array([i for i,m in enumerate(areas) if m[:2]==p]) for p in sorted(set(m[:2] for m in areas))}
 def project(beta):
  x=X0*np.exp(beta*feature[:,None,None,None]*score)
  for ids in groups.values():
   z=x[ids];r=E[ids];target=X0[ids].sum(0)
   for it in range(500):
    z*=np.divide(r,z.sum(-1),out=np.zeros_like(r),where=z.sum(-1)>0)[...,None]
    z*=np.divide(target,z.sum(0),out=np.zeros_like(target),where=z.sum(0)>0)[None,...]
    err=np.max(np.abs(z.sum(-1)-r)/np.maximum(r,1))
    if err<1e-10:break
   else:raise RuntimeError('Tax projection failed')
   x[ids]=z
  return x
 # Compare 86 city income tables not used by the base model. Fit one coefficient leaving prefecture groups out.
 inc=pd.read_csv(DATA/'income_tidy.csv.gz',dtype={k:str for k in ['area','sex','age','status','income']})
 obs=inc[(inc.sex=='0')&(inc.status=='0')&(inc.income!='00')&(inc.age!='00')].pivot(index=['area','age'],columns='income',values='count')
 checks=pd.read_csv(BASE/'validation/heldout_cities.csv',dtype={'area':str,'age':str,'prefecture':str})
 cidx={m:[i] for i,m in enumerate(areas)}
 for p,f in parents.groupby('parent_code'):cidx[p]=[areas.index(a) for a in f.area]
 ob=np.array([norm(obs.loc[(r.area,r.age)].values) for r in checks.itertuples()]);weights=checks.survey_expanded_known_income_count.to_numpy()
 betas=np.linspace(0,4,41);loss=[];tv=[];prediction=[]
 for beta in betas:
  x=project(beta);pr=np.array([norm(x[cidx[r.area],:,int(r.age)-1].sum((0,1))) for r in checks.itertuples()])
  loss.append(-np.sum(ob*np.log(np.maximum(pr,1e-15)),1));tv.append(.5*np.abs(pr-ob).sum(1));prediction.append(pr)
 loss=np.array(loss);tv=np.array(tv);prediction=np.array(prediction)
 folds=np.array([int(p[:2])%5 for p in checks.prefecture]);cv=np.zeros(len(checks));cvbeta=[]
 for fold in range(5):
  train=folds!=fold;test=~train;j=int(np.argmin(np.average(loss[:,train],axis=1,weights=weights[train])))
  cv[test]=tv[j,test];cvbeta.append({'fold':fold,'beta':float(betas[j]),'test_city_age_cells':int(test.sum())})
 best=int(np.argmin(np.average(loss,axis=1,weights=weights)));beta=float(betas[best]);base_tv=float(np.average(tv[0],weights=weights));cv_tv=float(np.average(cv,weights=weights))
 selected=beta if cv_tv<base_tv else 0.
 X=project(selected);C=np.concatenate([C0[...,:1],X],axis=-1);aggregate=C.sum(1);pop=N.sum(1)
 np.savez_compressed(OUT/'final_arrays.npz',areas=np.array(areas),population=N,counts_by_sex=C,counts=aggregate,probability=np.divide(aggregate,pop[...,None],out=np.full_like(aggregate,np.nan),where=pop[...,None]>0),p_age_income_given_municipality=np.divide(aggregate,pop.sum(-1)[:,None,None],out=np.full_like(aggregate,np.nan),where=pop.sum(-1)[:,None,None]>0),joint=aggregate/N.sum())
 quality=pd.DataFrame({'area':areas,'tax_source_area':sources,'log_tax_ratio':ratios,'clipped_log_tax_ratio':feature,'feature_clipped':np.abs(ratios)>.5})
 quality.to_csv(BASE/'validation/tax_proxy_quality.csv',index=False)
 checks['tv_tax_out_of_fold']=cv;checks['tv_tax_full_fit']=tv[best];checks.to_csv(BASE/'validation/city_validation_with_tax.csv',index=False)
 pd.DataFrame({'beta':betas,'weighted_cross_entropy':np.average(loss,axis=1,weights=weights),'weighted_tv':np.average(tv,axis=1,weights=weights)}).to_csv(BASE/'validation/tax_parameter_search.csv',index=False)
 summary={'tax_fiscal_year':2022,'tax_income_reference_year':2021,'feature':'log(municipal taxable-income-per-taxpayer / prefectural value), clipped [-0.5,0.5]','income_tilt_score':'log(bin representative/3 million yen), representatives 0.25,...,17.5 million','fit_criterion':'population-weighted known-income cross entropy; weights are expanded population, not sample sizes','coefficient_grid':[0,4,.1],'beta_full_fit':beta,'beta_selected':selected,'five_fold_by_prefecture':cvbeta,'tv_base':base_tv,'tv_tax_out_of_fold':cv_tv,'tv_tax_in_sample':float(np.average(tv[best],weights=weights)),'relative_tv_improvement_out_of_fold':1-cv_tv/base_tv,'municipality_proxy_missing_uses_parent_or_prefecture':int(sum(a!=s for a,s in zip(areas,sources))),'feature_clipped_count':int((np.abs(ratios)>.5).sum()),'warning':'City income tables are not used in base model but city data contribute to prefecture totals. CV is not independent microdata validation; small towns and individual wards are not validated by city holdouts.'}
 (BASE/'validation/tax_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print(json.dumps(summary,indent=2,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
