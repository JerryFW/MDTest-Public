"""Regression coverage for the dev7 reporting, time-integrity and Windows patch."""
from __future__ import annotations
import dataclasses
import importlib.util
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import mdtest
from mdtest.io import read_timeseries
from mdtest.workbench import list_observables

SPEC = importlib.util.spec_from_file_location("mdtest_clear_bench_dev7", ROOT / "testingScripts" / "mdtest_clear_benchmarks.py")
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class TimeIntegrityTests(unittest.TestCase):
    def test_invalid_order_rejected_before_all_modes_and_workbench(self):
        rng = np.random.default_rng(913)
        t = np.arange(100, dtype=float)
        x = rng.normal(size=100)
        variants = {
            "descending": t[::-1],
            "duplicate": np.r_[t[:50], t[49], t[51:]],
            "shuffled": rng.permutation(t),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, bad_time in variants.items():
                path = Path(tmp) / (name + '.csv')
                np.savetxt(path, np.c_[bad_time, x], header='time,value', delimiter=',', comments='')
                for mode, kwargs in ((mdtest.manual, {'m':10}),
                                     (mdtest.auto_safe, {}),
                                     (mdtest.auto_compare, {}),
                                     (mdtest.ess, {}),
                                     (mdtest.sensitivity, {}),
                                     (list_observables, {})):
                    with self.subTest(variant=name, mode=mode.__name__):
                        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                            mode(path, **kwargs)

    def test_very_short_early_return_cannot_bypass_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'descending.csv'
            np.savetxt(path, np.c_[np.arange(20, dtype=float)[::-1], np.ones(20)],
                       delimiter=',', header='time,value', comments='')
            for mode in (mdtest.auto_safe, mdtest.auto_compare, mdtest.ess):
                with self.subTest(mode=mode.__name__):
                    with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                        mode(path)

    def test_nonuniform_increasing_warns_but_valid_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'series.csv'
            t = np.arange(100, dtype=float)
            x = np.random.default_rng(32).normal(size=100)
            for offset, expect_warning in ((False, False), (True, True)):
                shifted = t + (t >= 50) if offset else t
                np.savetxt(path, np.c_[shifted, x], delimiter=',', header='time,value', comments='')
                for mode, opts in ((mdtest.manual, {'m':5}), (mdtest.ess, {}),
                                   (mdtest.auto_safe, {}), (mdtest.auto_compare, {}),
                                   (list_observables, {})):
                    with self.subTest(offset=offset, mode=mode.__name__):
                        with warnings.catch_warnings(record=True) as records:
                            warnings.simplefilter('always')
                            mode(path, **opts)
                        messages = [str(w.message) for w in records]
                        self.assertEqual(any('not exactly uniform' in msg for msg in messages), expect_warning)

    def test_validation_happens_after_drop_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'badrow.csv'
            path.write_text('time,value\n0,10\n1,11\n2,NaN\n3,13\n4,14\n', encoding='utf-8')
            with warnings.catch_warnings(record=True):
                warnings.simplefilter('always')
                arr,_ = read_timeseries(str(path), drop_nan=True)
            self.assertEqual(arr[:,0].tolist(), [0.,1.,3.,4.])
            path.write_text('time,value\n0,10\n1,11\n2,NaN\n1,13\n4,14\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                read_timeseries(str(path), drop_nan=True)


class BenchmarkReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nark_path = ROOT/'examples'/'data'/'NarK_TimeSeriesData.csv'
        cls.result = mdtest.auto_compare(cls.nark_path, col=6, drop_nan=True,
                                         m_trend_grid=[2,5,10,20,25],
                                         m_corr_grid=[10,20,25,30,40,50,60])

    def _parsed(self, data, filename='nark_volume_summary.json'):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/filename
            p.write_text(json.dumps(data), encoding='utf-8')
            return REPORT.parse_summary_json(p, ROOT, None, 0.10)

    def test_nark_column_and_starts_are_correct(self):
        r = self.result
        self.assertEqual(r.auto_safe.selected_start_index_sw, 561)
        self.assertEqual(r.ess.selected_start_index_ess, 616)
        row = self._parsed(dataclasses.asdict(r))
        self.assertEqual(row.observable_column, 6)
        self.assertAlmostEqual(row.mdtest_retained_mean, 935707.4112504, places=4)
        self.assertAlmostEqual(row.ess_retained_mean, 935648.7849286, places=4)
        self.assertEqual(row.n_total, read_timeseries(str(self.nark_path), drop_nan=True)[0].shape[0])
        self.assertNotAlmostEqual(row.mdtest_retained_mean, 87258.3104933, places=1)

    def test_inconsistent_column_is_not_guessed(self):
        d = dataclasses.asdict(self.result)
        d['ess']['settings']['column'] = 1
        with self.assertRaisesRegex(ValueError, 'Inconsistent .*column'):
            self._parsed(d)

    def test_missing_column_metadata_is_not_guessed(self):
        d = dataclasses.asdict(self.result)
        for obj in (d, d['auto_safe'], d['auto_safe']['manual_result'], d['ess'],
                    d['manual_result_star']):
            if isinstance(obj, dict):
                obj.pop('column', None)
                if isinstance(obj.get('settings'),dict):
                    obj['settings'].pop('column',None)
        with self.assertRaisesRegex(ValueError, 'lacks recorded .*column'):
            self._parsed(d)

    def test_dropped_rows_and_multicolumn_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'NarK_TimeSeriesData.csv'
            lines=['time,energy,other,other2,other3,other4,volume']
            for i in range(200):
                if i == 12:
                    lines.append(f'{i},NA,0,0,0,0,NA')
                else:
                    lines.append(f'{i},{100+i},0,0,0,0,{900000+3*i}')
            path.write_text('\n'.join(lines)+'\n')
            # Dev12 does not accept fabricated selections that contradict the
            # ESS scan or SW/combined relationship. Test the multicolumn/
            # dropped-row statistics with an authentic complete summary, and
            # the shared retained-statistic helper at explicit starts 5 and 7.
            d = dataclasses.asdict(mdtest.auto_compare(str(path), col=6, drop_nan=True))
            with tempfile.TemporaryDirectory() as info_dir:
                p = Path(info_dir)/'nark_volume_summary.json'
                p.write_text(json.dumps(d))
                row = REPORT.parse_summary_json(p, ROOT, Path(tmp), 0.1)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter('always')
                arr,_ = read_timeseries(str(path), drop_nan=True)
            self.assertEqual(row.n_total, 199)
            self.assertEqual(row.observable_column, 6)
            for idx in (5, 7):
                mean, variance = REPORT.retained_stats(arr[:, 6], idx)
                self.assertAlmostEqual(mean, np.mean(arr[idx:, 6]))
                self.assertAlmostEqual(variance, np.var(arr[idx:, 6], ddof=1))
                self.assertNotAlmostEqual(mean, np.mean(arr[idx:, 1]))
            if row.ess_start is not None:
                self.assertAlmostEqual(row.ess_retained_mean, np.mean(arr[row.ess_start:, 6]))
            if row.mdtest_start is not None:
                self.assertAlmostEqual(row.mdtest_retained_mean, np.mean(arr[row.mdtest_start:, 6]))

if __name__ == '__main__':
    unittest.main()
