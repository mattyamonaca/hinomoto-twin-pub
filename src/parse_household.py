"""Normalize the 2020 census household tables used by stage B (issue #16) into sources/household/.

Tables (人口等基本集計, statInfId in catalog/household/manifest.json):
  12-3 head sex x head age x family type -> general households        (municipality)   heads_tidy
  12-4 same -> general household members                               (municipality)   heads_members_tidy
  6-3  household size (1..10+) -> general households                  (municipality)   size_tidy
  4-3  sex x age x marital status -> population 15+                    (municipality)   marital_tidy
  13-2 sex x age(0..100+) x family type x relationship -> members      (pref, big cities) relationship_tidy
  9-1  family type x presence of members under 6/12/15/18/20, 3-gen    (municipality)   family_age_class_tidy (held-out)
  26-1 presence of 65+ member x size                                   (municipality)   elderly_size_tidy (held-out)
  8-1  presence of young member x size                                 (municipality)   age_class_size_tidy (held-out)
  参考表1-4 population by sex x age incl. 0-14                          (municipality)   population_all_ages_tidy
Ages are 18 bands A00..A17: 0-4, 5-9, ..., 80-84, 85+. Family types F1 夫婦のみ, F2 夫婦と子, F3 ひとり親と子 (男親+女親),
F4 核家族以外の親族世帯, F5 非親族を含む世帯, F6 単独世帯, F7 不詳. Nothing is imputed; '-' is 0.
"""
from paths import SOURCES,RAW
import numpy as np
import pandas as pd
import openpyxl
DEST=SOURCES/'household';HH=RAW/'household'
AGE18=[f'A{i:02}' for i in range(18)]
FAMILY=[('F1','111','夫婦のみの世帯'),('F2','112','夫婦と子供から成る世帯'),('F3','113+114','男親又は女親と子供から成る世帯'),('F4','12','核家族以外の親族世帯'),('F5','2','非親族を含む世帯'),('F6','3','単独世帯'),('F7','4','家族類型不詳')]
REL=[('R01','世帯主'),('R02','配偶者'),('R03','子'),('R04','子の配偶者'),('R05','世帯主の父母'),('R06','世帯主の配偶者の父母'),('R07','孫'),('R08','祖父母'),('R09','兄弟姉妹'),('R10','他の親族'),('R11','住み込みの雇人'),('R12','その他'),('R13','続き柄不詳')]
def num(v):
 if v in ('-',None,'',' ','…','X'):return 0.
 return float(v) if isinstance(v,(int,float)) else float(str(v).replace(',',''))
def merge85(vals21):
 """21 five-year bands (0-4 .. 100+) -> 18 bands with 85+ merged."""
 v=np.array([num(x) for x in vals21]);return np.concatenate([v[:17],[v[17:].sum()]])
def split_geo(cell):
 code,name=str(cell).split('_',1);return code,name

def heads(kind):
 """12-3 (households) / 12-4 (members): area x head sex x head age(18: 15歳未満 merged into A00..A02 -> keep as 'U15') x family type."""
 ws=openpyxl.load_workbook(HH/('head_age_family_type.xlsx' if kind=='households' else 'head_age_family_type_persons.xlsx'),read_only=True).active
 hdr=[str(c) for c in list(ws.iter_rows(min_row=8,max_row=8,values_only=True))[0]];col={h.split('_')[0]:i for i,h in enumerate(hdr)}
 def fam(r):
  g=lambda code:num(r[col[code]])
  return [g('111'),g('112'),g('113')+g('114'),g('12'),g('2'),g('3'),g('4')]
 rows=[]
 for r in ws.iter_rows(min_row=11,values_only=True):
  if r[3] not in ('1_男','2_女'):continue
  age=str(r[4]).split('_')[0]
  if not age.isdigit() or int(age)==0 or int(age)>17:continue   # 01 <15 .. 16 85+, 17 age unknown; skip totals (00) and 再掲
  band='U15' if age=='01' else 'UNK' if age=='17' else f'A{int(age)+1:02}'
  code,name=split_geo(r[2]);rows.append((code,name,r[0],r[3][0],band,*fam(r)))
 df=pd.DataFrame(rows,columns=['area','name','type','sex','head_age']+[f[0] for f in FAMILY])
 df.to_csv(DEST/f'heads_{kind}_tidy.csv.gz',index=False);return df

def size():
 ws=openpyxl.load_workbook(HH/'household_size.xlsx',read_only=True).active;rows=[]
 for r in ws.iter_rows(min_row=11,values_only=True):
  code,name=split_geo(r[2]);rows.append((code,name,r[0],*[num(x) for x in r[4:14]]))
 df=pd.DataFrame(rows,columns=['area','name','type']+[f'S{i:02}' for i in range(1,11)]);df.to_csv(DEST/'size_tidy.csv.gz',index=False);return df

def marital():
 ws=openpyxl.load_workbook(HH/'marital_status.xlsx',read_only=True).active;rows=[]
 for r in ws.iter_rows(min_row=12,values_only=True):
  if r[3]!='0_国籍総数' or r[4] not in ('1_男','2_女'):continue
  st=str(r[5]).split('_')[0]
  if st not in ('1','2','3','4','5'):continue
  code,name=split_geo(r[2]);v=np.array([num(x) for x in r[7:25]]);v15=np.concatenate([v[:14],[v[14:].sum()]])   # 15-19 .. 80-84, 85+
  rows.append((code,name,r[0],r[4][0],{'1':'single','2':'married','3':'widowed','4':'divorced','5':'unknown'}[st],*v15))
 df=pd.DataFrame(rows,columns=['area','name','type','sex','marital']+AGE18[3:]);df.to_csv(DEST/'marital_tidy.csv.gz',index=False);return df

def relationship():
 """13-2: area x sex x family type (coarse: 11 nuclear total, 111 couple only, 12, 2, 3, 4) x age x relationship."""
 ws=openpyxl.load_workbook(HH/'relationship.xlsx',read_only=True).active;rows=[]
 for r in ws.iter_rows(min_row=11,values_only=True):
  if r[3] not in ('1_男','2_女'):continue
  ft=str(r[4]).split('_')[0];age=str(r[5]).split('_')[0]
  if ft not in ('11','111','12','2','3','4') or not age.isdigit() or int(age)>21:continue
  code,name=split_geo(r[2]);a=int(age)-1;band=f'A{min(a,17):02}'
  vals=[num(x) for x in r[7:20]]
  rows.append((code,name,r[0],r[3][0],ft,band,*vals))
 df=pd.DataFrame(rows,columns=['area','name','type','sex','family_type','age']+[x[0] for x in REL])
 df=df.groupby(['area','name','type','sex','family_type','age'],as_index=False).sum()
 df.to_csv(DEST/'relationship_tidy.csv.gz',index=False);return df

def simple(fname,out,keys,first_col,ncols,keep=None,key_col=3):
 ws=openpyxl.load_workbook(HH/fname,read_only=True).active;rows=[]
 for r in ws.iter_rows(min_row=11,values_only=True):
  k=str(r[key_col]).split('_')[0] if keys else None
  if keep and k not in keep:continue
  code,name=split_geo(r[2]);rows.append((code,name,r[0],k,*[num(x) for x in r[first_col:first_col+ncols]]))
 return pd.DataFrame(rows,columns=['area','name','type','key']+[f'c{i}' for i in range(ncols)])

def population_all_ages():
 ws=openpyxl.load_workbook(RAW/'census_population.xlsx',read_only=True).active;rows=[]
 for r in ws.iter_rows(min_row=11,values_only=True):
  if r[0]!='0_国籍総数' or r[1] not in ('1_男','2_女'):continue
  code,name=split_geo(r[4]);rows.append((code,name,r[2],r[1][0],*merge85(r[6:27])))
 df=pd.DataFrame(rows,columns=['area','name','type','sex']+AGE18);df.to_csv(DEST/'population_all_ages_tidy.csv.gz',index=False);return df

def main():
 DEST.mkdir(parents=True,exist_ok=True)
 h=heads('households');m=heads('members');s=size();ma=marital();rel=relationship();pop=population_all_ages()
 fa=simple('family_type_age_class.xlsx','x',True,5,7,key_col=4);fa.columns=['area','name','type','family_type','total','u6','u12','u15','u18','u20','three_gen'];fa.to_csv(DEST/'family_age_class_tidy.csv.gz',index=False)
 el=simple('elderly_size.xlsx','x',True,4,8);el.columns=['area','name','type','elderly_class']+[f'S{i}' for i in ['00','01','02','03','04','05','06','07p']];el.to_csv(DEST/'elderly_size_tidy.csv.gz',index=False)
 ac=simple('age_class_size.xlsx','x',True,4,8);ac.columns=['area','name','type','age_class']+[f'S{i}' for i in ['00','01','02','03','04','05','06','07p']];ac.to_csv(DEST/'age_class_size_tidy.csv.gz',index=False)
 pd.DataFrame(FAMILY,columns=['family_code','census_codes','label']).to_csv(DEST/'family_type_bins.csv',index=False)
 pd.DataFrame(REL,columns=['relationship_code','label']).to_csv(DEST/'relationship_bins.csv',index=False)
 nat=h[h.area=='00000'];print('heads rows',len(h),'areas',h.area.nunique(),'national households (both sexes, all types)',float(nat[[f[0] for f in FAMILY]].to_numpy().sum()))
 print('members',len(m),'size',len(s),'marital',len(ma),'relationship',len(rel),'areas',rel.area.nunique(),'pop',len(pop))
if __name__=='__main__':main()
