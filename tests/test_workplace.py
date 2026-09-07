"""Stage C (issue #24): commuting category, IPF invariants on a toy OD/industry world, and the conditional API on a toy artifact."""
import sys,unittest,tempfile,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import build_workplace as bw

def toy_world(seed=0):
 """4 areas: 01101/01102 wards of 01100, 01201 a city in the same prefecture, 13101 another prefecture. Known joint counts N[o,d,g]
 are drawn at random; the published margins are derived from them so the IPF problem is feasible."""
 rng=np.random.default_rng(seed);areas=['01101','01102','01201','13101'];parent={'01101':'01100','01102':'01100'}
 A=len(areas);Gn=20;N=rng.integers(0,50,size=(A,A,Gn)).astype(float)
 for i in range(A):N[i,i]+=rng.integers(100,300,size=Gn)          # most people work where they live
 oi,di,ci,od=[],[],[],[]
 for i,o in enumerate(areas):
  for j,d in enumerate(areas):
   oi.append(i);di.append(j);ci.append(bw.category(o,d,parent));od.append(N[i,j].sum())
 oi,di,ci,od=map(np.array,(oi,di,ci,od))
 R=np.zeros((A,4,Gn));W=np.zeros((A,4,Gn))
 for p in range(len(oi)):R[oi[p],ci[p]]+=N[oi[p],di[p]];W[di[p],ci[p]]+=N[oi[p],di[p]]
 x={'areas':areas,'parent':parent,'oi':oi,'di':di,'ci':ci,'od':od,'R':R,'W':W,'U':np.zeros((A,Gn)),'od_unknown':np.zeros(A)}
 return x,N

class CategoryTests(unittest.TestCase):
 def test_census_commuting_categories(self):
  parent={'01101':'01100','01102':'01100'}
  self.assertEqual(bw.category('01101','01101',parent),0)
  self.assertEqual(bw.category('01101','01102',parent),1)   # other ward of the same designated city
  self.assertEqual(bw.category('01101','01201',parent),2)   # same prefecture
  self.assertEqual(bw.category('01201','01101',parent),2)   # a city into a ward: same prefecture, not same city
  self.assertEqual(bw.category('01101','13101',parent),3)

class IpfTests(unittest.TestCase):
 def test_margins_are_reproduced_and_seed_is_normalised(self):
  x,N=toy_world();X0=bw.seed(x)
  np.testing.assert_allclose(X0.sum(1),x['od'],rtol=1e-12)
  X,hist=bw.ipf(x,X0.copy(),iters=500,tol=1e-6)
  A=len(x['areas']);ro=x['oi']*4+x['ci'];wd=x['di']*4+x['ci']
  s=np.zeros((A*4,20));np.add.at(s,ro,X);t=np.zeros((A*4,20));np.add.at(t,wd,X)
  self.assertLess(np.abs(X.sum(1)-x['od']).max(),1e-4);self.assertLess(np.abs(s-x['R'].reshape(A*4,20)).max(),1e-4);self.assertLess(np.abs(t-x['W'].reshape(A*4,20)).max(),1e-4)
  self.assertTrue((X>=0).all())
 def test_flat_and_informed_seeds_agree_when_margins_pin_the_solution(self):
  x,N=toy_world(1);Xa,_=bw.ipf(x,bw.seed(x).copy(),iters=2000,tol=1e-8)
  flat=x['od'][:,None]*np.full((1,20),1/20);Xb,_=bw.ipf(x,flat.copy(),iters=2000,tol=1e-8)
  # both are KL projections onto the same affine constraints; with a full support they converge to the same table
  self.assertLess(np.abs(Xa-Xb).max()/x['od'].max(),0.05)
 def test_zero_od_pairs_stay_zero(self):
  x,N=toy_world(2);x['od']=x['od'].copy();x['od'][1]=0
  R=np.zeros_like(x['R']);W=np.zeros_like(x['W'])
  for p in range(len(x['oi'])):
   v=N[x['oi'][p],x['di'][p]]*(0 if p==1 else 1);R[x['oi'][p],x['ci'][p]]+=v;W[x['di'][p],x['ci'][p]]+=v
  x['R']=R;x['W']=W;X,_=bw.ipf(x,bw.seed(x).copy(),iters=300,tol=1e-6)
  self.assertEqual(X[1].sum(),0.)

class ApiTests(unittest.TestCase):
 def test_conditionals_normalise_and_switch_sides(self):
  import pandas as pd,persona_v4 as pv
  x,N=toy_world(3);X,_=bw.ipf(x,bw.seed(x).copy(),iters=500,tol=1e-6)
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);(td/'workplace').mkdir();(td/'industry').mkdir()
   np.savez(td/'workplace_c.npz',areas=np.array(x['areas']),origin=x['oi'],dest=x['di'],category=x['ci'],x=X.astype(np.float32),seed=X.astype(np.float32),unknown_workplace=np.zeros((4,20),np.float32),industry_codes=np.array(bw.G),categories=np.array(bw.CAT),model_version='test',stage='C')
   pd.DataFrame({'parent_code':['01100','01100'],'parent_name':['札幌市']*2,'area':['01101','01102'],'name':['中央区','北区']}).to_csv(td/'parent_mapping.csv',index=False)
   pd.DataFrame({'municipality_code':x['areas'],'municipality_name':['a','b','c','d']}).to_csv(td/'geography.csv',index=False)
   pd.DataFrame({'origin':x['areas'],'total':[1]*4,'own':[1]*4,'home':[0.5]*4}).to_csv(td/'workplace/od_origin_summary_tidy.csv.gz',index=False)
   pd.DataFrame({'industry_code':bw.G,'jsic_letter':list('ABCDEFGHIJKLMNOPQRST'),'industry_label':bw.G}).to_csv(td/'industry/industry_bins.csv',index=False)
   m=pv.WorkplaceDistribution(td,td)
   r=m.workplace('01101','G05');self.assertAlmostEqual(sum(e['p'] for e in r['p_workplace']),1.,places=9);self.assertAlmostEqual(sum(r['p_by_commuting_category'].values()),1.,places=9)
   self.assertAlmostEqual(r['p_workplace'][0]['persons'] if r['p_workplace'][0]['municipality_code']=='01101' else -1,float(X[0,4]),places=2)
   w=m.residence('13101','G05');self.assertAlmostEqual(sum(e['p'] for e in w['p_residence']),1.,places=9)
   mix={'G05':0.5,'G07':0.5};r2=m.workplace('01101',None,mix);self.assertAlmostEqual(sum(e['p'] for e in r2['p_workplace']),1.,places=9)
   agg=m.workplace('01100');self.assertAlmostEqual(agg['model_population'],float(X[:8].sum()),places=2)   # designated city = its two wards
   with self.assertRaises(ValueError):m.workplace('01101','G00')
 def test_mixture_is_conditioned_on_known_workplace_and_zero_population_is_refused(self):
  import json,pandas as pd,persona_v4 as pv
  # residence R (0): G01 -> A (1) known 10, unknown 90; G02 -> B (2) known 100, unknown 0; nothing else
  areas=['00001','00002','00003'];oi=np.array([0,0],np.int32);di=np.array([1,2],np.int32);ci=np.array([2,2],np.int8)
  X=np.zeros((2,20),np.float32);X[0,0]=10.;X[1,1]=100.;unk=np.zeros((3,20),np.float32);unk[0,0]=90.
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);(td/'workplace').mkdir();(td/'industry').mkdir()
   np.savez(td/'workplace_c.npz',areas=np.array(areas),origin=oi,dest=di,category=ci,x=X,seed=X,unknown_workplace=unk,industry_codes=np.array(bw.G),categories=np.array(bw.CAT),model_version='test',stage='C')
   pd.DataFrame({'parent_code':[],'parent_name':[],'area':[],'name':[]}).to_csv(td/'parent_mapping.csv',index=False)
   pd.DataFrame({'municipality_code':areas,'municipality_name':['R','A','B']}).to_csv(td/'geography.csv',index=False)
   pd.DataFrame({'origin':areas,'total':[1]*3,'own':[1]*3,'home':[0.]*3}).to_csv(td/'workplace/od_origin_summary_tidy.csv.gz',index=False)
   pd.DataFrame({'industry_code':bw.G,'jsic_letter':list('ABCDEFGHIJKLMNOPQRST'),'industry_label':bw.G}).to_csv(td/'industry/industry_bins.csv',index=False)
   m=pv.WorkplaceDistribution(td,td)
   r=m.workplace('00001',None,{'G01':0.5,'G02':0.5});p={e['municipality_code']:e['p'] for e in r['p_workplace']}
   self.assertAlmostEqual(p['00002'],1/11,places=9);self.assertAlmostEqual(p['00003'],10/11,places=9)   # known-workplace shares 10:100 within the 50/50 mixture
   self.assertAlmostEqual(r['unknown_workplace_share_outside_distribution'],0.45,places=9)               # 0.5*0.9 + 0.5*0
   json.dumps(r,allow_nan=False)
   with self.assertRaises(ValueError):m.workplace('00001','G03')          # OD pairs exist, but nobody of this industry
   with self.assertRaises(ValueError):m.residence('00002','G02')
   with self.assertRaises(ValueError):m.workplace('00001',None,{'G03':1.})

if __name__=='__main__':unittest.main()

class WebExportTests(unittest.TestCase):
 def test_files_reproduce_pair_totals_and_index(self):
  import json,hashlib,pandas as pd,export_workplace_web as ew
  from unittest.mock import patch
  x,N=toy_world(3);X,_=bw.ipf(x,bw.seed(x).copy(),iters=300,tol=1e-6)
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);(td/'data').mkdir();(td/'web').mkdir();(td/'validation').mkdir();(td/'sources'/'workplace').mkdir(parents=True)
   np.savez(td/'data/workplace_c.npz',areas=np.array(x['areas']),origin=x['oi'],dest=x['di'],category=x['ci'],x=X.astype(np.float32),seed=X.astype(np.float32),unknown_workplace=np.ones((4,20),np.float32),industry_codes=np.array(bw.G),categories=np.array(bw.CAT),model_version='test',stage='C')
   pd.DataFrame({'origin':x['areas'],'total':[1]*4,'own':[1]*4,'home':[0.5]*4}).to_csv(td/'sources/workplace/od_origin_summary_tidy.csv.gz',index=False)
   (td/'web/graph.json').write_text(json.dumps({'schema_version':3,'dataset_version':'v','graph':{}}))
   with patch.object(ew,'OUTPUT',td/'data'),patch.object(ew,'WEB',td/'web'),patch.object(ew,'REPORTS',td/'validation'),patch.object(ew,'SOURCES',td/'sources'):ew.main()
   g=json.loads((td/'web/graph.json').read_text());self.assertEqual(g['graph']['workplace']['version'],'test');self.assertTrue(g['dataset_version'].endswith('+C'))
   idx=json.loads((td/'web/workplace/index.json').read_text())['files']
   for rel,(nb,sha) in idx.items():
    b=(td/'web'/rel).read_bytes();self.assertEqual(len(b),nb);self.assertEqual(hashlib.sha256(b).hexdigest(),sha)
   o=json.loads((td/'web/workplace/o_01101.json').read_text());tot=sum(sum(r[2]) for r in o['rows'])
   self.assertAlmostEqual(tot,float(X[x['oi']==0].sum()),delta=0.01*len(o['rows'])*20)
   d=json.loads((td/'web/workplace/d_13101.json').read_text());self.assertAlmostEqual(sum(sum(r[2]) for r in d['rows']),float(X[x['di']==x['areas'].index('13101')].sum()),delta=0.5)
