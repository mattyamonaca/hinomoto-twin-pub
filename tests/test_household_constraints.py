import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import household_constraints as hc
from household_sample import HouseholdSampler
from build_household import presence_prob

class StructuralTests(unittest.TestCase):
    def table(self,f=3,a=8,k=2):
        N=np.zeros((7,2,18,10));T=np.zeros((7,2,18,10,13,2,18));ix=(f,0,a,k)
        N[ix]=100;T[ix+(0,0,a)]=100
        return N,T,ix
    def test_fractional_spouse_never_repeated_and_expectations_preserved(self):
        N,T,i=self.table();T[i+(1,1,7)]=40;T[i+(2,0,2)]=80;T[i+(9,0,13)]=80
        s=HouseholdSampler('x',arrays=(N,T));hh=s.sample_households(3000,42)
        self.assertTrue(all(len(h['members'])==3 for h in hh))
        self.assertTrue(all(sum(m['role']=='R02' for m in h['members'])<=1 for h in hh))
        patterns=hc.count_patterns([.4,.8,.8]);expected=sum(p*c for p,c in patterns)
        np.testing.assert_allclose(expected,[.4,.8,.8],atol=1e-12)
        for p,c in patterns:self.assertEqual(sum(c),2);self.assertLessEqual(c[0],1)
    def test_open_size_mean_and_presence_match_sampling_process(self):
        counts=[.4,8.2,.8];patterns=hc.count_patterns(counts)
        np.testing.assert_allclose(sum(p*c for p,c in patterns),counts)
        self.assertEqual({sum(c)+1 for p,c in patterns},{10,11})
        N,T,i=self.table(k=9);T[i+(1,1,7)]=40;T[i+(2,0,2)]=820;T[i+(9,0,13)]=80
        w=np.zeros(18);w[13:]=1
        expected=sum(p for p,c in patterns if c[2]>0)
        self.assertAlmostEqual(presence_prob(100,T[i],w),expected)
    def test_couple_children_and_age_support_preserve_population(self):
        N,T,i=self.table(f=1);T[i+(1,1,0)]=10;T[i+(1,1,7)]=90;T[i+(2,0,2)]=70;T[i+(4,1,15)]=30
        Z,rep=hc.constrain(N,T)
        self.assertAlmostEqual(Z.sum(),T.sum());self.assertEqual(Z[i+(4,1,15)],0)
        self.assertEqual(Z[i+(1,1,0)],0);self.assertEqual(Z[i+(2,0,2)],100)
        self.assertGreater(rep['reallocated_expected_members'],0)
        for h in HouseholdSampler('x',arrays=(N,Z)).sample_households(100,3):
            self.assertEqual([m['role'] for m in h['members']],['R01','R02','R03'])
    def test_empty_support_fails_instead_of_fabricating(self):
        N,T,i=self.table(f=0,k=1);T[i+(1,1,0)]=100
        with self.assertRaisesRegex(ValueError,'No admissible spouse'):hc.constrain(N,T)
    def test_legacy_forbidden_input_rejected(self):
        N,T,i=self.table();T[i+(1,1,0)]=100;T[i+(9,0,13)]=100
        with self.assertRaisesRegex(ValueError,'Forbidden'):HouseholdSampler('x',arrays=(N,T))
    def test_parent_rule_is_limited_not_a_typical_age_gap(self):
        N,T,i=self.table();T[i+(4,1,1)]=20;T[i+(4,1,17)]=80;T[i+(1,1,3)]=100
        Z,_=hc.constrain(N,T);self.assertEqual(Z[i+(4,1,1)],0)
        self.assertGreater(Z[i+(1,1,3)],0) # do not force a typical spouse age gap
        self.assertTrue(hc.support(3,8)[5,1,7]) # younger parent-in-law is not banned
    def test_actual_records_reject_duplicate_spouse(self):
        import pandas as pd
        d=pd.DataFrame([(1,1,3,2,3,0,0,8),(1,2,3,2,3,1,1,7),(1,3,3,2,3,1,1,9)],columns=['household_id','member_id','family','size_bin','size','role','sex','age18'])
        with self.assertRaisesRegex(ValueError,'constraints'):hc.validate_population(d)

if __name__=='__main__':unittest.main()
