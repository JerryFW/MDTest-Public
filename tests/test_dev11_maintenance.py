"""Dev11 independent-Audit-1/2 regressions: corrupted saves and transactional reports."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import mdtest

SPEC = importlib.util.spec_from_file_location('mdtest_dev11_reporter', ROOT / 'testingScripts' / 'mdtest_clear_benchmarks.py')
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class Dev11SavedResultAndReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.datadir = self.root / 'data'
        self.summaries = self.root / 'summaries'
        self.datadir.mkdir()
        self.summaries.mkdir()
        self.data = self.datadir / 'synthetic_stationary_ar1.csv'
        rng = np.random.default_rng(344)
        np.savetxt(self.data, np.column_stack([np.arange(400.0), rng.normal(size=400)]),
                   delimiter=',', header='time,value', comments='')
        self.summary = dataclasses.asdict(mdtest.auto_compare(self.data))
        self.path = self.summaries / 'stationary_ar1_summary.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.summary), encoding='utf-8')

    def parsed(self, **kw):
        self.save()
        return REPORT.parse_summary_json(self.path, ROOT, self.datadir, 0.10, **kw)

    def args(self, *additional):
        return [sys.executable, str(ROOT / 'testingScripts' / 'mdtest_clear_benchmarks.py'),
                '--package-root', str(ROOT), '--parse-existing', str(self.summaries),
                '--data-root', str(self.datadir), '--outdir', str(self.root / 'report'),
                '--no-summary-plots', *additional]

    def run_report(self, *additional):
        return subprocess.run(self.args(*additional), text=True, capture_output=True)

    def status(self):
        return json.loads((self.root / 'report' / 'report_completeness.json').read_text())

    def test_unchanged_valid_and_integral_float_scan_entries(self):
        result = self.parsed()
        self.assertEqual(result.n_total, 400)
        self.assertEqual(result.provenance_status, 'verified_cleaned_data')
        self.assertTrue(all(float(row['start_index']).is_integer()
                            for row in self.summary['ess']['scan_table']))

    def test_fractional_bool_and_out_of_range_selected_cutoffs(self):
        for value in [0.75, True, -1, 400, 999999, float('nan'), '0']:
            with self.subTest(index=repr(value)):
                saved = self.summary['ess']['selected_start_index_ess']
                self.summary['ess']['selected_start_index_ess'] = value
                with self.assertRaises(REPORT.IncompatibleSavedResultError):
                    self.parsed()
                self.summary['ess']['selected_start_index_ess'] = saved

    def test_null_timestamp_does_not_disable_validation(self):
        self.summary['ess']['selected_start_index_ess'] = 999999
        self.summary['ess']['selected_ts_ess'] = None
        with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'Incomplete'):
            self.parsed()

    def test_scan_trend_and_nested_manual_cutoffs(self):
        # Small series may have no SW trend entries; seed a valid nested record
        # before probing the boundary validation for those serialized fields.
        if not self.summary['auto_safe']['trend_table']:
            self.summary['auto_safe']['trend_table'] = [
                {'start_index': 0, 'ts': 0.0,
                 'm_results': [{'start_index': 0, 'ts': 0.0}]}
            ]
        mutations = [
            (lambda s: s['ess']['scan_table'][0].__setitem__('start_index', 0.75)),
            (lambda s: s['auto_safe']['trend_table'][0].__setitem__('start_index', 0.25)),
            (lambda s: s['auto_safe']['trend_table'][0]['m_results'][0].__setitem__('start_index', 0.5)),
        ]
        if isinstance(self.summary['manual_result_star'], dict):
            mutations.append(lambda s: s['manual_result_star'].__setitem__('start_index', 0.5))
        for mutate in mutations:
            with self.subTest(mutate=str(mutate)):
                candidate = json.loads(json.dumps(self.summary))
                mutate(candidate)
                self.summary, original = candidate, self.summary
                try:
                    with self.assertRaises(REPORT.IncompatibleSavedResultError):
                        self.parsed()
                finally:
                    self.summary = original

    def test_genuine_absent_sw_selection_keeps_null_pair_valid(self):
        self.summary['auto_safe']['selected_start_index_sw'] = None
        self.summary['auto_safe']['selected_ts_sw'] = None
        # ESS remains available and therefore supplies the conservative start.
        self.summary['selected_start_index_star'] = self.summary['ess']['selected_start_index_ess']
        self.summary['selected_ts_star'] = self.summary['ess']['selected_ts_ess']
        result = self.parsed()
        self.assertIsNone(result.mdtest_start)
        self.assertEqual(result.conservative_start, result.ess_start)

    def test_large_origin_off_by_one_legacy_timestamp_rejected(self):
        data = np.column_stack([1e9 + np.arange(400) * 1e-4,
                                np.random.default_rng(344).normal(size=400)])
        np.savetxt(self.data, data, delimiter=',', header='time,value', comments='')
        self.summary = dataclasses.asdict(mdtest.auto_compare(self.data))
        # Strip the modern parsed-digest metadata, preserving legitimate raw SHA.
        for obj in [self.summary, self.summary['auto_safe'], self.summary['ess'],
                    self.summary['manual_result_star'], self.summary['auto_safe'].get('manual_result')]:
            if isinstance(obj, dict):
                for key in ('parsed_array_sha256', 'parsed_n_rows', 'parser_schema'):
                    obj.get('provenance', {}).pop(key, None)
        self.assertEqual(self.parsed().provenance_status, 'legacy_raw_sha_verified')
        idx = int(self.summary['ess']['selected_start_index_ess'])
        # A one-sample offset at a large absolute clock origin was accepted in dev10.
        if idx + 1 == len(data):
            idx -= 1
            self.summary['ess']['selected_start_index_ess'] = idx
        self.summary['ess']['selected_ts_ess'] = float(data[idx + 1, 0])
        self.assertTrue(np.isclose(data[idx, 0], data[idx + 1, 0], rtol=1e-12, atol=1e-11))
        with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'indices/times'):
            self.parsed()

    def test_no_hash_legacy_requires_opt_in_and_is_labeled(self):
        for obj in [self.summary, self.summary['auto_safe'], self.summary['ess'],
                    self.summary['manual_result_star'], self.summary['auto_safe'].get('manual_result')]:
            if isinstance(obj, dict):
                for key in ('parsed_array_sha256', 'parsed_n_rows', 'parser_schema', 'input_sha256'):
                    obj.get('provenance', {}).pop(key, None)
        with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'allow-unverified-legacy'):
            self.parsed()
        allowed = self.parsed(allow_unverified_legacy=True)
        self.assertEqual(allowed.provenance_status, 'unverified_legacy')
        failed = self.run_report()
        self.assertNotEqual(failed.returncode, 0)
        accepted = self.run_report('--allow-unverified-legacy')
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        status = self.status()
        self.assertTrue(status['complete'])
        self.assertEqual(len(status['unauthenticated_legacy_summaries']), 1)
        self.assertIn('UNAUTHENTICATED LEGACY RESULTS',
                      (self.root / 'report' / 'human_report.md').read_text())

    def test_structural_comparison_damage_is_malformed_not_ignored(self):
        second = self.summaries / 'underdamped_ar2_summary.json'
        broken = json.loads(json.dumps(self.summary))
        broken['ess'] = None
        second.write_text(json.dumps(broken))
        accepted, malformed, ignored, count = REPORT.discover_summaries(self.summaries)
        self.assertEqual((len(accepted), len(malformed), len(ignored), count), (1, 1, 0, 2))
        failed = self.run_report()
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(self.status()['complete'])
        partial = self.run_report('--keep-going')
        self.assertEqual(partial.returncode, 0, partial.stderr)
        self.assertFalse(self.status()['complete'])
        self.assertEqual(self.status()['reported_cases'], 1)
        self.assertEqual(len(self.status()['malformed_summaries']), 1)

    def test_manual_only_is_ignored_not_malformed(self):
        manual = dataclasses.asdict(mdtest.manual(self.data, m=20))
        (self.summaries / 'manual_summary.json').write_text(json.dumps(manual))
        accepted, malformed, ignored, count = REPORT.discover_summaries(self.summaries)
        self.assertEqual((len(accepted), len(malformed), len(ignored), count), (1, 0, 1, 2))

    def test_failed_rerun_retires_old_report_and_invalidates_status(self):
        first = self.run_report()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(self.status()['complete'])
        original_human = (self.root / 'report' / 'human_report.md').read_text()
        with self.data.open('a', encoding='utf-8') as f:
            f.write('400,0.1\n')
        second = self.run_report()
        self.assertNotEqual(second.returncode, 0)
        self.assertFalse(self.status()['complete'])
        self.assertEqual(self.status()['status'], 'failed')
        self.assertFalse((self.root / 'report' / 'human_report.md').exists())
        archives = list((self.root / 'report' / 'previous_reports').glob('*/human_report.md'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_text(), original_human)
        self.assertTrue((archives[0].parent / 'report_completeness.json').is_file())

    def test_first_run_artifact_failure_never_sets_complete(self):
        argv = ['report', '--package-root', str(ROOT), '--parse-existing', str(self.summaries),
                '--data-root', str(self.datadir), '--outdir', str(self.root / 'report'),
                '--no-summary-plots']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                REPORT, 'write_human_report', side_effect=OSError('injected final-write failure')):
            with self.assertRaisesRegex(OSError, 'injected final-write failure'):
                REPORT.main()
        self.assertFalse(self.status()['complete'])
        self.assertFalse((self.root / 'report' / 'comparison_table.json').exists())

    def test_final_write_failure_after_success_retires_previous_artifacts(self):
        self.assertEqual(self.run_report().returncode, 0)
        argv = ['report', '--package-root', str(ROOT), '--parse-existing', str(self.summaries),
                '--data-root', str(self.datadir), '--outdir', str(self.root / 'report')]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                REPORT, 'make_plots', side_effect=OSError('injected figure failure')):
            with self.assertRaisesRegex(OSError, 'injected figure failure'):
                REPORT.main()
        self.assertFalse(self.status()['complete'])
        self.assertFalse((self.root / 'report' / 'human_report.md').exists())
        self.assertEqual(len(list((self.root / 'report' / 'previous_reports').glob('*/human_report.md'))), 1)


if __name__ == '__main__':
    unittest.main()
