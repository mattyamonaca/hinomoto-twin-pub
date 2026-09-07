"""Issue #21: contracts of the M2/M12 synthetic study and the same-denominator metrics (no national dataset needed)."""
import sys,unittest,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import synthetic_population_m12 as sp
import estimator as es
from model_math import norm

class SyntheticM12Tests(unittest.TestCase):
    def test_erf_matches_math(self):
        x=np.linspace(-4,4,81);self.assertLess(np.abs(sp.erf(x)-np.array([math.erf(v) for v in x])).max(),2e-7)
    def test_bin_probs_sum_to_one_and_shift_with_mu(self):
        p=sp.bin_probs_array(np.array([np.log(2e6),np.log(6e6)]))
        self.assertTrue(np.allclose(p.sum(-1),1));self.assertGreater(p[1,8:].sum(),p[0,8:].sum())
    def test_world_totals_and_observation_contract(self):
        w=sp.generate(3,P=2,K=4);inp=sp.observe(w)
        self.assertTrue(np.allclose(w['T'].sum(),w['N'].sum()))                       # every person is exactly once in the truth
        self.assertEqual(inp['ind_share'].shape,(8,2,13,sp.G));self.assertTrue(np.allclose(inp['ind_share'].sum(-1),1))
        self.assertEqual(inp['ind_q'].shape,(2,13,sp.G,16));self.assertTrue(np.allclose(inp['ind_q'].sum(-1),1))
        self.assertTrue(np.allclose(inp['ind_q'][:,0],inp['ind_q'][:,5]))            # table 24 has no age: identical across ages
        self.assertTrue((inp['Eraw']<=inp['N']).all())
        tilt=es.industry_tilt(inp,1.0);self.assertEqual(tilt.shape,(8,2,13,16));self.assertTrue((tilt>0).all())
    def test_no_industry_effect_makes_industry_shapes_flat_within_education_and_status(self):
        def shapes(w):return norm(w['T'][0,0,6,2,:,0,1:])                                # one area, sex, age; education 2, status regular: (G,16) shape per industry
        s0=shapes(sp.generate(1,P=2,K=4,ind_scale=0.));self.assertLess(.5*np.abs(s0[0]-s0[4]).sum(),1e-9)
        s1=shapes(sp.generate(1,P=2,K=4));self.assertGreater(.5*np.abs(s1[0]-s1[4]).sum(),0.1)
    def test_recovery_metrics_same_denominator(self):
        rng=np.random.default_rng(0);truth=norm(rng.random((5,2,13,16)));w=rng.random((5,2,13))*100;w[0]=0
        m,area=sp.recovery_metrics(truth,truth,w,areas_pop=np.array([100,9000,9000,100,9000]))
        self.assertEqual(m['tv_weighted'],0.);self.assertEqual(m['abs_error_share_ge500'],0.);self.assertTrue(np.isnan(area[0]))
        pred=truth.copy();pred[...,8:]*=0.5;pred=norm(pred)
        m2,_=sp.recovery_metrics(pred,truth,w);self.assertGreater(m2['tv_weighted'],0);self.assertGreater(m2['abs_error_share_ge500'],0)
        self.assertGreaterEqual(m2['tv_max'],m2['tv_p90']);self.assertGreaterEqual(m2['tv_p90'],m2['tv_median'])
    def test_evaluate_runs_all_four_models(self):
        w=sp.generate(2,P=2,K=5);inp=sp.observe(w);r=sp.evaluate(inp,w,gammas=(0.,1.),gammas_ind=(0.,1.),betas=(0.,.5))
        self.assertEqual(set(r),{'M0','M1','M2','M12'})
        self.assertEqual(r['M0']['gamma_edu'],0.);self.assertEqual(r['M0']['gamma_ind'],0.);self.assertEqual(r['M2']['gamma_edu'],0.);self.assertEqual(r['M1']['gamma_ind'],0.)
        for n in r:self.assertTrue(0<=r[n]['tv_weighted']<=1)
if __name__=='__main__':unittest.main()
