"""Reproducible small-area main-job annual income synthesis; Python 3.11+, numpy, pandas."""
from paths import REPORTS,OUTPUT as OUT,SOURCES as DATA
import json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from model_math import AGES,STATUS,norm,ipf

def read(n):return pd.read_csv(DATA/n,dtype={'area':str,'age':str,'sex':str,'type':str,'status':str,'income':str})
def categories(f):
 return np.column_stack([f.regular,f.dispatch+f.part_other,f.executive,f.self_with+f.self_without+f.homework,f.family])

def main(shrink=1000.):
 OUT.mkdir(parents=True,exist_ok=True)
 (REPORTS).mkdir(parents=True,exist_ok=True)
 pop=read('census_population_tidy.csv.gz');labor=read('census_imputed_age_tidy.csv.gz');status=read('census_imputed_detailed_status_tidy.csv.gz');seed=read('census_age_status_tidy.csv.gz');inc=read('income_tidy.csv.gz')
 geos=pop[['area','name','type']].drop_duplicates().sort_values('area')
 # Nonoverlapping geography: all wards (Tokyo special wards included), cities except designated-city parents, towns/villages.
 leaf=geos[geos.type.isin(['0','2','3'])].copy();areas=leaf.area.tolist();M=len(areas);A=13;S=2
 idx=pd.MultiIndex.from_product([areas,['1','2'],AGES],names=['area','sex','age'])
 N=pop.set_index(['area','sex','age']).reindex(idx).population.to_numpy().reshape(M,S,A)
 L=labor.set_index(['area','sex','age']).reindex(idx)
 Nraw=L.population.to_numpy().reshape(M,S,A);Eraw=L.employed.to_numpy().reshape(M,S,A)
 assert np.isfinite(N).all() and np.isfinite(Eraw).all()
 assert np.allclose(N.sum((0,1)),pop[(pop.area=='00000')&(pop.sex=='0')].sort_values('age').population)
 T=status.set_index(['area','sex']);D=seed.set_index(['area','sex']);
 W=np.zeros((M,S,A,5));fitrows=[];seed_sources=[]
 for mi,m in enumerate(areas):
  pref=m[:2]+'000';src=m if m in seed.area.values else pref;seed_sources.append(src)
  for si,s in enumerate(['1','2']):
   v=D.loc[(src,s)].set_index('age').reindex(AGES);q=categories(v)
   t=categories(T.loc[[(m,s)]])[0]
   # Published imputation tables differ only by occasional integer rounding.
   t*=Eraw[mi,si].sum()/max(t.sum(),1e-300)
   z,it,err=ipf(q,Eraw[mi,si],t)
   scale=np.divide(N[mi,si],Nraw[mi,si],out=np.ones(A),where=Nraw[mi,si]>0)
   W[mi,si]=z*scale[:,None]
   # Empty age-sex labor cells use prefecture employment rate and category mix if population imputation creates residents.
   for a in np.where((Nraw[mi,si]==0)&(N[mi,si]>0))[0]:
    pl=labor[(labor.area==pref)&(labor.sex==s)&(labor.age==AGES[a])].iloc[0]
    rate=pl.employed/pl.population if pl.population else 0
    W[mi,si,a]=N[mi,si,a]*rate*norm(q[a])
   fitrows.append((m,s,src,it,err))
 assert (W.sum(-1)<=N+1e-5).all()
 # ESS source tensor: region, sex, age incl total, selected source employment categories, income incl total.
 I=inc.pivot(index=['area','sex','age','status'],columns='income',values='count').sort_index(axis=1)
 def raw(area,s,a,k):return I.loc[(area,s,a,k)].to_numpy(float)
 def cat_counts(area,s,a):
  reg=raw(area,s,a,'22');nonreg=raw(area,s,a,'23');own=raw(area,s,a,'1')
  residual=raw(area,s,a,'2')-reg-nonreg
  return [reg,nonreg,np.maximum(residual,0),own],residual
 q=np.zeros((M,S,A,16));E=W[:,:,:,:4].sum(-1)
 smoothing=[];negatives=[]
 for mi,m in enumerate(areas):
  p=m[:2]+'000'
  for si,s in enumerate(['1','2']):
   for ai,a in enumerate(AGES):
    counts,res=cat_counts(p,s,a);national,_=cat_counts('00000',s,a)
    cp=[]
    for k in range(4):
     prior=norm(national[k][1:]+1e-8)
     vals=counts[k][1:];cp.append(norm(vals+shrink*prior))
    q[mi,si,ai]=np.sum(W[mi,si,ai,:4,None]*cp,axis=0)/max(E[mi,si,ai],1e-300)
 # Calibrate municipality income rows to prefecture-sex-age observed known-income shares.
 X=np.zeros_like(q);calibration=[]
 for p in sorted(set(m[:2]+'000' for m in areas)):
  ids=np.array([i for i,m in enumerate(areas) if m[:2]==p[:2]])
  for si,s in enumerate(['1','2']):
   for ai,a in enumerate(AGES):
    r=E[ids,si,ai];target=norm(raw(p,s,a,'0')[1:])
    z,it,err=ipf(q[ids,si,ai]*r[:,None],r,target*r.sum())
    X[ids,si,ai]=z
    calibration.append((p,s,a,it,err,float(np.max(np.abs(z.sum(0)/max(r.sum(),1)-target)))))
    c,res=cat_counts(p,s,a)
    for j in np.where(res<0)[0]:negatives.append((p,s,a,j,float(res[j])))
    for k,v in enumerate(c):smoothing.append((p,s,a,STATUS[k],float(v[0]),float(v[1:].sum()),float(shrink/(v[1:].sum()+shrink)) if shrink else 0.))
 # Bin 0 is a synthetic structural zero for nonworkers and unpaid family workers, NOT an observed exact-zero rate.
 Z=N-E
 C=np.concatenate([Z[...,None],X],axis=-1).sum(1) # municipality, age, income
 n=N.sum(1)
 P=np.divide(C,n[...,None],out=np.full_like(C,np.nan),where=n[...,None]>0)
 assert np.nanmax(np.abs(P.sum(-1)-1))<1e-9
 joint=C/N.sum()
 assert abs(joint.sum()-1)<1e-10
 np.savez_compressed(OUT/'model_arrays.npz',areas=np.array(areas),population=N,employment_status=W,counts_by_sex=np.concatenate([Z[...,None],X],axis=-1),counts=C,probability=P,joint=joint)
 age_labels=[f'{15+i*5}–{19+i*5}歳' for i in range(12)]+['75歳以上']
 edges=[0,50,100,150,200,250,300,400,500,600,700,800,900,1000,1250,1500,None]
 bins=[{'income_code':'ZERO','label':'非就業・無給家族従業のモデル上0円','lower_yen':0,'upper_yen':0,'is_structural_zero':True}]
 for i in range(16):bins.append({'income_code':f'I{i+1:02}','label':f'{edges[i]}–{edges[i+1]}万円未満' if i<15 else '1500万円以上','lower_yen':edges[i]*10000,'upper_yen':None if edges[i+1] is None else edges[i+1]*10000,'is_structural_zero':False})
 pd.DataFrame(bins).to_csv(OUT/'income_bins.csv',index=False)
 leaf['prefecture_code']=leaf.area.str[:2];leaf['age_status_seed_area']=seed_sources;leaf['population_15plus']=n.sum(1);leaf.to_csv(OUT/'municipalities.csv',index=False)
 # Separate parent mapping prevents accidental double counting of designated cities and wards.
 mapping=[]
 for _,r in geos[geos.type=='1'].iterrows():
  # Census area order lists a designated city followed immediately by all its wards.
  start=geos.index[geos.area==r.area][0]
  # Match prefix city name; Tokyo special-ward aggregate is the explicit 131xx set.
  child=leaf[leaf.area.str.startswith('131')] if r.area=='13100' else leaf[(leaf.type=='0')&leaf.name.str.startswith(r['name'])]
  for _,ch in child.iterrows():mapping.append((r.area,r['name'],ch.area,ch['name']))
 pd.DataFrame(mapping,columns=['parent_code','parent_name','area','name']).to_csv(OUT/'parent_mapping.csv',index=False)
 pd.DataFrame(fitrows,columns=['area','sex','seed_area','iterations','relative_error']).to_csv(REPORTS/'status_ipf.csv',index=False)
 pd.DataFrame(calibration,columns=['prefecture','sex','age','iterations','relative_error','max_income_share_error']).to_csv(REPORTS/'income_calibration.csv',index=False)
 pd.DataFrame(smoothing,columns=['prefecture','sex','age','status','source_total','known_income_total','national_shrinkage_weight']).to_csv(REPORTS/'income_source_quality.csv',index=False)
 pd.DataFrame(negatives,columns=['prefecture','sex','age','income_index','negative_residual']).to_csv(REPORTS/'residual_clipping.csv',index=False)
 # Held-out city-age distributions: city ESS income is never used to construct X.
 cmap={m:[i] for i,m in enumerate(areas)}
 for parent,_,ch,_ in mapping:cmap.setdefault(parent,[]).append(areas.index(ch))
 evalrows=[]
 for city in sorted(set(inc.area)-set([f'{i:02}000' for i in range(48)])):
  if city not in cmap:continue
  ids=cmap[city];pref=city[:2]+'000'
  for ai,a in enumerate(AGES):
   obs=raw(city,'0',a,'0')[1:];total=obs.sum()
   if total<1000:continue
   obs=norm(obs);pred=norm(X[ids,:,ai].sum((0,1)));base=norm(raw(pref,'0',a,'0')[1:]);national=norm(raw('00000','0',a,'0')[1:])
   evalrows.append((city,geos.set_index('area').loc[city,'name'],pref,a,total,.5*np.abs(pred-obs).sum(),.5*np.abs(base-obs).sum(),.5*np.abs(national-obs).sum(),pred[8:].sum(),obs[8:].sum()))
 ev=pd.DataFrame(evalrows,columns=['area','name','prefecture','age','survey_expanded_known_income_count','tv_model','tv_prefecture_only','tv_national_age','p_ge500_model','p_ge500_observed'])
 ev.to_csv(REPORTS/'heldout_cities.csv',index=False)
 summary={'model_version':'1.0','population_year':2020,'income_year':2022,'geography_year':2020,'age_definition':'15-19,...,70-74,75+','income_definition':'primary-job usual annual gross wages / net business revenue before personal tax; excludes secondary jobs, pensions, assets','leaf_regions':M,'age_groups':A,'income_bins':17,'cells':int(M*A*17),'population_15plus':float(N.sum()),'estimated_paid_workers':float(E.sum()),'structural_zero_probability':float(Z.sum()/N.sum()),'joint_sum':float(joint.sum()),'max_conditional_sum_error':float(np.nanmax(abs(P.sum(-1)-1))),'zero_population_municipality_age_cells':int((n==0).sum()),'status_ipf_max_relative_error':float(max(r[-1] for r in fitrows)),'income_calibration_max_share_error':float(max(r[-1] for r in calibration)),'income_national_pseudopopulation':shrink,'heldout_city_count':ev.area.nunique(),'heldout_city_age_cells':len(ev),'tv_model_weighted':float(np.average(ev.tv_model,weights=ev.survey_expanded_known_income_count)),'tv_prefecture_only_weighted':float(np.average(ev.tv_prefecture_only,weights=ev.survey_expanded_known_income_count)),'tv_national_age_weighted':float(np.average(ev.tv_national_age,weights=ev.survey_expanded_known_income_count)),'city_age_fraction_improved':float((ev.tv_model<ev.tv_prefecture_only).mean()),'negative_executive_residual_cells':len(negatives)}
 (REPORTS/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main(float(sys.argv[1]) if len(sys.argv)>1 else 1000.)
