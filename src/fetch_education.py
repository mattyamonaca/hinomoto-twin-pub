"""Download the raw public inputs for sex/education extension; no API key required."""
import base64,gzip,hashlib,json,re,time,urllib.parse,urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
WORKBOOKS={
 'census_education.xlsx':'https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201217&fileKind=0',
 'census_education_labor.xlsx':'https://www.e-stat.go.jp/stat-search/file-download?statInfId=000032201218&fileKind=0',
}
SID='0004008157'
def fetch_income(sex,model):
 dest=BASE/'raw/education'/f'income_education_{sex}.json.gz'
 if dest.exists():return
 p={k:v for k,v in model.items() if k not in ['matters','use_record']}
 p.update(rows=[],cols=[],tops=[],apiTops=[],currentRows=None,currentCols=None,mode='table',inputNumberOfRows=5000,inputNumberOfCols=100,movementId=0)
 for v in model['matters'].values():
  mid=v['matterId'];d={k:v[k] for k in ['matterId','tableName','dispTableName','positionNum']};d['allSelected']=0
  vals=list(v['listData'].values());pos={5:'rows',8:'rows',7:'cols'}.get(mid,'tops')
  if mid==3:vals=[x for x in vals if x['code']==sex]
  elif pos=='tops':vals=vals[:1]
  d['positionNum']={5:1,8:2,7:1}.get(mid,d['positionNum'])
  d['listData']=[dict(name=x['name'],code=x['code'],unit=x['unitName'],explanation=x['explanation']) for x in vals]
  p[pos].append(d)
 p['rows'].sort(key=lambda x:x['positionNum']);p['apiTops']=p['tops']
 for k in ['rows','cols','tops','apiTops']:p[k]=base64.b64encode(gzip.compress(json.dumps(p[k],ensure_ascii=False).encode())).decode()
 p={k:('' if v is None else int(v) if isinstance(v,bool) else v) for k,v in p.items()}
 for attempt in range(3):
  try:
   req=urllib.request.Request(f'https://www.e-stat.go.jp/dbview/api_get_result?sid={SID}',data=urllib.parse.urlencode(p).encode())
   with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
   vals=re.findall(r'<td class="stat-dbview-value">(.*?)</td>',data.get('table',''),re.S)
   if len(vals)!=16*15*17:raise ValueError(f'Unexpected income table size: {len(vals)}')
   with gzip.open(dest,'wt',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
   print(dest.name,len(vals),flush=True);return
  except Exception:
   if attempt==2:raise
   time.sleep(2)
def main():
 (BASE/'raw/education').mkdir(parents=True,exist_ok=True);(BASE/'sources/education').mkdir(parents=True,exist_ok=True)
 for name,url in WORKBOOKS.items():
  dest=BASE/'raw'/name
  if not dest.exists():
   with urllib.request.urlopen(url,timeout=180) as r:dest.write_bytes(r.read())
 metadata=BASE/'sources/education/income_model.json'
 if not metadata.exists():
  with urllib.request.urlopen(f'https://www.e-stat.go.jp/dbview/api_get_model?sid={SID}',timeout=120) as r:metadata.write_bytes(r.read())
 m=json.loads(metadata.read_text())
 for sex in ['0','1','2']:fetch_income(sex,m)
if __name__=='__main__':main()
