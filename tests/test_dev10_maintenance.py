"""Dev10 regression checks: saved-row identity, parser ambiguity and reporting inventory."""
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
sys.path.insert(0, str(ROOT/'src'))
import mdtest
from mdtest.io import read_timeseries

spec = importlib.util.spec_from_file_location('mdtest_dev10_reporter',ROOT/'testingScripts'/'mdtest_clear_benchmarks.py')
report = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = report
spec.loader.exec_module(report)


class Dev10InputAndProvenance(unittest.TestCase):
    def test_invalid_first_time_token_is_never_silent_header(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'bad.csv'
            for row in (',10', 'NA,10', 'broken,10', '0,NA', '0,'):
                p.write_text(row+'\n1,11\n2,12\n3,13\n4,14\n')
                with self.subTest(row=row),self.assertRaisesRegex(ValueError,'Ambiguous first CSV row'):
                    read_timeseries(str(p),drop_nan=True)
            p.write_text('time,value\n0,10\n1,11\n2,12\n3,13\n4,14\n')
            arr,_=read_timeseries(str(p))
            self.assertEqual(len(arr),5)

    def test_string_drop_nan_is_rejected_by_all_public_modes_and_workbench(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'series.csv'
            p.write_text('time,value\n'+''.join(f'{i},{"NA" if i in (7,8,9,10,11) else i*0.01}\n' for i in range(120)))
            for fn, extra in ((mdtest.manual,{'m':10}), (mdtest.auto_safe,{}), (mdtest.ess,{}),
                              (mdtest.auto_compare,{}), (mdtest.sensitivity,{})):
                with self.subTest(mode=fn.__name__),self.assertRaisesRegex(ValueError,'drop_nan must be a Boolean'):
                    fn(str(p),drop_nan='False',**extra)
            from mdtest.workbench import list_observables
            with self.assertRaisesRegex(ValueError,'drop_nan must be a Boolean'):
                list_observables(p,drop_nan='0')
            with self.assertRaisesRegex(ValueError,'non-numeric|NaN|nonnumeric|NaN'):
                mdtest.ess(p,drop_nan=False)
            self.assertTrue(len(read_timeseries(p,drop_nan=True)[0])==115)

    def test_cleaned_array_digest_rejects_updated_bytes_even_if_raw_hash_updated(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'synthetic_stationary_ar1.csv'
            data=np.c_[np.arange(180.),np.random.default_rng(45).normal(size=180)]
            np.savetxt(f,data,delimiter=',',header='time,value',comments='')
            d=dataclasses.asdict(mdtest.auto_compare(f))
            p=Path(td)/'stationary_ar1_summary.json';p.write_text(json.dumps(d))
            self.assertEqual(report.parse_summary_json(p,ROOT,Path(td),.1).n_total,180)
            import hashlib
            data[3,1]+=100
            np.savetxt(f,data,delimiter=',',header='time,value',comments='')
            sha=hashlib.sha256(f.read_bytes()).hexdigest()
            for obj in (d,d['auto_safe'],d['ess']):
                obj['provenance']['input_sha256']=sha
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(report.IncompatibleSavedResultError,'Cleaned input differs'):
                report.parse_summary_json(p,ROOT,Path(td),.1)

    def test_legacy_without_digest_uses_time_and_column_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'synthetic_stationary_ar1.csv'
            data=np.c_[np.arange(180.),np.random.default_rng(33).normal(size=180)]
            np.savetxt(f,data,delimiter=',',header='time,value',comments='')
            d=dataclasses.asdict(mdtest.auto_compare(f))
            for obj in (d,d['auto_safe'],d['ess']):
                for k in ('parser_schema','parsed_n_rows','parsed_array_sha256'):
                    obj['provenance'].pop(k,None)
            p=Path(td)/'stationary_ar1_summary.json';p.write_text(json.dumps(d))
            self.assertEqual(report.parse_summary_json(p,ROOT,Path(td),.1).n_total,180)
            d['ess']['selected_ts_ess'] += 1.0
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(report.IncompatibleSavedResultError,'indices/times'):
                report.parse_summary_json(p,ROOT,Path(td),.1)

    def test_malformed_summary_cannot_be_hidden_by_discovery(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); data_root=root/'data';data_root.mkdir()
            summaries=root/'summaries';summaries.mkdir()
            p=data_root/'synthetic_stationary_ar1.csv'
            np.savetxt(p,np.c_[np.arange(180.),np.random.default_rng(49).normal(size=180)],
                       delimiter=',',header='time,value',comments='')
            (summaries/'stationary_ar1_summary.json').write_text(json.dumps(dataclasses.asdict(mdtest.auto_compare(p))))
            (summaries/'underdamped_ar2_summary.json').write_text('{"auto_safe": ')
            cmd=[sys.executable,str(ROOT/'testingScripts'/'mdtest_clear_benchmarks.py'),
                 '--package-root',str(ROOT),'--parse-existing',str(summaries),
                 '--data-root',str(data_root),'--outdir',str(root/'out'),'--no-summary-plots']
            proc=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0)
            state=json.loads((root/'out'/'report_completeness.json').read_text())
            self.assertFalse(state['complete'])
            self.assertEqual(len(state['malformed_summaries']),1)
            proc=subprocess.run(cmd+['--keep-going'],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            state=json.loads((root/'out'/'report_completeness.json').read_text())
            self.assertFalse(state['complete'])
            self.assertEqual(state['summary_candidates'],2)
            self.assertEqual(state['reported_cases'],1)


if __name__=='__main__':
    unittest.main()
