"""Import data separately from code; never overwrite different existing content."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import urllib.request
from paths import CATALOG, PATHS

def digest(data): return hashlib.sha256(data).hexdigest()

def write_new(path, data):
    path = Path(path)
    if path.exists():
        if digest(path.read_bytes()) != digest(data):
            raise FileExistsError(f'Different data already exists: {path}. Use a separate data root.')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(data)
    try: temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)

def graph_from_html(data):
    match = re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', data.decode('utf-8'), re.S)
    if not match: raise ValueError('Legacy HTML has no graph data')
    graph = json.loads(match.group(1))
    return json.dumps({'schema_version':1, 'dataset_version':'2020-2022-v2-20260906', 'graph':graph}, ensure_ascii=False, separators=(',',':')).encode()

def destination(relative, paths):
    parts = Path(relative).parts
    if len(parts)<2 or '..' in parts or Path(relative).is_absolute(): raise ValueError(f'Invalid dataset path: {relative}')
    roots = {'raw':paths.raw, 'sources':paths.sources, 'data':paths.output, 'validation':paths.reports, 'web':paths.web}
    if parts[0] not in roots: raise ValueError(f'Unsupported dataset directory: {relative}')
    root = roots[parts[0]].resolve()
    target = root.joinpath(*parts[1:]).resolve()
    if not target.is_relative_to(root): raise ValueError(f'Dataset path escapes its root: {relative}')
    return target

def check_sources(directory):
    schema = json.loads((CATALOG/'source_schema.json').read_text())
    for relative, columns in schema['tables'].items():
        path = directory/relative
        if not path.is_file(): raise FileNotFoundError(f'Missing normalized table: {path}. Import a dataset or run fetch/prepare first.')
        opener = gzip.open if path.suffix=='.gz' else open
        with opener(path, 'rt', encoding='utf-8', newline='') as f:
            header = next(csv.reader(f), [])
        if header != columns: raise ValueError(f'Incompatible columns in {path}: expected {columns}, got {header}')

def migrate(legacy, paths=PATHS):
    legacy = Path(legacy).resolve()
    for name, target in [('raw',paths.raw),('sources',paths.sources),('data',paths.output),('validation',paths.reports)]:
        source = legacy/name
        if source.resolve()==target.resolve() or target.resolve().is_relative_to(source.resolve()):
            raise ValueError('Migration destination must be separate from the legacy directory')
        if source.exists():
            for file in sorted(source.rglob('*')):
                if file.is_file(): write_new(target/file.relative_to(source), file.read_bytes())
    example = legacy/'examples_v2.csv'
    if example.exists(): write_new(paths.output/example.name, example.read_bytes())
    html = legacy/'site/index.html'
    if html.exists() and 'id="graph-data"' in html.read_text(encoding='utf-8'):
        write_new(paths.web/'graph.json', graph_from_html(html.read_bytes()))
    check_sources(paths.sources)

def fetch_baseline(paths=PATHS, archive=None):
    """Compatibility import of the last bundled snapshot, pinned by commit and file hashes.

    Only allowlisted data members are read; executable code in the old archive is
    never extracted or run. Future datasets can use the native pack/import format.
    """
    lock = json.loads((CATALOG/'baseline.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(archive) if archive else Path(tmp)/'baseline.tar.gz'
        if not archive:
            with urllib.request.urlopen(lock['archive_url'], timeout=180) as response, local.open('wb') as dest:
                shutil.copyfileobj(response,dest)
        with tarfile.open(local,'r:gz') as tar:
            for entry in lock['files']:
                member = tar.getmember(lock['archive_prefix']+entry['path'])
                if not member.isfile(): raise ValueError('Expected a regular file')
                data = tar.extractfile(member).read()
                if digest(data)!=entry['sha256']: raise ValueError(f"Hash mismatch: {entry['path']}")
                if entry.get('transform')=='embedded_graph': data=graph_from_html(data)
                write_new(destination(entry.get('target',entry['path']),paths),data)
    check_sources(paths.sources)

def pack(archive, paths=PATHS):
    """Portable normalized-input and web snapshot, without source code or large model outputs."""
    files = {}
    for name, root in [('sources',paths.sources),('web',paths.web)]:
        if root.exists():
            for f in sorted(root.rglob('*')):
                if f.is_file(): files[name+'/'+f.relative_to(root).as_posix()]=f
    check_sources(paths.sources)
    manifest={'format_version':1,'files':{k:digest(f.read_bytes()) for k,f in files.items()}}
    archive=Path(archive);archive.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive,'x:gz') as tar:
        data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('dataset.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
        for name,f in files.items(): tar.add(f,arcname=name,recursive=False)

def import_pack(archive, paths=PATHS):
    with tarfile.open(archive,'r:gz') as tar:
        member=tar.getmember('dataset.json')
        if not member.isfile(): raise ValueError('Invalid manifest')
        manifest=json.load(tar.extractfile(member))
        if manifest.get('format_version')!=1: raise ValueError('Unsupported dataset format')
        for name,sha in manifest['files'].items():
            target=destination(name,paths);member=tar.getmember(name)
            if not member.isfile(): raise ValueError('Dataset members must be regular files')
            data=tar.extractfile(member).read()
            if digest(data)!=sha: raise ValueError(f'Hash mismatch: {name}')
            write_new(target,data)
    check_sources(paths.sources)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('migrate');m.add_argument('--from',dest='legacy',type=Path,required=True)
    f=sub.add_parser('fetch-baseline');f.add_argument('--archive',type=Path)
    for cmd in ['pack','import']:
        s=sub.add_parser(cmd);s.add_argument('archive',type=Path)
    sub.add_parser('check')
    args=p.parse_args()
    if args.command=='migrate':migrate(args.legacy)
    elif args.command=='fetch-baseline':fetch_baseline(archive=args.archive)
    elif args.command=='pack':pack(args.archive)
    elif args.command=='import':import_pack(args.archive)
    else:check_sources(PATHS.sources)
    print(f'{args.command}: OK ({PATHS.root})')

if __name__=='__main__':main()
