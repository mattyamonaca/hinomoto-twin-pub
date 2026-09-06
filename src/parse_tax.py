import xlrd,pandas as pd
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
w=xlrd.open_workbook(str(BASE/'raw/economic.xlsx'));s=w.sheet_by_index(0);rows=[]
for i in range(10,s.nrows):
 r=s.row_values(i);code=str(r[1]).strip()
 if len(code)!=5 or not code.isdigit():continue
 rows.append((code,str(r[8]).strip(),r[10] if isinstance(r[10],float) else None,r[11] if isinstance(r[11],float) else None,2022))
f=pd.DataFrame(rows,columns=['area','name','taxable_income_million_yen','income_taxpayers','fiscal_year']);f.to_csv(BASE/'sources/tax_tidy.csv',index=False)
print(f.shape);print(f[f.area.isin(['13000','13100','13103','13121','01100'])])
