"""Stage B of issue #16: household composition for selected municipalities (experimental).

Two levels, both from published 2020 census tables only:
 1. Aggregate member table X[F, r, s, a] (family type x relationship x sex x age band) per municipality, fitted by IPF to
    - persons by sex x age (population table scaled to general-household members, see notes),
    - heads by sex x age x family type (12-3; unknown-age heads spread within sex x family type),
    - non-head members per family type (12-4 - 12-3),
    - one spouse per couple household (F1, F2), no spouse in F3/F6,
    with the prefecture relationship structure (13-2) as the seed.
 2. Household-level assignment: for every head cell (F, head sex, head age) a household composition is drawn:
    spouse age from an IPF-fitted P(spouse age | head age) (age-gap prior, margins from X), number of children /
    other members from an IPF over (F, household size) fitted to the published size distribution (6-3), member ages
    from IPF-fitted P(member age | head age) with role-specific age-gap priors, margins from X.
    Households are materialized with largest-remainder rounding, so the result is deterministic.
Held-out evaluation: 8-1 (young member presence x size), 26-1 (65+ member presence x size), 9-1 (family type x young
member presence, 3-generation), 13-2 city rows (sex x age x relationship x coarse family type) where published, and
marital status (4-3: married persons vs heads with spouse + spouses) as a consistency check.
Outputs: data/household_b/<code>.npz (households as arrays), validation/household_b_<code>.json, household_b_summary.json
"""
import json,sys,time
import numpy as np
import pandas as pd
from paths import SOURCES,OUTPUT,REPORTS
from model_math import norm

D=SOURCES/'household'
F=['F1','F2','F3','F4','F5','F6','F7'];R=[f'R{i:02}' for i in range(1,14)];A18=[f'A{i:02}' for i in range(18)]
AGE_MID=np.array([2.5+5*i for i in range(17)]+[90.])
COARSE={'F1':'111','F2':'11x','F3':'11x','F4':'12','F5':'2','F6':'3','F7':'4'}   # 13-2 groups; 11x = nuclear minus couple-only
SIZES=list(range(1,11))
DEFAULT_AREAS=['13103','47201','01555']

def rd(name):
 cols=pd.read_csv(D/name,nrows=0).columns;return pd.read_csv(D/name,dtype={c:str for c in ['area','sex','head_age','family_type','age','marital'] if c in cols})

def ipf_nd(seed,margins,iters=500,tol=1e-7):
 """Generic IPF: margins = list of (axes_kept, target). axes_kept is a tuple of axes of `seed` that the target spans."""
 z=np.maximum(seed,1e-12)
 for ax,t in margins:
  sum_axes=tuple(i for i in range(z.ndim) if i not in ax);z*=(np.moveaxis(t,range(t.ndim),ax) if False else 1)
 for it in range(iters):
  err=0.
  for ax,t in margins:
   sum_axes=tuple(i for i in range(z.ndim) if i not in ax);cur=z.sum(sum_axes)
   f=np.divide(t,cur,out=np.zeros_like(t),where=cur>0)
   shape=[1]*z.ndim
   for i,a in enumerate(ax):shape[a]=t.shape[i]
   z=z*f.reshape(shape);err=max(err,np.max(np.abs(cur-t)/np.maximum(t,10)))
  if err<tol:break
 return z,it+1,float(err)

def size_fit(seed,H_F,size,P_F,iters=400000,tol=0.01):
 """Fit N[F,size] to three constraints: sum_size N = H_F, sum_F N = size counts, sum_size N*size = P_F (members per family type).
 Family types with a single feasible size (support of one column in the seed) are fixed first and removed from the margins;
 the rest is solved by cyclic KL projections (row scaling, column scaling, exponential tilt exp(lambda_F*size) by bisection)."""
 nF,nK=seed.shape;ks=np.arange(1,11,dtype=float)
 if size[9]>0:ks[9]=max((P_F.sum()-(ks[:9]*size[:9]).sum())/size[9],10.)   # open-ended 10+ bin: mean size implied by the member total
 z=np.zeros_like(seed);fixed=np.zeros(nF,bool);size_r=size.astype(float).copy()
 for f in range(nF):
  sup=np.where(seed[f]>0)[0]
  if H_F[f]<=0:fixed[f]=True;continue
  if len(sup)==1:z[f,sup[0]]=H_F[f];size_r[sup[0]]-=H_F[f];fixed[f]=True
 free=np.where(~fixed)[0];w=np.maximum(seed[free],1e-12)*(seed[free]>0);Hf=H_F[free];Pf=P_F[free];size_r=np.maximum(size_r,0)
 err=0.;target=np.divide(Pf,Hf,out=np.zeros_like(Pf),where=Hf>0)
 for it in range(iters):
  s_=w.sum(1);w=w*np.divide(Hf,s_,out=np.zeros_like(s_),where=s_>0)[:,None]
  s_=w.sum(0);w=w*np.divide(size_r,s_,out=np.zeros_like(s_),where=s_>0)[None,:]
  # exponential tilt per row so that the mean size equals the published mean (vectorized bisection on lambda)
  lo=np.full(len(free),-10.);hi=np.full(len(free),10.)
  for _ in range(50):
   lam=(lo+hi)/2;q=w*np.exp(lam[:,None]*ks);m=np.divide((q*ks).sum(1),q.sum(1),out=np.zeros(len(free)),where=q.sum(1)>0)
   lo=np.where(m<target,lam,lo);hi=np.where(m<target,hi,lam)
  t=w*np.exp(((lo+hi)/2)[:,None]*ks);w=t*np.divide(w.sum(1),t.sum(1),out=np.zeros(len(free)),where=t.sum(1)>0)[:,None]
  if it%50==0 or it==iters-1:
   err=max(np.abs(w.sum(1)-Hf).max(),np.abs(w.sum(0)-size_r).max(),np.abs((w*ks).sum(1)-Pf).max())
   if err<tol:break
 z[free]=w
 return z,it+1,float(err),ks

def gap_prior(head_mid,gap_mean,gap_sd,sign=+1):
 """P(member band | head band) from a Gaussian prior on (head age - member age) = gap; sign=-1 for older members."""
 P=np.zeros((18,18))
 for i,h in enumerate(head_mid):
  m=h-sign*gap_mean;P[i]=np.exp(-0.5*((AGE_MID-m)/gap_sd)**2);P[i,AGE_MID<0]=0
 return norm(P+1e-9)

def load_area(code):
 heads=rd('heads_households_tidy.csv.gz');members=rd('heads_members_tidy.csv.gz');size=rd('size_tidy.csv.gz');pop=rd('population_all_ages_tidy.csv.gz');rel=rd('relationship_tidy.csv.gz');mar=rd('marital_tidy.csv.gz')
 pref=code[:2]+'000';name=heads[heads.area==code].name.iloc[0]
 def head_tab(df):
  t=np.zeros((2,18,7));unk=np.zeros((2,7))
  for r in df[df.area==code].itertuples():
   si=int(r.sex)-1;v=np.array([getattr(r,f) for f in F])
   if r.head_age=='UNK':unk[si]+=v
   elif r.head_age=='U15':t[si,2]+=v
   else:t[si,int(r.head_age[1:])]+=v
  # unknown-age heads: spread within sex x family type in proportion to known ages (assumption)
  for si in range(2):
   for fi in range(7):
    col=t[si,:,fi];t[si,:,fi]=col+unk[si,fi]*(col/col.sum() if col.sum()>0 else np.r_[np.zeros(3),np.ones(15)/15])
  return t
 H=head_tab(heads);PM=head_tab(members)                      # households, members by head cell
 hh_all=heads[heads.area==code];unk_share=float(hh_all[hh_all.head_age=='UNK'][F].to_numpy().sum()/max(hh_all[F].to_numpy().sum(),1))
 P_F=PM.sum((0,1));H_F=H.sum((0,1))
 ptab=pop[pop.area==code].sort_values('sex')[A18].to_numpy(float)   # (2,18) all persons (imputed, incl. institutional)
 persons=ptab*P_F.sum()/ptab.sum()                              # scaled to general-household members (assumption)
 sz=size[size.area==code].iloc[0][[f'S{i:02}' for i in range(1,11)]].to_numpy(float)
 # prefecture relationship seed: P(r | coarse F, s, a)
 rp=rel[rel.area==pref];seed=np.zeros((7,13,2,18))
 for fi,f in enumerate(F):
  key=COARSE[f]
  for si,s in enumerate(['1','2']):
   sub=rp[rp.sex==s]
   if key=='11x':blk=sub[sub.family_type=='11'].set_index('age')[R].reindex(A18).fillna(0).to_numpy()-sub[sub.family_type=='111'].set_index('age')[R].reindex(A18).fillna(0).to_numpy()
   else:blk=sub[sub.family_type==key].set_index('age')[R].reindex(A18).fillna(0).to_numpy()
   seed[fi,:,si,:]=np.maximum(blk,0).T
 m=mar[mar.area==code];married=np.zeros((2,18))
 for r in m[m.marital=='married'].itertuples():married[int(r.sex)-1,3:]=np.array([getattr(r,a) for a in A18[3:]])
 city_rel=rel[rel.area==code]
 return {'code':code,'name':name,'pref':pref,'H':H,'PM':PM,'P_F':P_F,'H_F':H_F,'persons':persons,'size':sz,'seed':seed,'married':married,'city_rel':city_rel if len(city_rel) else None,'pop_raw':ptab,'unknown_age_head_share':unk_share}

def aggregate(x):
 """Step 1: X[F,r,s,a]. Heads fixed from 12-3; other roles by IPF."""
 H=x['H'];seed=x['seed'].copy();X=np.zeros((7,13,2,18))
 for fi in range(7):X[fi,0]=H[:,:,fi]                          # R01 head
 nonhead=x['persons']-X[:,0].sum(0);nonhead=np.maximum(nonhead,0)
 seed[:,0]=0
 # role totals per F from the prefecture seed, except spouses (structural) ; scale to P_F - H_F
 tgt=np.zeros((7,13))
 for fi,f in enumerate(F):
  need=max(x['P_F'][fi]-x['H_F'][fi],0);sh=seed[fi,1:].sum((1,2));sh=norm(sh+1e-9)
  if f in ('F1','F2'):sp=x['H_F'][fi];sh[0]=0;rest=norm(sh+1e-12)*max(need-sp,0);tgt[fi,1]=sp;tgt[fi,2:]=rest[1:]
  elif f in ('F3','F6'):sh[0]=0;tgt[fi,1:]=norm(sh+1e-12)*need if need>0 else 0
  else:tgt[fi,1:]=sh*need
  if f=='F6':tgt[fi,1:]=0
 s2=seed[:,1:].copy();s2*=(tgt[:,1:]>0)[:,:,None,None]
 # F6 heads only; keep zero seed there
 z,it,err=ipf_nd(s2,[((2,3),nonhead),((0,1),tgt[:,1:])])
 X[:,1:]=z
 return X,{'iterations':it,'error':err,'nonhead_target':float(nonhead.sum()),'nonhead_fitted':float(z.sum())}

def households(x,X):
 """Step 2: materialize households per family type with conditional member ages."""
 H=x['H'];hh=[];notes={}
 # ---- household size mix per F: IPF over (F, size) to the published size distribution
 sizeseed=np.zeros((7,10))
 sizeseed[0,1]=1;sizeseed[5,0]=1;sizeseed[6,:]=[0.3,0.3,0.2,0.1,0.05,0.03,0.01,0.005,0.003,0.002]
 sizeseed[1,2:]=[0.42,0.38,0.14,0.04,0.01,0.005,0.002,0.001];sizeseed[2,1:]=[0.5,0.32,0.12,0.04,0.01,0.005,0.003,0.001,0.001]
 sizeseed[3,1:]=[0.05,0.28,0.3,0.2,0.1,0.04,0.02,0.007,0.003];sizeseed[4,1:]=[0.5,0.25,0.12,0.06,0.03,0.02,0.01,0.007,0.003]
 mean_size=np.divide(x['P_F'],x['H_F'],out=np.ones(7),where=x['H_F']>0)
 # tilt seeds toward each F's published mean size before fitting
 for fi in range(7):
  if x['H_F'][fi]<=0:continue
  ks=np.arange(1,11);p=sizeseed[fi]
  if p.sum()==0:continue
  lo,hi=-5.,5.
  for _ in range(60):
   lam=(lo+hi)/2;q=norm(p*np.exp(lam*ks));m=(q*ks).sum()
   if m<mean_size[fi]:lo=lam
   else:hi=lam
  sizeseed[fi]=norm(p*np.exp(lam*ks))
 SZ,it,err,ks_eff=size_fit(sizeseed*x['H_F'][:,None],x['H_F'],x['size'],x['P_F']);x['size_eff']=ks_eff
 notes['size_ipf']={'iterations':it,'error':err,'constraints':'households per family type (12-3), households per size (6-3), members per family type (12-4)'}
 # ---- age-conditional links per F
 rng=np.random.default_rng(0)
 out=[]
 for fi,f in enumerate(F):
  if x['H_F'][fi]<=0:continue
  heads=H[:,:,fi]                                                    # (2,18)
  # spouse: P(spouse band | head sex, head band) fitted to X[fi, R02, opposite sex, band]
  sp_link=None
  if X[fi,1].sum()>0:
   sp_link=np.zeros((2,18,18))
   for si in range(2):
    rowm=heads[si]*(X[fi,1].sum()/max(heads.sum(),1e-9)) if f not in ('F1','F2') else heads[si]
    colm=X[fi,1,1-si];colm=colm*rowm.sum()/max(colm.sum(),1e-9)
    prior=gap_prior(AGE_MID,2.5 if si==0 else -2.5,4.5)
    z,_,_=ipf_nd(prior*rowm[:,None],[((0,),rowm),((1,),colm)]);sp_link[si]=norm(z+1e-12)
  # children (R03) and grandchildren (R07): P(child band | head band) ; parents (R05/R06) and grandparents (R08): older
  links={}
  for ri,(gm,gs,sign) in {2:(30,6.5,+1),6:(58,9,+1),4:(29,6,-1),5:(29,6,-1),7:(58,9,-1),8:(3,9,+1),3:(30,7,+1),9:(20,15,+1),10:(25,15,+1),11:(20,20,+1),12:(20,20,+1)}.items():
   tot=X[fi,ri].sum()
   if tot<=0:continue
   rowm=heads.sum(0)*tot/max(heads.sum(),1e-9)                      # members of this role spread over head ages
   colm=X[fi,ri].sum(0)
   prior=gap_prior(AGE_MID,gm,gs,sign)
   z,_,_=ipf_nd(prior*rowm[:,None],[((0,),rowm),((1,),colm)]);links[ri]=(norm(z+1e-12),norm(X[fi,ri].sum(1)+1e-12))   # P(band|head band), P(sex) per role band ignored -> use X sex split by band below
   links[ri]=(norm(z+1e-12),np.divide(X[fi,ri],X[fi,ri].sum(0,keepdims=True),out=np.full_like(X[fi,ri],0.5),where=X[fi,ri].sum(0,keepdims=True)>0))
  # role counts per household of size k: distribute non-head, non-spouse members among roles by X shares
  role_share=X[fi,2:].sum((1,2)).copy()
  for ri in range(2,13):
   if ri not in links:role_share[ri-2]=0                            # roles without a fitted link cannot receive members
  role_share=norm(role_share+1e-12)                                  # over R03..R13 with links
  spouse_p=min(X[fi,1].sum()/x['H_F'][fi],1.) if x['H_F'][fi]>0 else 0.
  out.append({'F':f,'heads':heads,'size_mix':norm(SZ[fi]+1e-12),'spouse_link':sp_link,'spouse_p':spouse_p,'links':links,'role_share':role_share})
 notes['spouse_probability']={o['F']:o['spouse_p'] for o in out}
 return out,notes

def materialize(x,X,plan):
 """Deterministic household list: columns [F, head_sex, head_age, size, member_role(13-slot counts by sex x age)].
 Represented as an aggregated table T[F, s_h, a_h, size, r, s, a] of member counts, plus household counts N[F,s_h,a_h,size]."""
 N=np.zeros((7,2,18,10));T=np.zeros((7,2,18,10,13,2,18))
 for o in plan:
  fi=F.index(o['F']);heads=o['heads'];mix=o['size_mix']
  for si in range(2):
   for ai in range(18):
    n=heads[si,ai]
    if n<=0:continue
    for k in range(10):
     nk=n*mix[k]
     if nk<=0:continue
     N[fi,si,ai,k]=nk;T[fi,si,ai,k,0,si,ai]+=nk                          # head
     remaining=(x['size_eff'][k]-1) if 'size_eff' in x else k          # members besides head (size = k+1; 10+ uses its mean size)
     if o['spouse_link'] is not None and remaining>0:
      sp=min(o['spouse_p'],1.)*nk
      T[fi,si,ai,k,1,1-si]+=sp*o['spouse_link'][si,ai];remaining-=min(o['spouse_p'],1.)
     if remaining>0:
      for ri in range(2,13):
       share=o['role_share'][ri-2]
       if share<=0 or ri not in o['links']:continue
       cnt=nk*remaining*share;lk,sexsplit=o['links'][ri]
       ages=lk[ai];T[fi,si,ai,k,ri]+=cnt*(sexsplit[:,:]*ages[None,:])
 return N,T

def presence_prob(n,cell,w):
 """P(at least one member in the target set) for households of one head cell, from the expected member table.

 `cell` is T[f,s_h,a_h,size] (role x sex x age, persons), n the number of households, w[age] the membership weight of an
 age band in the target set (1, 0, or fractional such as 0.2 for 5-9 when the target is 'under 6'). The head is member
 0 with weight w[head age]. Generative assumption (documented in docs/HOUSEHOLD_B.md): for each role the integer part of
 the expected count c_r = persons/n is a fixed slot filled from that role's sex x age distribution; the fractional parts
 form D = sum_r frac_r "mixed" slots that draw a role with probability frac_r/D. D itself need not be an integer (the
 10+ size bin carries a non-integer mean size), so the number of mixed slots is floor(D) with probability 1-(D-floor(D))
 and ceil(D) otherwise, which preserves the expected number of members. Members are drawn independently within a slot.
 """
 head=cell[0].sum(0);p_none=1-(head*w).sum()/head.sum() if head.sum()>0 else 1.
 mix_num=0.;mix_den=0.
 for ri in range(1,13):
  mem=cell[ri].sum(0);c=mem.sum()/n
  if c<=0:continue
  q=(mem*w).sum()/mem.sum();fl=int(np.floor(c+1e-9));frac=c-fl
  p_none*=(1-q)**fl;mix_num+=frac*q;mix_den+=frac
 if mix_den>1e-9:
  qm=mix_num/mix_den;d0=int(np.floor(mix_den+1e-9));delta=mix_den-d0
  if delta<1e-9:delta=0.
  p_none*=(1-delta)*(1-qm)**d0+delta*(1-qm)**(d0+1)
 return 1-p_none

def presence_count(N,T,w,size_k=None,family=None):
 """Expected number of households with at least one member in the target set defined by weights w[age]."""
 tot=0.
 for fi in ([family] if family is not None else range(7)):
  for si in range(2):
   for ai in range(18):
    for k in ([size_k] if size_k is not None else range(10)):
     n=N[fi,si,ai,k]
     if n<=0:continue
     tot+=n*(1 if w[ai]>=1 else presence_prob(n,T[fi,si,ai,k],w))
 return tot

def evaluate(x,N,T):
 """Held-out comparisons and consistency checks."""
 res={}
 memb=T.sum((0,1,2,3,4))                                             # (2,18) persons
 res['persons_vs_target_tv']=float(.5*np.abs(norm(memb.ravel())-norm(x['persons'].ravel())).sum())
 res['members_total']={'generated':float(memb.sum()),'published_12_4':float(x['P_F'].sum())}
 size_gen=N.sum((0,1,2));res['size_distribution_tv_vs_6_3']=float(.5*np.abs(norm(size_gen)-norm(x['size'])).sum())
 # 13-2 city rows (held out): persons by sex x age x role, and by coarse family type
 if x['city_rel'] is not None:
  cr=x['city_rel'];obs=np.zeros((13,2,18));gen=T.sum((0,1,2,3))
  for si,s in enumerate(['1','2']):
   sub=cr[(cr.sex==s)&(cr.family_type=='0')] if (cr.family_type=='0').any() else None
   blk=cr[cr.sex==s];fam_all=blk[blk.family_type.isin(['11','12','2','3','4'])].groupby('age')[R].sum().reindex(A18).fillna(0).to_numpy()
   obs[:,si,:]=fam_all.T
  res['heldout_13_2_role_sex_age']={'tv_joint':float(.5*np.abs(norm(gen.ravel())-norm(obs.ravel())).sum()),'tv_role_margin':float(.5*np.abs(norm(gen.sum((1,2)))-norm(obs.sum((1,2)))).sum()),'tv_age_given_role':{R[ri]:float(.5*np.abs(norm(gen[ri].ravel())-norm(obs[ri].ravel())).sum()) for ri in range(13) if obs[ri].sum()>1000},'observed_general_members':float(obs.sum())}
  res['persons_scaling_check']={'tv_pop_scaled_vs_13_2_members':float(.5*np.abs(norm(x['persons'].ravel())-norm(obs.sum(0).ravel())).sum())}
 # marital consistency: married persons (4-3) vs spouses + heads with a spouse (approx: heads in F1,F2 + spouses)
 heads_with_spouse=T[[0,1]][...,0,:,:].sum((0,1,2,3))+T[[3,4]][...,1,:,:].sum((0,1,2,3))*0
 spouses=T[...,1,:,:].sum((0,1,2,3))
 gen_married=heads_with_spouse+spouses
 m=x['married'];ok=m.sum()>0
 res['married_persons_check']={'generated_couple_members':float(gen_married[:,3:].sum()),'published_married_4_3':float(m.sum()),'tv_by_sex_age':float(.5*np.abs(norm(gen_married[:,3:].ravel())-norm(m[:,3:].ravel())).sum()) if ok else None,'note':'generated counts couple households (F1,F2) heads+spouses only; published married persons include married members in other roles'}
 # 8-1 / 26-1 / 9-1 held-out: presence of members by age class x size
 res['_presence_debug']=None
 ac=pd.read_csv(D/'age_class_size_tidy.csv.gz',dtype={'area':str,'age_class':str});el=pd.read_csv(D/'elderly_size_tidy.csv.gz',dtype={'area':str,'elderly_class':str});fa=pd.read_csv(D/'family_age_class_tidy.csv.gz',dtype={'area':str,'family_type':str})
 def presence(bands,size_k,weights=None,family=None):
  """Households in size bin `size_k` (all family types, or one) with at least one member in the target set; see presence_prob()."""
  w=np.zeros(18);w[bands]=1
  if weights is not None:w=weights
  return presence_count(N,T,w,size_k,family)
 res['_presence_debug']={'elderly_size2':None,'under6_size3':None}
 def size_presence_table(bands):
  return np.array([presence(bands,k) for k in range(6)]+[sum(presence(bands,k) for k in range(6,10))])
 w6d=np.zeros(18);w6d[0]=1;w6d[1]=0.2
 res['_presence_debug']={'elderly_size2':presence(list(range(13,18)),1),'under6_size3':presence([0],2,w6d),'elderly_size10p':presence(list(range(13,18)),9)}
 sub=ac[(ac.area==x['code'])];obs_u6=sub[sub.age_class=='1'].iloc[0][[f'S{i}' for i in ['01','02','03','04','05','06','07p']]].to_numpy(float) if len(sub) else None
 if obs_u6 is not None:
  w6=np.zeros(18);w6[0]=1;w6[1]=0.2                  # under 6 = all of 0-4 plus one fifth of 5-9 (uniform within the band)
  gen_u6=np.array([presence([0],k,w6) for k in range(6)]+[sum(presence([0],k,w6) for k in range(6,10))])
  res['heldout_8_1_under6_by_size']={'generated':gen_u6.round(1).tolist(),'observed':obs_u6.tolist(),'tv':float(.5*np.abs(norm(gen_u6)-norm(obs_u6)).sum()),'total_ratio':float(gen_u6.sum()/max(obs_u6.sum(),1)),'total_ratio_adjusted_for_unknown_age_heads':float(gen_u6.sum()*(1-x['unknown_age_head_share'])/max(obs_u6.sum(),1))}
 sub=el[(el.area==x['code'])&(el.elderly_class=='1')]
 if len(sub):
  obs65=sub.iloc[0][[f'S{i}' for i in ['01','02','03','04','05','06','07p']]].to_numpy(float);gen65=size_presence_table(list(range(13,18)))
  res['heldout_26_1_elderly_by_size']={'generated':gen65.round(1).tolist(),'observed':obs65.tolist(),'tv':float(.5*np.abs(norm(gen65)-norm(obs65)).sum()),'total_ratio':float(gen65.sum()/max(obs65.sum(),1)),'total_ratio_adjusted_for_unknown_age_heads':float(gen65.sum()*(1-x['unknown_age_head_share'])/max(obs65.sum(),1)),'note':'Published presence counts exclude age-unknown members; generated households allocate unknown-age heads to known ages, so the unadjusted ratio is expected to exceed 1 by about the unknown-age share.'}
 sub=fa[(fa.area==x['code'])]
 if len(sub):
  rows={}
  for f,code in [('F1','111'),('F2','112'),('F4','12'),('F5','2'),('F6','3')]:
   r=sub[sub.family_type==code]
   if not len(r):continue
   fi=F.index(f);gen_u15=sum(presence([0,1,2],k,family=fi) for k in range(10))
   rows[f]={'generated_households_with_under15':round(float(gen_u15),1),'observed':float(r.iloc[0].u15),'total_households':float(r.iloc[0].total)}
  res['heldout_9_1_under15_by_family_type']=rows
 return res

def final_checks(x,N,T,tol_persons=0.5):
 """Constraints that the final N/T must satisfy (persons): households per F, members per F (12-4), size counts (6-3), non-negativity."""
 hh_F=N.sum((1,2,3));mem_F=T.sum((1,2,3,4,5,6));size=N.sum((0,1,2))
 res={'households_per_family_type_max_error':float(np.abs(hh_F-x['H_F']).max()),'members_per_family_type_max_error':float(np.abs(mem_F-x['P_F']).max()),'size_counts_max_error':float(np.abs(size-x['size']).max()),'members_total_error':float(abs(T.sum()-x['P_F'].sum())),'nonnegative':bool((N>=-1e-9).all() and (T>=-1e-9).all())}
 res['passed']=bool(res['nonnegative'] and max(res['households_per_family_type_max_error'],res['members_per_family_type_max_error'],res['size_counts_max_error'])<tol_persons)
 return res

def run(code):
 t0=time.time();x=load_area(code);X,agg=aggregate(x);plan,notes=households(x,X);N,T=materialize(x,X,plan);ev=evaluate(x,N,T)
 checks=final_checks(x,N,T)
 if not checks['passed']:raise RuntimeError(f"Household output violates constraints: {checks}")
 (OUTPUT/'household_b').mkdir(parents=True,exist_ok=True)
 import provenance as pvn
 np.savez_compressed(OUTPUT/'household_b'/f'{code}.npz',households=N,members=T,aggregate=X,family_codes=np.array(F),relationship_codes=np.array(R),age_bands=np.array(A18),code=code,provenance=np.array(pvn.stamp('household_expected',inputs=sorted(D.glob('*.csv.gz')),settings={'code':code,'prefecture_seed':x['pref']},extra={'layout':'households[F,s_h,a_h,size] expected households; members[F,s_h,a_h,size,role,sex,age] expected members; aggregate[F,role,sex,age]'})))
 rep={'code':code,'name':x['name'],'prefecture_seed':x['pref'],'households':float(N.sum()),'published_households':float(x['H_F'].sum()),'unknown_age_head_share':x['unknown_age_head_share'],'final_checks':checks,'aggregate_ipf':agg,'plan':notes,'evaluation':ev,'elapsed_seconds':round(time.time()-t0,1),'assumptions':['Persons by sex x age are the imputed population scaled to general-household members (institutional residents and age-unknown removed proportionally).','Unknown-age heads are spread within sex x family type in proportion to known ages.','Relationship structure per family type comes from the prefecture (13-2) and is fitted to local sex x age; member ages are linked to head age through Gaussian age-gap priors fitted by IPF.','Members within a household are drawn independently given the head cell (sibling spacing, assortative matching beyond age are not modelled).','No within-household correlation of income or other individual attributes is modelled.']}
 (REPORTS/f'household_b_{code}.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2))
 return rep

def main(codes=None):
 codes=codes or DEFAULT_AREAS;summary={}
 for c in codes:
  r=run(c);ev=r['evaluation'];summary[c]={'name':r['name'],'households':r['households'],'size_tv':ev['size_distribution_tv_vs_6_3'],'persons_tv':ev['persons_vs_target_tv'],'heldout_13_2':ev.get('heldout_13_2_role_sex_age',{}).get('tv_joint'),'heldout_8_1_tv':ev.get('heldout_8_1_under6_by_size',{}).get('tv'),'heldout_26_1_tv':ev.get('heldout_26_1_elderly_by_size',{}).get('tv'),'heldout_26_1_ratio':ev.get('heldout_26_1_elderly_by_size',{}).get('total_ratio'),'heldout_26_1_ratio_adj':ev.get('heldout_26_1_elderly_by_size',{}).get('total_ratio_adjusted_for_unknown_age_heads'),'heldout_8_1_ratio':ev.get('heldout_8_1_under6_by_size',{}).get('total_ratio'),'heldout_8_1_ratio_adj':ev.get('heldout_8_1_under6_by_size',{}).get('total_ratio_adjusted_for_unknown_age_heads'),'heldout_9_1_F2_under15':[ev['heldout_9_1_under15_by_family_type']['F2']['generated_households_with_under15'],ev['heldout_9_1_under15_by_family_type']['F2']['observed']] if 'F2' in ev.get('heldout_9_1_under15_by_family_type',{}) else None,'unknown_age_head_share':r['unknown_age_head_share']}
  print(c,json.dumps(summary[c],ensure_ascii=False),flush=True)
 (REPORTS/'household_b_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main(sys.argv[1:] or None)
