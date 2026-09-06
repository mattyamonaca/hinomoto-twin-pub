"""Optional raw-source download and parsing. Offline model rebuild uses externally configured normalized sources instead."""
from paths import CATALOG,RAW,CODE_ROOT
from pathlib import Path
import json,urllib.request,hashlib,subprocess,sys
def main():
 raw=RAW;raw.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((CATALOG/'manifest.json').read_text())
 for entry in manifest['sources']:
  if 'raw_filename' not in entry:continue
  dest=raw/entry['raw_filename']
  if not dest.exists():
   print('Downloading',entry['title'],flush=True)
   with urllib.request.urlopen(entry['url'],timeout=180) as r:dest.write_bytes(r.read())
  digest=hashlib.sha256(dest.read_bytes()).hexdigest()
  if digest!=entry['raw_sha256']:raise RuntimeError(f'Source changed: {dest.name}. Inspect before parsing; do not silently use different data.')
 for script in ['fetch_income.py','parse_census.py','parse_income.py','parse_tax.py']:
  subprocess.run([sys.executable,str(CODE_ROOT/'src'/script)],check=True)
if __name__=='__main__':main()
