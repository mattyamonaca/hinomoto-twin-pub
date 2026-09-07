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

class StageAContractTests(unittest.TestCase):
    def test_manifest_dispatch_skips_response_entries(self):
        import download_industry as di
        m={'sources':[{'title':'wb','raw_file':'raw/x.xlsx','raw_sha256':'0'},{'title':'resp','raw_responses':['raw/a.json.gz']}]}
        self.assertEqual([e['title'] for e in di.workbook_entries(m)],['wb'])
        with self.assertRaises(ValueError):di.workbook_entries({'sources':[{'title':'bad'}]})
    def test_age_and_sex_validation(self):
        import persona_v3 as pv
        self.assertEqual(pv.age_index(15),0);self.assertEqual(pv.age_index(35),4);self.assertEqual(pv.age_index(99),12)
        with self.assertRaises(ValueError):pv.age_index(14)
        with self.assertRaises(ValueError):pv.sex_index('x')
    def test_verification_checks_detect_corruption_and_exit_code(self):
        import verify_employment as ve
        from unittest.mock import patch
        rng=np.random.default_rng(1);M=3
        kg=rng.random((M,2,13,7,21));kg[...,5:,1:]=0;kg[...,:5,0]=0
        N=kg.sum((3,4));W=kg[...,:5,:].sum(-1);ke=np.zeros((M,2,13,8,7));ke[...,0,:]=kg.sum(-1)
        ky=rng.random((M,2,13,4,16));fin=np.zeros((M,2,13,17));fin[...,1:]=ky.sum(3)
        cnt=kg[...,:5,1:].sum(3);gy=rng.random((M,2,13,20,16))
        d={'status_industry':kg,'education_status':ke,'status_income':ky,'industry_income':gy}
        res,ok=ve.checks(d,fin,W,N,cnt);self.assertTrue(ok,res)
        bad=dict(d);bad['status_income']=ky.copy();bad['status_income'][0,0,0,0,0]+=100
        res,ok=ve.checks(bad,fin,W,N,cnt);self.assertFalse(ok);self.assertGreater(res['production_income_margin_max_error_persons'],99)
        with patch.object(ve,'evaluate',return_value={'passed':False}):
            with self.assertRaises(SystemExit) as cm:ve.main()
            self.assertEqual(cm.exception.code,1)

class HouseholdTests(unittest.TestCase):
    def test_ipf_nd_matches_all_margins(self):
        import build_household as bh
        rng=np.random.default_rng(5);seed=rng.random((3,4,5,6))+0.1
        z0=rng.random((3,4,5,6));A=z0.sum((0,1));B=z0.sum((2,3))
        z,it,err=bh.ipf_nd(seed,[((2,3),A),((0,1),B)],iters=2000,tol=1e-10)
        self.assertTrue(np.allclose(z.sum((0,1)),A,atol=1e-6));self.assertTrue(np.allclose(z.sum((2,3)),B,atol=1e-6))
    def test_gap_prior_rows_normalized_and_ordered(self):
        import build_household as bh
        P=bh.gap_prior(bh.AGE_MID,30,6,+1)
        self.assertTrue(np.allclose(P.sum(1),1));self.assertLess(np.argmax(P[8]),8)   # children of a 40-44 head are younger

class HouseholdReviewCases(unittest.TestCase):
    """Regression cases from the PR #18 review: presence counts must follow a composition consistent with fixed member counts."""
    def _world(self,T,N):
        import build_household as bh
        x={'code':'x','persons':T.sum((0,1,2,3,4)),'size':N.sum((0,1,2)),'P_F':T.sum((1,2,3,4,5,6)),'married':np.zeros((2,18)),'city_rel':None,'unknown_age_head_share':0.}
        return bh,x
    def test_two_role_fixed_slot_gives_certain_presence(self):
        # 100 two-person households, head 40-44, the other member is 65-69 with role child 50% / other relative 50%
        N=np.zeros((7,2,18,10));T=np.zeros((7,2,18,10,13,2,18));N[3,0,8,1]=100;T[3,0,8,1,0,0,8]=100;T[3,0,8,1,2,0,13]=50;T[3,0,8,1,9,0,13]=50
        bh,x=self._world(T,N)
        import pandas as pd
        from unittest.mock import patch
        empty=pd.DataFrame(columns=['area','age_class','elderly_class','family_type'])
        with patch.object(pd,'read_csv',return_value=empty):
            res=bh.evaluate(x,N,T)
        self.assertEqual(round(res['_presence_debug']['elderly_size2']),100)
    def test_under6_not_double_counted(self):
        # 100 three-person households: head 30-34, one child 0-4, one other member 5-9 -> exactly 100 households with a member under 6 (0-4) ... +20 expected from 5-9 at most once
        N=np.zeros((7,2,18,10));T=np.zeros((7,2,18,10,13,2,18));N[1,0,6,2]=100;T[1,0,6,2,0,0,6]=100;T[1,0,6,2,2,0,0]=100;T[1,0,6,2,9,0,1]=100
        bh,x=self._world(T,N)
        import pandas as pd
        from unittest.mock import patch
        empty=pd.DataFrame(columns=['area','age_class','elderly_class','family_type'])
        with patch.object(pd,'read_csv',return_value=empty):
            res=bh.evaluate(x,N,T)
        self.assertEqual(round(res['_presence_debug']['under6_size3']),100)


class HouseholdMixedSlotCases(unittest.TestCase):
    """PR #18 follow-up (P2): the 10+ size bin has a non-integer mean size; fractional expected counts must keep their members."""
    def _table(self,elderly):
        # F4 households in the 10+ bin: head 40-44, nine non-elderly members, plus `elderly` members aged 65-69 per 100 households
        N=np.zeros((7,2,18,10));T=np.zeros((7,2,18,10,13,2,18));N[3,0,8,9]=100;T[3,0,8,9,0,0,8]=100;T[3,0,8,9,2,0,8]=900;T[3,0,8,9,4,0,13]=elderly
        return N,T
    def _elderly(self,N,T):
        import build_household as bh
        w=np.zeros(18);w[13:]=1
        return bh.presence_count(N,T,w,size_k=9)
    def test_reviewer_case_mean_size_10_4(self):
        N,T=self._table(40);self.assertAlmostEqual(self._elderly(N,T),40.,places=6)
    def test_fraction_below_half(self):
        N,T=self._table(30);self.assertAlmostEqual(self._elderly(N,T),30.,places=6)
    def test_fraction_at_or_above_half(self):
        N,T=self._table(70);self.assertAlmostEqual(self._elderly(N,T),70.,places=6)
    def test_integer_mean_size(self):
        N,T=self._table(100);self.assertAlmostEqual(self._elderly(N,T),100.,places=6)
    def test_mixed_roles_share_fractional_slots(self):
        # 0.4 mixed slots split between two roles: 65-69 with probability 0.25 (10 persons) and 40-44 (30 persons) -> 0.4*0.25 = 10 households
        N,T=self._table(10);T[3,0,8,9,9,0,8]=30
        self.assertAlmostEqual(self._elderly(N,T),10.,places=6)
    def test_evaluate_reports_10plus_bin(self):
        import build_household as bh,pandas as pd
        from unittest.mock import patch
        N,T=self._table(40)
        x={'code':'x','persons':T.sum((0,1,2,3,4)),'size':N.sum((0,1,2)),'P_F':T.sum((1,2,3,4,5,6)),'married':np.zeros((2,18)),'city_rel':None,'unknown_age_head_share':0.}
        with patch.object(pd,'read_csv',return_value=pd.DataFrame(columns=['area','age_class','elderly_class','family_type'])):
            res=bh.evaluate(x,N,T)
        self.assertAlmostEqual(res['_presence_debug']['elderly_size10p'],40.,places=6)


class StageAPublicationTests(unittest.TestCase):
    """Issue #22: labour-status split and the API contract of persona_v3."""
    def test_unemployed_split_preserves_row_and_column_margins(self):
        from model_math import ipf
        non=np.array([50.,120.,30.,200.,40.,10.,5.,90.]);pu=np.array([.1,.08,.06,.05,.04,.2,.05,.07]);K6=non.sum();u=.07
        z,_,_=ipf(np.stack([np.maximum(pu,1e-6),np.maximum(1-pu,1e-6)],-1)*non[:,None],non,np.array([K6*u,K6*(1-u)]),tol=1e-9)
        self.assertTrue(np.allclose(z.sum(1),non,atol=1e-6));self.assertAlmostEqual(z[:,0].sum()/K6,u,places=8)
        self.assertGreater(z[5,0]/non[5],z[3,0]/non[3])   # the education with the higher seed keeps the higher unemployment share
    def test_persona_rejects_six_status_artifact(self):
        import persona_v3 as pv,tempfile,pathlib
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);np.savez(p/'employment_a.npz',areas=np.array(['13103']),population=np.ones((1,2,13)),status_industry=np.zeros((1,2,13,6,21)),education_status=np.zeros((1,2,13,8,6)),status_income=np.zeros((1,2,13,4,16)),industry_income=np.zeros((1,2,13,20,16)),education_industry=np.zeros((1,2,13,8,21)),model_version='3.0-M12',variant='base')
            (p/'parent_mapping.csv').write_text('parent_code,area\n')
            with self.assertRaises(ValueError):pv.EmploymentDistribution(p,p)
    def test_status_codes_and_labor_mapping(self):
        import persona_v3 as pv,build_employment as bm
        self.assertEqual(pv.K,bm.K);self.assertEqual(len(pv.K),7);self.assertEqual(pv.J,bm.J)
        self.assertEqual(bm.BLOCK,8*4*20*16+8*20+8+8)


class EmploymentWebExportTests(unittest.TestCase):
    """Issue #22 review: the export refuses artifacts, inputs and graph that do not come from the same model."""
    def _world(self,ver_inputs='3.0-M12',ver_a='3.0-M12',ver_agg='3.0-M12',ver_graph='3.0-M12',variant='base',shift=0.):
        import export_employment_web as ew
        rng=np.random.default_rng(0);M=2;cube=rng.random((M,2,13,8,17))*100;N=cube.sum((3,4))
        B=8*4*20*16;blk=np.zeros((1,2,13,B+160+16))
        paid=rng.random((2,13,8,4,20,16));paid*= (cube.sum(0)[...,1:]/paid.sum((3,4)))[:,:,:,None,None,:]
        fam=rng.random((2,13,8,20));zero=cube.sum(0)[...,0];fam*=(0.5*zero/fam.sum(-1))[...,None];un=0.2*zero;ina=0.3*zero
        blk[0,...,:B]=paid.reshape(2,13,B);blk[0,...,B:B+160]=fam.reshape(2,13,160);blk[0,...,B+160:B+168]=un;blk[0,...,B+168:]=ina+shift
        class Z(dict):
            files=property(lambda self:list(self.keys()))
        d=Z(areas=np.array(['13103','13104']),model_version=np.array(ver_a),variant=np.array(variant));agg=Z(codes=np.array(['00000']),blocks=blk,model_version=np.array(ver_agg),variant=np.array('base'))
        x={'model_version':ver_inputs,'areas':['13103','13104'],'cube':cube,'N':N}
        payload={'model':{'model_version':ver_graph},'graph':{'munis':[{'c':'13103'},{'c':'13104'}],'pop':N.tolist()}}
        return ew,payload,d,agg,x
    def test_consistent_world_passes(self):
        ew,p,d,a,x=self._world();c=ew.check_consistency(p,d,a,x);self.assertLess(c['national_block_vs_inputs_paid_max_error_persons'],1e-6)
    def test_version_mismatch_is_refused(self):
        ew,p,d,a,x=self._world(ver_inputs='different-model')
        with self.assertRaises(ValueError):ew.check_consistency(p,d,a,x)
        ew,p,d,a,x=self._world(ver_graph='2.0')
        with self.assertRaises(ValueError):ew.check_consistency(p,d,a,x)
    def test_non_base_variant_and_margin_drift_are_refused(self):
        ew,p,d,a,x=self._world(variant='national_kg')
        with self.assertRaises(ValueError):ew.check_consistency(p,d,a,x)
        ew,p,d,a,x=self._world(shift=5.)
        with self.assertRaises(ValueError):ew.check_consistency(p,d,a,x)
