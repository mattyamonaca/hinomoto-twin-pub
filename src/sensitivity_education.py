"""Sensitivity of the v2 education x income allocation to its transported assumptions.

Variants re-run allocate() with alternative initial shapes and compare P(income | area, sex, age, education)
with the baseline. This measures how much the published probabilities depend on each assumption; it is
not an accuracy evaluation against observed municipal education x income tables (none are available).
The lambda variants change only the paid-income initial shape; education-specific employment rates are kept
unless the variant also uses a common rate.
"""
import json
import numpy as np
import pandas as pd
from build import BASE,AGES,norm
from build_education import EDU,INCOME_MAP,read,prepare,allocate,income_shapes

EXAMPLES=['13103','13121','02201','47201']  # 港区, 足立区, 青森市, 那覇市
GE500=slice(8,16)

def tempered(shapes,reference,lam):
 """q_lambda proportional to q0 * (q/q0)^lambda: lambda=1 baseline, 0 removes the education difference in the paid-income initial shape (employment rates untouched)."""
 q0=reference[:,:,None,:]
 return norm(q0*np.power(np.maximum(shapes,1e-12)/np.maximum(q0,1e-12),lam))

def unknown_income_to_reference(income_shrink):
 """Income-unknown workers get the all-education reference shape instead of the known-income proportions."""
 ess=read('income_education_tidy.csv.gz');ess=ess[ess.age!='00'].copy();ess['age']=ess.age.astype(int).clip(upper=13).map(lambda x:f'{x:02}')
 ess=ess.groupby(['sex','age','education','income'],as_index=False)['count'].sum()
 tab=ess.pivot(index=['sex','age','education'],columns='income',values='count').sort_index(axis=1)
 shapes=np.zeros((2,13,8,16))
 for si,s in enumerate(['1','2']):
  for ai,a in enumerate(AGES):
   total=tab.loc[(s,a,'0')].to_numpy();ref=norm(total[1:]+1e-8)
   for ei,parts in enumerate(INCOME_MAP):
    v=sum(tab.loc[(s,a,e)].to_numpy() for e in parts);unknown=max(v[0]-v[1:].sum(),0.)
    shapes[si,ai,ei]=norm(v[1:]+unknown*ref+income_shrink*ref)
 return shapes

def unknown_education_as_known_mix(inputs):
 """E08 takes the area's own mixture of known-education shapes (weighted by education counts) instead of the national reference."""
 s=inputs['shapes'];R=inputs['edu_counts'];known=[0,1,2,3,4,6]
 out=np.broadcast_to(s,R.shape[:3]+s.shape[2:]).copy()  # (M,2,13,8,16)
 w=R[...,known];mix=np.einsum('msae,saey->msay',w,s[:,:,known,:])
 mix=np.divide(mix,w.sum(-1)[...,None],out=np.zeros_like(mix),where=w.sum(-1)[...,None]>0)
 fallback=np.broadcast_to(inputs['reference'],mix.shape)
 out[...,7,:]=np.where(w.sum(-1)[...,None]>0,mix,fallback)
 return out

def allocate_any(inputs,shapes):
 if shapes.ndim==4:return allocate(inputs,shapes)[0]
 # per-area shapes: run allocate per (sex, age) with area-specific seeds
 from build_education import project
 N=inputs['N'];edu=inputs['edu_counts'];rate=inputs['rate_array'];inc=inputs['income_counts']
 cube=np.zeros(N.shape+(8,17))
 for si in range(2):
  for ai in range(13):
   r=rate[:,si,ai];seed=np.concatenate([(1-r)[...,None],r[...,None]*shapes[:,si,ai]],axis=-1)*edu[:,si,ai,:,None]
   cube[:,si,ai]=project(seed,edu[:,si,ai],inc[:,si,ai])[0]
 return np.concatenate([cube[...,:2].sum(-1,keepdims=True),cube[...,2:]],axis=-1)

def cond(counts):
 den=counts.sum(-1,keepdims=True);return np.divide(counts,den,out=np.full_like(counts,np.nan),where=den>0)

def odds_ratio(p,mi,si,ai):
 """Education E04 vs E02, income 500-600 (index 8) vs 300-400 (index 6)."""
 a=p[mi,si,ai,3];b=p[mi,si,ai,1]
 return float((a[8]/a[6])/(b[8]/b[6])) if np.isfinite(a[8]) and np.isfinite(b[8]) and a[6]>0 and b[6]>0 and b[8]>0 else float('nan')

def main():
 inputs=prepare();areas=inputs['areas'];idx={a:i for i,a in enumerate(areas)};R=inputs['edu_counts']
 base_counts=allocate(inputs)[0];base=cond(base_counts);ge_base=np.nansum(base[...,GE500],-1)
 # Common employment rate across education classes (weighted by education counts) for the fully-independent comparison.
 R=inputs['edu_counts'];rate=inputs['rate_array'];common=np.divide((rate*R).sum(-1),R.sum(-1),out=np.zeros(R.shape[:3]),where=R.sum(-1)>0)
 inputs_common=dict(inputs,rate_array=np.broadcast_to(common[...,None],rate.shape).copy())
 variants=[
  ('lambda_0.0','有業所得の初期形状にある学歴差を除く（λ=0。学歴別就業率は維持）',tempered(inputs['shapes'],inputs['reference'],0.)),
  ('lambda_0.0_common_rate','有業所得の初期形状の学歴差と学歴別就業率の差の両方を除く（学歴と所得を初期値で独立にする）',tempered(inputs['shapes'],inputs['reference'],0.),inputs_common),
  ('lambda_0.5','有業所得の初期形状の学歴差を半分に弱める（λ=0.5）',tempered(inputs['shapes'],inputs['reference'],.5)),
  ('lambda_1.5','有業所得の初期形状の学歴差を1.5倍に強める（λ=1.5）',tempered(inputs['shapes'],inputs['reference'],1.5)),
  ('income_shrink_300','所得形状の平滑化を弱める（擬似人口300）',income_shapes(300.)[0]),
  ('income_shrink_3000','所得形状の平滑化を強める（擬似人口3000）',income_shapes(3000.)[0]),
  ('income_unknown_to_reference','所得不詳の有業者を同性・同年齢の全体形状に置く',unknown_income_to_reference(inputs['income_shrink'])),
  ('education_unknown_as_known_mix','学歴不詳の所得形状を地域の既知学歴の混合にする',unknown_education_as_known_mix(inputs)),
 ]
 rows=[];summary={'baseline':{'description':'v2.0 as published','example_odds_ratio_E04_vs_E02_500_600_vs_300_400_age35_39_male':{c:odds_ratio(base,idx[c],0,4) for c in EXAMPLES}},'variants':{}}
 weights=R.copy()
 for var in variants:
  key,desc,shapes=var[:3];inp=var[3] if len(var)>3 else inputs
  counts=allocate_any(inp,shapes);p=cond(counts);ge=np.nansum(p[...,GE500],-1)
  tv=0.5*np.nansum(abs(p-base),-1)
  ok=np.isfinite(tv)&(R>0)
  entry={'description':desc,'weighted_mean_tv':float(np.average(tv[ok],weights=R[ok])),'weighted_mean_abs_change_p_ge500':float(np.average(abs(ge-ge_base)[ok],weights=R[ok])),'max_abs_change_p_ge500_cells_ge100':float(np.max(abs(ge-ge_base)[ok&(R>=100)])),'by_education':{},'example_odds_ratio':{c:odds_ratio(p,idx[c],0,4) for c in EXAMPLES},'example_p_ge500_age35_39_male_E04':{c:[float(ge_base[idx[c],0,4,3]),float(ge[idx[c],0,4,3])] for c in EXAMPLES}}
  for ei,e in enumerate(EDU):
   m=ok[...,ei];w=R[...,ei][m]
   entry['by_education'][e]={'weighted_mean_tv':float(np.average(tv[...,ei][m],weights=w)),'weighted_mean_abs_change_p_ge500':float(np.average(abs(ge-ge_base)[...,ei][m],weights=w))}
   rows.append((key,e,entry['by_education'][e]['weighted_mean_tv'],entry['by_education'][e]['weighted_mean_abs_change_p_ge500']))
  # constraint checks stay satisfied under every variant
  entry['max_income_margin_error']=float(np.max(abs(counts.sum(-2)-base_counts.sum(-2))));entry['max_education_margin_error']=float(np.max(abs(counts.sum(-1)-R)))
  summary['variants'][key]=entry;print(key,round(entry['weighted_mean_tv'],5),round(entry['weighted_mean_abs_change_p_ge500'],5),flush=True)
 summary['notes']=['Weights are model education populations R(m,s,a,e), not survey sample sizes.','TV is half the L1 distance between the variant and baseline P(income | area, sex, age, education).','All variants keep the v1 income margins and the census education margins; they change only how the fixed margins are split.','lambda variants temper only the paid-income initial shape q(y|s,a,e); education-specific employment rates stay unless the variant name says common_rate, so lambda_0.0 alone does not remove the education-income association from the final distribution that includes non-workers.','This is a sensitivity analysis of transported assumptions, not a validation against observed municipal education x income data.']
 (BASE/'validation/education_sensitivity.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 pd.DataFrame(rows,columns=['variant','education','weighted_mean_tv','weighted_mean_abs_change_p_ge500']).to_csv(BASE/'validation/education_sensitivity.csv',index=False)
 print(json.dumps({k:{'tv':round(v['weighted_mean_tv'],5),'ge500':round(v['weighted_mean_abs_change_p_ge500'],5)} for k,v in summary['variants'].items()},ensure_ascii=False,indent=1))
if __name__=='__main__':main()
