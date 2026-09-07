"""Stage-C conditional distributions: workplace municipality given residence (and industry), or residence given workplace.

  python src/persona_v4.py --municipality 13103 --industry G07            # P(workplace | lives in 港区, 情報通信業)
  python src/persona_v4.py --municipality 13103                           # P(workplace | lives in 港区), all industries
  python src/persona_v4.py --municipality 13103 --age 35 --sex male       # mixed over the stage-A industry distribution
  python src/persona_v4.py --workplace 13101 --industry G10               # P(residence | works in 千代田区, 金融業) ("働きに来る人")
Counts are 2020 census 15歳以上就業者 (both sexes). Workplace-based counts are employed persons who work in the area,
not the daytime population (which would also include students and others). Residents whose workplace is unknown
(従業地「不詳」) are reported as a share outside the distribution.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from paths import OUTPUT,SOURCES

G=[f'G{i:02}' for i in range(1,21)]

class WorkplaceDistribution:
 def __init__(self,data_dir=None,sources_dir=None):
  self.dir=Path(data_dir or OUTPUT);self.sources=Path(sources_dir or SOURCES);d=np.load(self.dir/'workplace_c.npz')
  self.areas=d['areas'].tolist();self.ix={a:i for i,a in enumerate(self.areas)};self.model_version=str(d['model_version'])
  self.oi=d['origin'];self.di=d['dest'];self.ci=d['category'];self.x=d['x'].astype(float);self.unknown=d['unknown_workplace'].astype(float)
  self.by_o={};self.by_d={}
  for p,(o,dd) in enumerate(zip(self.oi.tolist(),self.di.tolist())):self.by_o.setdefault(o,[]).append(p);self.by_d.setdefault(dd,[]).append(p)
  pm=pd.read_csv(self.dir/'parent_mapping.csv',dtype=str);self.parents={p:[self.ix[a] for a in f.area] for p,f in pm.groupby('parent_code')}
  geo=pd.read_csv(self.dir/'geography.csv',dtype=str);self.names=dict(zip(geo.municipality_code,geo.municipality_name))
  summ=pd.read_csv(self.sources/'workplace/od_origin_summary_tidy.csv.gz',dtype={'origin':str}).set_index('origin');self.home=summ.home.to_dict();self.own_total=summ.own.to_dict()
  bins=pd.read_csv(self.sources/'industry/industry_bins.csv',dtype=str);self.glabel=dict(zip(bins.industry_code,bins.industry_label))
 def ids(self,code):
  code=str(code).zfill(5)
  if code in self.ix:return [self.ix[code]]
  if code in self.parents:return self.parents[code]
  raise ValueError(f'Unknown 2020 municipality code: {code}')
 def _weights(self,industry,industry_mix):
  if industry is not None:
   if industry not in G:raise ValueError('industry must be G01..G20 (JSIC A..T); G00 has no workplace')
   w=np.zeros(20);w[G.index(industry)]=1.;return w,'industry '+industry
  if industry_mix is not None:
   w=np.array([industry_mix.get(g,0.) for g in G],float)
   if w.sum()<=0:raise ValueError('industry mix has no mass on G01..G20')
   return w/w.sum(),'mixture over industries (assumes workplace independent of age/sex/education given residence and industry)'
  return None,'all industries'
 def _top(self,codes,mass,top):
  order=np.argsort(-mass);tot=mass.sum();out=[]
  for k in order[:top]:
   if mass[k]<=0:break
   out.append({'municipality_code':self.areas[codes[k]],'name':self.names.get(self.areas[codes[k]]),'p':float(mass[k]/tot),'persons':float(mass[k])})
  return out
 def workplace(self,code,industry=None,industry_mix=None,top=15):
  """P(workplace municipality | residence, industry or mixture). Residence may be a designated city (wards summed)."""
  ids=self.ids(code);w,cond=self._weights(industry,industry_mix)
  ps=np.concatenate([self.by_o.get(i,[]) for i in ids]).astype(int)
  if not len(ps):raise ValueError('No published commuting flows for this residence.')
  known_g=self.x[ps].sum(0);unk_g=self.unknown[ids].sum(0);share_g=unk_g/np.maximum(known_g+unk_g,1e-12)   # P(workplace unknown | o, g)
  if w is None:m=self.x[ps].sum(1)
  elif industry is not None:m=self.x[ps]@w
  else:
   # the mixture is over all employed persons; the distribution below is conditional on a known workplace, so the
   # industry weights are re-conditioned: P(g | o, known) ∝ mix_g * (1 - P(unknown | o, g))
   wk=w*(1-share_g)
   if wk.sum()<=0:raise ValueError('The industry mixture has no employed persons with a known workplace in this residence; the distribution is undefined.')
   wk=wk/wk.sum();col=self.x[ps].sum(0);m=(self.x[ps]/np.maximum(col,1e-12)*wk).sum(1)*self.x[ps].sum()   # P(d|o,mix,known)=sum_g P(g|o,known) P(d|o,g), scaled to persons
  dest=self.di[ps]
  agg=np.zeros(len(self.areas));np.add.at(agg,dest,m);codes=np.nonzero(agg)[0];vals=agg[codes]
  own=sum(float(agg[i]) for i in ids);tot=vals.sum()
  if tot<=0:raise ValueError('The model population for this condition is zero (no employed persons with a known workplace); the distribution is undefined.')
  unk_share=float(share_g@w) if w is not None else float(unk_g.sum()/max(known_g.sum()+unk_g.sum(),1e-12))
  cats=np.zeros(4);np.add.at(cats,self.ci[ps],m)
  res={'residence_code':str(code).zfill(5),'residence_name':self.names.get(str(code).zfill(5)),'condition':cond,'model_version':self.model_version,'model_population':float(tot),'p_workplace':self._top(codes,vals,top),
       'p_by_commuting_category':{'own_municipality':float(cats[0]/tot),'other_ward_same_city':float(cats[1]/tot),'other_municipality_same_prefecture':float(cats[2]/tot),'other_prefecture':float(cats[3]/tot)},
       'unknown_workplace_share_outside_distribution':unk_share,
       'note':'Both sexes, 15歳以上就業者, 2020 census. Own-municipality includes work at home and 従業市区町村「不詳・外国」. Mixtures over industries assume workplace is independent of age/sex/education given residence and industry; the mixture weights are re-conditioned on a known workplace (unknown-workplace persons are reported outside the distribution).'}
  if industry is None and industry_mix is None:
   home=sum(self.home.get(self.areas[i],0.) for i in ids);res['p_work_at_home_within_own_municipality']=float(home/own) if own>0 else None
  return res
 def residence(self,code,industry=None,top=15):
  """P(residence municipality | workplace, industry): the people who come to work in the area ("働きに来る人")."""
  ids=self.ids(code);w,cond=self._weights(industry,None)
  ps=np.concatenate([self.by_d.get(i,[]) for i in ids]).astype(int)
  if not len(ps):raise ValueError('No published commuting flows into this workplace.')
  m=(self.x[ps]*w).sum(1) if w is not None else self.x[ps].sum(1);orig=self.oi[ps]
  agg=np.zeros(len(self.areas));np.add.at(agg,orig,m);codes=np.nonzero(agg)[0];vals=agg[codes];tot=vals.sum()
  if tot<=0:raise ValueError('The model population for this condition is zero (no employed persons of this industry work here); the distribution is undefined.')
  cats=np.zeros(4);np.add.at(cats,self.ci[ps],m)
  return {'workplace_code':str(code).zfill(5),'workplace_name':self.names.get(str(code).zfill(5)),'condition':cond,'model_version':self.model_version,'model_population':float(tot),'p_residence':self._top(codes,vals,top),
          'p_by_commuting_category':{'live_in_workplace_municipality':float(cats[0]/tot),'other_ward_same_city':float(cats[1]/tot),'other_municipality_same_prefecture':float(cats[2]/tot),'other_prefecture':float(cats[3]/tot)},
          'note':'Employed persons (15+) who work in the area by where they live; not the daytime population. Residents of the area whose workplace is unknown are excluded.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 p.add_argument('--municipality');p.add_argument('--workplace');p.add_argument('--industry');p.add_argument('--age',type=int);p.add_argument('--sex');p.add_argument('--education');p.add_argument('--top',type=int,default=15);p.add_argument('--data-dir',type=Path);p.add_argument('--sources-dir',type=Path)
 a=p.parse_args();m=WorkplaceDistribution(a.data_dir,a.sources_dir)
 if a.workplace:print(json.dumps(m.residence(a.workplace,a.industry,a.top),ensure_ascii=False,indent=2))
 elif a.municipality:
  mix=None
  if a.industry is None and (a.age is not None or a.sex is not None or a.education is not None):
   if a.age is None or a.sex is None:raise SystemExit('--age and --sex are required to mix over the stage-A industry distribution')
   from persona_v3 import EmploymentDistribution
   e=EmploymentDistribution(a.data_dir,a.sources_dir).margins(a.municipality,a.age,a.sex,a.education);mix=e.get('p_industry_given_employed')
   if not mix:raise SystemExit('Stage A has no industry distribution for this condition')
  print(json.dumps(m.workplace(a.municipality,a.industry,mix,a.top),ensure_ascii=False,indent=2))
 else:raise SystemExit('give --municipality (residence) or --workplace')
