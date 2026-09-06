"""Stage-A conditional distributions: employment status and industry on top of the production 5-attribute model.

Reads data/employment_a.npz (aggregated joints) for fast queries and recomputes the full block for one municipality
when a condition on both education and status/industry/income is requested.

  python src/persona_v3.py --municipality 13103 --age 35 --sex male                 # P(status | ...), P(industry | ...)
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

K=['K1','K2','K3','K4','K5','K6'];KL=['正規','非正規','役員','自営（内職含む）','無給家族従業','非就業（完全失業・非労働力）']
G=['G00']+[f'G{i:02}' for i in range(1,21)];EDU=[f'E{i:02}' for i in range(1,9)]

class EmploymentDistribution:
 def __init__(self,data_dir=None):
  self.dir=Path(data_dir or OUTPUT);d=np.load(self.dir/'employment_a.npz')
  self.areas=d['areas'].tolist();self.ix={a:i for i,a in enumerate(self.areas)};self.N=d['population']
  self.kg=d['status_industry'];self.ke=d['education_status'];self.ky=d['status_income'];self.gy=d['industry_income'];self.ge=d['education_industry']
  pm=pd.read_csv(self.dir/'parent_mapping.csv',dtype=str);self.parents={p:[self.ix[a] for a in f.area] for p,f in pm.groupby('parent_code') if p!='13100'}
  self.bins=pd.read_csv(SOURCES/'industry/industry_bins.csv',dtype=str)
  self._x=None
 def ids(self,code):
  code=str(code).zfill(5)
  if code in self.ix:return [self.ix[code]]
  if code in self.parents:return self.parents[code]
  raise ValueError(f'Unknown 2020 municipality code: {code}')
 def margins(self,code,age=None,sex=None,education=None):
  """Fast path from aggregated joints: P(status|cond), P(industry|cond, employed), P(income|cond, status)."""
  ids=self.ids(code);ai=None if age is None else min((int(age)-15)//5,12);si=None if sex is None else {'male':0,'female':1,'1':0,'2':1}[str(sex)]
  sl=lambda arr:arr[ids][:, [si] if si is not None else slice(None)][:,:, [ai] if ai is not None else slice(None)]
  if education is None:
   kg=sl(self.kg).sum((0,1,2));ke=None
  else:
   ei=EDU.index(education);ke=sl(self.ke)[...,ei,:].sum((0,1,2));kg=None
  out={'municipality_code':str(code).zfill(5),'age_band':None if ai is None else AGES[ai],'sex':sex,'education':education}
  if kg is not None:
   tot=kg.sum();out['population']=float(tot);out['p_status']=dict(zip(K,(kg.sum(1)/tot).tolist())) if tot else None
   emp=kg[:5,1:].sum();out['p_industry_given_employed']=dict(zip(G[1:],(kg[:5,1:].sum(0)/emp).tolist())) if emp else None
  else:
   tot=ke.sum();out['population']=float(tot);out['p_status']=dict(zip(K,(ke/tot).tolist())) if tot else None
   out['note']='industry and income conditional on education require the full block (use --status/--industry/--income-only)'
  ky=sl(self.ky).sum((0,1,2));out['p_income_given_status']={K[k]:norm(ky[k]).tolist() for k in range(4) if ky[k].sum()>0}
  return out
 def block(self,code,age,sex):
  """Full paid block (8 edu x 4 status x 20 industry x 16 income) plus family (8x20) and nonworkers (8) for one municipality, sex, age band."""
  import build_employment as bm
  if self._x is None:self._x=bm.load_inputs()
  ids=self.ids(code);ai=min((int(age)-15)//5,12);si={'male':0,'female':1,'1':0,'2':1}[str(sex)]
  b=bm.block(self._x,si,ai,ids=ids);return {'paid':b['paid'].sum(0),'family':b['family'].sum(0),'nonwork':b['nonwork'].sum(0),'age_band':AGES[ai]}
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
  return {'municipality_code':str(code).zfill(5),'age_band':b['age_band'],'sex':sex,'education':education,'status':status,'industry':industry,'model_population':float(den),'p_income':(c/den).tolist(),'note':'Paid workers only; K5/K6 have no main-job income. Denominator is the model population, not a survey sample.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 p.add_argument('--municipality',required=True);p.add_argument('--age',type=int);p.add_argument('--sex');p.add_argument('--education');p.add_argument('--status');p.add_argument('--industry');p.add_argument('--income-only',action='store_true');p.add_argument('--data-dir',type=Path)
 a=p.parse_args();m=EmploymentDistribution(a.data_dir)
 if a.income_only or a.status or a.industry:
  if a.age is None or a.sex is None:raise SystemExit('--age and --sex are required for status/industry conditions')
  print(json.dumps(m.income(a.municipality,a.age,a.sex,a.education,a.status,a.industry),ensure_ascii=False,indent=2))
 else:print(json.dumps(m.margins(a.municipality,a.age,a.sex,a.education),ensure_ascii=False,indent=2))
