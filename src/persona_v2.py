"""Query and sample age/sex/education/income bands within a municipality."""
import argparse,json
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[1]

class PersonaDistributionV2:
 def __init__(self,data_dir=None):
  self.directory=Path(data_dir or BASE/'data')
  d=np.load(self.directory/'municipality_model_v2.npz');self.codes=d['municipality_codes'].tolist();self.counts=d['counts'];self.index={m:i for i,m in enumerate(self.codes)}
  self.schema=json.loads((self.directory/'schema_v2.json').read_text())
 def _selection(self,municipality_code,age=None,sex=None,education=None):
  m=str(municipality_code).zfill(5)
  if m not in self.index:raise ValueError(f'Unknown 2020 municipality: {m}')
  ix=[list(range(13)),list(range(2)),list(range(8)),list(range(16))]
  if age is not None:
   if not isinstance(age,(int,np.integer)) or age<15:raise ValueError('Age must be an integer of 15 or above; values select 5-year bands.')
   ix[0]=[min((age-15)//5,12)]
  if sex is not None:
   s={'male':'1','female':'2','男':'1','女':'2'}.get(str(sex),str(sex))
   if s not in ['1','2']:raise ValueError('sex must be 1/male/男 or 2/female/女 (published statistical categories).')
   ix[1]=[int(s)-1]
  if education is not None:
   if education not in self.schema['education_codes']:raise ValueError('education must be E01,...,E08; see education_bins.csv')
   ix[2]=[self.schema['education_codes'].index(education)]
  c=self.counts[self.index[m]][np.ix_(*ix)]
  if c.sum()<=0:raise ValueError('The selected municipality/attribute combination has zero source/model population; distribution is undefined.')
  return c/c.sum(),ix
 def distribution(self,municipality_code,age=None,sex=None,education=None):
  """Always returns 4 axes; supplied conditions select length-one axes. Sum = 1."""
  return self._selection(municipality_code,age,sex,education)[0]
 def income_distribution(self,municipality_code,age=None,sex=None,education=None):
  return self.distribution(municipality_code,age,sex,education).sum((0,1,2))
 def sample(self,municipality_code,n=1,age=None,sex=None,education=None,seed=20260905):
  if not isinstance(n,int) or n<0:raise ValueError('n must be a nonnegative integer')
  p,ix=self._selection(municipality_code,age,sex,education);rng=np.random.default_rng(seed);draws=rng.choice(p.size,size=n,p=p.ravel());result=[]
  for k in draws:
   a,s,e,y=[ix[j][pos] for j,pos in enumerate(np.unravel_index(int(k),p.shape))]
   result.append({'municipality_code':str(municipality_code).zfill(5),'age_band':self.schema['labels']['age'][a],'sex_code':str(s+1),'sex':self.schema['labels']['sex'][s],'education_code':self.schema['education_codes'][e],'education':self.schema['labels']['education'][e],'income_band':self.schema['labels']['income'][y],'synthetic':True})
  return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--municipality',required=True);parser.add_argument('--age',type=int);parser.add_argument('--sex');parser.add_argument('--education');parser.add_argument('--sample',type=int);parser.add_argument('--seed',type=int,default=20260905);parser.add_argument('--income-only',action='store_true');parser.add_argument('--output',type=Path)
 args=parser.parse_args();model=PersonaDistributionV2();conditions=dict(age=args.age,sex=args.sex,education=args.education)
 if args.sample is not None:result=model.sample(args.municipality,args.sample,seed=args.seed,**conditions)
 elif args.income_only:result={'income_codes':model.schema['income_codes'],'probabilities':model.income_distribution(args.municipality,**conditions).tolist()}
 else:
  p,ix=model._selection(args.municipality,**conditions)
  result={'axes':model.schema['axes'],'codes':{axis:[model.schema[axis+'_codes'][k] for k in ix[j]] for j,axis in enumerate(model.schema['axes'])},'probabilities':p.tolist()}
 text=json.dumps(result,ensure_ascii=False,indent=2)
 if args.output:args.output.write_text(text)
 else:print(text)
