"""Fetch ESS 04000 (national education x status x age x income) by employment status for stage A, then normalize.

Same endpoint and table definition as fetch_education.py; the status dimension (matter 6) is filtered to
1 self-employed, 2 employees, 22 regular, 23 non-regular. Output: sources/industry/education_status_income_tidy.csv.gz
"""
from paths import CATALOG,SOURCES,RAW
import base64,gzip,html,json,re,time,urllib.parse,urllib.request
import pandas as pd
SID='0004008157';STATUSES=['1','2','22','23']

def fetch(sex,status,model):
 dest=RAW/'education'/f'income_education_{sex}_{status}.json.gz'
 if dest.exists():return dest
 p={k:v for k,v in model.items() if k not in ['matters','use_record']}
 p.update(rows=[],cols=[],tops=[],apiTops=[],currentRows=None,currentCols=None,mode='table',inputNumberOfRows=5000,inputNumberOfCols=100,movementId=0)
 for v in model['matters'].values():
  mid=v['matterId'];d={k:v[k] for k in ['matterId','tableName','dispTableName','positionNum']};d['allSelected']=0
  vals=list(v['listData'].values());pos={5:'rows',8:'rows',7:'cols'}.get(mid,'tops')
  if mid==3:vals=[x for x in vals if x['code']==sex]
  elif mid==6:vals=[x for x in vals if x['code']==status]
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
   if len(vals)!=16*15*17:raise ValueError(f'Unexpected table size: {len(vals)}')
   with gzip.open(dest,'wt',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
   print(dest.name,len(vals),flush=True);return dest
  except Exception:
   if attempt==2:raise
   time.sleep(2)

def main():
 (RAW/'education').mkdir(parents=True,exist_ok=True);(SOURCES/'industry').mkdir(parents=True,exist_ok=True)
 m=json.loads((CATALOG/'education/income_model.json').read_text());rows=[]
 for sex in ['1','2']:
  for st in STATUSES:
   d=json.load(gzip.open(fetch(sex,st,m),'rt'));body=d['table'].split('<tbody')[1].split('</tbody>')[0]
   for tr in re.findall(r'<tr>(.*?)</tr>',body,re.S):
    keys=re.findall(r'data-unique="([^"]+)"',tr);vals=re.findall(r'<td class="stat-dbview-value">(.*?)</td>',tr,re.S)
    if len(keys)!=2 or len(vals)!=17:raise ValueError('Table structure changed')
    age=keys[0].split('@')[-1];edu=keys[1]
    for inc,v in enumerate(vals):
     value=html.unescape(re.sub('<[^>]+>','',v)).strip();rows.append((sex,st,age,edu,f'{inc:02}',0. if value=='-' else float(value.replace(',',''))))
 f=pd.DataFrame(rows,columns=['sex','status','age','education','income','count'])
 assert len(f)==2*4*16*15*17 and not f.duplicated(['sex','status','age','education','income']).any()
 f.to_csv(SOURCES/'industry/education_status_income_tidy.csv.gz',index=False);print('education_status_income',len(f))
if __name__=='__main__':main()
