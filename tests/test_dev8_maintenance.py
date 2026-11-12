"""Boundary and reporting checks for the 2.2.0.dev8 maintenance candidate."""
from __future__ import annotations
import dataclasses
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import mdtest
from mdtest.io import read_timeseries
from mdtest import cli

SPEC = importlib.util.spec_from_file_location('mdtest_clear_bench_dev8', ROOT/'testingScripts'/'mdtest_clear_benchmarks.py')
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class AlphaValidation(unittest.TestCase):
    def test_invalid_alpha_rejected_in_every_public_entrypoint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'trend.csv'
            np.savetxt(path, np.c_[np.arange(1000), np.arange(1000)], delimiter=',',
                       header='time,value', comments='')
            for alpha in (0, -0.05, -1, 1, 1.1, float('nan'), float('inf'), -float('inf'), True, False, 'bad'):
                for fn, kwargs in ((mdtest.manual, {'m':10}), (mdtest.auto_safe, {}),
                                   (mdtest.auto_compare, {}), (mdtest.sensitivity, {})):
                    with self.subTest(alpha=repr(alpha), mode=fn.__name__):
                        with self.assertRaisesRegex(ValueError, 'alpha.*between 0 and 1'):
                            fn(path, alpha=alpha, **kwargs)

    def test_valid_alpha_and_mode_dispatch_keep_valid_behavior(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'trend.csv'
            np.savetxt(path, np.c_[np.arange(1000), np.arange(1000)], delimiter=',',
                       header='time,value', comments='')
            direct = mdtest.manual(path, m=10, alpha=0.05)
            via_dispatch = mdtest.analyze(path, mode='manual', m=10, alpha=0.05)
            self.assertFalse(direct.overall_pass)
            self.assertEqual(direct.tests["mean_trend_mk"].p_value, via_dispatch.tests["mean_trend_mk"].p_value)
            self.assertEqual(direct.overall_pass, via_dispatch.overall_pass)
            with self.assertRaisesRegex(ValueError, 'alpha.*between 0 and 1'):
                mdtest.analyze(path, mode='auto-safe', alpha=0.0)
            # CLI remains a thin wrapper over the same API validation.
            from argparse import Namespace
            with self.assertRaisesRegex(ValueError, 'alpha.*between 0 and 1'):
                cli.run_manual(Namespace(file=str(path), col=1, ts=0, m=10, n=None, delim='comma',
                                         alpha=-1.0, min_blocks=24, drop_nan=False,
                                         outdir=str(Path(td)/'report'), prefix=None,
                                         no_plots=True))


class DelimiterValidation(unittest.TestCase):
    def test_explicit_delimiter_overrides_csv_suffix_with_and_without_header(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenarios = [(';', 'semicolon'), ('\t', 'tab'), ('space', 'whitespace'), (',', 'comma')]
            for delim, tag in scenarios:
                separator = ' ' if delim=='space' else delim
                for has_header in (True, False):
                    data = ('time'+separator+'signal\n' if has_header else '') + ''.join(
                        f'{i}{separator}{2*i+1}\n' for i in range(5))
                    observed = []
                    for ext in ('.csv','.txt'):
                        p=root/(tag+('_hdr' if has_header else '_numeric')+ext)
                        p.write_text(data, encoding='utf-8')
                        arr,titles=read_timeseries(str(p),delim)
                        np.testing.assert_array_equal(arr, np.array([[i,2*i+1] for i in range(5)],dtype=float))
                        self.assertEqual(len(titles),2)
                        observed.append(arr)
                    np.testing.assert_array_equal(observed[0],observed[1])


class ReportIntegrity(unittest.TestCase):
    def test_relocated_saved_windows_path_prefers_matching_data_root(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            root=ROOT
            data_root=base/'relocated';data_root.mkdir()
            good=data_root/'synthetic_stationary_ar1.csv'
            np.savetxt(good, np.c_[np.arange(120),np.random.default_rng(1).normal(size=120)],
                       delimiter=',',header='time,observable',comments='')
            result=mdtest.auto_compare(good, col=1)
            summary=dataclasses.asdict(result)
            for obj in (summary,summary['auto_safe'],summary['ess'],summary['manual_result_star'],
                        summary['auto_safe']['manual_result']):
                if isinstance(obj,dict) and obj.get('file'):
                    obj['file']=r'C:\old\results\synthetic_stationary_ar1.csv'
            summary_path=base/'synthetic_stationary_ar1_summary.json'
            summary_path.write_text(json.dumps(summary),encoding='utf-8')
            parsed=REPORT.parse_summary_json(summary_path,root,data_root,0.1)
            self.assertEqual(parsed.source_data,str(good.resolve()))
            self.assertEqual(parsed.n_total,120)
            good.unlink()
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                REPORT.parse_summary_json(summary_path,root,data_root,0.1)

    def test_overlay_markers_use_physical_time(self):
        if REPORT.plt is None:
            self.skipTest('Matplotlib unavailable')
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            root=base/'package'; (root/'src'/'mdtest').mkdir(parents=True)
            import shutil
            shutil.copyfile(ROOT/'src'/'mdtest'/'io.py',root/'src'/'mdtest'/'io.py')
            data=base/'synthetic_stationary_ar1.csv'
            np.savetxt(data,np.c_[100+2*np.arange(7),np.arange(7)],
                       delimiter=',',header='time,value',comments='')
            row=REPORT.ComparisonRow(case_id='stationary_ar1',label='Stationary AR(1)',
                n_total=7,true_start=0,true_start_note='',ess_start=3,mdtest_start=3,
                conservative_start=3,ess_g=1.0,ess_neff=7,mdtest_m=2,mdtest_nblocks=3,
                expected_mean=0,expected_variance=1,ess_retained_mean=1,ess_retained_variance=1,
                mdtest_retained_mean=1,mdtest_retained_variance=1,
                conservative_retained_mean=1,conservative_retained_variance=1,
                interpretation='',source_summary='',source_data=str(data))
            with mock.patch.object(REPORT.plt.Axes,'axvline') as lines:
                REPORT.make_plots([row],base/'figures',root)
            self.assertEqual([call.args[1] if len(call.args)>1 else call.args[0] for call in lines.call_args_list],
                             [100,106,106,106])
            self.assertTrue((base/'figures'/'fig_timeseries_start_overlay.png').is_file())


if __name__=='__main__':
    unittest.main()
