"""Storage configuration, independent of the numerical model and working directory.

Explicit directory settings override root-derived defaults. For each key,
environment overrides JSON. Relative JSON paths are relative to the JSON file.
Reading configuration never creates files or directories.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import os

CODE_ROOT = Path(__file__).resolve().parents[1]
CATALOG = CODE_ROOT / 'catalog'

@dataclass(frozen=True)
class Paths:
    root: Path
    raw: Path
    sources: Path
    output: Path
    reports: Path
    web: Path

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        config = {}
        config_base = Path.cwd()
        if env.get('HINOMOTO_CONFIG'):
            config_path = Path(env['HINOMOTO_CONFIG']).expanduser().resolve()
            config = json.loads(config_path.read_text(encoding='utf-8'))
            config_base = config_path.parent
            unknown = set(config) - {'data_root', 'raw_dir', 'sources_dir', 'output_dir', 'reports_dir', 'web_dir'}
            if unknown:
                raise ValueError(f'Unknown storage configuration keys: {sorted(unknown)}')
        def resolve(value, base):
            p = Path(value).expanduser()
            return (p if p.is_absolute() else base / p).resolve()
        if env.get('HINOMOTO_DATA_ROOT'):
            root = resolve(env['HINOMOTO_DATA_ROOT'], Path.cwd())
        elif config.get('data_root'):
            root = resolve(config['data_root'], config_base)
        else:
            root = CODE_ROOT.parent / 'hinomoto-twin-data'
        def directory(key, suffix):
            env_key = 'HINOMOTO_' + key.upper()
            if env.get(env_key): return resolve(env[env_key], Path.cwd())
            if config.get(key): return resolve(config[key], config_base)
            return root / suffix
        return cls(root, directory('raw_dir','raw'), directory('sources_dir','sources'),
                   directory('output_dir','data'), directory('reports_dir','validation'), directory('web_dir','web'))

PATHS = Paths.from_env()
RAW, SOURCES, OUTPUT, REPORTS, WEB = PATHS.raw, PATHS.sources, PATHS.output, PATHS.reports, PATHS.web
