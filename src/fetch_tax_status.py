"""Fetch and normalize the FY2023 市町村税課税状況等の調 (総務省) municipal tables used ONLY for independent evaluation (Issue #21).

Tables (令和5年度 = income earned in 2022, the income year of the model):
  第2表 市町村別  個人の市町村民税の納税義務者等 : taxpayers by income type (給与所得者 / 営業等 / 農業 / その他), persons paying
                 both 均等割 and 所得割 (C), persons paying 均等割 only (F), 所得割額 (E)  -> raw/tax_status/J51-23-a.xlsx
  第11表 市町村別 課税標準額段階別所得割額等（合計）: 所得割の納税義務者数, 総所得金額等, 課税対象所得, 課税標準額 -> raw/tax_status/J51-23-b.xlsx
Neither table is an input of M0/M1/M2/M12 (the model's tax proxy is 市区町村のすがた2024, FY2022 = 2021 income, and the
production M12 uses beta=0, i.e. no tax feature at all). No bracket distribution by municipality is published; only totals.
Publisher: 総務省自治税務局. Licence: 政府標準利用規約（第2.0版）, CC BY 4.0 compatible. Nothing is imputed; '-' is 0.
Output: sources/tax_status/tax_status_2023_tidy.csv (one row per municipality, 6-digit 団体コード reduced to the 5-digit code).
"""
from paths import CATALOG,RAW,SOURCES
import hashlib,json,urllib.request
from pathlib import Path
import openpyxl
import pandas as pd

DEST=SOURCES/'tax_status'
def num(v):
 if v in (None,'','-',' ','…'):return 0.
 return float(v) if isinstance(v,(int,float)) else float(str(v).replace(',',''))

def fetch(manifest):
 for e in manifest['sources']:
  dest=RAW/Path(e['raw_file']).relative_to('raw');dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   print('Downloading',e['title'],flush=True)
   req=urllib.request.Request(e['url'],headers={'User-Agent':'hinomoto-twin (public statistics fetch)'})
   with urllib.request.urlopen(req,timeout=300) as r:dest.write_bytes(r.read())
  digest=hashlib.sha256(dest.read_bytes()).hexdigest()
  if digest!=e['raw_sha256']:raise RuntimeError(f'Source changed: {dest.name} ({digest}); inspect before using.')

def parse():
 ws=openpyxl.load_workbook(RAW/'tax_status/J51-23-a.xlsx',read_only=True).active;recs={}
 for r in ws.iter_rows(min_row=5,values_only=True):
  if r[1] is None or r[4] is None:continue
  code=str(r[1])[:5];d=recs.setdefault(code,{'area':code,'prefecture':r[2],'name':r[3]})
  kind={'給与所得者':'salary','営業等所得者':'business','農業所得者':'farm','その他の所得者':'other','家屋敷等のみ':'property_only','計':'total'}.get(str(r[4]).strip())
  if kind is None:continue
  d[f'{kind}_taxpayers']=num(r[5]);d[f'{kind}_income_levy_payers']=num(r[8]);d[f'{kind}_income_levy_thousand_yen']=num(r[11]);d[f'{kind}_percapita_levy_only']=num(r[13])
 ws=openpyxl.load_workbook(RAW/'tax_status/J51-23-b.xlsx',read_only=True).active
 for r in ws.iter_rows(min_row=5,values_only=True):
  if r[1] is None or str(r[4]).strip()!='市町村民税':continue
  code=str(r[1])[:5];d=recs.setdefault(code,{'area':code,'prefecture':r[2],'name':r[3]})
  d['income_levy_taxpayers']=num(r[5]);d['total_income_thousand_yen']=num(r[6]);d['taxable_income_thousand_yen']=num(r[13]);d['tax_base_thousand_yen']=num(r[14]);d['income_levy_after_credits_thousand_yen']=num(r[15])
 df=pd.DataFrame(list(recs.values())).sort_values('area');df['fiscal_year']=2023;df['income_year']=2022
 DEST.mkdir(parents=True,exist_ok=True);df.to_csv(DEST/'tax_status_2023_tidy.csv',index=False);return df

def main():
 manifest=json.loads((CATALOG/'tax_status/manifest.json').read_text(encoding='utf-8'))
 fetch(manifest);df=parse()
 print('municipalities',len(df),'salary taxpayers',df.salary_taxpayers.sum(),'income-levy taxpayers',df.income_levy_taxpayers.sum())
if __name__=='__main__':main()
