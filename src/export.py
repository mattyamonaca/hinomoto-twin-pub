"""Export municipality-conditioned age x income tables, including designated-city parents."""
from pathlib import Path
import json,gzip
import numpy as np
import pandas as pd
from build import BASE,OUT,AGES,norm

def main():
 d=np.load(OUT/'final_arrays.npz');b=np.load(OUT/'model_arrays.npz');leaf=pd.read_csv(OUT/'municipalities.csv',dtype={'area':str,'type':str,'prefecture_code':str,'age_status_seed_area':str});mapping=pd.read_csv(OUT/'parent_mapping.csv',dtype=str)
 areas=d['areas'].tolist();cube=d['counts'];base=b['counts'];N=d['population'].sum(1)
 # Pure income bins: merge synthetic zero component into the published <500,000 yen bin.
 def merge(x):return np.concatenate([x[...,:2].sum(-1,keepdims=True),x[...,2:]],-1)
 cube=merge(cube);base=merge(base);entries=[]
 for i,r in enumerate(leaf.itertuples()):
  level='designated_city_ward' if r.type=='0' and not r.area.startswith('131') else 'municipality'
  entries.append((r.area,r.name,level,cube[i],base[i],N[i],r.age_status_seed_area))
 for par,g in mapping.groupby('parent_code'):
  if par=='13100':continue # Tokyo special-ward aggregate is not a municipality.
  ids=[areas.index(m) for m in g.area];entries.append((par,g.iloc[0].parent_name,'municipality',cube[ids].sum(0),base[ids].sum(0),N[ids].sum(0),'aggregated_wards'))
 entries.sort(key=lambda e:e[0]);allareas=[e[0] for e in entries];allcounts=np.array([e[3] for e in entries]);allbase=np.array([e[4] for e in entries]);allN=np.array([e[5] for e in entries]);den=allN.sum(1)
 by_m=np.divide(allcounts,den[:,None,None],out=np.full_like(allcounts,np.nan),where=den[:,None,None]>0)
 by_ma=np.divide(allcounts,allN[...,None],out=np.full_like(allcounts,np.nan),where=allN[...,None]>0)
 age_names=[f'{15+5*i}～{19+5*i}歳' for i in range(12)]+['75歳以上']
 edges=[0,50,100,150,200,250,300,400,500,600,700,800,900,1000,1250,1500,None]
 inc_names=['50万円未満（就業収入なしを含む）']+[f'{edges[i]}～{edges[i+1]}万円未満' for i in range(1,15)]+['1500万円以上']
 codes=[f'I{i+1:02}' for i in range(16)]
 rows=[]
 for mi,e in enumerate(entries):
  for ai,a in enumerate(AGES):
   for yi in range(16):
    rows.append((e[0],e[1],e[2],a,age_names[ai],codes[yi],inc_names[yi],den[mi],allN[mi,ai],allcounts[mi,ai,yi],by_m[mi,ai,yi],by_ma[mi,ai,yi],allN[mi,ai]/den[mi] if den[mi] else np.nan,allbase[mi,ai,yi]/den[mi] if den[mi] else np.nan))
 frame=pd.DataFrame(rows,columns=['municipality_code','municipality_name','geography_level','age_code','age_band','income_code','income_band','population_15plus','population_municipality_age','estimated_count','p_age_income_given_municipality','p_income_given_municipality_age','p_age_given_municipality','p_age_income_given_municipality_without_tax_proxy'])
 frame.to_csv(OUT/'municipality_age_income.csv.gz',index=False,float_format='%.12g')
 # A plain CSV is convenient for direct import into data systems; keep gzip as a smaller delivery option.
 frame.to_csv(OUT/'municipality_age_income.csv',index=False,float_format='%.12g')
 meta=pd.DataFrame([(e[0],e[1],e[2],e[0][:2],den[i],e[6],bool(den[i]>0)) for i,e in enumerate(entries)],columns=['municipality_code','municipality_name','geography_level','prefecture_code','population_15plus','age_status_seed_area','conditional_distribution_defined'])
 meta.to_csv(OUT/'geography.csv',index=False)
 pd.DataFrame({'age_code':AGES,'age_band':age_names,'age_min':list(range(15,76,5)),'age_max':list(range(19,75,5))+[None]}).to_csv(OUT/'age_bins.csv',index=False)
 pd.DataFrame({'income_code':codes,'income_band':inc_names,'lower_yen':[None]+[v*10000 for v in edges[1:16]],'upper_yen':[v*10000 if v is not None else None for v in edges[1:]],'note':['非就業・無給家族従業者のモデル上0円を含む。0円と少額収入を分離していない。']+['']*15}).to_csv(OUT/'income_bins.csv',index=False)
 np.savez_compressed(OUT/'municipality_model.npz',municipality_codes=np.array(allareas),counts=allcounts,p_age_income_given_municipality=by_m,p_income_given_municipality_age=by_ma,population=allN)
 # Separate JSON per municipality enables fetch-on-demand without loading the nationwide distribution.
 dest=OUT/'municipalities';dest.mkdir(exist_ok=True)
 for mi,e in enumerate(entries):
  obj={'municipality_code':e[0],'municipality_name':e[1],'geography_level':e[2],'population_15plus':float(den[mi]),'age_codes':AGES,'age_bands':age_names,'income_codes':codes,'income_bands':inc_names,'p_age_income_given_municipality':by_m[mi].tolist(),'p_income_given_municipality_age':by_ma[mi].tolist(),'population_by_age':allN[mi].tolist(),'population_year':2020,'income_year':2022,'geography_year':2020}
  def clean(x):
   if isinstance(x,list):return [clean(v) for v in x]
   if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
   if isinstance(x,float) and not np.isfinite(x):return None
   return x
  (dest/(e[0]+'.json')).write_text(json.dumps(clean(obj),ensure_ascii=False,separators=(',',':'),allow_nan=False))
 # Examples show both requested joint-within-municipality and age-conditioned income probabilities.
 chosen=['13103','13121','14100','01100','47201','13382'];ex=frame[frame.municipality_code.isin(chosen)]
 ex.to_csv(OUT/'examples.csv',index=False,float_format='%.8g')
 check={'geographic_records':len(entries),'municipalities':int((meta.geography_level=='municipality').sum()),'designated_city_wards':int((meta.geography_level=='designated_city_ward').sum()),'age_groups':13,'income_groups':16,'probability_cells':len(frame),'nonempty_geographies':int((den>0).sum()),'zero_population_geographies':meta.loc[den==0,['municipality_code','municipality_name']].to_dict('records'),'max_sum_error_per_nonempty_municipality':float(np.nanmax(np.abs(by_m.sum((1,2))-1))),'max_sum_error_income_given_age':float(np.nanmax(np.abs(by_ma.sum(2)-1))),'nonoverlapping_15plus_population':float(d['population'].sum()),'caution':'Do not sum designated-city parents and their wards; all published boundaries are 2020. Tax source uses 2022 fiscal year.'}
 (BASE/'validation/export_checks.json').write_text(json.dumps(check,ensure_ascii=False,indent=2));print(json.dumps(check,ensure_ascii=False,indent=2))
 print('EXAMPLES: 35-39, income >=500万円')
 for m in chosen:
  i=allareas.index(m);ai=4;print(m,entries[i][1],'P(age,income>=500 | municipality)=',by_m[i,ai,8:].sum(),'P(income>=500 | municipality,35-39)=',by_ma[i,ai,8:].sum())
if __name__=='__main__':main()
