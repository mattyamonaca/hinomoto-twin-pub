"""Normalize ESS regional table 10-1 (sex x enrolment x status x industry x age) for the stage-A employment attributes.

Rows: area (00000 national, PP000 prefecture, C+code city), sex (0/1/2), education (0 total, 1 graduates, 2 enrolled),
status (0 total, 1 employees, 11 founders, 12 regular, 13 non-regular), industry (G00 total, G01..G20 major divisions;
sub-classes such as 051 are dropped), age columns 00 total, 01..13 (75+ merged from 75-79/80-84/85+).
"""
from paths import SOURCES,RAW
import numpy as np
import pandas as pd
import openpyxl
from parse_industry import number

def main():
 ws=openpyxl.load_workbook(RAW/'industry/ess_education_industry_age.xlsx',read_only=True).active
 recs=[]
 for r in ws.iter_rows(min_row=10,values_only=True):
  if r[1] is None:continue
  ind=str(r[9]).split('_')[0]
  if len(ind)!=2:continue                     # keep major divisions only
  acode,aname=str(r[1]).split('_',1);area='00000' if acode=='00' else acode+'000' if len(acode)==2 else 'C'+acode
  v=np.array([number(x) for x in r[10:24]])   # 00 total, 01..13 (13 = 75-79), then 80-84, 85+ ... check length
  recs.append((area,aname,str(r[3])[0],str(r[5])[0],str(r[7]).split('_')[0],'G'+ind,*v))
 ncols=len(recs[0])-6
 cols=['area','name','sex','education','status','industry']+[f'a{i:02}' for i in range(ncols)]
 df=pd.DataFrame(recs,columns=cols)
 # age columns: a00 total, a01..a12 = 15-19..70-74, a13 = 75+ (already merged in this table)
 age=[f'a{i:02}' for i in range(1,13)];old=[c for c in cols if c[0]=='a' and c[1:].isdigit() and int(c[1:])>=13]
 out=df[['area','name','sex','education','status','industry']].copy()
 for i,c in enumerate(age):out[f'{i+1:02}']=df[c]
 out['13']=df[old].sum(1);out['00']=df['a00']
 out.to_csv(SOURCES/'industry/ess_status_industry_age_tidy.csv.gz',index=False)
 print(len(out),'rows; areas',out.area.nunique(),'; age cols merged from',old, '; national total',float(out[(out.area=='00000')&(out.sex=='0')&(out.education=='0')&(out.status=='0')&(out.industry=='G00')]['00'].iloc[0]))
if __name__=='__main__':main()
