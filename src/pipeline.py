"""Run existing pipeline stages with explicit storage configuration."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from paths import CODE_ROOT, Paths

STAGES = {
    'fetch': ['download_sources.py', 'fetch_education.py', 'parse_education.py'],
    'prepare': ['parse_census.py', 'parse_income.py', 'parse_tax.py', 'parse_education.py'],
    'build': ['build.py', 'refine_tax.py', 'export.py', 'build_education.py', 'export_education.py'],
    'build-education': ['build_education.py', 'export_education.py'],
    'verify': ['verify.py', 'verify_education.py'],
    'verify-education': ['verify_education.py'],
    'sensitivity': ['sensitivity_education.py'],
    'site': ['build_site.py'],
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=[*STAGES, 'paths'])
    parser.add_argument('--config', type=Path)
    for key in ['data-root', 'raw-dir', 'sources-dir', 'output-dir', 'reports-dir', 'web-dir']:
        parser.add_argument('--'+key, type=Path)
    args = parser.parse_args()
    env = os.environ.copy()
    for key, value in vars(args).items():
        if key != 'stage' and value is not None:
            env['HINOMOTO_'+key.upper()] = str(value.expanduser().resolve())
    paths = Paths.from_env(env)
    if args.stage == 'paths':
        print(json.dumps({k: str(v) for k,v in vars(paths).items()}, indent=2))
        return
    if args.stage in ['build', 'build-education']:
        from dataset import check_sources
        check_sources(paths.sources)
    for directory in [paths.output, paths.reports]:
        directory.mkdir(parents=True, exist_ok=True)
    for script in STAGES[args.stage]:
        subprocess.run([sys.executable, str(CODE_ROOT/'src'/script)], env=env, check=True)

if __name__ == '__main__': main()
