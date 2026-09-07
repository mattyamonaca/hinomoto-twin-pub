"""Download the 2020 census household workbooks for stage B into raw/household, verify SHA-256 against the catalog, then normalize."""
from paths import CATALOG,RAW
import hashlib,json,subprocess,sys,urllib.request
from pathlib import Path

def main():
 manifest=json.loads((CATALOG/'household/manifest.json').read_text(encoding='utf-8'))
 for entry in manifest['sources']:
  dest=RAW/Path(entry['raw_file']).relative_to('raw');dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   print('Downloading',entry['title'],flush=True)
   with urllib.request.urlopen(entry['url'],timeout=300) as r:dest.write_bytes(r.read())
  digest=hashlib.sha256(dest.read_bytes()).hexdigest()
  if digest!=entry['raw_sha256']:raise RuntimeError(f'Source changed: {dest.name}. Inspect before parsing; do not silently use different data.')
 subprocess.run([sys.executable,str(Path(__file__).with_name('parse_household.py'))],check=True)
if __name__=='__main__':main()
