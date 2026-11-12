"""Public 2.2.0.dev7: saved JSON time identity must not round integers."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import mdtest

SPEC = importlib.util.spec_from_file_location('mdtest_final_timestamp_report',
    ROOT / 'testingScripts' / 'mdtest_clear_benchmarks.py')
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class ExactSavedJSONTimestampTests(unittest.TestCase):
    def test_integer_boundary_does_not_alias_as_float(self):
        actual = float(2**53)
        self.assertTrue(REPORT._saved_time_matches(actual, 2**53, None, 0))
        self.assertTrue(REPORT._saved_time_matches(actual, float(2**53), None, 0))
        self.assertFalse(REPORT._saved_time_matches(actual, 2**53 + 1, None, 0))
        self.assertFalse(REPORT._saved_time_matches(actual, 2**53 - 1, None, 0))
        self.assertFalse(REPORT._saved_time_matches(actual, 2**53 + 2, None, 0))

    def test_regular_and_nonfinite_timestamps(self):
        self.assertTrue(REPORT._saved_time_matches(2.5, 2.5, None, 0))
        self.assertTrue(REPORT._saved_time_matches(10.0, 10, None, 0))
        for val in (10**400, -(10**400), True, None, '10', float('inf'), float('nan')):
            with self.subTest(val=str(val)[:40]):
                self.assertFalse(REPORT._saved_time_matches(10.0, val, None, 0))
        self.assertFalse(REPORT._saved_time_matches(float('nan'), 1.0, None, 0))

    def test_saved_pair_extraction_preserves_integer_identity(self):
        payload = {'auto_safe': {'selected_start_index_sw': None, 'selected_ts_sw': None,
                                 'manual_result': None, 'trend_table': []},
                   'ess': {'selected_start_index_ess': 0, 'selected_ts_ess': 2**53 + 1,
                           'scan_table': []},
                   'selected_start_index_star': 0, 'selected_ts_star': float(2**53),
                   'manual_result_star': None}
        pairs = REPORT._saved_index_time_pairs(payload, 4)
        self.assertEqual(pairs[0], (0, 2**53 + 1))
        self.assertIsInstance(pairs[0][1], int)
        self.assertFalse(REPORT._saved_time_matches(float(2**53), pairs[0][1], None, 0))
        payload['ess']['selected_ts_ess'] = 10**400
        with self.assertRaises(REPORT.IncompatibleSavedResultError):
            REPORT._saved_index_time_pairs(payload, 4)

    def test_real_summary_and_keep_going_with_precision_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            datadir, summaries = work/'data', work/'summaries'
            datadir.mkdir(); summaries.mkdir()
            # A float64 timeline with exactly representable steps of 2.
            times = float(2**53) + np.arange(400, dtype=np.float64) * 2.0
            rng = np.random.default_rng(344)
            values = rng.normal(size=400)
            data = datadir/'synthetic_stationary_ar1.csv'
            np.savetxt(data, np.column_stack((times, values)), delimiter=',',
                       header='time,value', comments='', fmt='%.18g')
            summary = dataclasses.asdict(mdtest.auto_compare(data))
            p = summaries/'stationary_ar1_summary.json'
            p.write_text(json.dumps(summary))
            valid = REPORT.parse_summary_json(p, ROOT, datadir, 0.1)
            self.assertEqual(valid.n_total, 400)
            self.assertEqual(valid.provenance_status, 'verified_cleaned_data')
            # A separate intact case permits meaningful --keep-going reporting.
            good_data = datadir/'synthetic_underdamped_ar2.csv'
            good_data.write_bytes(data.read_bytes())
            good_summary = dataclasses.asdict(mdtest.auto_compare(good_data))
            (summaries/'underdamped_ar2_summary.json').write_text(json.dumps(good_summary))
            idx = summary['ess']['selected_start_index_ess']
            summary['ess']['selected_ts_ess'] = int(times[idx]) + 1
            p.write_text(json.dumps(summary))
            with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'indices/times'):
                REPORT.parse_summary_json(p, ROOT, datadir, 0.1)
            args = [sys.executable, str(ROOT/'testingScripts/mdtest_clear_benchmarks.py'),
                    '--package-root', str(ROOT), '--parse-existing', str(summaries),
                    '--data-root', str(datadir), '--outdir', str(work/'report'),
                    '--no-summary-plots', '--keep-going']
            result = subprocess.run(args, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads((work/'report/report_completeness.json').read_text())
            self.assertFalse(status['complete'])
            self.assertEqual(len(status['malformed_summaries']), 1)
            self.assertEqual(status['reported_cases'], 1)


if __name__ == '__main__':
    unittest.main()
