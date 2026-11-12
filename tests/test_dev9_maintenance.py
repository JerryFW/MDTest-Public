"""Regressions for dev9 inherited input/header, reporting and ts-integrity fixes."""
from __future__ import annotations
import dataclasses
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import mdtest
from mdtest.io import read_timeseries

SPEC = importlib.util.spec_from_file_location('mdtest_clear_bench_dev9', ROOT/'testingScripts'/'mdtest_clear_benchmarks.py')
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class HeaderIntegrity(unittest.TestCase):
    def test_duplicate_numeric_first_row_preserved_across_delimiters(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for sep, option, ext in ((',', 'comma', '.csv'), (';', ';', '.csv'),
                                     ('\t','tab','.txt'), (' ','space','.txt')):
                for ncols in (2, 4):
                    # The first row is all zero, so default scientific-notation
                    # names are duplicates that pandas would mangle.
                    data = np.tile(np.arange(100.0).reshape(-1,1), (1,ncols))
                    path = root / f'headerless_{ncols}_{len(option)}{ext}'
                    np.savetxt(path, data, delimiter=sep)
                    arr, titles = read_timeseries(path, delim=option)
                    with self.subTest(sep=repr(sep), columns=ncols):
                        np.testing.assert_array_equal(arr, data)
                        self.assertEqual(titles[0], 'time')
                        self.assertEqual(len(titles), ncols)

    def test_mixed_numeric_headerless_first_record_rejected_not_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for first in ('0,NA', '0,', '0,broken'):
                p = root / 'mixed.csv'
                p.write_text(first+'\n1,10\n2,20\n3,30\n4,40\n',encoding='utf-8')
                with self.subTest(first=first), self.assertRaisesRegex(ValueError,'Ambiguous first CSV row'):
                    read_timeseries(p, drop_nan=True)
            p = root / 'headed.csv'
            p.write_text('time,value\n0,NA\n1,10\n2,20\n3,30\n4,40\n',encoding='utf-8')
            with warnings.catch_warnings(record=True) as rec:
                warnings.simplefilter('always')
                arr, _ = read_timeseries(p,drop_nan=True)
            self.assertEqual(len(arr),4)
            self.assertTrue(any('Dropping 1' in str(x.message) for x in rec))


class ReportingIntegrity(unittest.TestCase):
    def _result(self, data: Path):
        return dataclasses.asdict(mdtest.auto_compare(data))

    def test_nested_only_hash_is_verified_and_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            data = folder / 'synthetic_stationary_ar1.csv'
            np.savetxt(data,np.c_[np.arange(180),np.random.default_rng(23).normal(size=180)],
                       delimiter=',',header='time,value',comments='')
            summary = self._result(data)
            expected = hashlib.sha256(data.read_bytes()).hexdigest()
            for obj in (summary, summary.get('auto_safe'), summary.get('ess')):
                if isinstance(obj,dict) and isinstance(obj.get('provenance'),dict):
                    obj['provenance'].pop('input_sha256',None)
            # Retain a hash exclusively in a valid nested ESS result. Dev12
            # intentionally rejects fabricated empty Manual result objects.
            summary['ess']['provenance']['input_sha256'] = expected
            p = folder / 'synthetic_stationary_ar1_summary.json'
            p.write_text(json.dumps(summary))
            parsed = REPORT.parse_summary_json(p,ROOT,folder,0.1)
            self.assertEqual(parsed.n_total,180)
            data.write_bytes(data.read_bytes().replace(b'1.000000000000000000e+00',
                                                       b'1.010000000000000000e+00', 1))
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                REPORT.parse_summary_json(p,ROOT,folder,0.1)
            summary['provenance']['input_sha256'] = 'f'*64
            with self.assertRaisesRegex(ValueError,'Conflicting input hashes'):
                REPORT._saved_input_hash(summary)

    def test_missing_source_fails_by_default_and_records_explicit_partial(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            data_root=base/'data'; data_root.mkdir()
            summaries=base/'summaries'; summaries.mkdir()
            pkg=base/'mini_package'; (pkg/'src'/'mdtest').mkdir(parents=True)
            from shutil import copyfile
            copyfile(ROOT/'src'/'mdtest'/'io.py',pkg/'src'/'mdtest'/'io.py')
            for case in ('stationary_ar1','underdamped_ar2'):
                p=data_root/f'synthetic_{case}.csv'
                np.savetxt(p,np.c_[np.arange(160),np.random.default_rng(len(case)).normal(size=160)],
                           delimiter=',',header='time,value',comments='')
                result=self._result(p)
                (summaries/f'{case}_summary.json').write_text(json.dumps(result))
            (data_root/'synthetic_underdamped_ar2.csv').unlink()
            cmd=[sys.executable,str(ROOT/'testingScripts'/'mdtest_clear_benchmarks.py'),
                 '--package-root',str(pkg),'--parse-existing',str(summaries),
                 '--data-root',str(data_root),'--outdir',str(base/'report'), '--no-summary-plots']
            failed=subprocess.run(cmd,text=True,capture_output=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('Could not find source data',failed.stderr)
            partial=subprocess.run(cmd+['--keep-going'],text=True,capture_output=True)
            self.assertEqual(partial.returncode,0,partial.stderr)
            completeness=json.loads((base/'report'/'report_completeness.json').read_text())
            self.assertFalse(completeness['complete'])
            self.assertEqual(completeness['recognized_summaries'],2)
            self.assertEqual(completeness['reported_cases'],1)
            self.assertEqual(len(completeness['skipped_missing_source']),1)


class StartTimeIntegrity(unittest.TestCase):
    def test_nonfinite_ts_rejected_in_manual_sensitivity_and_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'series.csv'
            np.savetxt(p,np.c_[np.arange(300),np.random.default_rng(15).normal(size=300)],
                       delimiter=',',header='time,value',comments='')
            for bad in (-float('inf'),float('inf'),float('nan'),'nan',True):
                for fn, kw in ((mdtest.manual, {'m':10}), (mdtest.sensitivity, {}),
                               (lambda f, **args:mdtest.analyze(f, mode='manual',**args),{'m':10})):
                    with self.subTest(bad=repr(bad),mode=str(fn)),self.assertRaisesRegex(ValueError,'finite physical start time'):
                        fn(p,ts=bad,**kw)
            self.assertEqual(mdtest.manual(p,m=10,ts=0.0).start_index,0)

if __name__=='__main__':
    unittest.main()
