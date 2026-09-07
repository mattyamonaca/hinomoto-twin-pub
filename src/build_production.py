"""Production income model (M12) as explicit stages with stored intermediate artifacts (Issue #34).

Every stage reads the artifact of the previous stage from data/stages/ and writes its own; the final arrays are made
from those artifacts, so the intermediate values that the Explorer describes are the ones the published data was
built from. Stage functions are the estimator's own (fit_status, status_income_shapes, mixture, education_tilt,
industry_tilt, calibrate, tax_project) — no separate implementation for explanation.

  status     W(m,s,a,k) paid-status persons, E paid workers, r(y|p,s,a,k) status income shapes   -> stages/status.npz
  mixture    q0 = mixture of the status shapes (no tilt), tilt_e^γ, tilt_g^γ₂, q_tilt = norm(q0·tilt)  -> stages/mixture.npz
  calibrate  X_m1 = calibrate(q0) (M1 baseline), X_m2 = calibrate(q_tilt), margin errors        -> stages/calibrated.npz
  finalize   Xt = tax_project(X_m2, β), counts_by_sex, final_arrays.npz, model_metadata.json

Provenance: each artifact stores a JSON string with the model settings, a fingerprint of the inputs (hash of the input
arrays), the hash of the upstream artifact and the code commit. A downstream stage refuses an upstream artifact whose
fingerprint or settings differ from the current inputs/model. `python src/build_production.py` runs all stages;
`--stage NAME` runs one stage from the stored upstream artifact (resume); `--check` compares the staged result with a
direct estimator.run() (must agree to 1e-9 persons: identical operations in the same order).
"""
import argparse,hashlib,json,os,subprocess,time
import numpy as np
from paths import SOURCES,OUTPUT,REPORTS
import estimator as es

STAGES=OUTPUT/'stages'
SETTINGS={'M12':{'gamma_education':1.5,'gamma_industry':1.0,'beta_tax':0.0,'model_version':'3.0-M12'},'M0':{'gamma_education':0.0,'gamma_industry':0.0,'beta_tax':0.5,'model_version':'2.0'}}
FINGERPRINT_KEYS=['N','Nraw','Eraw','seed_q','t_status','pref_rate','ess_cat','nat_cat','pref_target','tax_feature','edu_share','edu_q','edu_rate','ind_share','ind_q']

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):return sha_bytes(p.read_bytes())
def code_commit():
    try:return subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True,cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except Exception:return 'unknown'
def fingerprint(inp):
    """Hash of the input arrays the stages depend on (independent of file names)."""
    h=hashlib.sha256()
    for k in FINGERPRINT_KEYS:
        if k in inp:h.update(k.encode());h.update(np.ascontiguousarray(np.asarray(inp[k],dtype=float)).tobytes())
    h.update(','.join(inp['areas']).encode());return h.hexdigest()
def provenance(stage,model,fp,upstream=None,extra=None):
    d={'stage':stage,'model':model,**SETTINGS[model],'inputs_fingerprint':fp,'upstream':upstream or {},'code_commit':code_commit(),'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    if extra:d.update(extra)
    return json.dumps(d,ensure_ascii=False)
def load_stage(name,model,fp,require_upstream=None):
    """Load an artifact and refuse it if it was made for other inputs, another model or another upstream artifact."""
    p=STAGES/f'{name}.npz'
    if not p.exists():raise FileNotFoundError(f'{p} is missing; run `python src/build_production.py --stage {name}` (or the full build) first')
    d=np.load(p,allow_pickle=False);pv=json.loads(str(d['provenance']))
    if pv['model']!=model or pv['model_version']!=SETTINGS[model]['model_version']:raise ValueError(f"{p.name} was built for model {pv['model']} {pv['model_version']}, not {model}")
    for k in ('gamma_education','gamma_industry','beta_tax'):
        if abs(pv[k]-SETTINGS[model][k])>1e-12:raise ValueError(f"{p.name}: {k}={pv[k]} differs from the {model} setting {SETTINGS[model][k]}")
    if pv['inputs_fingerprint']!=fp:raise ValueError(f'{p.name} was built from different inputs (fingerprint {pv["inputs_fingerprint"][:12]}… vs {fp[:12]}…); rebuild the stages')
    if require_upstream:
        for up,sha in require_upstream.items():
            if pv['upstream'].get(up)!=sha:raise ValueError(f'{p.name} was built from a different {up} artifact; rebuild from that stage')
    return d,pv
def save_stage(name,arrays,prov):
    STAGES.mkdir(parents=True,exist_ok=True);p=STAGES/f'{name}.npz'
    np.savez_compressed(p,provenance=np.array(prov),**arrays);return sha_file(p)

def stage_status(inp,model,fp):
    W=es.fit_status(inp);cp=es.status_income_shapes(inp);E=W[...,:4].sum(-1)
    sha=save_stage('status',{'areas':np.array(inp['areas']),'prefs':np.array(inp['prefs']),'W':W,'E':E,'cp':cp},provenance('status',model,fp,extra={'layout':'W[m,s,a,k] persons (K1 regular, K2 non-regular, K3 executive, K4 self-employed, K5 family); E = sum of K1..K4; cp[p,s,a,k,y] status income shapes r(y|p,s,a,k), smoothed with pseudo-population 1000'}))
    return sha
def stage_mixture(inp,model,fp):
    d,pv=load_stage('status',model,fp);st=SETTINGS[model];W=d['W'];cp=d['cp']
    q0,E=es.mixture(inp,W,cp,None)
    te=es.education_tilt(inp,st['gamma_education']);tg=es.industry_tilt(inp,st['gamma_industry']) if st['gamma_industry'] else None
    tilt=None
    if te is not None:tilt=te
    if tg is not None:tilt=tg if tilt is None else tilt*tg
    q_tilt,_=es.mixture(inp,W,cp,tilt)
    ones=np.ones_like(q0)
    sha=save_stage('mixture',{'areas':d['areas'],'E':E,'q0':q0,'tilt_education':te if te is not None else ones,'tilt_industry':tg if tg is not None else ones,'tilt':tilt if tilt is not None else ones,'q_tilt':q_tilt},provenance('mixture',model,fp,upstream={'status':sha_file(STAGES/'status.npz')},extra={'layout':'q0[m,s,a,y] status-mixed income shape of paid workers (M1 input, no tilt); tilt_education = T_e^gamma, tilt_industry = T_g^gamma2 (ones when the coefficient is 0); q_tilt = norm(q0 * tilt) (M2 input, before calibration)'}))
    return sha
def stage_calibrate(inp,model,fp):
    ds,_=load_stage('status',model,fp);dm,_=load_stage('mixture',model,fp,require_upstream={'status':sha_file(STAGES/'status.npz')})
    E=dm['E'];X1=es.calibrate(inp,dm['q0'],E);X2=es.calibrate(inp,dm['q_tilt'],E)
    P=len(inp['prefs']);pref=inp['pref'];summary=[]
    for p in range(P):
        ids=np.where(pref==p)[0];tgt=inp['pref_target'][p]                       # (2,13,16)
        for si in range(2):
            for ai in range(13):
                r=E[ids,si,ai];tot=r.sum()
                if tot<=0:summary.append([p,si,ai,0.,0.]);continue
                z=X2[ids,si,ai];summary.append([p,si,ai,float(np.abs(z.sum(1)-r).max()),float(np.abs(z.sum(0)/tot-tgt[si,ai]).max())])
    sha=save_stage('calibrated',{'areas':ds['areas'],'E':E,'X_m1':X1,'X_m2':X2,'calibration_summary':np.array(summary)},provenance('calibrate',model,fp,upstream={'status':sha_file(STAGES/'status.npz'),'mixture':sha_file(STAGES/'mixture.npz')},extra={'layout':'X_m1[m,s,a,y] = calibrate(q0) (M1 baseline, reproduces model_arrays.npz (2e-12 persons measured)); X_m2 = calibrate(q_tilt) (M12 before tax); calibration_summary rows [pref, sex, age, max |row sum - E| persons, max |column share - published share|]'}))
    return sha
def stage_finalize(inp,model,fp):
    dc,pv=load_stage('calibrated',model,fp,require_upstream={'status':sha_file(STAGES/'status.npz'),'mixture':sha_file(STAGES/'mixture.npz')});st=SETTINGS[model]
    E=dc['E'];Xt=es.tax_project(inp,dc['X_m2'],E,st['beta_tax']);N=inp['N'];Z=N-E
    C=np.concatenate([Z[...,None],Xt],axis=-1);A=C.sum(1);pop=N.sum(1)
    assert np.isfinite(C).all() and C.min()>=-1e-8
    np.testing.assert_allclose(C.sum(-1),N,atol=1e-6)
    np.savez_compressed(OUTPUT/'final_arrays.npz',areas=np.array(inp['areas']),population=N,counts_by_sex=C,counts=A,probability=np.divide(A,pop[...,None],out=np.full_like(A,np.nan),where=pop[...,None]>0),p_age_income_given_municipality=np.divide(A,pop.sum(-1)[:,None,None],out=np.full_like(A,np.nan),where=pop.sum(-1)[:,None,None]>0),joint=A/N.sum(),provenance=np.array(provenance('finalize',model,fp,upstream={'calibrated':sha_file(STAGES/'calibrated.npz')})))
    meta={'model':model,'model_version':st['model_version'],'gamma_education':st['gamma_education'],'gamma_industry':st['gamma_industry'],'beta_tax':st['beta_tax'],'population_year':2020,'income_year':2022,'validation':'Development-set cross-validation; no independent validation of municipality sex/education-specific income or small towns.','inputs_fingerprint':fp,'code_commit':code_commit(),'stages':{n:sha_file(STAGES/f'{n}.npz') for n in ('status','mixture','calibrated')}}
    (OUTPUT/'model_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    (REPORTS/'production_model.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return meta
def check_equivalence(inp,model):
    """The staged final arrays must equal a direct estimator.run() (same functions in the same order)."""
    st=SETTINGS[model];r=es.run(inp,gamma=st['gamma_education'],gamma_industry=st['gamma_industry'],beta=st['beta_tax'])
    C=np.load(OUTPUT/'final_arrays.npz')['counts_by_sex'];diff=float(np.abs(C-r['counts_by_sex']).max())
    dc=np.load(STAGES/'calibrated.npz');margins={'staged_vs_direct_max_abs_persons':diff,'X_m2_vs_direct_max_abs_persons':float(np.abs(dc['X_m2']-r['X']).max()),'tolerance_persons':1e-9,'tolerance_reason':'identical numpy operations in the same order; only floating-point non-determinism could differ'}
    ma=OUTPUT/'model_arrays.npz'
    if ma.exists():
        m1=np.load(ma)['counts_by_sex'][...,1:];margins['X_m1_vs_model_arrays_max_abs_persons']=float(np.abs(dc['X_m1']-m1).max());margins['X_m1_note']='model_arrays.npz is produced by build.py (v1); the staged X_m1 reproduces it up to floating-point differences of the v1 code path (2e-12 persons measured)'
    margins['passed']=diff<=1e-9
    (REPORTS/'production_stages_check.json').write_text(json.dumps(margins,indent=2));print(json.dumps(margins,indent=1))
    if not margins['passed']:raise SystemExit(1)
    return margins

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stage',choices=['status','mixture','calibrate','finalize','all'],default='all');p.add_argument('--check',action='store_true');a=p.parse_args()
    model=os.environ.get('HINOMOTO_MODEL','M12')
    if model not in SETTINGS:raise ValueError('Unknown production model')
    inp=es.load_real_inputs(SOURCES)
    if model=='M12' and 'ind_share' not in inp:raise ValueError('M12 requires industry inputs; run fetch-industry first')
    fp=fingerprint(inp);t0=time.time()
    order=['status','mixture','calibrate','finalize'] if a.stage=='all' else [a.stage]
    for s in order:
        {'status':stage_status,'mixture':stage_mixture,'calibrate':stage_calibrate,'finalize':stage_finalize}[s](inp,model,fp);print(f'stage {s} done {time.time()-t0:.0f}s',flush=True)
    if a.stage in ('all','finalize'):print(json.loads((OUTPUT/'model_metadata.json').read_text()),flush=True)
    if a.check:check_equivalence(inp,model)
if __name__=='__main__':main()
