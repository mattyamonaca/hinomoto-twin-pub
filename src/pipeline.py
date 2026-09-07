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
    'build': ['build.py', 'refine_tax.py', 'build_production.py', 'export.py', 'build_education.py', 'export_education.py', 'export_web.py'],
    'build-education': ['build_education.py', 'export_education.py'],
    'verify': ['verify.py', 'verify_education.py'],
    'verify-education': ['verify_education.py'],
    'sensitivity': ['sensitivity_education.py'],
    'fetch-industry': ['download_industry.py'],
    'fetch-employment': ['fetch_employment.py'],
    'build-employment': ['build_employment.py'],
    'verify-employment': ['verify_employment.py'],
    'fetch-household': ['download_household.py'],
    'build-household': ['build_household.py'],
    'fetch-workplace': ['download_workplace.py'],
    'build-workplace': ['build_workplace.py'],
    'verify-workplace': ['verify_workplace.py'],
    'experiment': ['experiment_models.py'],
    'synthetic': ['synthetic_population.py'],
    'site': ['build_site.py'],
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=[*STAGES, 'paths'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--model', choices=['M0','M12'], default='M12')
    for key in ['data-root', 'raw-dir', 'sources-dir', 'output-dir', 'reports-dir', 'web-dir']:
        parser.add_argument('--'+key, type=Path)
    args = parser.parse_args()
    env = os.environ.copy()
    for key, value in vars(args).items():
        if key not in ('stage','model') and value is not None:
            env['HINOMOTO_'+key.upper()] = str(value.expanduser().resolve())
    env['HINOMOTO_MODEL']=args.model
    paths = Paths.from_env(env)
    if args.stage == 'paths':
        print(json.dumps({k: str(v) for k,v in vars(paths).items()}, indent=2))
        return
    if args.stage in ['build', 'build-education']:
        from dataset import check_sources
        check_sources(paths.sources)
        if args.stage == 'build':
            if not (paths.web/'graph.json').is_file():
                raise ValueError('Run dataset fetch-production into a fresh data root before building the web dataset')
            if args.model == 'M12' and not all((paths.sources/'industry'/f).is_file() for f in ['census_industry_age_tidy.csv.gz','income_industry_tidy.csv.gz']):
                raise ValueError('M12 requires industry data; run fetch-industry first')
    for directory in [paths.output, paths.reports]:
        directory.mkdir(parents=True, exist_ok=True)
    for script in STAGES[args.stage]:
        subprocess.run([sys.executable, str(CODE_ROOT/'src'/script)], env=env, check=True)

if __name__ == '__main__': main()
