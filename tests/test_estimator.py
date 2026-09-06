"""Contract tests for the array-level estimator on a small virtual population (no national data needed)."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import estimator as es
import synthetic_population as sp

class EstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=sp.generate(seed=7,theta_sd=0.,unknown_corr=0.,P=2,K=4)
        cls.inp=sp.observe(cls.world)
    def test_margins_hold_for_m0_and_m1(self):
        inp=self.inp
        for g in (0.,1.):
            r=es.run(inp,gamma=g,beta=0.5)
            X=r['Xt'];E=r['E'];pref=inp['pref']
            self.assertTrue(np.allclose(X.sum(-1),E,atol=1e-6))                       # area totals
            for p in range(inp['pref'].max()+1):
                ids=pref==p;share=es.norm(X[ids].sum(0))
                ok=E[ids].sum(0)>0
                self.assertTrue(np.allclose(share[ok],inp['pref_target'][p][ok],atol=1e-8))  # prefecture income shares
            self.assertTrue((r['counts_by_sex']>=-1e-9).all())
            self.assertTrue(np.allclose(r['counts_by_sex'].sum(-1),inp['N'],atol=1e-6))
    def test_education_allocation_preserves_margins(self):
        inp=self.inp;r=es.run(inp,gamma=1.,beta=0.)
        e=es.allocate_education(inp,r['counts_by_sex']);R=inp['edu_share']*inp['N'][...,None]
        self.assertTrue(np.allclose(e.sum(-1),R,atol=1e-4))
        old=np.concatenate([r['counts_by_sex'][...,:2].sum(-1,keepdims=True),r['counts_by_sex'][...,2:]],-1)
        self.assertTrue(np.allclose(e.sum(-2),old,atol=1e-6))
    def test_virtual_population_contract(self):
        w=self.world;inp=self.inp
        self.assertTrue(np.allclose(w['edu_p'].sum(-1),1,atol=1e-9))                       # education shares sum to 1
        self.assertTrue(np.allclose(w['T'].sum((3,4,5)),w['N'],atol=1e-6))                  # truth population equals census N
        self.assertTrue(np.allclose(inp['edu_share'].sum(-1)[w['N']>0],1,atol=1e-9))
        self.assertTrue(np.allclose(inp['edu_q'][:,:,6],inp['edu_q'][:,:,7]))                 # E07/E08 carry no education-specific shape
        self.assertTrue(np.allclose(inp['edu_q'][:,:,7],inp['edu_reference'],atol=1e-9))     # ... they equal the all-education reference
        t=sp.truth_income(w)
        self.assertEqual(t['paid_by_edu'].shape,w['N'].shape+(8,16));self.assertEqual(t['paid_by_sa'].shape,w['N'].shape+(16,))
    def test_gamma_zero_has_no_tilt(self):
        self.assertIsNone(es.education_tilt(self.inp,0.))
        t=es.education_tilt(self.inp,1.);self.assertEqual(t.shape,self.inp['N'].shape+(16,));self.assertTrue((t>0).all())
    def test_m2_hook_requires_inputs(self):
        with self.assertRaises(NotImplementedError):es.industry_tilt(self.inp,1.)
if __name__=='__main__':unittest.main()

class EmploymentIpfTests(unittest.TestCase):
    def test_ipf3_matches_margins(self):
        import build_employment as bm
        rng=np.random.default_rng(3);n=4
        seed=rng.random((n,8,4,20,16))+0.05
        A=rng.random((n,8,16))*100;B=rng.random((n,4));C=rng.random((n,20))
        tot=A.sum((1,2));B=B/B.sum(1,keepdims=True)*tot[:,None];C=C/C.sum(1,keepdims=True)*tot[:,None]
        z,it,err=bm.ipf3(seed,A,B,C,tol=1e-9,iters=2000)
        self.assertLess(np.abs(z.sum((2,3))-A).max(),1e-3);self.assertLess(np.abs(z.sum((1,3,4))-B).max(),1e-3);self.assertLess(np.abs(z.sum((1,2,4))-C).max(),1e-3)
        self.assertTrue((z>=0).all())
