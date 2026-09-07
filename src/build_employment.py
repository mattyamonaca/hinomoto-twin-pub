"""Stage A of issue #16: employment status and industry attributes conditional on the production distribution.

For each leaf area, sex and age the production (M12) counts C(e, z) over education (8) and the 17 internal income
components (0 = no main-job income, 1..16 = income classes) are kept as fixed margins and split by
  k  employment status: K1 regular, K2 non-regular, K3 executive, K4 self-employed (incl. home work),
                        K5 unpaid family worker, K6 unemployed (完全失業者), K7 not in the labour force (非労働力人口)
     labour-force status J1 employed = K1..K5, J2 unemployed = K6, J3 not in labour force = K7
  g  industry: G01..G20 JSIC major divisions for K1..K5 (G20 = 分類不能の産業, which in the 2020 census also holds
     the industry-unknown), G00 not applicable for K6/K7
Structural zeros: K6/K7 -> G00 and z=0; K5 -> z=0; K1..K4 -> z in 1..16.
The K6/K7 split uses the municipal unemployed / not-in-labour-force ratio of census 参考表1 (imputed) as the margin and
the prefecture education-specific unemployment share of census 12-1 as the seed of the education association.
Margins (same area, sex, age): C(e,z) [production]; W(k) [employment-status table of build.py, K6 = N - sum W];
census 6-3 industry counts of employed persons (K1..K5).
Seed associations (transported, documented in docs/EMPLOYMENT_A.md):
  P(k|e,s,a)      ESS 04000 national education x status x age (persons with a main job); K5 follows K4 within
                  the area's K5/K4 ratio; K6 from the prefecture education-specific employment rate (census 12-1)
  P(g|k,s,a,p)    ESS regional 10-1 (prefecture): employees / regular / non-regular; self-employed = total - employees;
                  enrolled (E06) uses the 在学者 rows
  P(z|k,g,s,a,p)  M0 status shapes r(y|p,s,a,k) tilted by ESS regional 24 (national industry x status x income; no age)
Outputs: data/employment_a.npz, validation/employment_a_build.json, validation/employment_a_heldout.csv
"""
import json,time
import numpy as np
import pandas as pd
from paths import SOURCES,OUTPUT,REPORTS
from model_math import AGES,norm
import estimator as es
import build_education as be

K=['K1','K2','K3','K4','K5','K6','K7'];J=['J1','J2','J3'];G=[f'G{i:02}' for i in range(1,21)];EDU=[f'E{i:02}' for i in range(1,9)]
INCOME_MAP=[['11'],['12','13'],['14','16','17'],['15','18'],['19'],['2'],['0'],['0']]
SHRINK_KG=300.   # pseudo-population toward the national association for small prefecture cells
SHRINK_U=100.    # pseudo-population toward the all-education unemployment share (K6/K7 split seed)
BLOCK=8*4*20*16+8*20+8+8   # flattened block per (sex, age): paid[e,k,g,y], family[e,g], unemployed[e], inactive[e]

def read(path,**kw):return pd.read_csv(path,dtype=str,**kw)

def load_inputs(sources_dir=None,output_dir=None):
 from pathlib import Path
 S=Path(sources_dir or SOURCES);O=Path(output_dir or OUTPUT)
 t0=time.time();inp=es.load_real_inputs(S);areas=inp['areas'];M=len(areas);pref=inp['pref'];prefs=inp['prefs'];P=len(prefs)
 d=np.load(O/'final_arrays.npz');assert d['areas'].tolist()==areas,'final_arrays.npz must match the leaf areas'
 meta=json.loads((O/'model_metadata.json').read_text()) if (O/'model_metadata.json').exists() else {'model_version':'unknown'}
 N=inp['N'];W=es.fit_status(inp);K6=np.maximum(N-W.sum(-1),0)
 cube=be.allocate({'shapes':inp['edu_q'],'N':N,'edu_counts':inp['edu_share']*N[...,None],'rate_array':inp['edu_rate'],'income_counts':d['counts_by_sex']},keep_components=True)[0]
 assert np.allclose(cube.sum((3,4)),N,atol=1e-4)
 # census 6-3 employed persons by industry (K1..K5); scale to the model's employed persons; prefecture composition if empty
 c=read(S/'industry/census_industry_age_tidy.csv.gz').set_index(['area','sex','age'])
 idx=pd.MultiIndex.from_product([areas,['1','2'],AGES],names=['area','sex','age'])
 cnt=np.nan_to_num(c.reindex(idx)[G].to_numpy(float).reshape(M,2,13,20))
 emp=W.sum(-1);gm=norm(np.where(cnt.sum(-1,keepdims=True)>0,cnt,inp['ind_share']))*emp[...,None]
 # --- P(k|e,s,a): national education x status x age (ESS 04000 by status)
 e4=read(S/'industry/education_status_income_tidy.csv.gz');e4['count']=e4['count'].astype(float)
 e4=e4[(e4.income=='00')&(e4.age!='00')].copy();e4['age']=e4.age.astype(int).clip(upper=13).map(lambda x:f'{x:02}')
 tab=e4.groupby(['sex','status','age','education'])['count'].sum()
 pk_e=np.zeros((2,13,8,4))   # K1 regular, K2 nonregular, K3 executive, K4 self
 for si,s in enumerate(['1','2']):
  for ai,a in enumerate(AGES):
   for ei,parts in enumerate(INCOME_MAP):
    v=lambda st:sum(tab.get((s,st,a,e_),0.) for e_ in parts)
    reg,non,empl,own=v('22'),v('23'),v('2'),v('1');pk_e[si,ai,ei]=[reg,non,max(empl-reg-non,0),own]
 pk_e=norm(pk_e+1e-6)
 # --- P(g|k,s,a,p) from ESS regional 10-1 (prefecture), enrolled rows for E06; national fallback via shrinkage
 t=read(S/'industry/ess_status_industry_age_tidy.csv.gz')
 for a in AGES:t[a]=t[a].astype(float)
 t=t[t.industry!='G00'].drop(columns=['name']).set_index(['area','sex','education','status','industry']).sort_index()
 def kg(area,s,edu):
  """counts (4 paid statuses + family-as-self, 13 ages, 20 industries) from a 10-1 area block"""
  blk=t.loc[(area,s,edu)];tot=blk.loc['0'][AGES].to_numpy();empl=blk.loc['1'][AGES].to_numpy();reg=blk.loc['12'][AGES].to_numpy();non=blk.loc['13'][AGES].to_numpy()
  own=np.maximum(tot-empl,0);exe=np.maximum(empl-reg-non,0)
  return np.stack([reg,non,exe,own]).transpose(2,0,1)  # (13,4,20)
 nat={(s,edu):kg('00000',s,edu) for s in ['1','2'] for edu in ['0','2']}
 pg=np.zeros((P,2,2,13,4,20))   # pref, sex, edu-group(0 graduates/total, 1 enrolled), age, k, g
 for pi,p in enumerate(prefs):
  for si,s in enumerate(['1','2']):
   for gi,edu in enumerate(['0','2']):
    c_=kg(p+'000',s,edu);prior=norm(nat[(s,edu)]+1e-6);pg[pi,si,gi]=norm(c_+SHRINK_KG*prior)
 # --- P(z|k,g,s): ESS regional 24 national industry x status x income -> tilt relative to the status total
 e24=read(S/'industry/income_industry_tidy.csv.gz');e24['count']=e24['count'].astype(float)
 e24=e24[(e24.area=='00000')&(e24.income!='00')]
 tilt=np.ones((2,4,20,16))
 for si,s in enumerate(['1','2']):
  piv=e24[e24.sex==s].pivot_table(index=['status','industry'],columns='income',values='count').sort_index(axis=1)
  def row(st,g):return piv.loc[(st,g)].to_numpy(float)
  for ki,st in enumerate(['22','23',None,'1']):
   for gi,g in enumerate(G):
    if st is None:num=np.maximum(row('2',g)-row('22',g)-row('23',g),0);den=np.maximum(row('2','G00')-row('22','G00')-row('23','G00'),0)
    else:num=row(st,g);den=row(st,'G00')
    qg=norm(num+1000*norm(den+1e-8));q0=norm(den+1e-8);tilt[si,ki,gi]=qg/np.maximum(q0,1e-12)
 cp=es.status_income_shapes(inp)   # (P,2,13,4,16) r(y|p,s,a,k)
 # --- K6/K7: municipal unemployed share among the not-employed (参考表1); prefecture fallback where the cell is empty
 lab=read(S/'census_imputed_age_tidy.csv.gz');lab['unemployed']=lab.unemployed.astype(float);lab['inactive']=lab.inactive.astype(float)
 L=lab.set_index(['area','sex','age']).reindex(idx);un=np.nan_to_num(L.unemployed.to_numpy(float).reshape(M,2,13));ina=np.nan_to_num(L.inactive.to_numpy(float).reshape(M,2,13))
 Lp=lab.set_index(['area','sex','age']);pu=np.zeros((P,2,13));pu_e=np.zeros((P,2,13,8))
 el=read(S/'education/census_education_labor_tidy.csv.gz').set_index(['area','sex','age','labor_status'])
 for pi,p in enumerate(prefs):
  for si,s in enumerate(['1','2']):
   for ai,a in enumerate(AGES):
    r=Lp.loc[(p+'000',s,a)];pu[pi,si,ai]=r.unemployed/max(r.unemployed+r.inactive,1.)
    u12=el.loc[(p+'000',s,a,'12'),EDU].to_numpy(float);n2=el.loc[(p+'000',s,a,'2'),EDU].to_numpy(float)
    pu_e[pi,si,ai]=(u12+SHRINK_U*pu[pi,si,ai])/(u12+n2+SHRINK_U)
 u_share=np.where(un+ina>0,un/np.maximum(un+ina,1.),pu[pref])   # (M,2,13)
 import sys;print(f'inputs loaded {time.time()-t0:.0f}s',file=sys.stderr,flush=True)
 return {'inp':inp,'areas':areas,'M':M,'pref':pref,'prefs':prefs,'N':N,'W':W,'K6':K6,'u_share':u_share,'pu_e':pu_e,'cube':cube,'gm':gm,'pk_e':pk_e,'pg':pg,'tilt':tilt,'cp':cp,'t101':t,'kg_fn':kg,'model_version':meta.get('model_version','unknown'),'sources_dir':str(S),'output_dir':str(O)}

def ipf3(seed,A,B,C,tol=1e-6,iters=600):
 """seed (n,8,4,20,16); margins A (n,8,16) over (e,y), B (n,4) over k, C (n,20) over g. Batched over n."""
 z=np.maximum(seed,1e-14)
 z*=(A>0)[:,:,None,None,:];z*=(B>0)[:,None,:,None,None];z*=(C>0)[:,None,None,:,None]
 for it in range(iters):
  s=z.sum((2,3));z*=np.divide(A,s,out=np.zeros_like(A),where=s>0)[:,:,None,None,:]
  s=z.sum((1,3,4));z*=np.divide(B,s,out=np.zeros_like(B),where=s>0)[:,None,:,None,None]
  s=z.sum((1,2,4));z*=np.divide(C,s,out=np.zeros_like(C),where=s>0)[:,None,None,:,None]
  dA=np.abs(z.sum((2,3))-A);dB=np.abs(z.sum((1,3,4))-B)
  err=max(np.max(dA/np.maximum(A,1e4)),np.max(dB/np.maximum(B,1e4)))   # relative for large margins, ~absolute (per 1e4 persons) for small ones
  if err<tol:return z,it+1,float(max(dA.max(),dB.max()))
 return z,iters,float(max(dA.max(),dB.max()))

def block(x,si,ai,ids=None,variant='base'):
 """Allocate one (sex, age) slice for areas `ids`. Returns dict of blocks: paid (n,8,4,20,16), family (n,8,20), nonwork (n,8), fit info."""
 inp=x['inp'];ids=np.arange(x['M']) if ids is None else np.asarray(ids);n=len(ids);pref=x['pref'][ids]
 cube=x['cube'][ids,si,ai];W=x['W'][ids,si,ai];K6=x['K6'][ids,si,ai];gm=x['gm'][ids,si,ai]
 A=cube[:,:,1:]                                   # (n,8,16) paid persons by education x income
 zero=cube[:,:,0]                                 # (n,8) family + nonworkers by education
 # split the zero component between K5 (family) and K6 (nonworkers) by education
 rate=inp['edu_rate'][ids,si,ai]                  # education-specific employment rate seed (prefecture)
 if variant=='k6_independent':rate=np.full_like(rate,rate.mean())
 seed=np.stack([np.maximum(rate,1e-6)*np.maximum(x['pk_e'][si,ai,:,3],1e-6),np.maximum(1-rate,1e-6)],-1)*zero[...,None]   # (n,8,2)
 fam=np.zeros((n,8));non=np.zeros((n,8));unemp=np.zeros((n,8));inact=np.zeros((n,8))
 pu_e=x['pu_e'][pref,si,ai];u=x['u_share'][ids,si,ai]                   # (n,8) seed share, (n,) margin share
 for i in range(n):
  z,_,_=es.ipf(seed[i],zero[i],np.array([W[i,4],K6[i]]),tol=1e-7);fam[i]=z[:,0];non[i]=z[:,1]
  z2,_,_=es.ipf(np.stack([np.maximum(pu_e[i],1e-6),np.maximum(1-pu_e[i],1e-6)],-1)*non[i][:,None],non[i],np.array([K6[i]*u[i],K6[i]*(1-u[i])]),tol=1e-7);unemp[i]=z2[:,0];inact[i]=z2[:,1]
 # family industry: self-employed profile of the prefecture (10-1), enrolled profile for E06
 pgp=x['pg'][pref]                                 # (n,2,13,4,20) -> use age ai
 pg_grad=pgp[:,si,0,ai];pg_enr=pgp[:,si,1,ai]      # (n,4,20)
 if variant=='national_kg':nat=np.stack([norm(x['kg_fn']('00000',['1','2'][si],'0')[ai]+1e-6)]*n);pg_grad=nat;pg_enr=np.stack([norm(x['kg_fn']('00000',['1','2'][si],'2')[ai]+1e-6)]*n)
 pg_e=np.repeat(pg_grad[:,None],8,1);pg_e[:,5]=pg_enr                       # (n,8,4,20)
 fam_g=(fam[...,None]*pg_e[:,:,3,:]).sum(1)   # (n,8,1)*(n,8,20) -> (n,20)
 paid_g=np.maximum(gm-fam_g,0);tot=W[:,:4].sum(-1);paid_g=norm(paid_g)*tot[:,None]
 # paid seed: R(e)*P(k|e)*P(g|k,e)*P(y|k,g)
 ry=x['cp'][pref,si,ai][:,:,None,:]*np.clip(x['tilt'][si],0.05,20.)[None]   # (n,4,20,16)
 ry=norm(np.maximum(ry,1e-4*ry.max(-1,keepdims=True)))                      # floor: no near-zero seed where the fixed (e,y) margin has mass
 pk=np.repeat(x['pk_e'][si,ai][None],n,0)                                    # (n,8,4)
 seed_paid=A.sum(-1)[:,:,None,None,None]*pk[:,:,:,None,None]*pg_e[:,:,:,:,None]*ry[:,None]
 z,it,err=ipf3(seed_paid,A,W[:,:4],paid_g)
 return {'paid':z,'family':fam[...,None]*pg_e[:,:,3,:],'nonwork':non,'unemployed':unemp,'inactive':inact,'iterations':it,'error':err}

def main(variant='base'):
 x=load_inputs();M=x['M'];t0=time.time()
 kg=np.zeros((M,2,13,7,21));ke=np.zeros((M,2,13,8,7));ky=np.zeros((M,2,13,4,16));gy=np.zeros((M,2,13,20,16));ge=np.zeros((M,2,13,8,21));indep=np.zeros((M,2,13));fits=[]
 # aggregate full blocks (paid e,k,g,y + family e,g + unemployed e + inactive e) for national, prefectures and aggregated-ward cities
 pm=pd.read_csv(OUTPUT/'parent_mapping.csv',dtype=str);groups={'00000':list(range(M))}
 for pi,p in enumerate(x['prefs']):groups[p+'000']=[i for i in range(M) if x['pref'][i]==pi]
 aix={a:i for i,a in enumerate(x['areas'])}
 for parent,f in pm.groupby('parent_code'):
  if parent!='13100':groups[parent]=[aix[a] for a in f.area if a in aix]
 gcodes=list(groups);agg=np.zeros((len(gcodes),2,13,BLOCK))
 for si in range(2):
  for ai in range(13):
   b=block(x,si,ai,variant=variant);z=b['paid'];fam=b['family'];un=b['unemployed'];ina=b['inactive'];non=un+ina
   for gi,code in enumerate(gcodes):
    ids=groups[code];agg[gi,si,ai]=np.concatenate([z[ids].sum(0).ravel(),fam[ids].sum(0).ravel(),un[ids].sum(0),ina[ids].sum(0)])
   kg[:,si,ai,:4,1:]=z.sum((1,4));kg[:,si,ai,4,1:]=fam.sum(1);kg[:,si,ai,5,0]=un.sum(1);kg[:,si,ai,6,0]=ina.sum(1)
   ke[:,si,ai,:,:4]=z.sum((3,4));ke[:,si,ai,:,4]=fam.sum(2);ke[:,si,ai,:,5]=un;ke[:,si,ai,:,6]=ina
   ky[:,si,ai]=z.sum((1,3));gy[:,si,ai]=z.sum((1,2));ge[:,si,ai,:,1:]=z.sum((2,4))+fam;ge[:,si,ai,:,0]=non
   # association strength: TV between the paid joint and the product of its (e,y),(k),(g) margins
   tot=np.maximum(z.sum((1,2,3,4)),1e-12);A=z.sum((2,3))/tot[:,None,None];B=z.sum((1,3,4))/tot[:,None];C=z.sum((1,2,4))/tot[:,None]
   prod=A[:,:,None,None,:]*B[:,None,:,None,None]*C[:,None,None,:,None];indep[:,si,ai]=.5*np.abs(z/tot[:,None,None,None,None]-prod).sum((1,2,3,4))
   fits.append({'sex':si+1,'age':AGES[ai],'iterations':b['iterations'],'max_relative_error':b['error']})
   print(f'sex {si+1} age {AGES[ai]} it={b["iterations"]} err={b["error"]:.1e} {time.time()-t0:.0f}s',flush=True)
 N=x['N'];assert np.allclose(kg.sum((3,4)),N,atol=1e-4) and np.allclose(ke.sum((3,4)),N,atol=1e-4)
 assert np.abs(ke[...,:5].sum(3)-x['W']).max()<0.1   # persons
 if variant=='base':np.savez_compressed(OUTPUT/'employment_a_agg.npz',codes=np.array(gcodes),blocks=agg.astype(np.float32),variant=variant,layout='paid[8,4,20,16] family[8,20] unemployed[8] inactive[8] per (sex, age); float32 persons',model_version=x['model_version'])
 np.savez_compressed(OUTPUT/('employment_a.npz' if variant=='base' else f'employment_a_{variant}.npz'),areas=np.array(x['areas']),population=N,status_industry=kg,education_status=ke,status_income=ky,industry_income=gy,education_industry=ge,independence_tv=indep,status_codes=np.array(K),labor_codes=np.array(J),industry_codes=np.array(['G00']+G),variant=variant,model_version=x['model_version'],sources_dir=x['sources_dir'],output_dir=x['output_dir'],stage='A')
 pop=N;ok=pop>0
 result={'variant':variant,'model_base':'3.0-M12','areas':M,'status_codes':K,'labor_codes':J,'industry_codes':['G00']+G,'margins':{'education_x_income':'production counts, preserved exactly','status':'employment-status table of build.py (K6+K7 = N - employed; K6/K7 split by the municipal unemployed share of census 参考表1)','industry':'census 6-3 employed persons scaled to model employed persons'},'shrink_kg_pseudopopulation':SHRINK_KG,'ipf':{'max_iterations':max(f['iterations'] for f in fits),'max_absolute_margin_error_persons':max(f['max_relative_error'] for f in fits),'max_education_income_margin_error_persons':float(np.abs(ke.sum(-1)-x['cube'].sum(-1)).max()),'max_status_margin_error_persons':float(np.abs(ke[...,:5].sum(3)-x['W']).max())},'association_tv_joint_vs_independent':{'weighted_mean':float(np.average(indep[ok],weights=pop[ok])),'median':float(np.median(indep[ok])),'p90':float(np.quantile(indep[ok],.9))},'nonworker_share':float(kg[...,5:,0].sum()/N.sum()),'unemployed_share':float(kg[...,5,0].sum()/N.sum()),'unemployed_share_of_not_employed':float(kg[...,5,0].sum()/max(kg[...,5:,0].sum(),1)),'family_share':float(kg[...,4,:].sum()/N.sum()),'elapsed_seconds':round(time.time()-t0,1),'notes':['Education x status x industry association is transported from national (04000) and prefecture (10-1) tables; municipal cross tables do not exist.','Industry x income shapes have no age dimension (table 24).','Preserving the production education x income margins means this stage does not change any published 5-attribute probability.','K6 (unemployed) vs K7 (not in labour force): municipal margin from census 参考表1 (imputed labour-force status), education association from prefecture census 12-1 with pseudo-population %d; no association with income is assumed (both have no main-job income).'%SHRINK_U]}
 (REPORTS/('employment_a_build.json' if variant=='base' else f'employment_a_build_{variant}.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in result.items() if k in ('ipf','association_tv_joint_vs_independent','nonworker_share','family_share','elapsed_seconds')},indent=1))
 return x,kg,ke,ky,ge
if __name__=='__main__':
 import sys;main(sys.argv[1] if len(sys.argv)>1 else 'base')
