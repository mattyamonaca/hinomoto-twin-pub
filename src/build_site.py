"""Assemble static UI code with an independently supplied web dataset."""
import argparse
import json
from pathlib import Path
import shutil
from paths import CODE_ROOT, WEB

def build(graph_path, destination):
    payload=json.loads(Path(graph_path).read_text(encoding='utf-8'))
    if payload.get('schema_version') not in (1,2,3) or not isinstance(payload.get('graph'),dict):
        raise ValueError('Expected web dataset schema_version 1-3 and graph object')
    required={'prefs','munis','pop','q','rates','ess','xc','xd','e','rs','ag','shrink','sens','sens_or'}
    if not required<=payload['graph'].keys():raise ValueError('Incomplete web dataset')
    destination=Path(destination).resolve()
    if destination==CODE_ROOT/'site':raise ValueError('Build output must be separate from site source')
    destination.mkdir(parents=True,exist_ok=True)
    for file in (CODE_ROOT/'site').iterdir():
        if file.is_file():shutil.copy2(file,destination/file.name)
    data=destination/'data';data.mkdir(exist_ok=True)
    shutil.copy2(graph_path,data/'graph.json')
    emp=payload['graph'].get('emp')
    if emp:
        web=Path(graph_path).parent
        for rel in [emp['inputs_file']]+list(emp['agg_files'].values()):
            src=web/rel
            if not src.is_file():raise FileNotFoundError(f'Stage-A web file missing: {src}')
            (data/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,data/rel)
    wp=payload['graph'].get('workplace')
    if wp:
        web=Path(graph_path).parent;src=web/'workplace'
        if not (src/'index.json').is_file():raise FileNotFoundError(f'Stage-C web files missing: {src}')
        shutil.copytree(src,data/'workplace',dirs_exist_ok=True)
    hh=payload['graph'].get('household')
    if hh:
        web=Path(graph_path).parent
        for c,info in hh['codes'].items():
            src=web/info['file']
            if not src.is_file():raise FileNotFoundError(f'Stage-B web file missing: {src}')
            (data/info['file']).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,data/info['file'])
    print(f'Site assembled at {destination}; dataset={payload.get("dataset_version", "unspecified")}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,default=WEB/'graph.json')
    parser.add_argument('--output',type=Path,default=CODE_ROOT/'dist/site')
    args=parser.parse_args();build(args.graph,args.output)
