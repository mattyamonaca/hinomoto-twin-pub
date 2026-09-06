"""Replace web distributions from verified model arrays, retaining only baseline geography/source metadata."""
import json,base64
import numpy as np
from paths import OUTPUT,WEB,REPORTS
import build_education as be

def norm(x):
    return np.divide(x,x.sum(-1,keepdims=True),out=np.zeros_like(x),where=x.sum(-1,keepdims=True)>0)
def encode(x):return base64.b64encode(np.asarray(x,dtype='<f8').tobytes()).decode('ascii')
def main():
    payload=json.loads((WEB/'graph.json').read_text());g=payload['graph']
    d=np.load(OUTPUT/'final_arrays.npz');b=np.load(OUTPUT/'model_arrays.npz');ed=np.load(OUTPUT/'education_leaf_arrays.npz')['counts'];inp=be.prepare()
    areas=d['areas'].tolist();ix={m:i for i,m in enumerate(areas)};N=d['population'];C=d['counts_by_sex'];B=b['counts_by_sex']
    import pandas as pd
    pm=pd.read_csv(OUTPUT/'parent_mapping.csv',dtype=str);parents={p:[ix[a] for a in f.area] for p,f in pm.groupby('parent_code')}
    pops=[];xs=[];bs=[];ers=[];rs=[];g['rates']={}
    for m in g['munis']:
        ids=[ix[m['c']]] if m['c'] in ix else parents[m['c']]
        n=N[ids].sum(0);c=C[ids].sum(0);baseline=B[ids].sum(0);e=ed[ids].sum(0)
        pops.append(n);xs.append(norm(c[...,1:]));bs.append(norm(baseline[...,1:]));ers.append(np.divide(c[...,1:].sum(-1),n,out=np.zeros_like(n),where=n>0));rs.append(norm(e.sum(-1)))
        rate=np.divide((inp['rate_array'][ids]*inp['edu_counts'][ids]).sum(0),inp['edu_counts'][ids].sum(0),out=np.zeros_like(inp['rate_array'][0]),where=inp['edu_counts'][ids].sum(0)>0)
        g['rates'][m['c']]=rate.tolist();m['rk']=m['c'];m['p']=float(n.sum())
    agg=[]
    for p in range(48):
        ids=list(range(len(areas))) if p==0 else [i for i,m in enumerate(areas) if m.startswith(f'{p:02}')]
        agg.append(norm(ed[ids].sum(0)).transpose(1,0,2,3))
    g.update(pop=np.asarray(pops).tolist(),xc=encode(bs),xd=encode(xs),e=encode(ers),rs=encode(rs),ag=encode(agg),q=inp['shapes'].tolist(),encoding='float64',sens={},sens_or=None)
    meta=json.loads((OUTPUT/'model_metadata.json').read_text());payload.update(dataset_version='2020-2022-'+meta['model_version']+'-20260906',model=meta)
    payload['schema_version']=2
    # Verify serialized values directly against the same arrays used by the API exports.
    for key,expected in [('xd',xs),('xc',bs),('e',ers),('rs',rs),('ag',agg)]:
        actual=np.frombuffer(base64.b64decode(g[key]),dtype='<f8').reshape(np.asarray(expected).shape)
        np.testing.assert_array_equal(actual,expected)
    np.testing.assert_allclose(np.asarray(pops)[[i for i,m in enumerate(g['munis']) if m['l']=='m']].sum(),N.sum(),atol=1e-6)
    (WEB/'graph.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False))
    (REPORTS/'web_verification.json').write_text(json.dumps({'passed':True,'model':meta,'geographies':len(pops),'encoding':'float64','checked':['serialized arrays exactly match model','nonoverlapping population','prefecture education-income aggregation']},indent=2))
    print('Web data generated:',payload['dataset_version'],flush=True)
if __name__=='__main__':main()
