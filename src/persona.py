"""Load P(age,income | municipality), condition by age, and sample synthetic persona bands."""
import argparse,csv,json
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[1]

class PersonaDistribution:
 def __init__(self,data_dir=None):
  self.directory=Path(data_dir or BASE/'data')
  d=np.load(self.directory/'municipality_model.npz');self.codes=d['municipality_codes'].tolist();self.counts=d['counts'];self.population=d['population'];self.index={c:i for i,c in enumerate(self.codes)}
  self.ages=list(csv.DictReader(open(self.directory/'age_bins.csv',encoding='utf-8')))
  self.incomes=list(csv.DictReader(open(self.directory/'income_bins.csv',encoding='utf-8')))
 def distribution(self,municipality_code,age=None):
  """No age: 13 x 16 joint distribution within municipality. Age specified: 16 income probabilities within its age band."""
  code=str(municipality_code).zfill(5)
  if code not in self.index:raise ValueError(f'Unknown 2020 municipality code: {code}')
  x=self.counts[self.index[code]].copy()
  if age is not None:
   if age<15:raise ValueError('This model covers ages 15 and older.')
   ai=min((int(age)-15)//5,12);x=x[ai]
  if x.sum()==0:raise ValueError('The 2020 source population for this municipality/age band is zero; a conditional distribution is undefined.')
  return x/x.sum()
 def sample(self,municipality_code,n=1,age=None,seed=20260905):
  p=self.distribution(municipality_code,age);rng=np.random.default_rng(seed);draws=rng.choice(p.size,size=n,p=p.ravel())
  result=[]
  for k in draws:
   ai,yi=divmod(int(k),16) if age is None else (min((int(age)-15)//5,12),int(k))
   result.append({'municipality_code':str(municipality_code).zfill(5),'age_band':self.ages[ai]['age_band'],'income_band':self.incomes[yi]['income_band'],'synthetic':True})
  return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--municipality',required=True);p.add_argument('--age',type=int);p.add_argument('--sample',type=int);p.add_argument('--seed',type=int,default=20260905);p.add_argument('--output',type=Path)
 args=p.parse_args();model=PersonaDistribution()
 result=model.sample(args.municipality,args.sample,args.age,args.seed) if args.sample else model.distribution(args.municipality,args.age).tolist()
 text=json.dumps(result,ensure_ascii=False,indent=2)
 if args.output:args.output.write_text(text)
 else:print(text)
