"""Verify limited structural rules in all stored households and repeated fresh draws.

This checks support rules, not the accuracy of unobserved household relationships.
"""
import argparse,json
import pandas as pd
import household_constraints as hc
from household_sample import HouseholdSampler
from paths import OUTPUT,REPORTS


def verify(codes,households=10000,seeds=(42,1234,20260908)):
    results={}
    for code in codes:
        sampler=HouseholdSampler(code)
        df=pd.read_csv(OUTPUT/'household_b'/f'{code}_population.csv.gz')
        result={'population':hc.validate_population(df),'seeds':[]}
        for seed in seeds:
            draws=sampler.sample_households(households,seed)
            rows=[]
            for h in draws:
                for m in h['members']:
                    rows.append((h['household_id'],m['member_id'],int(h['family_type'][1:])-1,
                                 9 if h['size_bin']=='10+' else int(h['size_bin'])-1,h['size'],
                                 int(m['role'][1:])-1,int(m['sex_code'])-1,int(m['age_band18'][1:])))
            sample=pd.DataFrame(rows,columns=['household_id','member_id','family','size_bin','size','role','sex','age18'])
            checked=hc.validate_population(sample)
            result['seeds'].append({'seed':seed,'households':households,'violations':checked['violations']})
        results[code]=result
        print(code,json.dumps(result),flush=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    (REPORTS/'household_structural_review.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('codes',nargs='*',default=['13103','47201','01555'])
    p.add_argument('--households',type=int,default=10000);a=p.parse_args()
    if a.households<=0:p.error('--households must be positive')
    verify(a.codes,a.households)
