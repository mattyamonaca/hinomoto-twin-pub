"""Issue #22: how much can the stage-A allocation miss when the unobserved education x status x industry x income
association differs from the transported one?

The estimator only sees three margins per municipality x sex x age: the fixed education x income counts (5-attribute
model), the status counts W and the industry counts. Any association inside the block that is not implied by those
margins comes from the seeds (national P(k|e), prefecture P(g|k), industry income tilt). Here a *true* block is built
from a different generative process (a tilted seed projected onto the same margins), so the estimator sees exactly the
same inputs, and the recovered block is compared with the truth. Baselines: the independent draw (product of the block's
own margins) and the estimator itself under the consistent scenario (must be exact).

Scenarios (all keep the 5-attribute margins, so the published probabilities cannot change; that is measured too):
  consistent        truth = estimator's own generative process (sanity: recovery error 0)
  edu_industry      direct education x industry association (E04/E05 twice as likely in G07/G10/G12/G15, E01/E02 twice
                    as likely in G01/G04/G05/G13) not mediated by status or income
  edu_status_income income shape within a status differs by education (E04/E05 regular workers shifted up, E01/E02 down)
  national_kg       the region's status x industry association is the national one, not the prefecture's
  unknown_informative education-unknown persons are more often non-regular (K2 x2, K1 x0.5)
  random_seed_{n}   log-normal tilts (sd 0.5) on (e,g), (e,k) and (k,g,y) with seed n = 1..3
Areas: all municipalities of Hokkaido (many small towns and wards) and Tokyo (special wards, cities, islands); ages
20-24, 35-39, 50-54, 65-69 by sex. Output: validation/employment_a_synthetic.json (+ docs/experiments copy by the PR).
"""
import json,time,sys
import numpy as np
from paths import SOURCES,OUTPUT,REPORTS
from model_math import AGES,norm
import build_employment as bm

PREFS=['01','13'];AGE_IDX=[1,4,7,10]
E=8;K=4;GN=20;Y=16

def tilts(name,rng):
    te=np.ones((E,GN));tk=np.ones((E,K));ty=np.ones((E,K,Y));tkg=np.ones((K,GN,Y));nat=False
    if name=='edu_industry':
        for e in (3,4):te[e,[6,9,11,14]]=2.
        for e in (0,1):te[e,[0,3,4,12]]=2.
    elif name=='edu_status_income':
        ramp=np.linspace(-1,1,Y)
        for e in (3,4):ty[e,0]=np.exp(0.6*ramp)
        for e in (0,1):ty[e,0]=np.exp(-0.6*ramp)
    elif name=='national_kg':nat=True
    elif name=='unknown_informative':tk[7,1]=2.;tk[7,0]=.5
    elif name.startswith('random_seed'):
        te=np.exp(rng.normal(0,.5,(E,GN)));tk=np.exp(rng.normal(0,.5,(E,K)));tkg=np.exp(rng.normal(0,.5,(K,GN,Y)))
    return te,tk,ty,tkg,nat

def truth_block(x,si,ai,ids,name,rng):
    """Same steps as bm.block() with a tilted seed; the margins are identical to what the estimator uses."""
    te,tk,ty,tkg,nat=tilts(name,rng)
    inp=x['inp'];ids=np.asarray(ids);n=len(ids);pref=x['pref'][ids]
    cube=x['cube'][ids,si,ai];W=x['W'][ids,si,ai];gm=x['gm'][ids,si,ai]
    A=cube[:,:,1:];zero=cube[:,:,0]
    b=bm.block(x,si,ai,ids=ids,variant='national_kg' if nat else 'base')   # family / nonworker split and industry profile unchanged
    fam=b['family'];pgp=x['pg'][pref];pg_grad=pgp[:,si,0,ai];pg_enr=pgp[:,si,1,ai]
    if nat:
        s_=['1','2'][si];pg_grad=np.stack([norm(x['kg_fn']('00000',s_,'0')[ai]+1e-6)]*n);pg_enr=np.stack([norm(x['kg_fn']('00000',s_,'2')[ai]+1e-6)]*n)
    pg_e=np.repeat(pg_grad[:,None],8,1);pg_e[:,5]=pg_enr
    paid_g=np.maximum(gm-fam.sum(1),0);paid_g=norm(paid_g)*W[:,:4].sum(-1)[:,None]
    ry=x['cp'][pref,si,ai][:,:,None,:]*np.clip(x['tilt'][si],0.05,20.)[None]*tkg[None]
    ry=norm(np.maximum(ry,1e-4*ry.max(-1,keepdims=True)))
    pk=np.repeat(x['pk_e'][si,ai][None],n,0)*tk[None]
    seed=A.sum(-1)[:,:,None,None,None]*pk[:,:,:,None,None]*(pg_e*te[None,:,None,:])[:,:,:,:,None]*ry[:,None]*ty[None,:,:,None,:]
    z,it,err=bm.ipf3(seed,A,W[:,:4],paid_g)
    return z,b,err

def metrics(zt,zh):
    """Per area: TV of the joint, of P(g|e), P(y|e,k,g) (weighted by truth), abs error of P(y>=500|e,k,g)."""
    out={}
    tt=zt.sum((1,2,3,4));tt=np.maximum(tt,1e-12)
    pt=zt/tt[:,None,None,None,None];ph=zh/np.maximum(zh.sum((1,2,3,4)),1e-12)[:,None,None,None,None]
    out['tv_joint']=.5*np.abs(pt-ph).sum((1,2,3,4))
    ge_t=zt.sum((2,4));ge_h=zh.sum((2,4));pe=ge_t.sum(-1)/tt[:,None]
    out['tv_industry_given_edu']=(pe*.5*np.abs(norm(ge_t)-norm(ge_h)).sum(-1)).sum(-1)
    ke_t=zt.sum((3,4));ke_h=zh.sum((3,4))
    out['tv_status_given_edu']=(pe*.5*np.abs(norm(ke_t)-norm(ke_h)).sum(-1)).sum(-1)
    wt=zt.sum(-1)/tt[:,None,None,None]
    out['tv_income_given_ekg']=(wt*.5*np.abs(norm(zt)-norm(zh)).sum(-1)).sum((1,2,3))
    out['abs_err_p500_given_ekg']=(wt*np.abs(norm(zt)[...,8:].sum(-1)-norm(zh)[...,8:].sum(-1))).sum((1,2,3))
    # published 5-attribute margin (e,y): must be identical
    out['max_abs_edu_income_margin_persons']=np.abs(zt.sum((2,3))-zh.sum((2,3))).max((1,2))
    return out

def independent(z):
    A=z.sum((2,3))/np.maximum(z.sum((1,2,3,4)),1e-12)[:,None,None]
    B=z.sum((1,3,4))/np.maximum(z.sum((1,2,3,4)),1e-12)[:,None];C=z.sum((1,2,4))/np.maximum(z.sum((1,2,3,4)),1e-12)[:,None]
    return A[:,:,None,None,:]*B[:,None,:,None,None]*C[:,None,None,:,None]*z.sum((1,2,3,4))[:,None,None,None,None]

def summarize(vals,weights):
    v=np.asarray(vals);w=np.asarray(weights);ok=w>0
    return {'weighted_mean':float(np.average(v[ok],weights=w[ok])),'equal_area_mean':float(v[ok].mean()),'median':float(np.median(v[ok])),'p90':float(np.quantile(v[ok],.9)),'max':float(v[ok].max())}

def main():
    t0=time.time();x=bm.load_inputs(SOURCES,OUTPUT);areas=x['areas']
    ids=[i for i,a in enumerate(areas) if a[:2] in PREFS];rng0=np.random.default_rng(0)
    names=['consistent','edu_industry','edu_status_income','national_kg','unknown_informative','random_seed_1','random_seed_2','random_seed_3']
    res={'areas':len(ids),'prefectures':PREFS,'ages':[AGES[a] for a in AGE_IDX],'cells':len(ids)*2*len(AGE_IDX),'scenarios':{},'pre_registered':{'question':'recovery of P(k,g,y|e) inside the block when the true association differs from the transported seed; published (e,y) margins must be preserved exactly','baselines':['independent draw: product of the block margins','estimator under the consistent scenario'],'reading':'a scenario TV is the size of the unverifiable error for that kind of departure; it is not an estimate of the actual error, which cannot be measured without municipal cross tables'}}
    for name in names:
        rng=np.random.default_rng(int(name[-1]) if name.startswith('random') else 0)
        acc={};w=[];margin=[]
        for si in range(2):
            for ai in AGE_IDX:
                zt,b_est_nat,err=truth_block(x,si,ai,ids,name,rng)
                zh=bm.block(x,si,ai,ids=ids)['paid']
                zi=independent(zt)
                m_est=metrics(zt,zh);m_ind=metrics(zt,zi)
                for k,v in m_est.items():acc.setdefault(k,[]).extend(v.tolist())
                for k,v in m_ind.items():acc.setdefault('independent_'+k,[]).extend(v.tolist())
                w.extend(zt.sum((1,2,3,4)).tolist())
        sc={k:summarize(v,w) for k,v in acc.items() if not k.endswith('margin_persons')}
        sc['max_abs_edu_income_margin_persons']=float(np.max(acc['max_abs_edu_income_margin_persons']))
        res['scenarios'][name]=sc
        print(name,'tv_joint',round(sc['tv_joint']['weighted_mean'],4),'indep',round(sc['independent_tv_joint']['weighted_mean'],4),'p500 err',round(sc['abs_err_p500_given_ekg']['weighted_mean'],4),'margin',sc['max_abs_edu_income_margin_persons'],f'{time.time()-t0:.0f}s',flush=True)
    res['elapsed_seconds']=round(time.time()-t0,1)
    (REPORTS/'employment_a_synthetic.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
