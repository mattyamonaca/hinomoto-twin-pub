"""Apply the explicitly selected production estimator to baseline arrays."""
import json
import numpy as np
from paths import SOURCES, OUTPUT, REPORTS
import estimator as es

def main():
    import os
    model=os.environ.get('HINOMOTO_MODEL','M12')
    if model not in ('M0','M12'):raise ValueError('Unknown production model')
    inp=es.load_real_inputs(SOURCES)
    if model=='M12' and 'ind_share' not in inp:raise ValueError('M12 requires industry inputs; run fetch-industry first')
    gamma,industry,beta=(1.5,1.,0.) if model=='M12' else (0.,0.,.5)
    r=es.run(inp,gamma=gamma,gamma_industry=industry,beta=beta)
    C=r['counts_by_sex'];N=inp['N'];A=C.sum(1);pop=N.sum(1)
    assert np.isfinite(C).all() and C.min()>=-1e-8
    np.testing.assert_allclose(C.sum(-1),N,atol=1e-6)
    np.savez_compressed(OUTPUT/'final_arrays.npz',areas=np.array(inp['areas']),population=N,counts_by_sex=C,counts=A,probability=np.divide(A,pop[...,None],out=np.full_like(A,np.nan),where=pop[...,None]>0),p_age_income_given_municipality=np.divide(A,pop.sum(-1)[:,None,None],out=np.full_like(A,np.nan),where=pop.sum(-1)[:,None,None]>0),joint=A/N.sum())
    meta={'model':model,'model_version':'3.0-M12' if model=='M12' else '2.0','gamma_education':gamma,'gamma_industry':industry,'beta_tax':beta,'population_year':2020,'income_year':2022,'validation':'Development-set cross-validation; no independent validation of municipality sex/education-specific income or small towns.'}
    (OUTPUT/'model_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    (REPORTS/'production_model.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print(meta,flush=True)
if __name__=='__main__':main()
