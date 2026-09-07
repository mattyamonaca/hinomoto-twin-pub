"""Provenance strings for stored artifacts (Issue #34): which inputs, code commit and settings produced a file.

`stamp(stage, inputs=[paths], settings={...}, upstream={name: path})` returns a JSON string to store inside an npz
(`provenance=np.array(stamp(...))`) or a report. `read(npz)` parses it. `same_inputs(a, b)` compares fingerprints.
"""
import hashlib,json,os,subprocess,time
from pathlib import Path

def sha_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def code_commit():
    try:return subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True,cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except Exception:return 'unknown'
def stamp(stage,inputs=(),settings=None,upstream=None,extra=None):
    d={'stage':stage,'inputs':{Path(p).name:sha_file(p) for p in inputs if Path(p).is_file()},'settings':settings or {},'upstream':{k:sha_file(v) for k,v in (upstream or {}).items() if Path(v).is_file()},'code_commit':code_commit(),'created':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    if extra:d.update(extra)
    return json.dumps(d,ensure_ascii=False)
def read(npz):
    return json.loads(str(npz['provenance'])) if 'provenance' in npz.files else None
