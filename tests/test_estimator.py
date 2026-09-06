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
    def test_gamma_zero_has_no_tilt(self):
        self.assertIsNone(es.education_tilt(self.inp,0.))
        t=es.education_tilt(self.inp,1.);self.assertEqual(t.shape,self.inp['N'].shape+(16,));self.assertTrue((t>0).all())
    def test_m2_hook_requires_inputs(self):
        with self.assertRaises(NotImplementedError):es.industry_tilt(self.inp,1.)
if __name__=='__main__':unittest.main()
