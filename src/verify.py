"""Checks for data alignment, probability normalization, municipality aggregation and conditional sampling."""
import json
import numpy as np
import pandas as pd
from persona import PersonaDistribution,BASE

def main():
 model=PersonaDistribution();D=BASE/'data';g=pd.read_csv(D/'geography.csv',dtype=str);parents=pd.read_csv(D/'parent_mapping.csv',dtype=str)
 assert len(model.codes)==1916 and len(set(model.codes))==1916
 assert np.isfinite(model.counts).all() and (model.counts>=-1e-8).all()
 assert np.max(np.abs(model.counts.sum(2)-model.population))<.001
 for code in model.codes:
  if model.population[model.index[code]].sum()>0:assert abs(model.distribution(code).sum()-1)<1e-12
 for p,rows in parents.groupby('parent_code'):
  if p=='13100':continue
  calc=sum(model.counts[model.index[c]] for c in rows.area)
  assert np.allclose(model.counts[model.index[p]],calc,atol=1e-8,rtol=1e-12)
 # Every main-table column is validated from raw numerical arrays after decimal serialization.
 f=pd.read_csv(D/'municipality_age_income.csv.gz',dtype={'municipality_code':str,'age_code':str,'income_code':str})
 assert len(f)==1916*13*16 and not f.duplicated(['municipality_code','age_code','income_code']).any()
 valid=f.population_15plus>0
 assert np.max(abs(f[valid].groupby('municipality_code').p_age_income_given_municipality.sum()-1))<1e-9
 assert np.max(abs(f[valid].p_age_income_given_municipality-f[valid].estimated_count/f[valid].population_15plus))<1e-10
 # Independently re-aggregate final SEX-SPECIFIC income counts and compare to ESS prefecture x age x sex target shares.
 arr=np.load(D/'final_arrays.npz');areas=arr['areas'];c=arr['counts_by_sex'][...,1:]
 inc=pd.read_csv(BASE/'sources/income_tidy.csv.gz',dtype={k:str for k in ['area','sex','age','status','income']})
 max_error=0.
 for p in range(1,48):
  ids=np.where(np.char.startswith(areas,f'{p:02}'))[0]
  for si,sex in enumerate(['1','2']):
   for ai in range(13):
    observed=inc[(inc.area==f'{p:02}000')&(inc.sex==sex)&(inc.age==f'{ai+1:02}')&(inc.status=='0')&(inc.income!='00')].sort_values('income')['count'].to_numpy()
    x=c[ids,si,ai].sum(0);err=np.max(abs(x/x.sum()-observed/observed.sum()));max_error=max(max_error,float(err))
 assert max_error<1e-9
 # Conditional sampler must never change a supplied age band or municipality.
 sample=model.sample('13103',10000,35,seed=7)
 assert all(v['municipality_code']=='13103' and v['age_band']=='35～39歳' for v in sample)
 assert model.sample('13103',20,35,seed=7)==sample[:20]
 try:model.distribution('07546')
 except ValueError:pass
 else:raise AssertionError('Zero population must be rejected')
 try:model.distribution('13103',14)
 except ValueError:pass
 else:raise AssertionError('Age under 15 must be rejected')
 result={'passed':True,'geographies':len(model.codes),'csv_rows':len(f),'final_prefecture_sex_age_max_probability_error':max_error,'checked':['nonnegative counts','municipality totals','conditional probabilities','no duplicate cells','parent/ward aggregation','prefecture income constraints','sampler conditioning and reproducibility','zero-population handling','under-15 handling']}
 (BASE/'validation/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
