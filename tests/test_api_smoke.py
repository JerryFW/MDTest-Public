from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import mdtest


class PublicApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        mdtest.make_benchmark_data(self.data, n_points=3000, seed=12345)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_returns_structured_result_without_files(self):
        r = mdtest.manual(
            self.data / "synthetic_variance_relaxation_independent.csv",
            col=1, ts=0, m=10, n="max",
        )
        self.assertEqual(r.m, 10)
        self.assertGreater(r.n, 0)
        self.assertIn("mean_trend_mk", r.tests)
        self.assertFalse(Path(r.output_prefix).with_suffix(".json").exists())

    def test_auto_safe_direct_python_interface(self):
        r = mdtest.auto_safe(
            self.data / "synthetic_mean_drift_independent.csv",
            col=1,
            m_trend_grid=[2, 5, 10],
            m_corr_grid=[5, 10, 20, 40],
            stride_points=150,
        )
        self.assertIsNotNone(r.selected_start_index_sw)
        self.assertEqual(r.status, "pass")

    def test_auto_compare_exposes_separate_starts(self):
        r = mdtest.auto_compare(
            self.data / "synthetic_variance_relaxation_independent.csv",
            col=1,
            m_trend_grid=[2, 5, 10],
            m_corr_grid=[5, 10, 20, 40],
            stride_points=150,
            ess_stride_points=150,
        )
        self.assertGreaterEqual(r.ess.selected_g, 1.0)
        self.assertIsNotNone(r.auto_safe.selected_start_index_sw)
        self.assertIsNotNone(r.selected_start_index_star)

    def test_ess_can_run_separately(self):
        r = mdtest.ess(self.data / "synthetic_stationary_ar1.csv", col=1, scan_stride_points=150)
        self.assertGreaterEqual(r.selected_g, 1.0)
        self.assertGreater(r.selected_neff, 0.0)


if __name__ == "__main__":
    unittest.main()
