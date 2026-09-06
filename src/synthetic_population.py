"""Virtual populations with a known joint distribution, observed only through tables of the real granularity.

For each scenario and seed a synthetic country (P prefectures x K municipalities) is generated with a known
P(status, education, income | area, sex, age). Only tables that exist for Japan are handed to the estimators:
census population, employment and status totals per area, prefecture age x status seeds, a sampled income
survey at prefecture / national / largest-city level, a tax proxy, census education counts per area and
prefecture-level education x labour tables. M0 and M1 are then run through `estimator.py` and compared with
the hidden truth. Results describe recovery under the stated generating conditions, not Japanese accuracy.
Outputs: validation/synthetic_recovery.json, synthetic_recovery.csv.
"""
import json,itertools
import numpy as np
import pandas as pd
from paths import REPORTS
from model_math import norm
import estimator as es

EDGES=np.array([0,50,100,150,200,250,300,400,500,600,700,800,900,1000,1250,1500,1e9])*1e4
STAT=['regular','nonregular','executive','self','family']
SCENARIOS={
 'assoc_constant_unknown_random':{'theta_sd':0.,'unknown_corr':0.},
 'assoc_varying_unknown_random':{'theta_sd':.35,'unknown_corr':0.},
 'assoc_constant_unknown_correlated':{'theta_sd':0.,'unknown_corr':.8},
 'assoc_varying_unknown_correlated':{'theta_sd':.35,'unknown_corr':.8},
 'no_association':{'theta_sd':0.,'unknown_corr':0.,'theta_scale':0.},
 'no_association_income_independent_of_urbanity':{'theta_sd':0.,'unknown_corr':0.,'theta_scale':0.,'delta_urban':0.},
 'assoc_constant_weak_tax_proxy':{'theta_sd':0.,'unknown_corr':0.,'tax_noise':.3},
 'assoc_varying_unknown_correlated_weak_tax_proxy':{'theta_sd':.35,'unknown_corr':.8,'tax_noise':.3},
 'no_association_weak_tax_proxy':{'theta_sd':0.,'unknown_corr':0.,'theta_scale':0.,'tax_noise':.3},
}

def bin_probs(mu,sigma):
 """Log-normal income (yen) into the 16 published classes."""
 from math import erf
 cdf=lambda x:0.5*(1+erf((np.log(np.maximum(x,1))-mu)/(sigma*np.sqrt(2))))
 c=np.array([cdf(e) for e in EDGES]);c[0]=0;c[-1]=1;return np.diff(c)

def generate(seed,theta_sd,unknown_corr,theta_scale=1.,delta_urban=.18,tax_noise=.05,P=6,K=20,survey_rate=0.02):
 rng=np.random.default_rng(seed);M=P*K;pref=np.repeat(np.arange(P),K)
 pop_total=np.exp(rng.normal(np.log(30000),1.0,M)).clip(1500,400000)
 age_base=norm(np.array([5,6,6,6,7,8,9,8,7,7,8,8,15.]))
 urban=rng.normal(0,1,M)                               # latent urbanity: education, income level, tax proxy
 delta=delta_urban*urban+rng.normal(0,0.08,M)          # municipal income level (log scale)
 theta=np.clip(1+rng.normal(0,theta_sd,M),0.2,2.2)*theta_scale      # local strength of education-income association (0 = none)
 N=np.zeros((M,2,13));edu_p=np.zeros((M,2,13,8));status_p=np.zeros((M,2,13,8,5));inc_p=np.zeros((M,2,13,8,5,16))
 edu_effect=np.array([-.25,-.05,.05,.25,.45,-.3,-.35,0.])   # log-income effect by education (E08 unknown = mixture)
 stat_effect=np.array([.15,-.55,.45,-.1,-2.5])
 for m in range(M):
  age_shift=norm(age_base*np.exp(-0.15*urban[m]*np.arange(13)/12+0.3*urban[m]*(np.arange(13)<6)))
  for s in range(2):
   N[m,s]=np.round(pop_total[m]*(0.48 if s==0 else 0.52)*age_shift)
   for a in range(13):
    young=1-a/12
    base=np.array([0.10-0.06*young,0.42-0.1*young,0.13+0.05*young,0.22+0.12*young*(1+0.5*urban[m]),0.04+0.03*young*(1+0.5*urban[m]),0.,0.01,0.])
    base=np.maximum(base,0.005);base[5]=0.55 if a==0 else (0.12 if a==1 else 0.005)
    unk=1/(1+np.exp(-(-2.2+0.6*urban[m]+rng.normal(0,.3))))     # unknown share varies by municipality (2%-40%)
    pe=norm(base)*(1-unk);pe[7]=unk;edu_p[m,s,a]=pe
    for e in range(8):
     emp=1/(1+np.exp(-(0.4+0.5*(1 if e in (3,4) else 0)-0.6*(1 if e==5 else 0)-1.2*(a>=11)-0.8*(a==0)+0.3*urban[m]*0.2-0.35*s)))
     st=np.array([0.55+0.15*(e in (3,4))-0.3*s,0.25+0.25*s+0.1*(e==5),0.05+0.06*(e==4),0.10,0.05]);st=norm(np.maximum(st,0.01))
     status_p[m,s,a,e]=st*emp   # paid + unpaid family workers; remainder are nonworkers
     for k in range(5):
      mu=np.log(3.0e6)+0.25*np.sin((a-4)/4)-0.35*s+stat_effect[k]+theta[m]*edu_effect[e]+delta[m]
      inc_p[m,s,a,e,k]=bin_probs(mu,0.55)
 # unknown-education persons: income like a mixture of the true education mix, optionally correlated with low income
 for m in range(M):
  for s in range(2):
   for a in range(13):
    mix=norm(edu_p[m,s,a,:7]);w=mix*np.exp(-unknown_corr*edu_effect[:7]*3);w=norm(w)
    inc_p[m,s,a,7]=np.einsum('e,eky->ky',w,inc_p[m,s,a,:7]);status_p[m,s,a,7]=np.einsum('e,ek->k',w,status_p[m,s,a,:7])
 # truth: counts per (m,s,a,e,k,y) with nonworkers as a 17th income component 0
 T=np.zeros((M,2,13,8,5,17))
 for m in range(M):
  for s in range(2):
   for a in range(13):
    n=N[m,s,a]
    for e in range(8):
     ne=n*edu_p[m,s,a,e];worker=status_p[m,s,a,e]
     for k in range(5):
      nk=ne*worker[k]
      if k==4:T[m,s,a,e,k,0]=nk           # unpaid family workers: no main-job income (modelled as 0)
      else:T[m,s,a,e,k,1:]=nk*inc_p[m,s,a,e,k]
    # nonworkers
    T[m,s,a,:,0,0]+=n*edu_p[m,s,a]*(1-status_p[m,s,a].sum(-1))   # store nonworkers in status slot 0 income 0 (used only via totals)
 return {'P':P,'K':K,'M':M,'pref':pref,'N':N,'edu_p':edu_p,'status_p':status_p,'inc_p':inc_p,'T':T,'delta':delta,'theta':theta,'urban':urban,'rng':rng,'survey_rate':survey_rate,'tax_noise':tax_noise}

def truth_income(world):
 """Hidden targets: paid-worker income shares P(y|m,s,a) and P(y|m,s,a,e) (16 classes) and full distributions incl. nonworkers."""
 T=world['T'];paid=T[...,:4,1:].sum(3)           # (M,2,13,8,16)
 by_e=norm(paid);by_sa=norm(paid.sum(3))
 return {'paid_by_edu':by_e,'paid_by_sa':by_sa,'R':T.sum((4,5))}

def observe(world):
 """Tables at the granularity actually available in Japan."""
 rng=world['rng'];T=world['T'];N=world['N'];M=world['M'];P=world['P'];pref=world['pref'];rate=world['survey_rate']
 Eraw=T[...,:4,1:].sum((3,4,5))+T[...,4,0].sum(3)   # employed = paid workers + unpaid family workers
 t_status=np.zeros((M,2,5))
 for k in range(4):t_status[...,k]=T[...,k,1:].sum((2,3,4))
 t_status[...,4]=T[...,4,0].sum((2,3))
 age_status=np.zeros((M,2,13,5))
 for k in range(4):age_status[...,k]=T[...,k,1:].sum((3,4))
 age_status[...,4]=T[...,4,0].sum(3)
 seed_q=np.zeros((M,2,13,5));pref_rate=np.zeros((P,2,13))
 for p in range(P):
  ids=pref==p;pq=age_status[ids].sum(0);seed_q[ids]=pq[None];pref_rate[p]=Eraw[ids].sum(0)/np.maximum(N[ids].sum(0),1)
 # income survey: sample persons at survey_rate, expand back
 def survey(counts):return rng.poisson(counts*rate)/rate
 paid=T[...,:4,1:]                                     # (M,2,13,8,4,16) known income (all paid workers report)
 samp=survey(paid)
 ess_cat=np.zeros((P,2,13,4,16));pref_target=np.zeros((P,2,13,16))
 for p in range(P):
  c=samp[pref==p].sum((0,3))   # (2,13,4,16)
  ess_cat[p]=c;pref_target[p]=norm(c.sum(2))
 nat_cat=ess_cat.sum(0)
 nat_edu=samp.sum((0,4));edu_q=norm(nat_edu+1000*norm(nat_edu.sum(2)+1e-8)[:,:,None,:])   # (2,13,8,16) smoothed as in build_education
 tax=np.clip(world['delta']-np.array([world['delta'][pref==p].mean() for p in pref])+rng.normal(0,world['tax_noise'],M),-.5,.5)
 edu_share=norm(T.sum((4,5)))                           # census education counts per area (incl. unknown)
 # education x labour at prefecture level only (as 12-1 for most municipalities)
 edu_rate=np.zeros((M,2,13,8))
 for p in range(P):
  ids=pref==p;emp=(T[ids][...,:4,1:].sum((4,5))+T[ids][...,4,0]).sum(0);tot=T[ids].sum((4,5)).sum(0)
  edu_rate[ids]=((emp+100*(emp.sum(-1,keepdims=True)/np.maximum(tot.sum(-1,keepdims=True),1)))/(tot+100))[None]
 # held-out cities: 3 largest municipalities per prefecture, survey tables by age
 ids=[];age=[];obs=[];weight=[];hp=[];codes=[]
 for p in range(P):
  big=np.where(pref==p)[0][np.argsort(-N[pref==p].sum((1,2)))[:3]]
  for m in big:
   for a in range(13):
    o=samp[m,:,a].sum((0,1,2));tot=o.sum()
    if tot<1000:continue
    ids.append([int(m)]);age.append(a);obs.append(norm(o));weight.append(tot);hp.append(p);codes.append(f'{p:02}{m:03}')
 heldout={'ids':ids,'age':np.array(age),'obs':np.array(obs),'weight':np.array(weight),'pref':np.array(hp),'codes':codes}
 return {'areas':[f'{p:02}{m:03}' for m,p in enumerate(pref)],'pref':pref,'N':N,'Nraw':N.copy(),'Eraw':Eraw,'seed_q':seed_q,'t_status':t_status,'pref_rate':pref_rate,'ess_cat':ess_cat,'nat_cat':nat_cat,'pref_target':pref_target,'tax_feature':tax,'edu_share':edu_share,'edu_q':edu_q,'edu_rate':edu_rate,'heldout':heldout}

def evaluate(inp,world,gammas=(0.,.5,1.,1.5,2.,3.,4.,6.),betas=(0.,.25,.5,1.,1.5,2.,3.)):
 truth=truth_income(world);N=inp['N'];pop=N;R=truth['R']
 W=es.fit_status(inp);cp=es.status_income_shapes(inp);h=inp['heldout'];w=h['weight']
 best={};res={}
 for g in gammas:
  q,E=es.mixture(inp,W,cp,es.education_tilt(inp,g));Xb=es.calibrate(inp,q,E)
  for b in betas:
   Xt=es.tax_project(inp,Xb,E,b);m=es.city_metrics(inp,Xt);res[(g,b)]=(Xt,E,float(np.average(m['loss'],weights=w)))
 def pick(allowed):
  k=min([k for k in res if allowed(k)],key=lambda k:res[k][2]);return k
 out={}
 for name,allowed in {'M0':lambda k:k[0]==0.,'M1':lambda k:True}.items():
  k=pick(allowed);Xt,E,_=res[k];Z=N-E;cbs=np.concatenate([Z[...,None],Xt],-1)
  tv_sa=.5*np.abs(norm(Xt)-truth['paid_by_sa']).sum(-1);ok=E>0
  ecounts=es.allocate_education(inp,cbs)
  tsum=world['T'].sum(4);full_truth=norm(np.concatenate([tsum[...,:2].sum(-1,keepdims=True),tsum[...,2:]],-1))   # P(y|m,s,a,e) incl. nonworkers in class 0
  tv_e=.5*np.abs(norm(ecounts)-full_truth).sum(-1);oke=R>0
  small=(pop.sum((1,2))<8000)[:,None,None]
  out[name]={'gamma':k[0],'beta':k[1],'tv_income_given_area_sex_age_weighted':float(np.average(tv_sa[ok],weights=E[ok])),'tv_income_given_area_sex_age_unweighted_mean':float(tv_sa[ok].mean()),'tv_small_areas':float(tv_sa[ok&small].mean()),'tv_large_areas':float(tv_sa[ok&~small].mean()),'tv_income_given_area_sex_age_edu_weighted':float(np.average(tv_e[oke],weights=R[oke])),'tv_by_education':[float(np.average(tv_e[...,e][oke[...,e]],weights=R[...,e][oke[...,e]])) for e in range(8)]}
 return out

def main(seeds=(1,2,3)):
 rows=[];summary={'scenarios':{},'notes':['Recovery of the hidden joint distribution under the stated generating process; not an accuracy claim for Japan.','Survey tables are Poisson-sampled at 2% and expanded; prefecture education x labour tables only; municipal 表3-1 unavailable (prefecture seeds).','M0/M1 parameters are selected on the 3 largest municipalities per prefecture (as the 86-city selection), evaluated on all municipalities against the truth.']}
 for sc,cfg in SCENARIOS.items():
  per=[]
  for seed in seeds:
   world=generate(seed,**cfg);inp=observe(world);r=evaluate(inp,world);per.append(r)
   for name in r:rows.append(dict(scenario=sc,seed=seed,model=name,**{k:v for k,v in r[name].items() if k!='tv_by_education'}))
   print(sc,seed,{n:round(r[n]['tv_income_given_area_sex_age_weighted'],4) for n in r},{n:round(r[n]['tv_income_given_area_sex_age_edu_weighted'],4) for n in r},flush=True)
  agg={}
  for name in ['M0','M1']:
   agg[name]={k:float(np.mean([p[name][k] for p in per])) for k in per[0][name] if k not in ('tv_by_education','gamma','beta')}
   agg[name]['gamma_selected']=[p[name]['gamma'] for p in per];agg[name]['beta_selected']=[p[name]['beta'] for p in per]
   agg[name]['tv_by_education']=np.mean([p[name]['tv_by_education'] for p in per],0).round(4).tolist()
  agg['M1_minus_M0_tv_sa']=agg['M1']['tv_income_given_area_sex_age_weighted']-agg['M0']['tv_income_given_area_sex_age_weighted']
  agg['M1_minus_M0_tv_edu']=agg['M1']['tv_income_given_area_sex_age_edu_weighted']-agg['M0']['tv_income_given_area_sex_age_edu_weighted']
  agg['seed_range_M1_minus_M0_tv_sa']=[float(min(p['M1']['tv_income_given_area_sex_age_weighted']-p['M0']['tv_income_given_area_sex_age_weighted'] for p in per)),float(max(p['M1']['tv_income_given_area_sex_age_weighted']-p['M0']['tv_income_given_area_sex_age_weighted'] for p in per))]
  summary['scenarios'][sc]=dict(config=cfg,**agg)
 (REPORTS/'synthetic_recovery.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 pd.DataFrame(rows).to_csv(REPORTS/'synthetic_recovery.csv',index=False)
 print(json.dumps({k:{'M0':round(v['M0']['tv_income_given_area_sex_age_weighted'],4),'M1':round(v['M1']['tv_income_given_area_sex_age_weighted'],4),'edu M0':round(v['M0']['tv_income_given_area_sex_age_edu_weighted'],4),'edu M1':round(v['M1']['tv_income_given_area_sex_age_edu_weighted'],4)} for k,v in summary['scenarios'].items()},indent=1))
if __name__=='__main__':main()
