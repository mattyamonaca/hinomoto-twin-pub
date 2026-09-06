"""Check v2 census constraints, v1 preservation, serialized files, and conditional sampling."""
import gzip,json
import numpy as np
import pandas as pd
from persona_v2 import BASE,PersonaDistributionV2

def main():
 D=BASE/'data';model=PersonaDistributionV2();x=model.counts;shape=(1916,13,2,8,16)
 assert x.shape==shape and len(set(model.codes))==1916
 assert np.isfinite(x).all() and (x>=0).all()
 old=np.load(D/'municipality_model.npz');assert model.codes==old['municipality_codes'].tolist()
 difference=float(np.max(abs(x.sum((2,3))-old['counts'])));assert difference<1e-5
 leaf=np.load(D/'education_leaf_arrays.npz');original=np.load(D/'final_arrays.npz');c=leaf['counts'];z=original['counts_by_sex']
 expected=np.concatenate([z[...,:2].sum(-1,keepdims=True),z[...,2:]],axis=-1)
 sex_difference=float(np.max(abs(c.sum(-2)-expected)));assert sex_difference<1e-6
 # Independent reconstruction of education margins from the normalized census source.
 f=pd.read_csv(BASE/'sources/education/census_education_tidy.csv.gz',dtype={'area':str,'sex':str,'age':str}).set_index(['area','sex','age'])
 edu=[f'E{i:02}' for i in range(1,9)];ages=[f'{a:02}' for a in range(1,14)]
 ix=pd.MultiIndex.from_product([leaf['areas'],['1','2'],ages],names=['area','sex','age'])
 r=f.reindex(ix)[edu].to_numpy(float).reshape(1896,2,13,8);n=original['population']
 for mi,si,ai in zip(*np.where((r.sum(-1)==0)&(n>0))):r[mi,si,ai]=f.loc[(leaf['areas'][mi][:2]+'000',str(si+1),ages[ai]),edu]
 target=np.divide(r,r.sum(-1,keepdims=True),out=np.zeros_like(r),where=r.sum(-1,keepdims=True)>0)*n[...,None]
 max_edu_error=float(np.max(abs(c.sum(-1)-target)));assert max_edu_error<1e-4
 mapping=pd.read_csv(D/'parent_mapping.csv',dtype=str)
 for p,group in mapping.groupby('parent_code'):
  if p!='13100':assert np.allclose(x[model.index[p]],sum(x[model.index[a]] for a in group.area),rtol=1e-11,atol=1e-7)
 den=x.sum((1,2,3,4));e=x.sum(-1)
 joint=np.divide(x,den[:,None,None,None,None],out=np.full_like(x,np.nan),where=den[:,None,None,None,None]>0)
 cond=np.divide(x,e[...,None],out=np.full_like(x,np.nan),where=e[...,None]>0)
 # Exact grid checks also detect duplicate/missing cells and swapped dimensions.
 offset=0;block=13*2*8*16
 for frame in pd.read_csv(D/'municipality_age_sex_education_income.csv.gz',dtype={k:str for k in ['municipality_code','age_code','sex_code','education_code','income_code']},chunksize=332800):
  size=len(frame);inds=np.arange(offset,offset+size);r=inds%block
  assert np.array_equal(frame.municipality_code.to_numpy(),np.asarray(model.codes)[inds//block])
  for name,values in [('age_code',r//256+1),('sex_code',r//128%2+1),('education_code',r//16%8+1),('income_code',r%16+1)]:
   actual=frame[name].str[1:] if name in ['education_code','income_code'] else frame[name]
   assert np.array_equal(actual.astype(int).to_numpy(),values)
  for key,values in [('estimated_count',x),('p_age_sex_education_income_given_municipality',joint),('p_income_given_municipality_age_sex_education',cond)]:
   assert np.allclose(frame[key],values.ravel()[offset:offset+size],rtol=1e-10,atol=1e-11,equal_nan=True),key
  offset+=size
 assert offset==np.prod(shape) and np.nanmax(abs(joint.sum((1,2,3,4))-1))<1e-10
 for m in ['13103','14100','07546']:
  obj=json.load(gzip.open(D/'municipalities_v2'/(m+'.json.gz'),'rt'));j=np.asarray(obj['p_age_sex_education_income_given_municipality'],dtype=float)
  assert np.allclose(j,joint[model.index[m]],equal_nan=True,atol=1e-12)
 samples=model.sample('13103',500,age=35,sex='male',education='E04',seed=7)
 assert all(r['age_band']=='35～39歳' and r['sex_code']=='1' and r['education_code']=='E04' for r in samples)
 assert model.sample('13103',20,age=35,sex='1',education='E04',seed=7)==samples[:20]
 assert model.sample('13103',0)==[]
 assert not np.allclose(model.income_distribution('13103',35,'1','E02'),model.income_distribution('13103',35,'1','E04'))
 for m,kwargs in [('07546',{}),('13103',{'age':14}),('13103',{'age':35.5}),('13103',{'sex':'0'}),('13103',{'education':'E99'}),('13103',{'age':15,'education':'E04'})]:
  try:model.distribution(m,**kwargs)
  except ValueError:pass
  else:raise AssertionError(f'Invalid/empty condition did not fail: {m}, {kwargs}')
 result={'passed':True,'model_version':'2.0','shape':list(shape),'csv_rows_verified':offset,'max_old_age_income_count_difference':difference,'max_old_age_sex_income_count_difference':sex_difference,'max_census_education_target_count_error':max_edu_error,'checks':['nonnegative finite counts','all v1 municipal age/income margins','all sex-specific income margins','education targets independently reconstructed','parent/ward aggregation','all CSV coordinates and probabilities','representative JSON consistency','conditioned sample fields and reproducibility','zero population and invalid filters','income association differs by education'],'validation_scope':'Internal/source consistency. No independent municipal education-income accuracy validation.'}
 (BASE/'validation/education_verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
