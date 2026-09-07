"""Reference values for the Explorer's stage-C panel: persona_v4 results for sample conditions
(validation/workplace_web_reference.json), compared by tests/web_workplace_check.cjs."""
import json
from paths import REPORTS,OUTPUT,SOURCES
import persona_v4 as pv,persona_v3 as p3
def main():
    m=pv.WorkplaceDistribution(OUTPUT,SOURCES);cases=[]
    for code,ind in [('13103',None),('13103','G07'),('27100',None),('01555','G01'),('47201','G16')]:
        r=m.workplace(code,ind,None,top=15);cases.append({'side':'residence','code':code,'industry':ind,'result':r})
    for code,ind in [('13101',None),('13101','G10'),('27100','G05')]:
        r=m.residence(code,ind,top=15);cases.append({'side':'workplace','code':code,'industry':ind,'result':r})
    e=p3.EmploymentDistribution(OUTPUT,SOURCES).margins('13103',35,'male');mix=e['p_industry_given_employed']
    cases.append({'side':'residence','code':'13103','industry':None,'mix':{'age':35,'sex':'male'},'result':m.workplace('13103',None,mix,top=15)})
    (REPORTS/'workplace_web_reference.json').write_text(json.dumps({'model_version':m.model_version,'cases':cases},ensure_ascii=False));print('cases',len(cases))
if __name__=='__main__':main()
