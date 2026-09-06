"""Split v1 age/sex/income counts by education using census margins and income associations."""
from paths import SOURCES,REPORTS,OUTPUT as OUT
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model_math import AGES,norm

EDU=[f'E{i:02}' for i in range(1,9)]
D=SOURCES/'education'
INCOME_MAP=[['11'],['12','13'],['14','16','17'],['15','18'],['19'],['2'],['0'],['0']]

def read(name):return pd.read_csv(D/name,dtype={k:str for k in ['area','sex','age','labor_status','education','income']})

def project(seed,rows,cols):
 """Batched KL projection. Last two axes are education and internal income component."""
 if not np.allclose(rows.sum(-1),cols.sum(-1),rtol=1e-10,atol=1e-6):raise ValueError('Unequal margins')
 z=np.maximum(seed,1e-14)
 z=np.where((rows>0)[...,None] & (cols>0)[...,None,:],z,0.)
 for it in range(2000):
  z*=np.divide(rows,z.sum(-1),out=np.zeros_like(rows),where=z.sum(-1)>0)[...,None]
  z*=np.divide(cols,z.sum(-2),out=np.zeros_like(cols),where=z.sum(-2)>0)[...,None,:]
  err=np.max(abs(z.sum(-1)-rows)/np.maximum(rows,1))
  if err<1e-10:return z,it+1,float(err)
 raise RuntimeError(f'Education IPF did not converge: {err}')

def income_shapes(income_shrink=1000.):
 """National education x income shapes q(y|s,a,e) and the all-education reference q0(y|s,a). Returns shapes, reference, quality rows."""
 ess=read('income_education_tidy.csv.gz')
 # Sum 75-79,80-84,85+ into the shared 75+ age class; omit all-age totals.
 ess=ess[ess.age!='00'].copy();ess['age']=ess.age.astype(int).clip(upper=13).map(lambda x:f'{x:02}')
 ess=ess.groupby(['sex','age','education','income'],as_index=False)['count'].sum()
 tab=ess.pivot(index=['sex','age','education'],columns='income',values='count').sort_index(axis=1)
 shapes=np.zeros((2,13,8,16));reference=np.zeros((2,13,16));quality=[]
 for si,s in enumerate(['1','2']):
  for ai,a in enumerate(AGES):
   ref=norm(tab.loc[(s,a,'0')].to_numpy()[1:]+1e-8);reference[si,ai]=ref
   for ei,parts in enumerate(INCOME_MAP):
    values=sum(tab.loc[(s,a,e)].to_numpy() for e in parts)
    shapes[si,ai,ei]=norm(values[1:]+income_shrink*ref)
    quality.append((s,a,EDU[ei],float(values[0]),float(values[1:].sum()),income_shrink/(values[1:].sum()+income_shrink)))
 return shapes,reference,quality

def prepare(income_shrink=1000.,rate_shrink=100.):
 """Load v1 arrays and census education inputs. Returns a dict of everything allocate() needs."""
 original=np.load(OUT/'final_arrays.npz');areas=original['areas'].tolist();N=original['population'];income_counts=original['counts_by_sex']
 census=read('census_education_tidy.csv.gz').set_index(['area','sex','age'])
 labor=read('census_education_labor_tidy.csv.gz').set_index(['area','sex','age','labor_status'])
 shapes,reference,income_quality=income_shapes(income_shrink)
 # Labor-known denominators avoid treating labor nonresponse as nonemployment.
 cache={}
 available=set(labor.index.get_level_values('area'))
 def rates(area,s,a):
  key=(area,s,a)
  if key in cache:return cache[key]
  employed=labor.loc[(area,s,a,'11'),EDU].to_numpy(float)
  known=employed+labor.loc[(area,s,a,'12'),EDU].to_numpy(float)+labor.loc[(area,s,a,'2'),EDU].to_numpy(float)
  if area=='00000':prior=np.full(8,(employed.sum()+1)/(known.sum()+2))
  else:prior=rates('00000' if area.endswith('000') else area[:2]+'000',s,a)
  result=(employed+rate_shrink*prior)/(known+rate_shrink)
  cache[key]=result;return result
 edu_counts=np.zeros(N.shape+(8,));rate_array=np.zeros_like(edu_counts);quality=[]
 for mi,m in enumerate(areas):
  p=m[:2]+'000';labor_source=m if m in available else p
  for si,s in enumerate(['1','2']):
   for ai,a in enumerate(AGES):
    values=census.loc[(m,s,a),EDU].to_numpy(float);observed_total=values.sum();fallback=False
    if observed_total==0 and N[mi,si,ai]>0:values=census.loc[(p,s,a),EDU].to_numpy(float);fallback=True
    edu_counts[mi,si,ai]=norm(values)*N[mi,si,ai]
    rate_array[mi,si,ai]=rates(labor_source,s,a)
    quality.append((m,s,a,observed_total,float(N[mi,si,ai]),labor_source,fallback,float(edu_counts[mi,si,ai,7]/N[mi,si,ai]) if N[mi,si,ai]>0 else None))
 return {'areas':areas,'N':N,'income_counts':income_counts,'shapes':shapes,'reference':reference,'edu_counts':edu_counts,'rate_array':rate_array,'quality':quality,'income_quality':income_quality,'income_shrink':income_shrink,'rate_shrink':rate_shrink}

def allocate(inputs,shapes=None):
 """Allocate v1 income counts to education classes with IPF. Returns 16-bin counts (area, sex, age, education, income) and fit rows."""
 shapes=inputs['shapes'] if shapes is None else shapes
 N=inputs['N'];edu_counts=inputs['edu_counts'];rate_array=inputs['rate_array'];income_counts=inputs['income_counts']
 cube=np.zeros(N.shape+(8,17));fits=[]
 for si,s in enumerate(['1','2']):
  for ai,a in enumerate(AGES):
   r=rate_array[:,si,ai]
   seed=np.concatenate([(1-r)[...,None],r[...,None]*shapes[si,ai][None]],axis=-1)*edu_counts[:,si,ai,:,None]
   cube[:,si,ai],it,err=project(seed,edu_counts[:,si,ai],income_counts[:,si,ai])
   fits.append((s,a,it,err))
 # The model's synthetic zero and earned <50万円 component merge only after allocation.
 final=np.concatenate([cube[...,:2].sum(-1,keepdims=True),cube[...,2:]],axis=-1)
 return final,fits

def main(income_shrink=1000.,rate_shrink=100.):
 REPORTS.mkdir(parents=True,exist_ok=True)
 OUT.mkdir(parents=True,exist_ok=True)
 inputs=prepare(income_shrink,rate_shrink);N=inputs['N'];edu_counts=inputs['edu_counts'];income_counts=inputs['income_counts']
 final,fits=allocate(inputs)
 old=np.concatenate([income_counts[...,:2].sum(-1,keepdims=True),income_counts[...,2:]],axis=-1)
 assert np.max(abs(final.sum(-2)-old))<1e-6
 assert np.max(abs(final.sum(-1)-edu_counts))<1e-4
 np.savez_compressed(OUT/'education_leaf_arrays.npz',areas=np.array(inputs['areas']),population=N,education_population=edu_counts,counts=final)
 pd.DataFrame(inputs['quality'],columns=['area','sex','age','observed_age_known_population','model_population','labor_seed_area','population_fallback_to_prefecture','education_unknown_share']).to_csv(REPORTS/'education_source_quality.csv.gz',index=False)
 pd.DataFrame(inputs['income_quality'],columns=['sex','age','education','source_total','known_income_count','shrinkage_weight']).to_csv(REPORTS/'education_income_quality.csv',index=False)
 pd.DataFrame(fits,columns=['sex','age','iterations','relative_error']).to_csv(REPORTS/'education_ipf.csv',index=False)
 result={'model_version':'2.0','leaf_geographies':len(inputs['areas']),'axes':['municipality','sex','age','education','income'],'shape':list(final.shape),'income_shrink_pseudopopulation':income_shrink,'labor_rate_shrink_pseudopopulation':rate_shrink,'population_15plus':float(N.sum()),'education_unknown_probability':float(edu_counts[...,7].sum()/N.sum()),'enrolled_probability':float(edu_counts[...,5].sum()/N.sum()),'raw_population_fallback_cells':int(sum(v[-2] for v in inputs['quality'])),'max_old_income_count_difference':float(np.max(abs(final.sum(-2)-old))),'max_education_count_error':float(np.max(abs(final.sum(-1)-edu_counts))),'warning':'Census education/labor association and national ESS education/income association are transported assumptions. No independent municipal education-income validation. Sex is the binary category published by these surveys.'}
 (REPORTS/'education_build.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
