"""Download the 2020 census 従業地・通学地集計 workbooks for stage C (issue #24) into raw/workplace and normalize them.

The catalog (catalog/workplace/manifest.json) lists 142 workbooks: table 3 (OD, one per prefecture of residence),
table 8 (industry x commuting category per municipality), tables 9 and 10 (ODI for large cities, evaluation only).
On the first fetch the SHA-256 of each workbook is recorded in the catalog; afterwards a changed file is an error.

  python src/download_workplace.py            # fetch what is missing, verify, then parse
  python src/download_workplace.py --tables 3 8   # subset
"""
from paths import CATALOG,RAW
import argparse,hashlib,json,subprocess,sys,time,urllib.request
from pathlib import Path

MANIFEST=CATALOG/'workplace/manifest.json'

def fetch(url,dest,retries=3):
 for i in range(retries):
  try:
   with urllib.request.urlopen(url,timeout=600) as r:data=r.read()
   if len(data)<10000 or not data.startswith(b'PK'):raise RuntimeError(f'unexpected payload ({len(data)} bytes) for {url}')
   dest.write_bytes(data);return
  except Exception as e:
   if i==retries-1:raise
   print('retry',dest.name,e,flush=True);time.sleep(5)

def main(tables=None,parse=True):
 manifest=json.loads(MANIFEST.read_text(encoding='utf-8'));changed=False
 for src in manifest['sources']:
  if tables and src['table'] not in tables:continue
  for f in src['files']:
   dest=RAW/Path(f['raw_file']).relative_to('raw');dest.parent.mkdir(parents=True,exist_ok=True)
   if not dest.exists():print('Downloading table',src['table'],f['label'],flush=True);fetch(f['url'],dest)
   digest=hashlib.sha256(dest.read_bytes()).hexdigest()
   if 'raw_sha256' not in f:f['raw_sha256']=digest;f['raw_bytes']=dest.stat().st_size;changed=True
   elif f['raw_sha256']!=digest:raise RuntimeError(f'Source changed: {dest.name}. Inspect before parsing; do not silently use different data.')
 if changed:MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=1),encoding='utf-8');print('Recorded SHA-256 for new workbooks in',MANIFEST)
 if parse:subprocess.run([sys.executable,str(Path(__file__).with_name('parse_workplace.py'))],check=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 p.add_argument('--tables',nargs='*');p.add_argument('--no-parse',action='store_true');a=p.parse_args()
 main(a.tables,not a.no_parse)
