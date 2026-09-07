"""Issue #24 (last item): publish the stage-C residence x workplace x industry table for the Explorer.

Format (decided before implementation, docs/WORKPLACE_C.md §9): one small JSON per residence municipality
(web/workplace/o_<code>.json: destinations with commuting category and the 20 industry counts, the unknown-workplace
counts by industry and the work-at-home count) and one per workplace municipality (web/workplace/d_<code>.json:
origins with category and industry counts). The page fetches only the files of the selected municipality (wards of a
designated city are fetched together). graph.json gets `workplace: {version, index, sha256, ...}`; workplace/index.json
lists every file with its byte size and SHA-256 so the page can refuse a stale file set.
Acceptance criteria (set here, checked by tests/web_workplace_check.cjs): the page reproduces persona_v4 for the
sample conditions to 1e-4 in probability and max(0.5 person, 1e-5) in the denominator (counts are stored rounded to 0.01 person); total added size under 80 MB; a single municipality file under 1 MB.
"""
import json,hashlib
import numpy as np
import pandas as pd
from paths import OUTPUT,WEB,REPORTS,SOURCES

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    d=np.load(OUTPUT/'workplace_c.npz');areas=d['areas'].tolist();oi=d['origin'];di=d['dest'];ci=d['category'];X=d['x'].astype(float);U=d['unknown_workplace'].astype(float)
    summ=pd.read_csv(SOURCES/'workplace/od_origin_summary_tidy.csv.gz',dtype={'origin':str}).set_index('origin')
    payload=json.loads((WEB/'graph.json').read_text(encoding='utf-8'));g=payload['graph']
    out=WEB/'workplace';out.mkdir(exist_ok=True);index={}
    def rnd(row):return [round(float(v),2) for v in row]
    by_o={};by_d={}
    for p in range(len(oi)):by_o.setdefault(int(oi[p]),[]).append(p);by_d.setdefault(int(di[p]),[]).append(p)
    total_bytes=0;largest=0
    for i,code in enumerate(areas):
        ps=by_o.get(i,[]);rows=[[areas[int(di[p])],int(ci[p]),rnd(X[p])] for p in sorted(ps,key=lambda p:-X[p].sum())]
        home=float(summ.home.get(code,0.)) if code in summ.index else 0.
        o={'code':code,'rows':rows,'unknown':rnd(U[i]),'home':home,'model_version':str(d['model_version'])}
        b=json.dumps(o,ensure_ascii=False,separators=(',',':')).encode();f=out/f'o_{code}.json';f.write_bytes(b);index[f'workplace/o_{code}.json']=[len(b),sha(b)];total_bytes+=len(b);largest=max(largest,len(b))
        ps=by_d.get(i,[]);rows=[[areas[int(oi[p])],int(ci[p]),rnd(X[p])] for p in sorted(ps,key=lambda p:-X[p].sum())]
        w={'code':code,'rows':rows,'model_version':str(d['model_version'])}
        b=json.dumps(w,ensure_ascii=False,separators=(',',':')).encode();f=out/f'd_{code}.json';f.write_bytes(b);index[f'workplace/d_{code}.json']=[len(b),sha(b)];total_bytes+=len(b);largest=max(largest,len(b))
    # areas of the held-out evaluation (tables 9 / 10): taken from the saved verification rows, not a hand-written list
    hv=pd.read_csv(REPORTS/'workplace_c_heldout.csv',dtype={'area':str,'table':str})
    ev={'model_version':str(d['model_version']),'source':'validation/workplace_c_heldout.csv','table9_residence_areas':sorted(hv[hv.table=='9'].area.unique().tolist()),'table10_workplace_areas':sorted(hv[hv.table=='10'].area.unique().tolist())}
    eb=json.dumps(ev,ensure_ascii=False,separators=(',',':')).encode();(out/'evaluated_areas.json').write_bytes(eb);index['workplace/evaluated_areas.json']=[len(eb),sha(eb)];total_bytes+=len(eb);largest=max(largest,len(eb))
    # the index is written after every file is registered, so graph.workplace.files and the index agree
    ib=json.dumps({'model_version':str(d['model_version']),'files':index},ensure_ascii=False,separators=(',',':')).encode();(out/'index.json').write_bytes(ib)
    g['workplace']={'version':str(d['model_version']),'stage':'C','evaluated_areas':'workplace/evaluated_areas.json','index':'workplace/index.json','index_sha256':sha(ib),'files':len(index),'industry_codes':d['industry_codes'].tolist(),'categories':d['categories'].tolist(),
                    'note':'2020 census 従業地・通学地集計, 15歳以上就業者 both sexes; residence-side rows o_<code>.json, workplace-side rows d_<code>.json; unknown workplace outside the distribution'}
    if '+C' not in payload.get('dataset_version',''):payload['dataset_version']=payload.get('dataset_version','')+'+C'
    (WEB/'graph.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    rep={'files':len(index),'total_bytes':total_bytes+len(ib),'largest_file_bytes':largest,'criteria':{'total_bytes_max':80_000_000,'file_bytes_max':1_000_000},'passed':total_bytes+len(ib)<80_000_000 and largest<1_000_000,'pairs':int(len(oi)),'persons':float(X.sum())}
    (REPORTS/'workplace_web_export.json').write_text(json.dumps(rep,indent=2));print(json.dumps(rep))
    if not rep['passed']:raise SystemExit(1)
if __name__=='__main__':main()
