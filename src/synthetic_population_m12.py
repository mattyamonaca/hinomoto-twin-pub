"""Virtual populations with education AND industry: recovery of M0 / M1 / M2 / M12 on the same denominator (Issue #21).

Extends synthetic_population.py (M0/M1 only). Each world has a known P(status, education, industry, income | area, sex, age)
and is observed only through tables of the granularity that exists for Japan:
  census population / employed / status totals per area, prefecture age x status seeds, the sampled income survey
  (prefecture, national, largest cities), a tax proxy, census education counts, prefecture education x labour tables,
  census 6-3 (area x sex x age x industry, full count, with an "unclassifiable" class) and ESS table 24
  (national sex x industry x income of paid workers, no age, survey-sampled).
The generating processes deliberately include mechanisms the estimators do not model: an education x industry
interaction on income (the multiplicative tilt assumes none), industry effects that change with age (table 24 has no
age) or with the region (national shapes are transplanted), informative unknowns, very small areas with empty cells,
and a world where industry has no direct income effect. Recovery is measured against the hidden truth on ALL areas
with the same denominator for every model. Results describe recovery under the stated generating conditions only.
Outputs: validation/synthetic_recovery_m12.json, synthetic_recovery_m12.csv (one row per scenario x seed x model).
"""
import json,time
import numpy as np
import pandas as pd
from paths import REPORTS
from model_math import norm
import estimator as es
from synthetic_population import EDGES

G=7                                # 6 industry groups + unclassifiable (index 6), stands in for JSIC A-T + 分類不能
IND_EFFECT=np.array([-.35,.05,-.05,-.30,.40,.10,0.])      # log-income effect: primary, manufacturing, construction/transport, retail/personal services, finance/IT/professional, public/education/medical, unknown
IND_AGE=np.array([.05,.15,.05,-.10,.25,.20,0.])            # optional age gradient of the industry effect (per 6 age bands)
EDU_EFFECT=np.array([-.25,-.05,.05,.25,.45,-.3,-.35,0.])
STAT_EFFECT=np.array([.15,-.55,.45,-.1,-2.5])
SCENARIOS={
 'base_constant_effects':{},
 'regional_varying_associations':{'theta_sd':.35,'phi_sd':.35},
 'education_industry_interaction':{'interaction':.25},
 'industry_effect_age_dependent':{'age_gradient':1.},
 'industry_effect_regional':{'regional_ind_sd':.2},
 'informative_unknowns':{'unknown_corr':.8,'unknown_ind_corr':.8},
 'sparse_small_areas':{'pop_log_mean':np.log(2500),'pop_min':300,'pop_max':20000},
 'no_direct_industry_effect':{'ind_scale':0.},
 'no_direct_education_effect':{'theta_scale':0.},
 'all_violations_weak_tax_proxy':{'theta_sd':.35,'phi_sd':.35,'interaction':.25,'age_gradient':1.,'regional_ind_sd':.2,'unknown_corr':.8,'unknown_ind_corr':.8,'tax_noise':.3},
}

def erf(x):
 """Vectorised erf (Abramowitz-Stegun 7.1.26, |error| < 1.5e-7); scipy is not a dependency."""
 s=np.sign(x);x=np.abs(x);t=1/(1+0.3275911*x)
 y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*np.exp(-x*x)
 return s*y

def bin_probs_array(mu,sigma=.55):
 """Log-normal income (yen) into the 16 classes for an array of mu; returns mu.shape + (16,)."""
 e=np.log(np.maximum(EDGES,1))
 c=0.5*(1+erf((e-mu[...,None])/(sigma*np.sqrt(2))));c[...,0]=0;c[...,-1]=1
 return np.diff(c,axis=-1)

def generate(seed,theta_sd=0.,phi_sd=0.,interaction=0.,age_gradient=0.,regional_ind_sd=0.,unknown_corr=0.,unknown_ind_corr=0.,theta_scale=1.,ind_scale=1.,delta_urban=.18,tax_noise=.05,pop_log_mean=np.log(30000),pop_min=1500,pop_max=400000,P=6,K=20,survey_rate=0.02):
 rng=np.random.default_rng(seed);M=P*K;pref=np.repeat(np.arange(P),K)
 pop_total=np.exp(rng.normal(pop_log_mean,1.0,M)).clip(pop_min,pop_max)
 age_base=norm(np.array([5,6,6,6,7,8,9,8,7,7,8,8,15.]))
 urban=rng.normal(0,1,M)
 delta=delta_urban*urban+rng.normal(0,0.08,M)
 theta=np.clip(1+rng.normal(0,theta_sd,M),0.2,2.2)*theta_scale       # local strength of the education-income association
 phi=np.clip(1+rng.normal(0,phi_sd,M),0.2,2.2)*ind_scale             # local strength of the industry-income association
 inter=rng.normal(0,1,(8,G))*interaction;inter[:,6]=0;inter[6:]=0      # education x industry interaction (fixed per world)
 reg_ind=rng.normal(0,regional_ind_sd,(M,G));reg_ind[:,6]=0          # regional industry effects (national shape transfer violated)
 a_idx=np.arange(13);s_idx=np.arange(2)
 # population and education composition (as synthetic_population.generate)
 age_shift=norm(age_base[None]*np.exp(-0.15*urban[:,None]*a_idx[None]/12+0.3*urban[:,None]*(a_idx[None]<6)))   # (M,13)
 N=np.round(pop_total[:,None,None]*np.array([0.48,0.52])[None,:,None]*age_shift[:,None,:])
 young=1-a_idx/12
 base=np.stack([0.10-0.06*young,0.42-0.1*young,0.13+0.05*young,np.zeros(13),np.zeros(13),np.zeros(13),np.full(13,.01),np.zeros(13)],-1)   # (13,8)
 base=np.repeat(base[None],M,0)
 base[:,:,3]=0.22+0.12*young[None]*(1+0.5*urban[:,None]);base[:,:,4]=0.04+0.03*young[None]*(1+0.5*urban[:,None])
 base=np.maximum(base,0.005);base[:,:,5]=np.where(a_idx==0,0.55,np.where(a_idx==1,0.12,0.005))[None]
 unk=1/(1+np.exp(-(-2.2+0.6*urban[:,None,None]+rng.normal(0,.3,(M,2,13)))))
 edu_p=np.zeros((M,2,13,8));edu_p[...,:7]=norm(base[:,None,:,:7])*(1-unk[...,None]);edu_p[...,7]=unk
 # employment and status by education (paid + family); remainder are nonworkers
 e_idx=np.arange(8)
 emp=1/(1+np.exp(-(0.4+0.5*np.isin(e_idx,[3,4])[None,None,None]-0.6*(e_idx==5)[None,None,None]-1.2*(a_idx>=11)[None,None,:,None]-0.8*(a_idx==0)[None,None,:,None]+0.3*urban[:,None,None,None]*0.2-0.35*s_idx[None,:,None,None])))
 st=np.stack([np.broadcast_to(0.55+0.15*np.isin(e_idx,[3,4])[None]-0.3*s_idx[:,None],(2,8)),np.broadcast_to(0.25+0.25*s_idx[:,None]+0.1*(e_idx==5)[None],(2,8)),np.broadcast_to(0.05+0.06*(e_idx==4)[None],(2,8)),np.full((2,8),.10),np.full((2,8),.05)],-1)   # (2,8,5)
 st=norm(np.maximum(st,0.01))
 status_p=st[None,:,None,:,:]*emp[...,None]           # (M,2,13,8,5)
 # industry given education, status and area: high-education toward group 4/5, self-employed toward 0/3, urban toward 4, rural toward 0
 ind_base=np.array([[.20,.20,.15,.25,.05,.15],[.12,.24,.16,.24,.08,.16],[.08,.24,.14,.22,.14,.18],[.04,.18,.10,.18,.28,.22],[.02,.12,.06,.12,.40,.28],[.10,.20,.12,.30,.10,.18],[.15,.20,.15,.30,.05,.15],[.10,.20,.14,.24,.14,.18]])   # (8,6)
 prof=rng.dirichlet(np.full(6,20.),M)*6                # random regional industry profile (multiplicative)
 urb=np.exp(np.outer(urban,np.array([-.6,0.,-.1,.1,.5,.1])))
 ind_known=ind_base[None,:,:]*prof[:,None,:]*urb[:,None,:]      # (M,8,6)
 stat_shift=np.array([[1,1,1,1,1,1],[1,.9,1,1.3,.8,1.1],[.8,1.2,1,1,1.4,.7],[2.5,.6,1.2,1.6,.9,.4],[4.,.5,.8,1.5,.3,.3]])   # (5,6)
 ind_unk=1/(1+np.exp(-(-3.5+0.4*urban)))                  # unclassifiable share per area (1-10%)
 ind_p=np.zeros((M,2,13,8,5,G))
 known=norm(ind_known[:,None,None,:,None,:]*stat_shift[None,None,None,None,:,:])   # (M,1,1,8,5,6)
 ind_p[...,:6]=known*(1-ind_unk[:,None,None,None,None,None]);ind_p[...,6]=ind_unk[:,None,None,None,None]
 ind_p=np.broadcast_to(ind_p,(M,2,13,8,5,G)).copy()
 # income: mu(m,s,a,e,g,k)
 mu=(np.log(3.0e6)+0.25*np.sin((a_idx-4)/4))[None,None,:,None,None,None]-0.35*s_idx[None,:,None,None,None,None]+STAT_EFFECT[None,None,None,None,None,:]\
  +theta[:,None,None,None,None,None]*EDU_EFFECT[None,None,None,:,None,None]\
  +phi[:,None,None,None,None,None]*(IND_EFFECT[None,None,None,None,:,None]+age_gradient*IND_AGE[None,None,None,None,:,None]*((a_idx-6)/6)[None,None,:,None,None,None]+reg_ind[:,None,None,None,:,None])\
  +inter[None,None,None,:,:,None]+delta[:,None,None,None,None,None]
 mu=np.broadcast_to(mu,(M,2,13,8,G,5)).copy()
 inc_p=bin_probs_array(mu)                              # (M,2,13,8,G,5,16)
 # unknown industry: mixture of the area's known industries (optionally tilted to low income); unknown education: mixture of known educations
 w_g=norm(ind_p[...,:6]*np.exp(-unknown_ind_corr*IND_EFFECT[:6]*3))            # (M,2,13,8,5,6)
 inc_p[...,6,:,:]=np.einsum('msaekg,msaegky->msaeky',w_g,inc_p[...,:6,:,:])
 w_e=norm(edu_p[...,:7]*np.exp(-unknown_corr*EDU_EFFECT[:7]*3))                # (M,2,13,7)
 inc_p[...,7,:,:,:]=np.einsum('msae,msaegky->msagky',w_e,inc_p[...,:7,:,:,:])
 status_p[...,7,:]=np.einsum('msae,msaek->msak',w_e,status_p[...,:7,:])
 ind_p[...,7,:,:]=np.einsum('msae,msaekg->msakg',w_e,ind_p[...,:7,:,:])
 # truth counts T(m,s,a,e,g,k,17): paid statuses have income classes 1..16, family workers and nonworkers are class 0
 T=np.zeros((M,2,13,8,G,5,17))
 ne=N[...,None]*edu_p                                    # (M,2,13,8)
 nk=ne[...,None]*status_p                                # (M,2,13,8,5)
 nkg=nk[...,None]*ind_p                                  # (M,2,13,8,5,G)
 nkg=np.transpose(nkg,(0,1,2,3,5,4))                     # (M,2,13,8,G,5)
 T[...,:4,1:]=nkg[...,:4,None]*inc_p[...,:4,:]
 T[...,4,0]=nkg[...,4]
 nonwork=ne-nk.sum(-1)                                   # nonworkers: put in status 0 / industry 6 / class 0 as in synthetic_population (status "regular" slot, income class 0)
 T[...,6,0,0]+=nonwork
 return {'P':P,'K':K,'M':M,'pref':pref,'N':N,'edu_p':edu_p,'T':T,'delta':delta,'theta':theta,'phi':phi,'urban':urban,'rng':rng,'survey_rate':survey_rate,'tax_noise':tax_noise,'pop_total':pop_total}

def truth_income(world):
 T=world['T'];paid=T[...,:4,1:].sum(5)                   # (M,2,13,8,G,16)
 by_e=norm(paid.sum(4));by_sa=norm(paid.sum((3,4)))
 return {'paid_by_edu':by_e,'paid_by_sa':by_sa,'R':T.sum((4,5,6))}

def observe(world):
 """Tables at the granularity available in Japan; includes census 6-3 and ESS table 24 for M2."""
 rng=world['rng'];T=world['T'];N=world['N'];M=world['M'];P=world['P'];pref=world['pref'];rate=world['survey_rate']
 Te=T.sum(4)                                             # (M,2,13,8,5,17) without industry
 Eraw=Te[...,:4,1:].sum((3,4,5))+Te[...,4,0].sum(3)
 t_status=np.zeros((M,2,5));age_status=np.zeros((M,2,13,5))
 for k in range(4):t_status[...,k]=Te[...,k,1:].sum((2,3,4));age_status[...,k]=Te[...,k,1:].sum((3,4))
 t_status[...,4]=Te[...,4,0].sum((2,3));age_status[...,4]=Te[...,4,0].sum(3)
 seed_q=np.zeros((M,2,13,5));pref_rate=np.zeros((P,2,13))
 for p in range(P):
  ids=pref==p;pq=age_status[ids].sum(0);seed_q[ids]=pq[None];pref_rate[p]=Eraw[ids].sum(0)/np.maximum(N[ids].sum(0),1)
 def survey(counts):return rng.poisson(counts*rate)/rate
 paid=Te[...,:4,1:]                                      # (M,2,13,8,4,16)
 samp=survey(paid)
 ess_cat=np.zeros((P,2,13,4,16));pref_target=np.zeros((P,2,13,16))
 for p in range(P):
  c=samp[pref==p].sum((0,3));ess_cat[p]=c;pref_target[p]=norm(c.sum(2))
 nat_cat=ess_cat.sum(0)
 nat_edu=samp.sum((0,4));ref=norm(nat_edu.sum(2)+1e-8)[:,:,None,:];edu_q=norm(nat_edu+1000*ref)
 edu_q[:,:,6]=edu_q[:,:,7]=norm(nat_edu.sum(2)+1000*ref[:,:,0])
 tax=np.clip(world['delta']-np.array([world['delta'][pref==p].mean() for p in pref])+rng.normal(0,world['tax_noise'],M),-.5,.5)
 edu_share=norm(Te.sum((4,5)))
 edu_rate=np.zeros((M,2,13,8))
 for p in range(P):
  ids=pref==p;emp=(Te[ids][...,:4,1:].sum((4,5))+Te[ids][...,4,0]).sum(0);tot=Te[ids].sum((4,5)).sum(0)
  edu_rate[ids]=((emp+100*(emp.sum(-1,keepdims=True)/np.maximum(tot.sum(-1,keepdims=True),1)))/(tot+100))[None]
 # --- M2 tables. census 6-3: employed persons (paid + family) by area x sex x age x industry, full count
 emp_g=T[...,:4,1:].sum((3,5,6))+T[...,4,0].sum(3)      # (M,2,13,G)
 tot=emp_g.sum(-1,keepdims=True);ind_share=np.divide(emp_g,tot,out=np.zeros_like(emp_g),where=tot>0)
 pcnt=np.zeros((P,2,13,G))
 for p in range(P):pcnt[p]=emp_g[pref==p].sum(0)
 empty=tot[...,0]==0;ind_share[empty]=norm(pcnt)[pref][empty]
 # ESS table 24: national sex x industry x income of paid workers, no age, survey-sampled; smoothed toward the all-industry shape
 samp_g=survey(T[...,:4,1:]).sum((0,2,3,5))            # (2,G,16)
 ref_g=norm(samp_g.sum(1)+1e-8)[:,None,:];ind_q=np.repeat(norm(samp_g+1000*ref_g)[:,None,:,:],13,1)   # (2,13,G,16)
 # held-out "cities": 3 largest municipalities per prefecture, survey tables by age
 ids=[];age=[];obs=[];weight=[];hp=[];codes=[]
 for p in range(P):
  big=np.where(pref==p)[0][np.argsort(-N[pref==p].sum((1,2)))[:3]]
  for m in big:
   for a in range(13):
    o=samp[m,:,a].sum((0,1,2));t=o.sum()
    if t<1000:continue
    ids.append([int(m)]);age.append(a);obs.append(norm(o));weight.append(t);hp.append(p);codes.append(f'{p:02}{m:03}')
 heldout={'ids':ids,'age':np.array(age),'obs':np.array(obs),'weight':np.array(weight),'pref':np.array(hp),'codes':codes}
 return {'areas':[f'{p:02}{m:03}' for m,p in enumerate(pref)],'pref':pref,'N':N,'Nraw':N.copy(),'Eraw':Eraw,'seed_q':seed_q,'t_status':t_status,'pref_rate':pref_rate,'ess_cat':ess_cat,'nat_cat':nat_cat,'pref_target':pref_target,'tax_feature':tax,'edu_share':edu_share,'edu_q':edu_q,'edu_reference':ref[:,:,0],'edu_rate':edu_rate,'heldout':heldout,'ind_share':ind_share,'ind_q':ind_q}

THRESH={'ge300':6,'ge500':8,'ge700':10}               # class index from which the cumulative share is taken (edges 300/500/700万円)
MODELS={'M0':lambda k:k[0]==0. and k[1]==0.,'M1':lambda k:k[1]==0.,'M2':lambda k:k[0]==0.,'M12':lambda k:True}

def recovery_metrics(pred,truth,weights,areas_pop=None,pref=None):
 """Same-denominator metrics for one model: pred/truth (M,2,13,16) shares, weights (M,2,13) paid workers."""
 ok=weights>0;tv=.5*np.abs(pred-truth).sum(-1)
 area_tv=np.array([np.average(tv[m][ok[m]],weights=weights[m][ok[m]]) if ok[m].any() else np.nan for m in range(len(tv))])
 out={'tv_weighted':float(np.average(tv[ok],weights=weights[ok])),'tv_equal_area_mean':float(np.nanmean(area_tv)),'tv_median':float(np.median(tv[ok])),'tv_p90':float(np.quantile(tv[ok],.9)),'tv_max':float(tv[ok].max())}
 for name,i in THRESH.items():
  err=np.abs(pred[...,i:].sum(-1)-truth[...,i:].sum(-1));out['abs_error_share_'+name]=float(np.average(err[ok],weights=weights[ok]))
 if areas_pop is not None:
  small=areas_pop<8000;out['tv_small_areas_equal_mean']=float(np.nanmean(area_tv[small])) if small.any() else None;out['tv_large_areas_equal_mean']=float(np.nanmean(area_tv[~small])) if (~small).any() else None
 return out,area_tv

def evaluate(inp,world,gammas=(0.,1.,2.,3.,4.,6.),gammas_ind=(0.,1.,2.,3.,4.),betas=(0.,.5,1.,2.,3.)):
 truth=truth_income(world);N=inp['N'];R=truth['R']
 W=es.fit_status(inp);cp=es.status_income_shapes(inp);h=inp['heldout'];w=h['weight']
 res={}
 for g in gammas:
  te=es.education_tilt(inp,g)
  for gi in gammas_ind:
   ti=es.industry_tilt(inp,gi) if gi else None;tilt=te if ti is None else (ti if te is None else te*ti)
   q,E=es.mixture(inp,W,cp,tilt);Xb=es.calibrate(inp,q,E)
   for b in betas:
    Xt=es.tax_project(inp,Xb,E,b);m=es.city_metrics(inp,Xt);res[(g,gi,b)]=(Xt,E,float(np.average(m['loss'],weights=w)))
 out={};area={}
 for name,allowed in MODELS.items():
  k=min([k for k in res if allowed(k)],key=lambda k:res[k][2]);Xt,E,_=res[k]
  met,area_tv=recovery_metrics(norm(Xt),truth['paid_by_sa'],E,world['pop_total'])
  Z=N-E;cbs=np.concatenate([Z[...,None],Xt],-1);ecounts=es.allocate_education(inp,cbs)
  tsum=world['T'].sum((4,5));full_truth=norm(np.concatenate([tsum[...,:2].sum(-1,keepdims=True),tsum[...,2:]],-1))
  tv_e=.5*np.abs(norm(ecounts)-full_truth).sum(-1);oke=R>0
  met['tv_income_given_area_sex_age_edu_weighted']=float(np.average(tv_e[oke],weights=R[oke]))
  met.update({'gamma_edu':k[0],'gamma_ind':k[1],'beta':k[2]});out[name]=met;area[name]=area_tv
 for name in ('M1','M2','M12'):
  d=area[name]-area['M0'];out[name]['area_tv_change_vs_M0_max_worsening']=float(np.nanmax(d));out[name]['fraction_areas_improved_vs_M0']=float(np.nanmean(d<0))
 d=area['M12']-area['M1'];out['M12']['area_tv_change_vs_M1_max_worsening']=float(np.nanmax(d));out['M12']['fraction_areas_improved_vs_M1']=float(np.nanmean(d<0))
 return out

def main(seeds=(1,2,3,4,5),scenarios=None):
 t0=time.time();rows=[];summary={'protocol':__doc__,'seeds':list(seeds),'grid':{'gamma_edu':[0.,1.,2.,3.,4.,6.],'gamma_ind':[0.,1.,2.,3.,4.],'beta':[0.,.5,1.,2.,3.]},'selection':'population-weighted cross entropy on the 3 largest municipalities per prefecture (as the 86-city selection); evaluation on all municipalities x sex x age against the hidden truth, weighted by paid workers (same denominator for every model)','scenarios':{}}
 for sc,cfg in (scenarios or SCENARIOS).items():
  per=[]
  for seed in seeds:
   world=generate(seed,**cfg);inp=observe(world);r=evaluate(inp,world);per.append(r)
   for name in r:rows.append(dict(scenario=sc,seed=seed,model=name,**r[name]))
   print(sc,seed,{n:round(r[n]['tv_weighted'],4) for n in r},f'{time.time()-t0:.0f}s',flush=True)
  agg={}
  for name in MODELS:
   agg[name]={k:float(np.mean([p[name][k] for p in per])) for k in per[0][name] if k not in ('gamma_edu','gamma_ind','beta') and per[0][name][k] is not None}
   agg[name]['selected']=[[p[name]['gamma_edu'],p[name]['gamma_ind'],p[name]['beta']] for p in per]
  for name in ('M1','M2','M12'):
   diff=[p[name]['tv_weighted']-p['M0']['tv_weighted'] for p in per];agg[name+'_minus_M0_tv_weighted']=float(np.mean(diff));agg[name+'_minus_M0_seed_range']=[float(min(diff)),float(max(diff))]
  diff=[p['M12']['tv_weighted']-p['M1']['tv_weighted'] for p in per];agg['M12_minus_M1_tv_weighted']=float(np.mean(diff));agg['M12_minus_M1_seed_range']=[float(min(diff)),float(max(diff))]
  summary['scenarios'][sc]=dict(config={k:(float(v) if isinstance(v,(int,float,np.floating)) else v) for k,v in cfg.items()},**agg)
 summary['elapsed_seconds']=round(time.time()-t0,1)
 (REPORTS/'synthetic_recovery_m12.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 pd.DataFrame(rows).to_csv(REPORTS/'synthetic_recovery_m12.csv',index=False)
 print(json.dumps({k:{n:round(v[n]['tv_weighted'],4) for n in MODELS} for k,v in summary['scenarios'].items()},indent=1))
 return summary
if __name__=='__main__':main()
