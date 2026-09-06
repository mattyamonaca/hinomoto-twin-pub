from paths import CATALOG,SOURCES,RAW
import json,gzip,base64,urllib.request,urllib.parse,re,time,csv,html
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=RAW
m=json.load(open(CATALOG/'income_model.json'))
def fetch(sex,status):
 name=f'income_{sex}_{status}.json.gz'; dest=ROOT/name
 if dest.exists(): return name
 p={k:v for k,v in m.items() if k not in ['matters','use_record']}
 p.update(rows=[],cols=[],tops=[],apiTops=[],currentRows=None,currentCols=None,mode='table',inputNumberOfRows=5000,inputNumberOfCols=100,movementId=0)
 for v in m['matters'].values():
  mid=v['matterId']; d={k:v[k] for k in ['matterId','tableName','dispTableName','positionNum']};d['allSelected']=0
  vals=list(v['listData'].values());pos={1:'rows',6:'rows',7:'cols'}.get(mid,'tops')
  if mid in [3,5]: vals=[x for x in vals if x['code']=={3:sex,5:status}[mid]]
  elif pos=='tops': vals=vals[:1]
  d['positionNum']={1:1,6:2,7:1}.get(mid,d['positionNum'])
  d['listData']=[dict(name=x['name'],code=x['code'],unit=x['unitName'],explanation=x['explanation']) for x in vals]
  p[pos].append(d)
 p['rows'].sort(key=lambda x:x['positionNum']);p['apiTops']=p['tops']
 for k in ['rows','cols','tops','apiTops']:
  p[k]=base64.b64encode(gzip.compress(json.dumps(p[k],ensure_ascii=False).encode())).decode()
 p={k:('' if v is None else int(v) if isinstance(v,bool) else v) for k,v in p.items()}
 for attempt in range(3):
  try:
   r=urllib.request.urlopen(urllib.request.Request('https://www.e-stat.go.jp/dbview/api_get_result?sid=0004008500',data=urllib.parse.urlencode(p).encode()),timeout=120)
   data=json.load(r)
   assert 'table' in data,str(data)[:200]
   vals=re.findall(r'<td class="stat-dbview-value">(.*?)</td>',data['table'],re.S)
   assert len(vals)==134*17*14,(len(vals),data.get('moveData'))
   with gzip.open(dest,'wt') as f:json.dump(data,f,ensure_ascii=False)
   print(name,len(vals),flush=True);return name
  except Exception as ex:
   print('retry',name,repr(ex),flush=True)
   if attempt==2: raise
   time.sleep(2)
if __name__=='__main__':
 ROOT.mkdir(parents=True,exist_ok=True)
 import sys
 tasks=[('0','0')] if '--probe' in sys.argv else [(s,k) for s in ['0','1','2'] for k in ['0','1','2','22','23']]
 with ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(lambda t:fetch(*t),tasks))
