"""Publish stage A (employment status x industry) for the Explorer, alongside the 5-attribute web dataset.

Distribution format (decided in docs/EMPLOYMENT_A.md §5 before implementation):
  graph.json  (schema_version 3)  `emp`: small global parameters the page needs to re-run the stage-A allocation for
              one municipality x sex x age: national P(k|e,s,a), prefecture P(g|k,s,a,p) (graduates / enrolled),
              industry income tilt, prefecture status income shapes r(y|p,s,a,k), prefecture education-specific
              unemployment shares. Little-endian float32, base64.
  employment_inputs.bin           per leaf municipality x sex x age: W1..W5, K6+K7, unemployed share, 20 industry
              counts scaled to employed persons (27 float32 values). Fetched on first use.
  employment/agg_<code>.bin       pre-aggregated full blocks (paid[e,k,g,y], family[e,g], unemployed[e], inactive[e]
              per sex x age) for the nation, each prefecture and each aggregated-ward city, because summing the
              recomputed blocks of all their municipalities in the browser would take too long. float32 persons.
The page reproduces employment_a.npz; validation/employment_web_verification.json records the comparison run by
`node tests/web_employment_check.cjs` (jsdom) against Python values for sample municipalities.
"""
import json,base64,hashlib
import numpy as np
from paths import OUTPUT,WEB,REPORTS,SOURCES
import build_employment as bm

def b64f32(x):return base64.b64encode(np.ascontiguousarray(np.asarray(x,dtype='<f4')).tobytes()).decode('ascii')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def check_consistency(payload,d,agg,x,tol_persons=0.5):
    """Refuse to publish unless the recomputation inputs (x), the saved artifacts (employment_a.npz, employment_a_agg.npz)
    and the 5-attribute web dataset (graph.json) come from the same model and agree on the education x income margins.
    Returns the checks dict; raises ValueError on any mismatch."""
    versions={'inputs':str(x['model_version']),'employment_a':str(d['model_version']),'employment_a_agg':str(agg['model_version']),'graph':str((payload.get('model') or {}).get('model_version','unknown'))}
    if len(set(versions.values()))!=1:raise ValueError(f'model versions differ: {versions}')
    variants={'employment_a':str(d['variant']) if 'variant' in d.files else 'base','employment_a_agg':str(agg['variant']) if 'variant' in agg.files else 'base'}
    if any(v!='base' for v in variants.values()):raise ValueError(f'only the base variant can be published: {variants}')
    areas=d['areas'].tolist()
    if x['areas']!=areas:raise ValueError('sources/output arrays do not match employment_a.npz')
    if agg['codes'].tolist()[0]!='00000':raise ValueError('employment_a_agg.npz must start with the national block')
    # 5-attribute margins: the national aggregated block must reproduce the education x income-component counts of x
    # (built from final_arrays.npz, the same arrays the graph was exported from) and the graph's population per municipality
    nat=agg['blocks'][0].astype(float);B=8*4*20*16;paid=nat[...,:B].reshape(2,13,8,4,20,16).sum((3,4));zero=nat[...,B:B+160].reshape(2,13,8,20).sum(-1)+nat[...,B+160:B+168]+nat[...,B+168:B+176]
    cube=x['cube'].sum(0)   # (2,13,8,17)
    err_paid=float(np.abs(paid-cube[...,1:]).max());err_zero=float(np.abs(zero-cube[...,0]).max())
    g=payload['graph'];ix={a:i for i,a in enumerate(areas)}
    # the browser dataset must carry exactly the leaf municipalities of the model, and its per-municipality arrays
    # (population, income distribution xd, employment rate e, education shares rs, education employment-rate seeds
    # rates, income shapes q) must be the ones derived from the same final_arrays / education inputs as x
    leaf_codes=[m['c'] for m in g['munis'] if m['c'] in ix]
    if set(leaf_codes)!=set(areas) or len(leaf_codes)!=len(areas):raise ValueError(f'graph.json municipalities differ from the model areas: {len(leaf_codes)} vs {len(areas)} (missing: {sorted(set(areas)-set(leaf_codes))[:5]})')
    order=[ix[c] for c in leaf_codes];rows=[i for i,m in enumerate(g['munis']) if m['c'] in ix]
    def dec(key,shape):
        arr=np.frombuffer(base64.b64decode(g[key]),dtype='<f8');return arr.reshape(shape)
    M=len(g['munis']);pops=np.asarray(g['pop'],float)[rows];N=x['N'][order]
    comp=x['cube'][order].sum(3)                                             # (leaf,2,13,17) income components of the 5-attribute model
    paid_counts=comp[...,1:];E=paid_counts.sum(-1)
    xd=dec('xd',(M,2,13,16))[rows];e=dec('e',(M,2,13))[rows];rs=dec('rs',(M,2,13,8))[rows]
    def nz(a):return np.divide(a,a.sum(-1,keepdims=True),out=np.zeros_like(a),where=a.sum(-1,keepdims=True)>0)
    err_pop=float(np.abs(pops-N).max());err_xd=float(np.abs(xd-nz(paid_counts)).max());err_e=float(np.abs(e-np.divide(E,N,out=np.zeros_like(E),where=N>0)).max())
    err_rs=float(np.abs(rs-nz(x['cube'][order].sum(4))).max())
    rates=np.array([g['rates'][c] for c in leaf_codes]);has=(x['inp']['edu_share'][order]*N[...,None])>0   # export_web stores 0 where the education count is 0
    err_rates=float(np.abs(rates-x['inp']['edu_rate'][order])[has].max())
    err_q=float(np.abs(np.asarray(g['q'],float)-np.asarray(x['inp']['edu_q'],float)).max())
    checks={'versions':versions,'variants':variants,'leaf_municipalities':len(leaf_codes),'national_block_vs_inputs_paid_max_error_persons':err_paid,'national_block_vs_inputs_zero_component_max_error_persons':err_zero,'graph_population_vs_inputs_max_error_persons':err_pop,'graph_income_distribution_max_abs_error':err_xd,'graph_employment_rate_max_abs_error':err_e,'graph_education_share_max_abs_error':err_rs,'graph_education_rate_seed_max_abs_error':err_rates,'graph_income_shape_max_abs_error':err_q}
    if max(err_paid,err_zero,err_pop)>tol_persons:raise ValueError(f'aggregated blocks / inputs / graph disagree on the 5-attribute margins: {checks}')
    if max(err_xd,err_e,err_rs,err_rates,err_q)>1e-6:raise ValueError(f'graph.json 5-attribute arrays were not derived from the same inputs as the stage-A recomputation: {checks}')
    return checks

def main():
    payload=json.loads((WEB/'graph.json').read_text(encoding='utf-8'));g=payload['graph']
    d=np.load(OUTPUT/'employment_a.npz');areas=d['areas'].tolist();ix={a:i for i,a in enumerate(areas)}
    agg=np.load(OUTPUT/'employment_a_agg.npz')
    x=bm.load_inputs(SOURCES,OUTPUT)
    checks=check_consistency(payload,d,agg,x)
    M=x['M'];kg=d['status_industry']
    # per-municipality inputs: W1..W5, K6+K7, unemployed share, 20 industry counts (scaled) -> (M,2,13,27)
    inp=np.concatenate([x['W'],x['K6'][...,None],x['u_share'][...,None],x['gm']],-1).astype('<f4')
    assert inp.shape==(M,2,13,27)
    # the web dataset orders municipalities by g['munis'] (leaves + aggregated wards): store leaf index per muni
    leaf_index=[ix.get(m['c'],-1) for m in g['munis']]
    (WEB/'employment_inputs.bin').write_bytes(inp.tobytes())
    ed=WEB/'employment';ed.mkdir(exist_ok=True)
    files={}
    for code,blk in zip(agg['codes'].tolist(),agg['blocks']):
        f=ed/f'agg_{code}.bin';f.write_bytes(np.ascontiguousarray(blk,dtype='<f4').tobytes());files[code]=sha(f)
    emp={'version':str(d['model_version']),'stage':'A','variant':str(d['variant']),'status_codes':bm.K,'labor_codes':bm.J,'industry_codes':['G00']+bm.G,
         'prefs':x['prefs'],'pref_of_muni':[int(x['pref'][i]) if i>=0 else -1 for i in leaf_index],'leaf_index':leaf_index,
         'pk_e':b64f32(x['pk_e']),'pg':b64f32(x['pg']),'tilt':b64f32(x['tilt']),'cp':b64f32(x['cp']),'pu_e':b64f32(x['pu_e']),
         'shapes':{'pk_e':[2,13,8,4],'pg':[len(x['prefs']),2,2,13,4,20],'tilt':[2,4,20,16],'cp':[len(x['prefs']),2,13,4,16],'pu_e':[len(x['prefs']),2,13,8],'inputs':[M,2,13,27],'block':[2,13,bm.BLOCK]},
         'inputs_file':'employment_inputs.bin','inputs_sha256':sha(WEB/'employment_inputs.bin'),'agg_files':{c:f'employment/agg_{c}.bin' for c in files},'agg_sha256':files,
         'block_layout':'paid[8,4,20,16] family[8,20] unemployed[8] inactive[8]','encoding':'float32 little-endian','shrink_kg':bm.SHRINK_KG,'shrink_u':bm.SHRINK_U,
         'tolerance':{'ipf_relative':1e-6,'seed_floor':1e-4,'tilt_clip':[0.05,20.0]}}
    g['emp']=emp;payload['schema_version']=3
    payload['dataset_version']=payload['dataset_version'].split('+')[0]+'+A'
    (WEB/'graph.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    # consistency: national aggregate equals the sum of the pairwise joints
    nat=agg['blocks'][agg['codes'].tolist().index('00000')].astype(float);paid=nat[...,:8*4*20*16].reshape(2,13,8,4,20,16)
    err=float(np.abs(paid.sum((2,4))-d['status_income'].sum(0)).max())
    rep={'passed':err<1.0,'consistency':checks,'schema_version':3,'dataset_version':payload['dataset_version'],'model_version':emp['version'],'inputs_bytes':(WEB/'employment_inputs.bin').stat().st_size,'agg_files':len(files),'agg_bytes_total':sum((ed/f'agg_{c}.bin').stat().st_size for c in files),'graph_bytes':(WEB/'graph.json').stat().st_size,'national_status_income_vs_pairwise_max_error_persons':err}
    (REPORTS/'employment_web_export.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2));print(json.dumps(rep,ensure_ascii=False,indent=1))
    if not rep['passed']:raise SystemExit(1)
if __name__=='__main__':main()
