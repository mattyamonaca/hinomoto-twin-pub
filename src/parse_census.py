from paths import SOURCES,RAW
from pathlib import Path
import openpyxl,pandas as pd
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
R=RAW

def run(kind):
 SOURCES.mkdir(parents=True,exist_ok=True)
 out=SOURCES/(kind+'_tidy.csv.gz')
 rows=[];p=R/(kind+'.xlsx');w=openpyxl.load_workbook(p,read_only=True,data_only=True);s=w.active
 for r in s.iter_rows(min_row=11,values_only=True):
  if kind=='census_population':
   if r[0]!='0_国籍総数':continue
   geo,sex,typ=r[4],r[1],r[2]
   for age in range(1,14):
    n=r[age+8] if age<13 else sum(float(x) if x!='-' else 0 for x in r[21:27])
    rows.append((geo.split('_',1)[0],geo.split('_',1)[1],typ,sex[0],f'{age:02}',n))
  elif kind=='census_imputed_age':
   age=r[4].split('_')[0]
   if not age.isdigit() or not 1<=int(age)<=15:continue
   geo=r[2];age=f'{min(13,int(age)):02}'
   rows.append((geo.split('_',1)[0],geo.split('_',1)[1],r[0],r[3][0],age,*r[5:17]))
  elif kind=='census_imputed_detailed_status':
   if r[5]!='0_総数':continue
   geo=r[2];rows.append((geo.split('_',1)[0],geo.split('_',1)[1],r[0],r[3][0],*r[6:16]))
  elif kind=='census_age_status':
   if r[3]!='0_総数' or r[5]!='0_総数':continue
   age=r[4].split('_')[0]
   if not age.isdigit() or not 1<=int(age)<=15:continue
   geo=r[1];age=f'{min(13,int(age)):02}'
   rows.append((geo.split('_',1)[0],geo.split('_',1)[1],r[0],r[2][0],age,*r[6:17]))
 cols=['area','name','type','sex']
 if kind=='census_population':cols+=['age','population']
 elif kind=='census_imputed_age':cols+=['age','population','labor','employed','main','house_work','school_work','absent','unemployed','inactive','house','school','other']
 else:
  if kind=='census_age_status':cols+=['age']
  cols+=['employed','employee','regular','dispatch','part_other','executive','self_with','self_without','family','homework']
  if kind=='census_age_status':cols+=['unknown']
 f=pd.DataFrame(rows,columns=cols)
 dims=[x for x in ['area','name','type','sex','age'] if x in f]
 nums=[c for c in cols if c not in dims]
 f[nums]=f[nums].replace('-',0).astype(float)
 f=f.groupby(dims,as_index=False)[nums].sum()
 f.to_csv(out,index=False)
 print(kind,f.shape,f[f.sex=='0'].groupby('type').area.nunique().to_dict(),flush=True)
 print(f[(f.sex=='0')&(f.area.isin(['00000','01100','01101','13100','13101']))].head(8).to_string(index=False),flush=True)
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(run,['census_population','census_imputed_age','census_imputed_detailed_status','census_age_status']))
