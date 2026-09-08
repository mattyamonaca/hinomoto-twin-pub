"""Rebuilding base arrays must invalidate stale extension references."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from export_web import set_build_metadata

class WebMetadataTests(unittest.TestCase):
    def test_rebuild_invalidates_extensions_but_retains_source(self):
        p = {'schema_version': 3, 'dataset_version': 'published',
             'graph': {'emp': {}, 'household': {}, 'workplace': {}, 'munis': [1]}}
        m = {'model_version': '3.0-M12', 'inputs_fingerprint': 'a', 'code_commit': 'abc'}
        set_build_metadata(p, m)
        self.assertEqual(p['graph'], {'munis': [1]})
        self.assertEqual(p['schema_version'], 2)
        self.assertEqual(p['source_dataset_version'], 'published')
        first = p['dataset_version']
        set_build_metadata(p, copy.deepcopy(m))
        self.assertEqual(p['dataset_version'], first)
        self.assertEqual(p['source_dataset_version'], 'published')
        set_build_metadata(p, dict(m, inputs_fingerprint='b'))
        self.assertNotEqual(p['dataset_version'], first)
