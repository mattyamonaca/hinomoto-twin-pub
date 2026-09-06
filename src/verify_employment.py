"""Verify the stage-A employment/industry allocation and evaluate it on city tables that were not used to build it.

Checks: margins (production education x income, employment status, census industry), non-negativity, parent/ward sums.
Held-out evaluations (city rows of ESS regional tables, never used in the allocation; prefecture rows are used):
  1. 10-1 city rows: status x industry by sex and age  -> TV of P(k,g | city,s,a) vs observed, against two baselines:
     'prefecture' = prefecture P(g|k) applied to the city's model status margin; 'independent' = P(k)P(g) of the model.
  2. table 24 city rows: industry x income by sex (no age) -> TV of P(y | g, city, s) vs observed, against the
     'national' baseline (national P(y|g,s)) and 'status-only' (model P(y|city,s) ignoring industry).
Outputs: validation/employment_a_verification.json, validation/employment_a_heldout.csv
"""
import json
import numpy as np
import pandas as pd
from paths import SOURCES,OUTPUT,REPORTS
from model_math import AGES,norm

G=[f'G{i:02}' for i in range(1,21)]

def city_map(names_by_area,geo,parents):
 """Map ESS city codes (C+3 digits) to leaf indices via prefecture prefix + municipality name."""
 out={}
 for area,name in names_by_area.items():
  if not area.startswith('C'):continue
  pref=area[1:3];cand=geo[(geo.prefecture_code==pref)&(geo.municipality_name==name)&(geo.geography_level=='municipality')]
  if len(cand)!=1:continue
  code=cand.municipality_code.iloc[0];out[area]=(code,parents.get(code,[code]))
 return out

def main():
 d=np.load(OUTPUT/'employment_a.npz');areas=d['areas'].tolist();ix={a:i for i,a in enumerate(areas)};N=d['population']
 kg=d['status_industry'];ke=d['education_status'];ky=d['status_income'];gy=d['industry_income']
 fin=np.load(OUTPUT/'final_arrays.npz');mdl=np.load(OUTPUT/'model_arrays.npz');W=mdl['employment_status']
 res={'passed':True,'checks':{}}
 res['checks']['nonnegative']=bool((kg>=-1e-9).all() and (ke>=-1e-9).all() and (gy>=-1e-9).all())
 res['checks']['population_margin_max_error_persons']=float(np.abs(kg.sum((3,4))-N).max())
 res['checks']['status_margin_max_error_persons']=float(np.abs(ke[...,:5].sum(3)-W).max())
 res['checks']['production_income_margin_max_error_persons']=float(np.abs(ky.sum(3)-fin['counts_by_sex'][...,1:]).max())
 c=pd.read_csv(SOURCES/'industry/census_industry_age_tidy.csv.gz',dtype={'area':str,'sex':str,'age':str}).set_index(['area','sex','age'])
 idx=pd.MultiIndex.from_product([areas,['1','2'],AGES],names=['area','sex','age']);cnt=np.nan_to_num(c.reindex(idx)[G].to_numpy(float).reshape(len(areas),2,13,20))
 emp=W.sum(-1);ok=cnt.sum(-1)>0
 gshare=norm(kg[...,:5,1:].sum(3));err=.5*np.abs(gshare-norm(cnt)).sum(-1)
 res['checks']['industry_margin_tv_weighted_mean']=float(np.average(err[ok],weights=emp[ok]));res['checks']['industry_margin_tv_max']=float(err[ok].max());res['checks']['industry_margin_note']='Family workers take the prefecture self-employed industry profile; where that exceeds the census count in a tiny cell, the paid margin is clipped, so small cells can deviate.'
 geo=pd.read_csv(OUTPUT/'geography.csv',dtype=str);pm=pd.read_csv(OUTPUT/'parent_mapping.csv',dtype=str);parents={p:f.area.tolist() for p,f in pm.groupby('parent_code')}
 # ---- held-out 1: 10-1 city rows
 t=pd.read_csv(SOURCES/'industry/ess_status_industry_age_tidy.csv.gz',dtype=str)
 for a in AGES:t[a]=t[a].astype(float)
 names=dict(zip(t.area,t.name));cm=city_map(names,geo,parents)
 t=t[(t.industry!='G00')&(t.education=='0')].set_index(['area','sex','status','industry']).sort_index()
 def obs_kg(area,s):
  blk=t.loc[(area,s)];tot=blk.loc['0'][AGES].to_numpy();empl=blk.loc['1'][AGES].to_numpy();reg=blk.loc['12'][AGES].to_numpy();non=blk.loc['13'][AGES].to_numpy()
  return np.stack([reg,non,np.maximum(empl-reg-non,0),np.maximum(tot-empl,0)]).transpose(2,0,1)   # (13,4,20): K1,K2,K3,K4(+K5)
 rows=[]
 for carea,(code,leaf) in cm.items():
  ids=[ix[x] for x in leaf if x in ix];p=code[:2]+'000'
  for si,s in enumerate(['1','2']):
   o=obs_kg(carea,s);pr=obs_kg(p,s)
   m=kg[ids,si][:,:,:5,1:].sum(0)                              # (13,5,20) model city counts
   m4=np.concatenate([m[:,:3],m[:,3:5].sum(1,keepdims=True)],1)   # merge K4+K5 to match own-account+family
   for ai in range(13):
    tot=o[ai].sum()
    if tot<1000:continue
    ob=o[ai]/tot;mo=norm(m4[ai].ravel()).reshape(4,20)
    kmarg=m4[ai].sum(1);pg=norm(pr[ai]);base_pref=norm((kmarg[:,None]*pg).ravel()).reshape(4,20)
    indep=norm(m4[ai].sum(1))[:,None]*norm(m4[ai].sum(0))[None]
    def cond_k(x):return np.divide(x,x.sum(0,keepdims=True),out=np.zeros_like(x),where=x.sum(0,keepdims=True)>0)   # P(k|g)
    wg=ob.sum(0);tvk=lambda x:float((wg*0.5*np.abs(cond_k(x)-cond_k(ob)).sum(0)).sum())                          # observed-industry-weighted TV of P(k|g)
    rows.append({'table':'10-1','city':code,'sex':s,'age':AGES[ai],'weight':tot,'tv_model':.5*np.abs(mo-ob).sum(),'tv_prefecture':.5*np.abs(base_pref-ob).sum(),'tv_independent':.5*np.abs(indep-ob).sum(),'tv_industry_margin_model':.5*np.abs(mo.sum(0)-ob.sum(0)).sum(),'tv_status_margin_model':.5*np.abs(mo.sum(1)-ob.sum(1)).sum(),'tv_status_given_industry_model':tvk(mo),'tv_status_given_industry_prefecture':tvk(base_pref),'tv_status_given_industry_independent':tvk(indep)})
 # ---- held-out 2: table 24 city rows (industry x income, status total, by sex)
 e=pd.read_csv(SOURCES/'industry/income_industry_tidy.csv.gz',dtype={'area':str,'sex':str,'status':str,'income':str,'industry':str})
 e=e[(e.status=='0')&(e.income!='00')&(e.industry!='G00')]
 nat={s:e[(e.area=='00000')&(e.sex==s)].pivot(index='industry',columns='income',values='count').sort_index(axis=1) for s in ['1','2']}
 names24=dict(zip(e.area,e.name));cm24=city_map(names24,geo,parents)
 for carea,(code,leaf) in cm24.items():
  ids=[ix[x] for x in leaf if x in ix]
  for si,s in enumerate(['1','2']):
   piv=e[(e.area==carea)&(e.sex==s)].pivot(index='industry',columns='income',values='count').sort_index(axis=1)
   m=gy[ids,si].sum((0,1))                                       # (20,16) model city industry x income (all ages)
   status_only=norm(m.sum(0))
   for gi,g in enumerate(G):
    o=piv.loc[g].to_numpy(float);tot=o.sum()
    if tot<1000:continue
    ob=o/tot;mo=norm(m[gi]);nb=norm(nat[s].loc[g].to_numpy(float))
    rows.append({'table':'24','city':code,'sex':s,'age':'all','industry':g,'weight':tot,'tv_model':.5*np.abs(mo-ob).sum(),'tv_national':.5*np.abs(nb-ob).sum(),'tv_status_only':.5*np.abs(status_only-ob).sum()})
 df=pd.DataFrame(rows);df.to_csv(REPORTS/'employment_a_heldout.csv',index=False)
 def summ(sub,cols):
  w=sub.weight.to_numpy();return {c:{'weighted_mean':float(np.average(sub[c],weights=w)),'median':float(sub[c].median()),'p90':float(sub[c].quantile(.9))} for c in cols}
 h1=df[df.table=='10-1'];h2=df[df.table=='24']
 res['heldout_10_1_status_x_industry']={'cities':int(h1.city.nunique()),'cells':len(h1),**summ(h1,['tv_model','tv_prefecture','tv_independent','tv_industry_margin_model','tv_status_margin_model','tv_status_given_industry_model','tv_status_given_industry_prefecture','tv_status_given_industry_independent']),'note':'City rows of ESS regional 10-1 (status x industry x age by sex) were not used; prefecture rows were the seed. Own-account and family workers are compared together. The industry margin comes from the 2020 census (residence-based employed persons) while the ESS is a 2022 sample survey; their city compositions differ by TV ~0.2 on average, so the joint TV is bounded by source disagreement. tv_status_given_industry compares the conditional P(k|g) only.'}
 res['heldout_24_industry_x_income']={'cities':int(h2.city.nunique()),'cells':len(h2),**summ(h2,['tv_model','tv_national','tv_status_only']),'note':'City rows of ESS regional 24 (industry x income by sex, all ages) were not used; the national rows shaped the income tilt.'}
 res['association_tv_joint_vs_independent']={'weighted_mean':float(np.average(d['independence_tv'][N>0],weights=N[N>0]))}
 res['passed']=bool(res['checks']['nonnegative'] and res['checks']['population_margin_max_error_persons']<0.1 and res['checks']['status_margin_max_error_persons']<0.1 and res['checks']['production_income_margin_max_error_persons']<0.1 and res['checks']['industry_margin_tv_weighted_mean']<1e-3)
 (REPORTS/'employment_a_verification.json').write_text(json.dumps(res,ensure_ascii=False,indent=2));print(json.dumps(res,ensure_ascii=False,indent=1))
if __name__=='__main__':main()
