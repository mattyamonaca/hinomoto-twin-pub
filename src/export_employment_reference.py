"""Reference blocks for the web reproduction check: Python stage-A allocation for sample municipality x sex x age cells.

Writes validation/employment_web_reference.json (paid[e,k,g,y] flattened, family, unemployed, inactive) so that
`node tests/web_employment_check.cjs` can compare the browser recomputation cell by cell.
"""
import json
import numpy as np
from paths import SOURCES,OUTPUT,REPORTS
import build_employment as bm
SAMPLES=[('13103',0,4),('13103',1,9),('01555',1,8),('47201',0,10),('27127',0,6),('13103',0,12)]
def main():
    x=bm.load_inputs(SOURCES,OUTPUT);ix={a:i for i,a in enumerate(x['areas'])};out=[]
    for code,s,a in SAMPLES:
        b=bm.block(x,s,a,ids=[ix[code]])
        out.append({'code':code,'sex':s,'age':a,'paid':b['paid'][0].ravel().tolist(),'family':b['family'][0].ravel().tolist(),'unemployed':b['unemployed'][0].tolist(),'inactive':b['inactive'][0].tolist(),'iterations':int(b['iterations']),'error':float(b['error'])})
    (REPORTS/'employment_web_reference.json').write_text(json.dumps({'model_version':x['model_version'],'samples':out}))
    print('reference cells',len(out))
if __name__=='__main__':main()
