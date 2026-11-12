"""Widget upload / workspace selection regression tests, independent of ipywidgets."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from mdtest.workbench import MDTestWorkbench, list_workspace_files


class DummyOutput:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def clear_output(self, wait=False): pass


class UploadReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mdtest_uploaded_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wb = MDTestWorkbench.__new__(MDTestWorkbench)
        self.wb._tmp = tempfile.TemporaryDirectory(prefix='mdtest_snapshot_')
        self.addCleanup(self.wb._tmp.cleanup)
        self.wb.upload = SimpleNamespace(value=())
        self.wb.file_path = SimpleNamespace(value='')
        self.wb.delim = SimpleNamespace(value='comma')
        self.wb.drop_nan = SimpleNamespace(value=False)
        self.wb.observable = SimpleNamespace(value=None, options=[])
        self.wb.load_status = SimpleNamespace(value='')
        self.wb.upload_status = SimpleNamespace(value='')
        self.wb.export_button = SimpleNamespace(disabled=True)
        self.wb.status = SimpleNamespace(value='')
        self.wb.output = DummyOutput()
        self.wb.result = None
        self.wb._completed_request = None
        self.wb.current_file = None
        self.wb._active_source_kind = None
        self.wb._loaded_source_signature = None
        self.sample = b't,energy\n0,1\n1,2\n2,3\n3,4\n'

    def test_ipywidgets_8_memoryview_file_auto_loads(self):
        new = ({'name': 'energy.csv', 'content': memoryview(self.sample), 'size': len(self.sample)},)
        self.wb.upload.value = new
        self.wb._on_upload_changed({'new': new})
        self.assertIn('File received', self.wb.upload_status.value)
        self.assertIn('energy.csv', self.wb.upload_status.value)
        self.assertIn('Loaded uploaded snapshot', self.wb.load_status.value)
        self.assertEqual(self.wb.observable.value, 1)
        self.assertEqual(self.wb._loaded_source_signature[0], 'upload')
        self.assertEqual(Path(self.wb.current_file).read_bytes(), self.sample)

    def test_ipywidgets_7_mapping_auto_loads(self):
        new = {'energy.csv': {'content': self.sample}}
        self.wb.upload.value = new
        self.wb._on_upload_changed({'new': new})
        self.assertEqual(Path(self.wb.current_file).suffix, '.csv')
        self.assertIn('energy.csv', self.wb.upload_status.value)
        self.assertEqual(self.wb.observable.options[0][1], 1)

    def test_same_name_reupload_invalidates_and_replaces_snapshot(self):
        first = ({'name': 'energy.csv', 'content': memoryview(self.sample)},)
        self.wb.upload.value = first
        self.wb._on_upload_changed({'new': first})
        path_first = self.wb.current_file
        self.wb.result = object()
        self.wb._completed_request = object()
        self.wb.export_button.disabled = False
        second = ({'name': 'energy.csv', 'content': memoryview(self.sample.replace(b'3,4', b'3,9'))},)
        self.wb.upload.value = second
        self.wb._on_upload_changed({'new': second})
        self.assertNotEqual(path_first, self.wb.current_file)
        self.assertTrue(self.wb.export_button.disabled)
        self.assertIsNone(self.wb._completed_request)
        self.assertIn('Loaded uploaded snapshot', self.wb.load_status.value)

    def test_broken_and_empty_browser_payload_are_visible(self):
        for item, text in (({'name':'bad.csv'}, 'did not transfer'),
                           ({'name':'empty.csv','content':b''}, 'empty')):
            with self.subTest(item=item):
                new = (item,)
                self.wb.upload.value = new
                self.wb._on_upload_changed({'new': new})
                self.assertIn(text, self.wb.upload_status.value)
                self.assertIsNone(self.wb.current_file)

    def test_existing_jupyter_files_are_available_without_widget_upload(self):
        (self.root / 'examples' / 'data').mkdir(parents=True)
        f = self.root / 'examples' / 'data' / 'my_series.csv'
        f.write_bytes(self.sample)
        found = list_workspace_files(self.root)
        self.assertIn(('examples/data/my_series.csv', str(f)), found)
        (self.root / '.venv').mkdir()
        self.assertNotIn('.venv', [label for label, _ in list_workspace_files(self.root)])
        self.wb.file_path.value = str(f)
        self.wb._active_source_kind = 'path'
        self.wb._on_load()
        self.assertEqual(self.wb._loaded_source_signature[0], 'path')
        self.assertEqual(self.wb.observable.value, 1)

    def test_html_filename_escaped(self):
        new = ({'name':'<script>alert(1)</script>.csv', 'content':self.sample},)
        self.wb.upload.value = new
        self.wb._on_upload_changed({'new':new})
        self.assertIn('&gt;', self.wb.upload_status.value)
        self.assertNotIn('<script>', self.wb.upload_status.value)


if __name__ == '__main__':
    unittest.main()
