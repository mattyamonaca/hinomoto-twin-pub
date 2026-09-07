"""Issue #23: draw households and their members from the stage-B expected tables, build an integer population,
evaluate it, and link members aged 15+ to the individual attributes (M12 five attributes + stage A).

Input: data/household_b/<code>.npz (N[F,s_h,a_h,size] households, T[F,s_h,a_h,size,role,sex,age] expected members).
Generative model per head cell (identical to presence_prob() in build_household.py, documented in docs/HOUSEHOLD_B.md):
  for each role r the integer part of the expected count c_r = members_r / households is a fixed slot filled from that
  role's sex x age distribution; the fractional parts form D = sum_r frac_r mixed slots (floor(D) with probability
  1 - (D - floor D), ceil(D) otherwise) that draw a role with probability frac_r / D. Sizes 1..9 are exact integers;
  the open-ended "10+" bin carries a non-integer mean, so its households have floor(mean) or ceil(mean) members
  (a stated assumption: the size distribution inside 10+ is not published).
Integer population: households per head cell by stochastic rounding of N with a fixed seed (expected value preserved).
Linkage: a member aged 15+ (18-band -> 13 model bands, 75+ merged) draws (education, status, industry, income) from the
stage-A block of its (municipality, sex, age band); the (education, income) margin of that block is the published
5-attribute model, so the linked persons reproduce persona_v2 in expectation. Members under 15 carry no such attributes
(they are outside the 15+ income population). No within-household correlation of education/income is modelled (stated).
Denominators: households = general households (施設等の世帯を除く); persons = general-household members, which is
smaller than the 15+ resident population used by the individual model (institutional residents, age-unknown removed).
CLI:
  python src/household_sample.py --municipality 13103 --households 5 --seed 1        # sample households with members
  python src/household_sample.py --municipality 13103 --population --seed 1          # integer population + evaluation
  python src/household_sample.py --municipality 13103 --households 3 --link          # attach individual attributes
"""
import argparse,json,time
import numpy as np
import pandas as pd
from paths import SOURCES,OUTPUT,REPORTS
from model_math import norm

F=['F1','F2','F3','F4','F5','F6','F7'];FL=['夫婦のみ','夫婦と子供','ひとり親と子供','核家族以外の親族','非親族を含む','単独','不詳']
R=[f'R{i:02}' for i in range(1,14)];RL=['世帯主','配偶者','子','子の配偶者','世帯主の父母','配偶者の父母','孫','祖父母','兄弟姉妹','他の親族','住み込みの雇人','その他','続き柄不詳']
A18=[f'A{i:02}' for i in range(18)];A18L=[f'{5*i}〜{5*i+4}歳' for i in range(17)]+['85歳以上']
D=SOURCES/'household'
U18_SHARE_15_19=0.6;U18_SEED=18   # ages are 5-year bands: 15-19 holds 15, 16, 17 (under 18) and 18, 19; uniform single years -> 3/5

def age18_to_model(a):
    """18 five-year bands from 0-4 -> 13 model bands from 15-19 (75+ merged); None under 15."""
    return None if a<3 else min(a-3,12)

class HouseholdSampler:
    def __init__(self,code,data_dir=None,arrays=None):
        from pathlib import Path
        self.code=str(code).zfill(5);self.dir=Path(data_dir or OUTPUT)
        if arrays is not None:self.N,self.T=arrays
        else:d=np.load(self.dir/'household_b'/f'{self.code}.npz');self.N=d['households'];self.T=d['members']
        self.cells=np.argwhere(self.N>1e-9)
        self.mean_size=np.zeros(10)
        for k in range(10):
            n=self.N[...,k].sum();self.mean_size[k]=self.T[...,k,:,:,:].sum()/n if n>0.5 else k+1
        self.prep={}
        for f,s,a,k in self.cells:
            n=self.N[f,s,a,k];cell=self.T[f,s,a,k]                     # (13,2,18)
            roles=[]
            for r in range(1,13):
                m=cell[r];c=m.sum()/n
                if c<=1e-12:continue
                roles.append((r,c,norm(m.ravel()+0.)))
            self.prep[(f,s,a,k)]=roles
    def _members(self,f,s,a,k,rng):
        """One household: list of (role, sex, age18); the head first."""
        out=[(0,int(s),int(a))];fl=[];frac_r=[];frac_w=[]
        for r,c,p in self.prep[(f,s,a,k)]:
            n_fix=int(np.floor(c+1e-9));fr=c-n_fix
            for _ in range(n_fix):fl.append((r,p))
            if fr>1e-9:frac_r.append((r,p));frac_w.append(fr)
        Dm=float(sum(frac_w));n_mix=int(np.floor(Dm+1e-9));delta=Dm-n_mix
        if delta>1e-9 and rng.random()<delta:n_mix+=1
        if n_mix and frac_r:
            w=np.array(frac_w)/Dm
            for _ in range(n_mix):
                r,p=frac_r[rng.choice(len(frac_r),p=w)];fl.append((r,p))
        for r,p in fl:
            j=int(rng.choice(36,p=p));out.append((int(r),j//18,j%18))
        return out
    def sample_households(self,n,seed=20260907):
        rng=np.random.default_rng(seed);w=np.array([self.N[tuple(c)] for c in self.cells]);w=w/w.sum()
        picks=rng.choice(len(self.cells),size=n,p=w);hh=[]
        for i,ci in enumerate(picks):
            f,s,a,k=[int(v) for v in self.cells[ci]];mem=self._members(f,s,a,k,rng)
            hh.append({'household_id':i+1,'municipality_code':self.code,'family_type':F[f],'family_type_label':FL[f],'size_bin':'10+' if k==9 else str(k+1),'size':len(mem),'head_sex':str(s+1),'head_age_band':A18[a],
                       'members':[{'member_id':j+1,'is_head':bool(j==0),'role':R[r],'role_label':RL[r],'sex_code':str(sx+1),'age_band18':A18[ag],'age_band_label':A18L[ag],'in_income_population':bool(ag>=3)} for j,(r,sx,ag) in enumerate(mem)]})
        return hh
    def population(self,seed=20260907):
        """Integer population: households per head cell by stochastic rounding of N; members drawn per household."""
        rng=np.random.default_rng(seed);rows=[];hid=0
        # controlled (sequential) rounding within each family type x size bin: the running total of the expected counts
        # is rounded with one uniform offset, so every (family type, size) total is off by at most one household
        counts={}
        for f in range(7):
            for k in range(10):
                cells=[c for c in self.cells if c[0]==f and c[3]==k]
                if not cells:continue
                u=rng.random();cum=0.;prev=0
                for c in cells:
                    cum+=self.N[tuple(c)];now=int(np.floor(cum+u));counts[tuple(int(v) for v in c)]=now-prev;prev=now
        for f,s,a,k in self.cells:
            cnt=counts[(int(f),int(s),int(a),int(k))]
            for _ in range(cnt):
                hid+=1;mem=self._members(f,s,a,k,rng)
                for j,(r,sx,ag) in enumerate(mem):rows.append((hid,j+1,f,k,len(mem),r,sx,ag))
        df=pd.DataFrame(rows,columns=['household_id','member_id','family','size_bin','size','role','sex','age18'])
        return df

def independent_population(sampler,seed=20260907):
    """Baseline: same households (head cell counts), but non-head members drawn from the municipality-wide member
    sex x age distribution, independent of head age, role and each other."""
    rng=np.random.default_rng(seed);df=sampler.population(seed).copy()
    pool=sampler.T[:,:,:,:,1:,:,:].sum((0,1,2,3,4)).ravel();pool=pool/pool.sum()
    nh=(df.member_id>1).to_numpy();draws=rng.choice(36,size=nh.sum(),p=pool)
    df.loc[nh,'sex']=draws//18;df.loc[nh,'age18']=draws%18
    return df

def presence_tables(df):
    """Households with a member 65+ / under 6 (0-4 plus one fifth of 5-9, drawn) / under 15 / under 18, by size and family type."""
    df=df.copy();df['u6']=(df.age18==0)|((df.age18==1)&(np.random.default_rng(1).random(len(df))<.2))
    df['u18']=(df.age18<3)|((df.age18==3)&(np.random.default_rng(U18_SEED).random(len(df))<U18_SHARE_15_19))   # 15-19: 3/5 under 18 (uniform single years)
    g=df.groupby('household_id');agg=pd.DataFrame({'size':g['size'].first(),'family':g['family'].first(),'e65':g['age18'].max()>=13,'u6':g['u6'].any(),'u15':(g['age18'].min()<3),'u18':g['u18'].any()})
    agg['size7']=np.minimum(agg['size'],7)
    return agg

def evaluate_population(sampler,df,label='model'):
    """Constraint and held-out comparison of an integer population against the expected tables and published counts."""
    N=sampler.N;T=sampler.T;res={'label':label,'households':int(df.household_id.nunique()),'persons':int(len(df))}
    hh=df[df.member_id==1]
    exp_F=N.sum((1,2,3));got_F=np.array([(hh.family==f).sum() for f in range(7)])
    exp_size=N.sum((0,1,2));got_size=np.array([(hh.size_bin==k).sum() for k in range(10)])
    exp_mem_F=T.sum((1,2,3,4,5,6));got_mem_F=np.array([(df.family==f).sum() for f in range(7)])
    res['households_per_family_type']={'expected':exp_F.round(1).tolist(),'sampled':got_F.tolist(),'max_abs_error':float(np.abs(exp_F-got_F).max()),'max_rel_error':float(np.max(np.abs(exp_F-got_F)/np.maximum(exp_F,1)))}
    res['households_per_size_bin']={'expected':exp_size.round(1).tolist(),'sampled':got_size.tolist(),'max_abs_error':float(np.abs(exp_size-got_size).max())}
    res['members_per_family_type']={'expected':exp_mem_F.round(1).tolist(),'sampled':got_mem_F.tolist(),'max_rel_error':float(np.max(np.abs(exp_mem_F-got_mem_F)/np.maximum(exp_mem_F,1)))}
    exp_sa=T.sum((0,1,2,3,4));got_sa=np.zeros((2,18))
    for (s,a),c in df.groupby(['sex','age18']).size().items():got_sa[s,a]=c
    res['members_sex_age_tv']=float(.5*np.abs(norm(exp_sa.ravel())-norm(got_sa.ravel())).sum())
    exp_rsa=T.sum((0,1,2,3));got_rsa=np.zeros((13,2,18))
    for (r,s,a),c in df.groupby(['role','sex','age18']).size().items():got_rsa[r,s,a]=c
    res['members_role_sex_age_tv']=float(.5*np.abs(norm(exp_rsa.ravel())-norm(got_rsa.ravel())).sum())
    # held-out published counts
    agg=presence_tables(df);code=sampler.code
    ac=pd.read_csv(D/'age_class_size_tidy.csv.gz',dtype={'area':str,'age_class':str});el=pd.read_csv(D/'elderly_size_tidy.csv.gz',dtype={'area':str,'elderly_class':str});fa=pd.read_csv(D/'family_age_class_tidy.csv.gz',dtype={'area':str,'family_type':str})
    cols=[f'S{i}' for i in ['01','02','03','04','05','06','07p']]
    def bysize(flag):return np.array([((agg['size7']==k)&agg[flag]).sum() for k in range(1,8)],float)
    sub=el[(el.area==code)&(el.elderly_class=='1')]
    if len(sub):
        obs=sub.iloc[0][cols].to_numpy(float);gen=bysize('e65');res['heldout_26_1_elderly_by_size']={'observed':obs.tolist(),'sampled':gen.tolist(),'tv':float(.5*np.abs(norm(gen)-norm(obs)).sum()),'total_ratio':float(gen.sum()/max(obs.sum(),1))}
    sub=ac[(ac.area==code)&(ac.age_class=='1')]
    if len(sub):
        obs=sub.iloc[0][cols].to_numpy(float);gen=bysize('u6');res['heldout_8_1_under6_by_size']={'observed':obs.tolist(),'sampled':gen.tolist(),'tv':float(.5*np.abs(norm(gen)-norm(obs)).sum()),'total_ratio':float(gen.sum()/max(obs.sum(),1))}
    sub=fa[fa.area==code]
    if len(sub):
        rows={}
        for f,c in [('F1','111'),('F2','112'),('F4','12'),('F5','2'),('F6','3')]:
            r=sub[sub.family_type==c]
            if not len(r):continue
            fi=F.index(f);rows[f]={'sampled_households_with_under15':int(((agg.family==fi)&agg.u15).sum()),'observed':float(r.iloc[0].u15),'total_households':float(r.iloc[0].total)}
        res['heldout_9_1_under15_by_family_type']=rows
    return res

def sa_adjust(df,sampler,iters=200000,seed=3):
    """Attribute-swap adjustment (simulated-annealing style): swap the age band of two same-role members in different
    households when it lowers the deviation of the member sex x age distribution from the expected table. Household
    structure (roles, sizes) is untouched. Reports the objective before/after and the time."""
    t0=time.time();rng=np.random.default_rng(seed);exp=sampler.T.sum((0,1,2,3,4));exp=exp/exp.sum()*len(df)
    got=np.zeros((2,18))
    for (s,a),c in df.groupby(['sex','age18']).size().items():got[s,a]=c
    obj=lambda g:float(np.abs(g-exp).sum());before=obj(got)
    role=df.role.to_numpy();sex=df.sex.to_numpy();age=df.age18.to_numpy().copy();hh=df.household_id.to_numpy();n=len(df)
    byrole={r:np.where(role==r)[0] for r in range(1,13)};temp=1.0;accepted=0
    for it in range(iters):
        r=rng.integers(1,13);idx=byrole[r]
        if len(idx)<2:continue
        i,j=idx[rng.integers(len(idx))],idx[rng.integers(len(idx))]
        if hh[i]==hh[j] or age[i]==age[j] or sex[i]!=sex[j]:continue
        # swapping ages between same-sex members changes nothing in the sex x age margin; instead move member i to a
        # band that is under-represented: propose age[i] -> age[j]'s band if that band is short and i's band is long
        s=sex[i];ai=age[i];aj=age[j];delta=(abs(got[s,ai]-1-exp[s,ai])+abs(got[s,aj]+1-exp[s,aj]))-(abs(got[s,ai]-exp[s,ai])+abs(got[s,aj]-exp[s,aj]))
        if delta<0 or rng.random()<np.exp(-delta/max(temp,1e-6)):
            age[i]=aj;got[s,ai]-=1;got[s,aj]+=1;accepted+=1
        temp*=0.99995
    out=df.copy();out['age18']=age
    return out,{'objective_before':before,'objective_after':obj(got),'accepted_moves':accepted,'iterations':iters,'seconds':round(time.time()-t0,1),'note':'moves member ages within a role toward the expected sex x age margin; household composition fixed; head ages untouched only by chance (heads are role 0 and never moved)'}

class Linker:
    """Attach the individual attributes (education, status, industry, income) to members aged 15+."""
    def __init__(self,code,data_dir=None,sources_dir=None):
        import persona_v3 as pv
        self.code=str(code).zfill(5);self.emp=pv.EmploymentDistribution(data_dir,sources_dir);self.pv=pv;self.blocks={}
    def block(self,s,a13):
        key=(s,a13)
        if key not in self.blocks:
            b=self.emp.block(self.code,15+5*a13,['male','female'][s]);paid=b['paid'];fam=b['family'];un=b['unemployed'];ina=b['inactive']
            cells=[];w=[]
            for e in range(8):
                for k in range(4):
                    for g in range(20):
                        for y in range(16):
                            v=paid[e,k,g,y]
                            if v>0:cells.append((e,k,g+1,y+1));w.append(v)
                for g in range(20):
                    if fam[e,g]>0:cells.append((e,4,g+1,0));w.append(fam[e,g])
                if un[e]>0:cells.append((e,5,0,0));w.append(un[e])
                if ina[e]>0:cells.append((e,6,0,0));w.append(ina[e])
            w=np.array(w);self.blocks[key]=(cells,w/w.sum())
        return self.blocks[key]
    def link(self,members,seed=20260907):
        """members: list of dicts with sex_code and age_band18 (from sample_households). Adds attributes in place."""
        rng=np.random.default_rng(seed);K=self.pv.K;G=self.pv.G;E=self.pv.EDU
        for m in members:
            a=A18.index(m['age_band18']);a13=age18_to_model(a)
            if a13 is None:m.update({'in_income_population':False,'education_code':None,'status_code':None,'industry_code':None,'income_band':None,'note':'15歳未満：所得母集団（15歳以上）の外'});continue
            cells,p=self.block(int(m['sex_code'])-1,a13);e,k,g,y=cells[rng.choice(len(cells),p=p)]
            m.update({'in_income_population':True,'model_age_band':self.pv.AGES[a13],'education_code':E[e],'status_code':K[k],'labor_status_code':'J1' if k<5 else 'J2' if k==5 else 'J3','industry_code':G[g],'income_band':None if y==0 else f'I{y:02}','income_note':'主な仕事の収入なし' if y==0 else None})
        return members

def link_population(linker,df,seed=20260907):
    """Vectorised linkage of an integer population: members 15+ draw (education, status, industry, income) per (sex, age band)."""
    rng=np.random.default_rng(seed);K=linker.pv.K;G=linker.pv.G;E=linker.pv.EDU
    out=df.copy();out['a13']=[age18_to_model(a) for a in out.age18];out['education']=None;out['status']=None;out['industry']=None;out['income']=None
    for (s,a13),idx in out[out.a13.notna()].groupby(['sex','a13']).groups.items():
        cells,p=linker.block(int(s),int(a13));pick=rng.choice(len(cells),size=len(idx),p=p);arr=np.array(cells)[pick]
        out.loc[idx,'education']=[E[e] for e in arr[:,0]];out.loc[idx,'status']=[K[k] for k in arr[:,1]];out.loc[idx,'industry']=[G[g] for g in arr[:,2]];out.loc[idx,'income']=[None if y==0 else f'I{y:02}' for y in arr[:,3]]
    return out.drop(columns=['a13'])

def linked_check(linker,df):
    """The linked members reproduce the published 5-attribute distribution P(education, income | sex, age band) of the
    municipality (persona_v2) up to sampling noise; the denominators differ (general-household members vs residents 15+)."""
    import persona_v2 as p2
    m=p2.PersonaDistributionV2(linker.emp.dir);rows=[];E=linker.pv.EDU
    sub=df[df.education.notna()].copy();sub['a13']=[age18_to_model(a) for a in sub.age18]
    for (s,a13),g in sub.groupby(['sex','a13']):
        ref=m.distribution(linker.code,age=15+5*int(a13),sex=str(int(s)+1))[0,0]      # (8,16) education x income (I01 includes no income)
        got=np.zeros((8,16))
        for e,y,c in g.groupby(['education','income'],dropna=False).size().reset_index().itertuples(index=False):
            got[E.index(e),0 if y is None or (isinstance(y,float)) else int(y[1:])-1]+=c
        rows.append({'sex':int(s)+1,'age_band':linker.pv.AGES[int(a13)],'members':int(len(g)),'model_population_15plus':float(linker.emp.N[linker.emp.ix[linker.code],int(s),int(a13)]),'tv_education_income':float(.5*np.abs(norm(ref.ravel())-norm(got.ravel())).sum())})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--municipality',required=True);p.add_argument('--link-population',action='store_true');p.add_argument('--households',type=int,default=0);p.add_argument('--population',action='store_true');p.add_argument('--link',action='store_true');p.add_argument('--seed',type=int,default=20260907);p.add_argument('--sa',action='store_true');p.add_argument('--data-dir');p.add_argument('--sources-dir')
    a=p.parse_args();S=HouseholdSampler(a.municipality,a.data_dir)
    if a.population:
        t0=time.time();df=S.population(a.seed);t1=time.time()-t0
        rep={'code':S.code,'seed':a.seed,'mean_size_10plus_assumption':float(S.mean_size[9]),'sampling_seconds':round(t1,1),'model':evaluate_population(S,df,'model'),'independent':evaluate_population(S,independent_population(S,a.seed),'independent members')}
        if a.sa:
            adj,info=sa_adjust(df,S);rep['sa_adjusted']=evaluate_population(S,adj,'sa_adjusted');rep['sa']=info
        out=OUTPUT/'household_b'
        if a.link_population:
            L=Linker(S.code,a.data_dir,a.sources_dir);t2=time.time();df=link_population(L,df,a.seed);rep['linkage']={'seconds':round(time.time()-t2,1),'members_15plus':int(df.education.notna().sum()),'members_under_15':int(df.education.isna().sum()),'by_sex_age':linked_check(L,df),'note':'members 15+ draw (education, status, industry, income) from the stage-A block of their sex x age band; no within-household correlation; 0-14 have no attributes'}
            rep['linkage']['max_tv_education_income']=max(r['tv_education_income'] for r in rep['linkage']['by_sex_age']);rep['linkage']['weighted_tv_education_income']=float(np.average([r['tv_education_income'] for r in rep['linkage']['by_sex_age']],weights=[r['members'] for r in rep['linkage']['by_sex_age']]))
        df.to_csv(out/f'{S.code}_population.csv.gz',index=False)
        (REPORTS/f'household_b_population_{S.code}.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2));print(json.dumps({k:rep[k] for k in ('code','sampling_seconds','mean_size_10plus_assumption')}|{'model':{k:v for k,v in rep['model'].items() if k.startswith('heldout') or k.endswith('tv')}},ensure_ascii=False,indent=1))
    if a.households:
        hh=S.sample_households(a.households,a.seed)
        if a.link:
            L=Linker(S.code,a.data_dir,a.sources_dir)
            for h in hh:L.link(h['members'],a.seed+h['household_id'])
        print(json.dumps({'municipality_code':S.code,'denominator':'一般世帯（施設等の世帯を除く）とその構成員。15歳以上の構成員だけが所得母集団','households':hh},ensure_ascii=False,indent=1))
if __name__=='__main__':main()
