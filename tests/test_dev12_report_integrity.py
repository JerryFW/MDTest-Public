"""Dev12 adversarial saved-result consistency and fresh-run completeness tests."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_dev11_maintenance as base
REPORT, ROOT = base.REPORT, base.ROOT


class Dev12Integrity(base.Dev11SavedResultAndReport):
    # Reuse dev11 synthetic fixture but only run the new tests in this subclass.
    __test__ = False

    def test_ess_empty_object_is_malformed(self):
        self.summary['ess'] = {}
        self.save()
        accepted, malformed, ignored, count = REPORT.discover_summaries(self.summaries)
        self.assertEqual((len(accepted), len(malformed), len(ignored), count), (0, 1, 0, 1))
        self.assertNotEqual(self.run_report().returncode, 0)
        self.assertFalse(self.status()['complete'])

    def test_ess_required_missing_distinct_from_sw_explicit_null(self):
        self.assertIsNone(self.summary['auto_safe']['selected_start_index_sw'])
        self.assertIsNotNone(self.parsed())
        for key in ('selected_start_index_ess', 'selected_ts_ess', 'selected_g',
                    'selected_neff', 'scan_table'):
            with self.subTest(key=key):
                prev = self.summary['ess'].pop(key)
                try:
                    with self.assertRaises(REPORT.IncompatibleSavedResultError):
                        self.parsed()
                finally:
                    self.summary['ess'][key] = prev

    def test_combined_start_in_range_but_inconsistent(self):
        self.summary['selected_start_index_star'] = 399
        self.summary['selected_ts_star'] = 399.0
        with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'max\\(SW, ESS\\)'):
            self.parsed()
        self.save()
        self.assertNotEqual(self.run_report().returncode, 0)
        self.assertFalse(self.status()['complete'])

    def test_selected_ess_moved_consistently_in_time_but_not_scan(self):
        self.summary['ess']['selected_start_index_ess'] = 10
        self.summary['ess']['selected_ts_ess'] = 10.0
        self.summary['selected_start_index_star'] = 10
        self.summary['selected_ts_star'] = 10.0
        with self.assertRaises(REPORT.IncompatibleSavedResultError):
            self.parsed()

    def test_ess_negative_and_nonfinite_g(self):
        for g in (-1000., 0., float('nan'), float('inf')):
            with self.subTest(g=g):
                old = self.summary['ess']['selected_g']
                self.summary['ess']['selected_g'] = g
                try:
                    with self.assertRaises(REPORT.IncompatibleSavedResultError):
                        self.parsed()
                finally:
                    self.summary['ess']['selected_g'] = old

    def test_ess_neff_and_scan_metrics_must_agree(self):
        for selector, value in ((('ess', 'selected_neff'), -1.0),
                                (('ess', 'selected_neff'), 9999.0)):
            with self.subTest(selector=selector, value=value):
                trial = copy.deepcopy(self.summary)
                trial[selector[0]][selector[1]] = value
                old, self.summary = self.summary, trial
                try:
                    with self.assertRaises(REPORT.IncompatibleSavedResultError):
                        self.parsed()
                finally:
                    self.summary = old
        self.summary['ess']['scan_table'][0]['g'] = 2.0
        with self.assertRaises(REPORT.IncompatibleSavedResultError):
            self.parsed()

    def test_sw_combined_block_metadata_consistency(self):
        self.assertIsNotNone(self.summary['manual_result_star'])
        trial = copy.deepcopy(self.summary)
        trial['selected_m_corr_star'] = 99
        old, self.summary = self.summary, trial
        try:
            with self.assertRaisesRegex(REPORT.IncompatibleSavedResultError, 'block metadata'):
                self.parsed()
        finally:
            self.summary = old

    def test_empty_scan_constant_series_is_valid(self):
        import dataclasses
        import numpy as np
        import mdtest
        data = self.datadir / 'synthetic_stationary_ar1.csv'
        np.savetxt(data, np.column_stack([np.arange(400.), np.ones(400)]),
                   delimiter=',', comments='', header='time,value')
        self.summary = dataclasses.asdict(mdtest.auto_compare(data))
        self.assertFalse(self.summary['ess']['scan_table'])
        self.assertEqual(self.parsed().ess_g, 1.0)

    def test_fresh_run_ledgers_failed_and_missing_output(self):
        # Test the generator independently of the reporter: a recorded False
        # result cannot disappear if the associated expected summary is absent.
        out = self.root / 'fresh'
        with mock.patch.object(REPORT, 'run', side_effect=[True]+[True, True, True, False, True]+[True]):
            root, ledger = REPORT.run_examples(ROOT, out, 400, 20260627, True, True)
        self.assertEqual(root, out / 'raw_mdtest_outputs')
        self.assertEqual(len(ledger), 7)  # data + five synthetics + NarK
        bad = [x for x in ledger if x['case_id'] == 'underdamped_ar2'][0]
        self.assertFalse(bad['command_success'])
        self.assertFalse(bad['summary_present'])

    def test_failed_fresh_run_never_declares_five_case_report_complete(self):
        self.save()
        out = self.root / 'fresh_report'
        import shutil
        fake_data = out / 'data'
        fake_data.mkdir(parents=True)
        shutil.copy2(self.data, fake_data / self.data.name)
        ledger = [
            {'case_id': 'stationary_ar1', 'command_success': True,
             'expected_summary': str(self.path), 'summary_present': True},
            {'case_id': 'underdamped_ar2', 'command_success': False,
             'expected_summary': str(self.summaries/'underdamped_ar2_summary.json'),
             'summary_present': False},
        ]
        argv = ['report', '--package-root', str(ROOT), '--outdir', str(out),
                '--keep-going', '--no-summary-plots']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                REPORT, 'run_examples', return_value=(self.summaries, ledger)):
            self.assertEqual(REPORT.main(), 0)
        status = json.loads((out/'report_completeness.json').read_text())
        self.assertFalse(status['complete'])
        self.assertEqual(status['status'], 'incomplete')
        self.assertEqual(status['failed_commands'], ['underdamped_ar2'])
        self.assertEqual(status['missing_expected_summaries'], ['underdamped_ar2'])
        self.assertEqual(status['reported_cases'], 1)

    def test_successful_command_missing_expected_summary_is_incomplete(self):
        self.save()
        out = self.root / 'fresh_missing_output'
        ledger = [{'case_id': 'stationary_ar1', 'command_success': True,
                   'expected_summary': str(self.path), 'summary_present': True},
                  {'case_id': 'underdamped_ar2', 'command_success': True,
                   'expected_summary': str(self.summaries/'underdamped_ar2_summary.json'),
                   'summary_present': False}]
        argv = ['report', '--package-root', str(ROOT), '--outdir', str(out),
                '--keep-going', '--no-summary-plots']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(
                REPORT, 'run_examples', return_value=(self.summaries, ledger)):
            self.assertEqual(REPORT.main(), 0)
        status = json.loads((out/'report_completeness.json').read_text())
        self.assertFalse(status['complete'])
        self.assertEqual(status['missing_expected_summaries'], ['underdamped_ar2'])
        self.assertEqual(status['missing_reported_cases'], ['underdamped_ar2'])
        self.assertFalse(status['failed_commands'])

    def test_parse_existing_subset_still_complete(self):
        self.assertEqual(self.run_report().returncode, 0)
        self.assertTrue(self.status()['complete'])
        self.assertNotIn('failed_commands', self.status())


# Avoid inherited dev11 tests being duplicated by unittest discovery.
for _attr in list(vars(base.Dev11SavedResultAndReport)):
    if _attr.startswith('test_') and _attr not in vars(Dev12Integrity):
        setattr(Dev12Integrity, _attr, None)

if __name__ == '__main__':
    unittest.main()
