"""Assemble static UI code with an independently supplied web dataset."""
import argparse
import json
from pathlib import Path
import shutil
from paths import CODE_ROOT, WEB

def build(graph_path, destination):
    payload=json.loads(Path(graph_path).read_text(encoding='utf-8'))
    if payload.get('schema_version') not in (1,2) or not isinstance(payload.get('graph'),dict):
        raise ValueError('Expected web dataset schema_version=1 and graph object')
    required={'prefs','munis','pop','q','rates','ess','xc','xd','e','rs','ag','shrink','sens','sens_or'}
    if not required<=payload['graph'].keys():raise ValueError('Incomplete web dataset')
    destination=Path(destination).resolve()
    if destination==CODE_ROOT/'site':raise ValueError('Build output must be separate from site source')
    destination.mkdir(parents=True,exist_ok=True)
    for file in (CODE_ROOT/'site').iterdir():
        if file.is_file():shutil.copy2(file,destination/file.name)
    data=destination/'data';data.mkdir(exist_ok=True)
    shutil.copy2(graph_path,data/'graph.json')
    print(f'Site assembled at {destination}; dataset={payload.get("dataset_version", "unspecified")}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,default=WEB/'graph.json')
    parser.add_argument('--output',type=Path,default=CODE_ROOT/'dist/site')
    args=parser.parse_args();build(args.graph,args.output)
