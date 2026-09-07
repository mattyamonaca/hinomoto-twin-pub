"""Issue #23: household composition summaries for the Explorer (selected municipalities, stage B experimental).

Reads the integer populations written by household_sample.py (data/household_b/<code>_population.csv.gz) and writes
web/household/<code>.json with, per member sex x age band (18 bands incl. 0-14): the share living alone, with a spouse,
with a child under 18 in the household, with a parent, with a member 65+, and the household-size distribution; plus the
family-type distribution of households and the denominators (general households, general-household members, members
15+ vs the resident population 15+ of the individual model). graph.json gets `household: {codes, seed, note}`.
"""
import json,hashlib
import numpy as np
import pandas as pd
from paths import OUTPUT,WEB,REPORTS
import household_sample as hs

def summarize(code):
    df=pd.read_csv(OUTPUT/'household_b'/f'{code}_population.csv.gz')
    # under-18 inside the 15-19 band: single years are not generated; assume uniform single years, so 3/5 of 15-19 are under 18
    df=df.copy();rng=np.random.default_rng(hs.U18_SEED);df['u18']=(df.age18<3)|((df.age18==3)&(rng.random(len(df))<hs.U18_SHARE_15_19))
    g=df.groupby('household_id')
    hh=pd.DataFrame({'hsize':g['size'].first(),'family':g['family'].first(),'has_spouse':g['role'].apply(lambda r:(r==1).any()),'child_u18':g.apply(lambda x:((x.role==2)&x.u18).any()),'has_parent':g['role'].apply(lambda r:r.isin([4,5]).any()),'has_65':g['age18'].apply(lambda a:(a>=13).any()),'has_child_any':g['role'].apply(lambda r:(r==2).any())})
    m=df.merge(hh,left_on='household_id',right_index=True)
    couple=m.role.isin([0,1])
    # spouse co-residence is observable only for the head (an R02 member exists) and the spouse of the head (R02 itself);
    # couples among other relationships (children with R04, parents, grandparents) cannot be paired from the tables
    m['spouse_known']=couple;m['has_spouse']=((m.role==0)&m['has_spouse'])|(m.role==1)
    m['child_u18']=couple&m['child_u18'];m['has_child_any']=couple&m['has_child_any']      # own child in the household (member is head or spouse)
    m['has_parent']=(m.role==2)|(couple&m['has_parent'])                                  # member is a child of the head, or a parent(-in-law) of the head lives here
    rows=[]
    for s in range(2):
        for a in range(18):
            x=m[(m.sex==s)&(m.age18==a)];n=len(x)
            if not n:rows.append(None);continue
            rows.append({'n':int(n),'alone':float((x['hsize']==1).mean()),'with_spouse':float(x.has_spouse.mean()),'spouse_known':float(x.spouse_known.mean()),'with_child_u18':float(x.child_u18.mean()),'with_child_any':float(x.has_child_any.mean()),'with_parent':float(x.has_parent.mean()),'with_65':float(x.has_65.mean()),'is_head':float((x.role==0).mean()),'size':[float((x['hsize']==k).mean()) for k in range(1,7)]+[float((x['hsize']>=7).mean())]})
    fam=[int((hh.family==f).sum()) for f in range(7)]
    d=np.load(OUTPUT/'household_b'/f'{code}.npz');N=d['households']
    out={'code':code,'households':int(len(hh)),'members':int(len(df)),'members_15plus':int((df.age18>=3).sum()),'members_under_15':int((df.age18<3).sum()),'expected_households':float(N.sum()),'family_type':fam,'family_codes':hs.F,'family_labels':hs.FL,'age_bands':hs.A18L,'by_sex_age':rows,
         'note':'一般世帯（施設等の世帯を除く）の整数個票（seed 1）から集計。分母は各行の構成員数 n。世帯構成は2020年国勢調査の世帯表から生成した推定で、構成員の所得・学歴とは独立に抽出している。配偶者との同居は本人が世帯主または世帯主の配偶者の場合だけ判定でき（spouse_known）、それ以外の続き柄の夫婦関係は公表表から特定できない。18歳未満は単歳がないため、15〜19歳階級の3/5を18歳未満とみなす仮定で数える。'}
    return out

def main():
    payload=json.loads((WEB/'graph.json').read_text(encoding='utf-8'));g=payload['graph']
    (WEB/'household').mkdir(exist_ok=True);codes={}
    for f in sorted((OUTPUT/'household_b').glob('*_population.csv.gz')):
        code=f.name.split('_')[0];out=summarize(code);p=WEB/'household'/f'{code}.json';p.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
        codes[code]={'file':f'household/{code}.json','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'households':out['households'],'members':out['members']};print(code,out['households'],out['members'])
    g['household']={'codes':codes,'stage':'B','seed':1,'note':'selected municipalities only (experimental)'}
    (WEB/'graph.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    # resident 15+ population of the individual model for the denominators note
    fin=np.load(OUTPUT/'final_arrays.npz');areas=fin['areas'].tolist();rep={}
    for code in codes:
        i=areas.index(code);rep[code]={'members_15plus':json.loads((WEB/'household'/f'{code}.json').read_text())['members_15plus'],'resident_population_15plus':float(fin['population'][i].sum())}
    (REPORTS/'household_web_export.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2));print(json.dumps(rep))
if __name__=='__main__':main()
