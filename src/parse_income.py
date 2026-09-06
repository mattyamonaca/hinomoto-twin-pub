import json,gzip,re,html
from pathlib import Path
import pandas as pd
BASE=Path(__file__).resolve().parents[1]
root=BASE/'raw'
rows=[]
expected={f'income_{s}_{k}.json.gz' for s in ['0','1','2'] for k in ['0','1','2','22','23']}
files=sorted(root.glob('income_*_*.json.gz'))
if {p.name for p in files} != expected:raise ValueError('Expected exactly 15 sex/status income responses; run fetch_income.py first.')
for file in files:
 _,sex,status=file.name.split('.')[0].split('_');d=json.load(gzip.open(file,'rt'));body=d['table'].split('<tbody')[1].split('</tbody>')[0]
 for tr in re.findall(r'<tr>(.*?)</tr>',body,re.S):
  keys=re.findall(r'data-unique="([^"]+)"',tr)
  vals=re.findall(r'<td class="stat-dbview-value">(.*?)</td>',tr,re.S)
  assert len(keys)==2 and len(vals)==14
  area=keys[0].split('@')[-1];income=keys[1]
  for age,val in enumerate(vals):
   val=html.unescape(re.sub('<[^>]+>','',val)).strip(); n=0 if val=='-' else float(val.replace(',',''))
   rows.append((area,sex,status,f'{age:02d}',income,n,val))
f=pd.DataFrame(rows,columns=['area','sex','status','age','income','count','raw_value'])
assert len(f)==478380, f'Unexpected source cell count: {len(f)}'
assert not f.duplicated(['area','sex','status','age','income']).any()
f.to_csv(BASE/'sources/income_tidy.csv.gz',index=False)
print(f.shape);print(f[(f.area=='00000')&(f.sex=='0')&(f.age=='00')].groupby('status').apply(lambda x:pd.Series({'total':x[x.income=='00']['count'].sum(),'known':x[x.income!='00']['count'].sum()}),include_groups=False))
