"""Export municipality-conditioned age x sex x education x income distribution, v2."""
from paths import SOURCES,REPORTS,OUTPUT as OUT
from pathlib import Path
import gzip,json,shutil
import numpy as np
import pandas as pd
from model_math import AGES

EDU=[f'E{i:02}' for i in range(1,9)]
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,float) and not np.isfinite(x):return None
 return x

def main():
 REPORTS.mkdir(parents=True,exist_ok=True)
 d=np.load(OUT/'education_leaf_arrays.npz');areas=d['areas'].tolist();leaf=d['counts'].transpose(0,2,1,3,4)
 meta=pd.read_csv(OUT/'geography.csv',dtype={'municipality_code':str,'prefecture_code':str});parents=pd.read_csv(OUT/'parent_mapping.csv',dtype=str)
 mapping={p:f.area.tolist() for p,f in parents.groupby('parent_code')}
 entries=[]
 for m in meta.municipality_code:
  ids=[areas.index(m)] if m in areas else [areas.index(c) for c in mapping[m]]
  entries.append(leaf[ids].sum(0))
 counts=np.array(entries);codes=meta.municipality_code.to_numpy();population=counts.sum((1,2,3,4))
 np.savez_compressed(OUT/'municipality_model_v2.npz',municipality_codes=codes.astype(str),counts=counts,axes=np.array(['age','sex','education','income']))
 shutil.copyfile(SOURCES/'education/education_bins.csv',OUT/'education_bins.csv')
 pd.DataFrame({'sex_code':['1','2'],'sex_label':['男','女'],'note':['公表統計の性別区分。性自認の分布ではない。']*2}).to_csv(OUT/'sex_bins.csv',index=False)
 labels={
  'age':pd.read_csv(OUT/'age_bins.csv',dtype=str).age_band.tolist(),
  'sex':['男','女'],
  'education':pd.read_csv(OUT/'education_bins.csv',dtype=str).education_label.tolist(),
  'income':pd.read_csv(OUT/'income_bins.csv',dtype=str).income_band.tolist(),
 }
 schema={'model_version':'2.0','axes':['age','sex','education','income'],'shape':[13,2,8,16],'age_codes':AGES,'sex_codes':['1','2'],'education_codes':EDU,'income_codes':[f'I{i:02}' for i in range(1,17)],'labels':labels,'joint_probability':'P(age,sex,education,income | municipality); denominator is municipal population aged 15+','conditional_probability':'P(income | municipality,age,sex,education)','population_year':2020,'income_year':2022,'geography_year':2020,'undefined_probability':None}
 (OUT/'schema_v2.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
 directory=OUT/'municipalities_v2';directory.mkdir(exist_ok=True)
 grid=pd.MultiIndex.from_product([AGES,['1','2'],EDU,schema['income_codes']],names=['age_code','sex_code','education_code','income_code']).to_frame(index=False)
 csv_path=OUT/'municipality_age_sex_education_income.csv.gz'
 examples=[];total_rows=0;max_error=0.
 with gzip.open(csv_path,'wt',encoding='utf-8',newline='',compresslevel=5) as handle:
  for mi,m in enumerate(codes):
   c=counts[mi];den=c.sum();e=c.sum(-1)
   joint=c/den if den else np.full_like(c,np.nan)
   conditional=np.divide(c,e[...,None],out=np.full_like(c,np.nan),where=e[...,None]>0)
   frame=grid.copy();frame.insert(0,'municipality_code',m)
   frame['estimated_count']=c.ravel();frame['p_age_sex_education_income_given_municipality']=joint.ravel();frame['p_income_given_municipality_age_sex_education']=conditional.ravel()
   frame.to_csv(handle,index=False,header=(mi==0),float_format='%.12g');total_rows+=len(frame)
   record={'municipality_code':m,'municipality_name':meta.iloc[mi].municipality_name,'geography_level':meta.iloc[mi].geography_level,'model_version':'2.0','axes':schema['axes'],'age_codes':AGES,'sex_codes':['1','2'],'education_codes':EDU,'income_codes':schema['income_codes'],'population_15plus':float(den),'population_by_age_sex_education':e.tolist(),'p_age_sex_education_income_given_municipality':joint.tolist(),'p_income_given_municipality_age_sex_education':conditional.tolist()}
   with gzip.open(directory/(m+'.json.gz'),'wt',encoding='utf-8',compresslevel=5) as f:json.dump(clean(record),f,ensure_ascii=False,separators=(',',':'),allow_nan=False)
   if den:max_error=max(max_error,float(abs(joint.sum()-1)))
   if m in ['13103','13121','14100','01100','47201']:
    for si,s in enumerate(['男','女']):
     for ei,elabel in enumerate(labels['education']):
      examples.append((m,meta.iloc[mi].municipality_name,'35～39歳',s,EDU[ei],elabel,float(e[4,si,ei]),float(joint[4,si,ei,8:].sum()),float(conditional[4,si,ei,8:].sum())))
   if (mi+1)%400==0:print('Exported',mi+1,'municipalities',flush=True)
 pd.DataFrame(examples,columns=['municipality_code','municipality_name','age_band','sex','education_code','education','estimated_population','p_age_sex_education_ge500_given_municipality','p_ge500_given_municipality_age_sex_education']).to_csv(OUT/'examples_v2.csv',index=False,float_format='%.10g')
 result={'model_version':'2.0','geographies':len(codes),'shape_per_municipality':[13,2,8,16],'csv_rows':total_rows,'defined_municipalities':int((population>0).sum()),'max_joint_sum_error':max_error,'compressed_csv_bytes':csv_path.stat().st_size}
 (REPORTS/'education_export.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
