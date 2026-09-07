"""Stage-A conditional distributions: employment status and industry on top of the production 5-attribute model.

Reads data/employment_a.npz (aggregated joints) for fast queries and recomputes the full block for one municipality
when a condition on both education and status/industry/income is requested.

  python src/persona_v3.py --municipality 13103 --age 35 --sex male                 # P(labour status), P(status | ...), P(industry | ...)
  python src/persona_v3.py --municipality 13103 --age 35 --sex male --status K1 --industry G07   # income given status & industry
  python src/persona_v3.py --municipality 13103 --age 35 --sex male --education E04 --status K1 --industry G07 --income-only
Denominators are the model population of the stated condition (2020 census based), never survey sample sizes.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from paths import OUTPUT,SOURCES
from model_math import AGES,norm

K=['K1','K2','K3','K4','K5','K6','K7'];KL=['正規の職員・従業員','非正規（派遣・パート等）','役員','自営業主（内職含む）','無給家族従業者','完全失業者','非労働力人口']
J=['J1','J2','J3'];JL=['就業者','完全失業者','非労働力人口']
G=['G00']+[f'G{i:02}' for i in range(1,21)];EDU=[f'E{i:02}' for i in range(1,9)]

def age_index(age):
 """5-year band index for an age in years; ages under 15 are outside the model."""
 age=int(age)
 if age<15:raise ValueError('This model covers ages 15 and older.')
 return min((age-15)//5,12)
def sex_index(sex):
 try:return {'male':0,'female':1,'1':0,'2':1,'m':0,'f':1}[str(sex).lower()]
 except KeyError:raise ValueError('sex must be male/female (or 1/2)')

class EmploymentDistribution:
 def __init__(self,data_dir=None,sources_dir=None):
  self.dir=Path(data_dir or OUTPUT);self.sources=Path(sources_dir or SOURCES);d=np.load(self.dir/'employment_a.npz')
  self.areas=d['areas'].tolist();self.ix={a:i for i,a in enumerate(self.areas)};self.N=d['population']
  self.model_version=str(d['model_version']) if 'model_version' in d.files else 'unknown';self.variant=str(d['variant']) if 'variant' in d.files else 'base'
  if d['status_industry'].shape[3]!=len(K):raise ValueError(f"employment_a.npz has {d['status_industry'].shape[3]} status classes; this API expects {len(K)} (K6 完全失業 / K7 非労働力 split). Rebuild with `make build-employment`.")
  self.kg=d['status_industry'];self.ke=d['education_status'];self.ky=d['status_income'];self.gy=d['industry_income'];self.ge=d['education_industry']
  pm=pd.read_csv(self.dir/'parent_mapping.csv',dtype=str);self.parents={p:[self.ix[a] for a in f.area] for p,f in pm.groupby('parent_code') if p!='13100'}
  self.bins=pd.read_csv(self.sources/'industry/industry_bins.csv',dtype=str)
  self._x=None
 def ids(self,code):
  code=str(code).zfill(5)
  if code in self.ix:return [self.ix[code]]
  if code in self.parents:return self.parents[code]
  raise ValueError(f'Unknown 2020 municipality code: {code}')
 def margins(self,code,age=None,sex=None,education=None):
  """Fast path from aggregated joints: P(status|cond), P(industry|cond, employed), P(income|cond, status)."""
  ids=self.ids(code);ai=None if age is None else age_index(age);si=None if sex is None else sex_index(sex)
  sl=lambda arr:arr[ids][:, [si] if si is not None else slice(None)][:,:, [ai] if ai is not None else slice(None)]
  if education is None:
   kg=sl(self.kg).sum((0,1,2));ke=None
  else:
   ei=EDU.index(education);ke=sl(self.ke)[...,ei,:].sum((0,1,2));kg=None
  out={'municipality_code':str(code).zfill(5),'age_band':None if ai is None else AGES[ai],'sex':sex,'education':education,'model_version':self.model_version}
  if kg is not None:
   tot=kg.sum();out['population']=float(tot);ks=kg.sum(1);out['p_status']=dict(zip(K,(ks/tot).tolist())) if tot else None
   out['p_labor_status']=dict(zip(J,[float(ks[:5].sum()/tot),float(ks[5]/tot),float(ks[6]/tot)])) if tot else None
   out['p_position_given_employed']=dict(zip(K[:5],(ks[:5]/ks[:5].sum()).tolist())) if ks[:5].sum()>0 else None
   emp=kg[:5,1:].sum();out['p_industry_given_employed']=dict(zip(G[1:],(kg[:5,1:].sum(0)/emp).tolist())) if emp else None
   ky=sl(self.ky).sum((0,1,2));out['p_income_given_status']={K[k]:norm(ky[k]).tolist() for k in range(4) if ky[k].sum()>0}
  else:
   tot=ke.sum();out['population']=float(tot);out['p_status']=dict(zip(K,(ke/tot).tolist())) if tot else None
   out['p_labor_status']=dict(zip(J,[float(ke[:5].sum()/tot),float(ke[5]/tot),float(ke[6]/tot)])) if tot else None
   out['p_position_given_employed']=dict(zip(K[:5],(ke[:5]/ke[:5].sum()).tolist())) if ke[:5].sum()>0 else None
   if ai is not None and si is not None:
    # education-conditional industry and income need the full block for this municipality, sex and age band
    b=self.block(code,age,sex);z=b['paid'][ei];fam=b['family'][ei]
    emp=z.sum()+fam.sum();out['p_industry_given_employed']=dict(zip(G[1:],((z.sum((0,2))+fam)/emp).tolist())) if emp>0 else None
    out['p_income_given_status']={K[k]:norm(z[k].sum(0)).tolist() for k in range(4) if z[k].sum()>0}
   else:
    out['p_industry_given_employed']=None;out['p_income_given_status']=None
    out['note']='industry and income conditional on education are computed from the full block and require --age and --sex'
  return out
 def block(self,code,age,sex):
  """Full paid block (8 edu x 4 status x 20 industry x 16 income) plus family (8x20) and nonworkers (8) for one municipality, sex, age band."""
  import build_employment as bm
  if self._x is None:
   meta=self.dir/'model_metadata.json'
   if not (self.dir/'final_arrays.npz').exists():raise ValueError(f'{self.dir} has no final_arrays.npz; on-demand recomputation needs the production arrays the artifact was built from')
   if meta.exists():
    mv=json.loads(meta.read_text()).get('model_version','unknown')
    if mv!=self.model_version:raise ValueError(f"Saved artifact was built for model {self.model_version}, but {self.dir} holds model {mv}")
   x=bm.load_inputs(self.sources,self.dir)
   if x['areas']!=self.areas:raise ValueError('Input sources/output arrays do not match the saved employment_a.npz area order')
   if x['model_version']!=self.model_version:raise ValueError(f"Saved artifact was built for model {self.model_version}, but the inputs are model {x['model_version']}")
   if self.variant!='base':raise ValueError(f'On-demand recomputation reproduces the base variant only (artifact variant: {self.variant})')
   self._x=x
  ids=self.ids(code);ai=age_index(age);si=sex_index(sex)
  b=bm.block(self._x,si,ai,ids=ids);return {'paid':b['paid'].sum(0),'family':b['family'].sum(0),'nonwork':b['nonwork'].sum(0),'unemployed':b['unemployed'].sum(0),'inactive':b['inactive'].sum(0),'age_band':AGES[ai]}
 def income(self,code,age,sex,education=None,status=None,industry=None):
  b=self.block(code,age,sex);z=b['paid']
  if education is not None:z=z[EDU.index(education)][None]
  if status is not None:
   if status not in K[:4]:raise ValueError('Income classes exist only for paid statuses K1-K4')
   z=z[:,K.index(status)][:,None]
  if industry is not None:
   if industry=='G00':raise ValueError('G00 (not applicable) has no paid income')
   z=z[:,:,G.index(industry)-1][:,:,None]
  c=z.sum((0,1,2));den=c.sum()
  if den<=0:raise ValueError('The model population for this condition is zero; the conditional distribution is undefined.')
  return {'municipality_code':str(code).zfill(5),'age_band':b['age_band'],'sex':sex,'education':education,'status':status,'industry':industry,'model_version':self.model_version,'model_population':float(den),'p_income':(c/den).tolist(),'note':'Paid workers only; K5 (family workers), K6 (unemployed) and K7 (not in labour force) have no main-job income. Denominator is the model population, not a survey sample.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 p.add_argument('--municipality',required=True);p.add_argument('--age',type=int);p.add_argument('--sex');p.add_argument('--education');p.add_argument('--status');p.add_argument('--industry');p.add_argument('--income-only',action='store_true');p.add_argument('--data-dir',type=Path);p.add_argument('--sources-dir',type=Path)
 a=p.parse_args();m=EmploymentDistribution(a.data_dir,a.sources_dir)
 if a.income_only or a.status or a.industry:
  if a.age is None or a.sex is None:raise SystemExit('--age and --sex are required for status/industry conditions')
  print(json.dumps(m.income(a.municipality,a.age,a.sex,a.education,a.status,a.industry),ensure_ascii=False,indent=2))
 else:print(json.dumps(m.margins(a.municipality,a.age,a.sex,a.education),ensure_ascii=False,indent=2))
