"""Array-level estimator for the municipal income model (M0) and its experimental variants (M1, M2 hook).

Every function takes and returns numpy arrays; nothing here reads or writes files. `load_real_inputs()`
builds the input contract from the normalized sources, and `synthetic_population.py` builds the same
contract from a virtual population, so the same code runs on both.

Input contract (leaf areas M, prefectures P, sexes 2, ages 13, statuses 5, incomes 16, educations 8):
  areas        list[str]      leaf area codes (non-overlapping)
  pref         (M,) int       prefecture index of each area
  N            (M,2,13)       imputed population 15+
  Nraw, Eraw   (M,2,13)       age-known population and employed persons (labor table)
  seed_q       (M,2,13,5)     age x status seed shape (own table or prefecture)
  t_status     (M,2,5)        status totals per area x sex
  pref_rate    (P,2,13)       prefecture employment rate (fallback for empty cells)
  ess_cat      (P,2,13,4,16)  known-income counts by paid status category (regular, nonregular, executive, self)
  nat_cat      (2,13,4,16)    the same for the whole country
  pref_target  (P,2,13,16)    published known-income shares, status total
  tax_feature  (M,)           clipped log(taxable income per taxpayer / prefecture)
  edu_share    (M,2,13,8)     education composition (E08 unknown kept)
  edu_q        (2,13,8,16)    national education x income shapes (paid workers, smoothed)
  edu_rate     (M,2,13,8)     education-specific employment-rate seeds
  heldout      dict           city evaluation cells: ids (list of leaf index lists), age (int idx), obs (n,16), weight (n,), pref (n,)
"""
import numpy as np
from model_math import AGES,norm,ipf

MIDS=np.array([25,75,125,175,225,275,350,450,550,650,750,850,950,1125,1375,1750.])
SCORE=np.log(MIDS/300)

def fit_status(inp):
 """Stage 1-2: age x employment-status table per area and sex, then population linkage. Returns W (M,2,13,5)."""
 N=inp['N'];Nraw=inp['Nraw'];Eraw=inp['Eraw'];M=N.shape[0];W=np.zeros((M,2,13,5))
 for mi in range(M):
  for si in range(2):
   q=inp['seed_q'][mi,si];t=inp['t_status'][mi,si].copy()
   t*=Eraw[mi,si].sum()/max(t.sum(),1e-300)
   z,it,err=ipf(q,Eraw[mi,si],t)
   scale=np.divide(N[mi,si],Nraw[mi,si],out=np.ones(13),where=Nraw[mi,si]>0)
   W[mi,si]=z*scale[:,None]
   for a in np.where((Nraw[mi,si]==0)&(N[mi,si]>0))[0]:
    W[mi,si,a]=N[mi,si,a]*inp['pref_rate'][inp['pref'][mi],si,a]*norm(q[a])
 return W

def status_income_shapes(inp,shrink=1000.):
 """Stage 3: r(y|p,s,a,k) smoothed toward the national shape. Returns (P,2,13,4,16)."""
 prior=norm(inp['nat_cat']+1e-8)[None]
 return norm(inp['ess_cat']+shrink*prior)

def composition_tilt(share,q,N,pref,gamma):
 """Generic M1/M2 tilt: ratio of the group-composition-implied income shape of the area to that of its prefecture, raised to gamma.
 share (M,2,13,G) group composition per area; q (2,13,G,16) national income shape per group; returns (M,2,13,16) or None."""
 if gamma==0:return None
 P=int(pref.max())+1
 area_shape=np.einsum('msag,sagy->msay',share,q)
 wsum=np.zeros((P,)+share.shape[1:])
 for p in range(P):
  ids=np.where(pref==p)[0];wsum[p]=np.einsum('msag,msa->sag',share[ids],N[ids])
 pref_shape=np.einsum('psag,sagy->psay',norm(wsum),q)[pref]
 ratio=np.divide(area_shape,pref_shape,out=np.ones_like(area_shape),where=pref_shape>0)
 return np.power(np.maximum(ratio,1e-6),gamma)

def education_tilt(inp,gamma):
 """M1: education composition (census 11-2) with national education x income shapes (ESS 04000)."""
 return composition_tilt(inp['edu_share'],inp['edu_q'],inp['N'],inp['pref'],gamma)

def industry_tilt(inp,gamma):
 """M2 hook: industry composition per area x sex x age (census 6-3) with national/prefecture industry x income shapes (ESS regional table 24).
 Requires inp['ind_share'] (M,2,13,G) and inp['ind_q'] (2,13,G,16); not yet supplied by load_real_inputs (see docs/EXPERIMENT_M12.md)."""
 if 'ind_share' not in inp or 'ind_q' not in inp:raise NotImplementedError('M2 inputs (industry composition and industry x income shapes) are not part of the current data contract')
 return composition_tilt(inp['ind_share'],inp['ind_q'],inp['N'],inp['pref'],gamma)

def mixture(inp,W,cp,tilt=None):
 """Stage 4: mix status-specific shapes by the area's paid-status composition; optional multiplicative tilt. Returns (q, E)."""
 E=W[...,:4].sum(-1)
 q=np.einsum('msak,msaky->msay',W[...,:4],cp[inp['pref']])
 q=np.divide(q,E[...,None],out=np.zeros_like(q),where=E[...,None]>0)
 if tilt is not None:q=norm(q*tilt)
 return q,E

def calibrate(inp,q,E):
 """Stage 5: per prefecture x sex x age, fit area x income counts to area totals E and published income shares. Returns X (M,2,13,16)."""
 pref=inp['pref'];X=np.zeros_like(q);P=int(pref.max())+1
 for p in range(P):
  ids=np.where(pref==p)[0]
  for si in range(2):
   for ai in range(13):
    r=E[ids,si,ai];target=inp['pref_target'][p,si,ai]
    z,it,err=ipf(q[ids,si,ai]*r[:,None],r,target*r.sum())
    X[ids,si,ai]=z
 return X

def tax_project(inp,X0,E,beta):
 """Stage 6: tilt by the tax proxy and restore the prefecture income margins and area totals."""
 if beta==0:return X0.copy()
 pref=inp['pref'];feature=inp['tax_feature'];x=X0*np.exp(beta*feature[:,None,None,None]*SCORE);P=int(pref.max())+1
 for p in range(P):
  ids=np.where(pref==p)[0];z=x[ids];r=E[ids];target=X0[ids].sum(0)
  for it in range(500):
   z*=np.divide(r,z.sum(-1),out=np.zeros_like(r),where=z.sum(-1)>0)[...,None]
   z*=np.divide(target,z.sum(0),out=np.zeros_like(target),where=z.sum(0)>0)[None,...]
   err=np.max(np.abs(z.sum(-1)-r)/np.maximum(r,1))
   if err<1e-10:break
  else:raise RuntimeError('Tax projection failed')
  x[ids]=z
 return x

def city_predictions(inp,X):
 """Predicted known-income shares for each held-out city x age cell (n,16)."""
 h=inp['heldout'];return np.array([norm(X[ids,:,a].sum((0,1))) for ids,a in zip(h['ids'],h['age'])])

def city_metrics(inp,X):
 pr=city_predictions(inp,X);ob=inp['heldout']['obs']
 return {'tv':.5*np.abs(pr-ob).sum(1),'loss':-np.sum(ob*np.log(np.maximum(pr,1e-15)),1)}

def run(inp,gamma=0.,beta=0.,shrink=1000.,W=None,cp=None,X_base=None,gamma_industry=0.):
 """Full M0 (gamma=0) / M1 (gamma>0) run. Returns dict with W, E, X (before tax), Xt (after tax), counts_by_sex (M,2,13,17)."""
 if W is None:W=fit_status(inp)
 if cp is None:cp=status_income_shapes(inp,shrink)
 if X_base is None:
  tilt=education_tilt(inp,gamma)
  if gamma_industry:
   t2=industry_tilt(inp,gamma_industry);tilt=t2 if tilt is None else tilt*t2
  q,E=mixture(inp,W,cp,tilt);X_base=calibrate(inp,q,E)
 else:E=W[...,:4].sum(-1)
 Xt=tax_project(inp,X_base,E,beta)
 Z=inp['N']-E
 return {'W':W,'E':E,'X':X_base,'Xt':Xt,'counts_by_sex':np.concatenate([Z[...,None],Xt],axis=-1)}

def allocate_education(inp,counts_by_sex):
 """v2 education split of by-sex income counts; returns (M,2,13,8,16) 16-bin counts."""
 from build_education import allocate
 R=inp['edu_share']*inp['N'][...,None]
 sub={'shapes':inp['edu_q'],'N':inp['N'],'edu_counts':R,'rate_array':inp['edu_rate'],'income_counts':counts_by_sex}
 return allocate(sub)[0]

# ---------------------------------------------------------------------------------------------------
def load_real_inputs(sources_dir,reports_dir=None,shrink_unused=None):
 """Build the input contract from the normalized public statistics (same logic as build.py / refine_tax.py / build_education.py)."""
 import pandas as pd
 from pathlib import Path
 S=Path(sources_dir)
 def read(n):return pd.read_csv(S/n,dtype={'area':str,'age':str,'sex':str,'type':str,'status':str,'income':str,'labor_status':str,'education':str})
 def categories(f):return np.column_stack([f.regular,f.dispatch+f.part_other,f.executive,f.self_with+f.self_without+f.homework,f.family])
 pop=read('census_population_tidy.csv.gz');labor=read('census_imputed_age_tidy.csv.gz');status=read('census_imputed_detailed_status_tidy.csv.gz');seed=read('census_age_status_tidy.csv.gz');inc=read('income_tidy.csv.gz')
 geos=pop[['area','name','type']].drop_duplicates().sort_values('area');leaf=geos[geos.type.isin(['0','2','3'])];areas=leaf.area.tolist();M=len(areas)
 prefs=sorted(set(a[:2] for a in areas));pidx={p:i for i,p in enumerate(prefs)};pref=np.array([pidx[a[:2]] for a in areas]);P=len(prefs)
 idx=pd.MultiIndex.from_product([areas,['1','2'],AGES],names=['area','sex','age'])
 N=pop.set_index(['area','sex','age']).reindex(idx).population.to_numpy().reshape(M,2,13)
 L=labor.set_index(['area','sex','age']).reindex(idx);Nraw=L.population.to_numpy().reshape(M,2,13);Eraw=L.employed.to_numpy().reshape(M,2,13)
 T=status.set_index(['area','sex']);D=seed.set_index(['area','sex']);seed_areas=set(seed.area)
 seed_q=np.zeros((M,2,13,5));t_status=np.zeros((M,2,5))
 for mi,m in enumerate(areas):
  src=m if m in seed_areas else m[:2]+'000'
  for si,s in enumerate(['1','2']):
   seed_q[mi,si]=categories(D.loc[(src,s)].set_index('age').reindex(AGES));t_status[mi,si]=categories(T.loc[[(m,s)]])[0]
 Lp=labor.set_index(['area','sex','age']);pref_rate=np.zeros((P,2,13))
 for p,i in pidx.items():
  for si,s in enumerate(['1','2']):
   for ai,a in enumerate(AGES):
    r=Lp.loc[(p+'000',s,a)];pref_rate[i,si,ai]=r.employed/r.population if r.population else 0
 I=inc.pivot(index=['area','sex','age','status'],columns='income',values='count').sort_index(axis=1)
 def raw(area,s,a,k):return I.loc[(area,s,a,k)].to_numpy(float)
 def cat(area,s,a):
  reg=raw(area,s,a,'22');non=raw(area,s,a,'23');own=raw(area,s,a,'1');res=raw(area,s,a,'2')-reg-non
  return np.stack([reg[1:],non[1:],np.maximum(res,0)[1:],own[1:]])
 ess_cat=np.zeros((P,2,13,4,16));nat_cat=np.zeros((2,13,4,16));pref_target=np.zeros((P,2,13,16))
 for si,s in enumerate(['1','2']):
  for ai,a in enumerate(AGES):
   nat_cat[si,ai]=cat('00000',s,a)
   for p,i in pidx.items():ess_cat[i,si,ai]=cat(p+'000',s,a);pref_target[i,si,ai]=norm(raw(p+'000',s,a,'0')[1:])
 # tax proxy
 tax=pd.read_csv(S/'tax_tidy.csv',dtype={'area':str}).set_index('area')
 parent={}
 for _,r in geos[geos.type=='1'].iterrows():
  child=leaf[leaf.area.str.startswith('131')] if r.area=='13100' else leaf[(leaf.type=='0')&leaf.name.str.startswith(r['name'])]
  for c in child.area:parent[c]=r.area
 ratios=[]
 for m in areas:
  p=m[:2]+'000';src=m;t=tax.loc[src] if src in tax.index else None
  if t is None or not np.isfinite(t.taxable_income_million_yen) or not t.income_taxpayers>0:src=parent.get(m,p);t=tax.loc[src]
  if not np.isfinite(t.taxable_income_million_yen) or not t.income_taxpayers>0:src=p;t=tax.loc[p]
  pmean=tax.loc[p,'taxable_income_million_yen']/tax.loc[p,'income_taxpayers'];ratios.append(np.log(t.taxable_income_million_yen/t.income_taxpayers/pmean))
 tax_feature=np.clip(np.array(ratios),-.5,.5)
 # education inputs from build_education.prepare (uses the configured storage); align to leaf order
 import build_education as be
 be_inputs=be.prepare()
 assert be_inputs['areas']==areas,'education inputs must align with leaf areas'
 edu_share=np.divide(be_inputs['edu_counts'],N[...,None],out=np.zeros_like(be_inputs['edu_counts']),where=N[...,None]>0)
 # held-out cities: ESS city tables with >=1000 known-income persons per age
 cmap={m:[i] for i,m in enumerate(areas)}
 for c,par in parent.items():cmap.setdefault(par,[]).append(areas.index(c))  # includes 13100 (Tokyo special wards aggregate), as in build.py
 ids=[];age=[];obs=[];weight=[];hp=[];codes=[]
 for city in sorted(set(inc.area)-set([f'{i:02}000' for i in range(48)])):
  if city not in cmap:continue
  for ai,a in enumerate(AGES):
   o=raw(city,'0',a,'0')[1:];tot=o.sum()
   if tot<1000:continue
   ids.append(cmap[city]);age.append(ai);obs.append(norm(o));weight.append(tot);hp.append(pidx[city[:2]]);codes.append(city)
 heldout={'ids':ids,'age':np.array(age),'obs':np.array(obs),'weight':np.array(weight),'pref':np.array(hp),'codes':codes}
 return {'areas':areas,'prefs':prefs,'pref':pref,'N':N,'Nraw':Nraw,'Eraw':Eraw,'seed_q':seed_q,'t_status':t_status,'pref_rate':pref_rate,'ess_cat':ess_cat,'nat_cat':nat_cat,'pref_target':pref_target,'tax_feature':tax_feature,'edu_share':edu_share,'edu_q':be_inputs['shapes'],'edu_rate':be_inputs['rate_array'],'edu_reference':be_inputs['reference'],'heldout':heldout,'parent':parent}
