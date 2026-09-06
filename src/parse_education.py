"""Normalize the education census cross-tabs and ESS 04000 without imputing unknowns."""
from paths import SOURCES,RAW
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip,html,json,re
import numpy as np
import pandas as pd
import openpyxl
DEST=SOURCES/'education'
EDUCATION=[
 ('E01','小学校・中学校','小学校と中学校を統合'),
 ('E02','高校・旧中相当','国勢調査の高校・旧中区分。専門学校2年未満を接続時に含む'),
 ('E03','短大・高専等','専門学校2年以上4年未満等を含む国勢調査区分'),
 ('E04','大学等','専門学校4年以上等を含む国勢調査区分。学士号の有無を意味しない'),
 ('E05','大学院','修士・専門職・博士を統合'),
 ('E06','在学中','最終卒業校は推定しない'),
 ('E07','未就学','学校に在学したことがない者'),
 ('E08','不詳','卒業学校不詳と在学か否か不詳を統合'),
]
CODES=[r[0] for r in EDUCATION]
def number(v):
 if v=='-':return 0.
 if isinstance(v,(int,float)):return float(v)
 raise ValueError(f'Unrecognized census value {v!r}')
def grouped(vals):
 t=np.array([number(v) for v in vals],float)
 out=np.array([t[2]+t[3],t[4],t[5],t[6],t[7],t[9],t[10],t[8]+t[11]])
 if abs(out.sum()-t[0])>1e-6:raise ValueError('Education components do not sum to published population.')
 return out

def census(kind):
 w=openpyxl.load_workbook(RAW/(kind+'.xlsx'),read_only=True,data_only=True);s=w.active;rows=[]
 for r in s.iter_rows(min_row=11,values_only=True):
  if kind=='census_education':geo,sex,age=r[2],r[3],r[4];status=None;vals=r[5:17]
  else:
   geo,sex,age=r[1],r[2],r[3];status=r[6].split('_')[0];vals=r[7:19]
   if status not in ['0','11','12','2','3']:continue
  age=age.split('_')[0]
  if not age.isdigit() or not 1<=int(age)<=17:continue
  code,name=geo.split('_',1);age=f'{min(int(age),13):02}'
  dims=[code,name,sex.split('_')[0],age]
  if status is not None:dims.append(status)
  rows.append(dims+grouped(vals).tolist())
 dims=['area','name','sex','age']+(['labor_status'] if kind.endswith('_labor') else [])
 f=pd.DataFrame(rows,columns=dims+CODES).groupby(dims,as_index=False)[CODES].sum()
 if f.empty or f.duplicated(dims).any():raise ValueError('Invalid census cross-table')
 f.to_csv(DEST/(kind+'_tidy.csv.gz'),index=False)
 print(kind,len(f),f.area.nunique(),flush=True)

def income():
 rows=[]
 for sex in ['0','1','2']:
  d=json.load(gzip.open(RAW/'education'/f'income_education_{sex}.json.gz','rt'))
  body=d['table'].split('<tbody')[1].split('</tbody>')[0]
  for tr in re.findall(r'<tr>(.*?)</tr>',body,re.S):
   keys=re.findall(r'data-unique="([^"]+)"',tr);vals=re.findall(r'<td class="stat-dbview-value">(.*?)</td>',tr,re.S)
   if len(keys)!=2 or len(vals)!=17:raise ValueError('Income table structure changed')
   age=keys[0].split('@')[-1];edu=keys[1]
   for inc,v in enumerate(vals):
    value=html.unescape(re.sub('<[^>]+>','',v)).strip();n=0. if value=='-' else float(value.replace(',',''))
    rows.append((sex,age,edu,f'{inc:02}',n,value))
 f=pd.DataFrame(rows,columns=['sex','age','education','income','count','raw_value'])
 assert len(f)==12240 and not f.duplicated(['sex','age','education','income']).any()
 f.to_csv(DEST/'income_education_tidy.csv.gz',index=False)
 print('income_education',len(f),flush=True)

def main():
 DEST.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(census,['census_education','census_education_labor']))
 income()
 pd.DataFrame(EDUCATION,columns=['education_code','education_label','note']).to_csv(DEST/'education_bins.csv',index=False)
if __name__=='__main__':main()
