"""Contract tests use small artificial files; national data is not a test dependency."""
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from paths import Paths, CODE_ROOT
import dataset
from build_site import build

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.paths=Paths.from_env({'HINOMOTO_DATA_ROOT':str(self.root/'dataset')})
    def tearDown(self):self.tmp.cleanup()

    def test_config_relative_paths_and_environment_precedence(self):
        config=self.root/'settings.json'
        config.write_text(json.dumps({'data_root':'data root','sources_dir':'read only input'}))
        p=Paths.from_env({'HINOMOTO_CONFIG':str(config),'HINOMOTO_OUTPUT_DIR':str(self.root/'run 2')})
        self.assertEqual(p.sources,self.root/'read only input')
        self.assertEqual(p.output,self.root/'run 2')
        self.assertEqual(p.reports,self.root/'data root/validation')
        self.assertFalse(p.root.exists())

    def test_importing_processing_modules_does_not_touch_data(self):
        env=dict(os.environ,HINOMOTO_DATA_ROOT=str(self.paths.root))
        env.pop('HINOMOTO_CONFIG',None)
        modules=['build','build_education','refine_tax','parse_income','parse_tax','parse_census','parse_education','fetch_income','fetch_education','download_sources','export','export_education','verify','verify_education','sensitivity_education']
        code='import sys;sys.path.insert(0,'+repr(str(CODE_ROOT/'src'))+');'+';'.join('import '+m for m in modules)
        subprocess.run([sys.executable,'-c',code],env=env,cwd=self.root,check=True,capture_output=True)
        self.assertFalse(self.paths.root.exists())

    def test_existing_data_cannot_be_silently_overwritten(self):
        p=self.root/'data.csv';dataset.write_new(p,b'original')
        dataset.write_new(p,b'original')
        with self.assertRaises(FileExistsError):dataset.write_new(p,b'changed')
        self.assertEqual(p.read_bytes(),b'original')

    def test_dataset_paths_cannot_escape_configured_storage(self):
        for path in ['../secret','sources/../../secret','/tmp/secret','src/build.py']:
            with self.assertRaises(ValueError):dataset.destination(path,self.paths)

    def test_pack_import_and_hash_validation(self):
        self.paths.sources.mkdir(parents=True)
        (self.paths.sources/'tiny.csv').write_text('code,count\n001,3\n')
        archive=self.root/'dataset.tar.gz'
        with patch.object(dataset,'check_sources'):
            dataset.pack(archive,self.paths)
            other=Paths.from_env({'HINOMOTO_DATA_ROOT':str(self.root/'other')})
            dataset.import_pack(archive,other)
        self.assertEqual((other.sources/'tiny.csv').read_bytes(),(self.paths.sources/'tiny.csv').read_bytes())
        with tarfile.open(self.root/'bad.tar.gz','w:gz') as tar:
            for name,data in [('dataset.json',json.dumps({'format_version':1,'files':{'sources/tiny.csv':'wrong'}}).encode()),('sources/tiny.csv',b'changed')]:
                info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        with self.assertRaisesRegex(ValueError,'Hash mismatch'):
            dataset.import_pack(self.root/'bad.tar.gz',other)

    def test_schema_rejects_wrong_columns(self):
        self.paths.sources.mkdir(parents=True)
        with gzip.open(self.paths.sources/'tiny.csv.gz','wt') as f:f.write('wrong,count\n1,2\n')
        catalog=self.root/'catalog';catalog.mkdir()
        (catalog/'source_schema.json').write_text(json.dumps({'tables':{'tiny.csv.gz':['code','count']}}))
        with patch.object(dataset,'CATALOG',catalog):
            with self.assertRaisesRegex(ValueError,'Incompatible columns'):dataset.check_sources(self.paths.sources)

    def test_site_rejects_an_incompatible_web_dataset(self):
        graph=self.root/'graph.json';graph.write_text('{"schema_version": 99, "graph": {}}')
        with self.assertRaises(ValueError):build(graph,self.root/'site')
        self.assertFalse((self.root/'site').exists())

if __name__=='__main__':unittest.main()
