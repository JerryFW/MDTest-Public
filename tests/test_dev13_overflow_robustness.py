"""Dev13: malformed huge saved JSON integers must not abort --keep-going."""
from __future__ import annotations

import copy
import json

import test_dev11_maintenance as base

REPORT = base.REPORT
HUGE = 10 ** 400


class Dev13OverflowRobustness(base.Dev11SavedResultAndReport):
    def test_huge_saved_numbers_are_incompatible_not_overflows(self):
        variants = [
            lambda s: s['ess'].__setitem__('selected_g', HUGE),
            lambda s: s['ess'].__setitem__('selected_neff', HUGE),
            lambda s: s['ess']['scan_table'][0].__setitem__('g', HUGE),
            lambda s: s['ess']['scan_table'][0].__setitem__('neff', HUGE),
            lambda s: s.__setitem__('selected_ts_star', HUGE),
            lambda s: s['ess'].__setitem__('selected_ts_ess', HUGE),
            lambda s: s.__setitem__('selected_m_corr_star', HUGE),
            lambda s: s.__setitem__('selected_n_corr_star', HUGE),
        ]
        for i, modify in enumerate(variants):
            with self.subTest(mutation=i):
                before = self.summary
                self.summary = copy.deepcopy(before)
                try:
                    modify(self.summary)
                    with self.assertRaises(REPORT.IncompatibleSavedResultError):
                        self.parsed()
                finally:
                    self.summary = before
        self.assertIsNotNone(self.parsed())

    def test_huge_standalone_saved_timestamp_rejected(self):
        self.assertFalse(REPORT._saved_time_matches(0.0, HUGE, None, 0))
        self.assertFalse(REPORT._saved_time_matches(0.0, True, None, 0))
        with self.assertRaises(REPORT.IncompatibleSavedResultError):
            REPORT._finite_metric(HUGE, 'metric', minimum=1.0)
        with self.assertRaises(REPORT.IncompatibleSavedResultError):
            REPORT._positive_int(HUGE, 'block size')

    def test_keep_going_reports_healthy_summary_when_other_has_huge_integer(self):
        bad = self.summaries / 'underdamped_ar2_summary.json'
        broken = copy.deepcopy(self.summary)
        broken['ess']['selected_g'] = HUGE
        bad.write_text(json.dumps(broken), encoding='utf-8')
        completed = self.run_report('--keep-going')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        status = self.status()
        self.assertFalse(status['complete'])
        self.assertEqual(status['status'], 'incomplete')
        self.assertEqual(status['reported_cases'], 1)
        self.assertEqual(len(status['malformed_summaries']), 1)
        self.assertIn('INCOMPLETE BENCHMARK REPORT',
                      (self.root / 'report' / 'human_report.md').read_text())
        self.assertIn('cannot be represented', status['malformed_summaries'][0]['reason'])


# The inherited dev11 tests are executed in their original module; avoid
# duplication from this subclass when unittest discovers all test files.
for _name in vars(base.Dev11SavedResultAndReport):
    if _name.startswith('test_') and _name not in vars(Dev13OverflowRobustness):
        setattr(Dev13OverflowRobustness, _name, None)
