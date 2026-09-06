"""Download the two industry workbooks for the M2 experiment into raw/industry and verify their SHA-256 against the catalog."""
from paths import CATALOG,RAW
import hashlib,json,subprocess,sys,urllib.request
from pathlib import Path

def workbook_entries(manifest):
 """Entries fetched here: single workbooks with raw_file + raw_sha256. Entries with raw_responses (dbview
 responses) are fetched by fetch_employment.py and are skipped, not treated as an error."""
 out=[]
 for e in manifest['sources']:
  if 'raw_file' in e and 'raw_sha256' in e:out.append(e)
  elif 'raw_responses' in e:continue
  else:raise ValueError(f"Manifest entry without raw_file/raw_sha256 or raw_responses: {e.get('title')}")
 return out

def main():
 manifest=json.loads((CATALOG/'industry/manifest.json').read_text(encoding='utf-8'))
 for entry in workbook_entries(manifest):
  dest=RAW/Path(entry['raw_file']).relative_to('raw');dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   print('Downloading',entry['title'],flush=True)
   with urllib.request.urlopen(entry['url'],timeout=300) as r:dest.write_bytes(r.read())
  digest=hashlib.sha256(dest.read_bytes()).hexdigest()
  if digest!=entry['raw_sha256']:raise RuntimeError(f'Source changed: {dest.name}. Inspect before parsing; do not silently use different data.')
 subprocess.run([sys.executable,str(Path(__file__).with_name('parse_industry.py'))],check=True)
 # the stage-A table 10-1 is also a workbook in this manifest; normalize it when present
 if (RAW/'industry/ess_education_industry_age.xlsx').exists():subprocess.run([sys.executable,str(Path(__file__).with_name('parse_employment.py'))],check=True)
if __name__=='__main__':main()
