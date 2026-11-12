from __future__ import annotations
import tempfile, unittest
from types import SimpleNamespace
from dataclasses import asdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
import mdtest
from mdtest.education import explain_result, references_for_result
from mdtest.presentation import export_guided_report, format_guided_text
from mdtest.workbench import MDTestWorkbench, WorkbenchRequest, list_observables, run_request, workbench_status
from mdtest.visualization import InputProvenanceError, create_diagnostic_figures

class Round3WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.data=self.base/'data'
        mdtest.make_benchmark_data(self.data,n_points=3000,seed=12345)
    def tearDown(self): self.tmp.cleanup()

    def test_list_observables_is_inspection_only(self):
        f=self.data/'synthetic_mean_drift_independent.csv'
        info=list_observables(f)
        self.assertEqual(info['n_rows'],3000)
        self.assertEqual(info['observables'][0][0],1)

    def test_workbench_request_matches_public_api(self):
        f=self.data/'synthetic_variance_relaxation_independent.csv'
        kw=dict(col=1,m_trend_grid=(2,5,10),m_corr_grid=(5,10,20,40),stride_points=150,ess_stride_points=150)
        via_ui=run_request(WorkbenchRequest(file=str(f),mode='auto-compare',**kw))
        direct=mdtest.auto_compare(f,**kw)
        self.assertEqual(asdict(via_ui),asdict(direct))

    def test_guided_explanation_and_references_are_presentation_only(self):
        f=self.data/'synthetic_variance_relaxation_independent.csv'
        r=mdtest.auto_compare(f,col=1,m_trend_grid=[2,5,10],m_corr_grid=[5,10,20,40],stride_points=150,ess_stride_points=150)
        before=asdict(r)
        text=format_guided_text(r)
        notes=explain_result(r)
        refs=references_for_result(r)
        after=asdict(r)
        self.assertEqual(before,after)
        self.assertIn('ESS/IACT',text)
        self.assertTrue(any('Stationarity' in n.title or 'stationarity' in n.explanation for n in notes))
        self.assertTrue(any('Chodera' in x.citation for x in refs))

    def test_export_guided_report_creates_bundle(self):
        f=self.data/'synthetic_stationary_ar1.csv'
        r=mdtest.ess(f,col=1,scan_stride_points=150)
        out=export_guided_report(r,self.base/'report',include_figures=True)
        for key in ('json','text','html'):
            self.assertTrue(Path(out[key]).exists())
        self.assertIn('ess_scan',out['figures'])
        html=Path(out['html']).read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64,',html)
        self.assertNotIn("src='mdtest_workbench_ess_scan.png'",html)
        # ESSResult intentionally carries no input path in the frozen result schema;
        # raw-trajectory plotting is available for Manual/AutoSafe/AutoCompare results.

    def test_technical_explanation_is_distinct_and_reports_settings(self):
        f=self.data/'synthetic_variance_relaxation_independent.csv'
        r=mdtest.auto_compare(f,col=1,m_trend_grid=[2,5,10],m_corr_grid=[5,10,20,40],stride_points=150,ess_stride_points=150)
        guided=format_guided_text(r,level='guided')
        technical=format_guided_text(r,level='technical')
        self.assertNotEqual(guided,technical)
        self.assertIn('Recorded inference settings',technical)
        self.assertIn('m_trend_grid=',technical)
        self.assertIn('test statistic=',technical)
        self.assertNotIn('stationarity-certified',technical)
        self.assertNotIn('did not certify stationarity',technical)
        with self.assertRaises(ValueError):
            format_guided_text(r,level='unknown-level')

    def _headless_path_workbench(self, file, mode='auto-compare'):
        wb=MDTestWorkbench.__new__(MDTestWorkbench)
        wb.result=None; wb._completed_request=None
        wb.current_file=str(Path(file).resolve())
        wb._active_source_kind='path'
        wb.file_path=SimpleNamespace(value=str(file))
        wb.upload=SimpleNamespace(value={})
        wb.delim=SimpleNamespace(value='comma')
        wb.drop_nan=SimpleNamespace(value=False)
        wb.observable=SimpleNamespace(value=1,options=[('1: value',1)])
        wb.mode=SimpleNamespace(value=mode)
        wb.alpha=SimpleNamespace(value=0.05)
        wb.min_blocks=SimpleNamespace(value=24)
        wb.trend_grid=SimpleNamespace(value='2,5,10')
        wb.corr_grid=SimpleNamespace(value='5,10,20,40')
        wb.stride=SimpleNamespace(value='150')
        wb.ess_stride=SimpleNamespace(value='150')
        wb.ess_min_lag=SimpleNamespace(value=3)
        wb.ess_max_lag=SimpleNamespace(value='')
        wb.manual_ts=SimpleNamespace(value=0.0)
        wb.manual_m=SimpleNamespace(value=10)
        wb.manual_n=SimpleNamespace(value='max')
        wb.explanation_level=SimpleNamespace(value='guided')
        wb.export_dir=SimpleNamespace(value=str(self.base/'headless_export'))
        wb.export_button=SimpleNamespace(disabled=True)
        wb.load_status=SimpleNamespace(value='')
        wb.status=SimpleNamespace(value='')
        class DummyOutput:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def clear_output(self,wait=False): pass
        wb.output=DummyOutput()
        wb._loaded_source_signature=wb._current_source_signature()
        return wb

    def test_live_workbench_rejects_stale_loaded_source_without_ipywidgets(self):
        f1=self.data/'synthetic_stationary_ar1.csv'
        f2=self.data/'synthetic_mean_drift_independent.csv'
        wb=self._headless_path_workbench(f1)
        wb.result=object(); wb._completed_request=wb._request(); wb.export_button.disabled=False
        wb.file_path.value=str(f2)  # deliberately bypass observer
        with self.assertRaisesRegex(ValueError,'changed after columns were loaded'):
            wb._request()
        self.assertIsNone(wb.current_file)
        self.assertIsNone(wb._loaded_source_signature)
        self.assertTrue(wb.export_button.disabled)
        self.assertEqual(wb.observable.options,[])

    def test_same_filename_upload_replacement_is_detected_by_content_hash(self):
        wb=MDTestWorkbench.__new__(MDTestWorkbench)
        wb._tmp=tempfile.TemporaryDirectory(prefix='mdtest_test_upload_')
        self.addCleanup(wb._tmp.cleanup)
        wb.result=None; wb._completed_request=None; wb.current_file=None
        wb._active_source_kind='upload'
        wb.file_path=SimpleNamespace(value='')
        original=b't,a\n0,1\n1,2\n2,3\n'
        replacement=b't,x,y\n0,10,20\n1,11,21\n2,12,22\n'
        wb.upload=SimpleNamespace(value={'same.csv': {'name':'same.csv','content':original}})
        wb.delim=SimpleNamespace(value='comma'); wb.drop_nan=SimpleNamespace(value=False)
        wb.observable=SimpleNamespace(value=1,options=[('1: a',1)])
        wb.mode=SimpleNamespace(value='ess'); wb.alpha=SimpleNamespace(value=0.05); wb.min_blocks=SimpleNamespace(value=1)
        wb.trend_grid=SimpleNamespace(value='bad-unused'); wb.corr_grid=SimpleNamespace(value='bad-unused'); wb.stride=SimpleNamespace(value='bad-unused')
        wb.ess_stride=SimpleNamespace(value=''); wb.ess_min_lag=SimpleNamespace(value=1); wb.ess_max_lag=SimpleNamespace(value='')
        wb.manual_ts=SimpleNamespace(value=0.0); wb.manual_m=SimpleNamespace(value=10); wb.manual_n=SimpleNamespace(value='bad-unused')
        wb.export_button=SimpleNamespace(disabled=True); wb.load_status=SimpleNamespace(value=''); wb.status=SimpleNamespace(value='')
        class DummyOutput:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def clear_output(self,wait=False): pass
        wb.output=DummyOutput()
        sig=wb._current_source_signature(); wb._loaded_source_signature=sig; wb.current_file=sig[1]
        wb.upload.value={'same.csv': {'name':'same.csv','content':replacement}}  # bypass observer on purpose
        self.assertNotEqual(sig[2], wb._current_source_signature()[2])
        with self.assertRaisesRegex(ValueError,'changed after columns were loaded'):
            wb._request()

    def test_entering_path_after_upload_selects_path_source(self):
        path_file=self.data/'synthetic_stationary_ar1.csv'
        wb=MDTestWorkbench.__new__(MDTestWorkbench)
        wb._tmp=tempfile.TemporaryDirectory(prefix='mdtest_test_upload_'); self.addCleanup(wb._tmp.cleanup)
        wb.current_file=None; wb._loaded_source_signature=None; wb.result=None; wb._completed_request=None
        wb._active_source_kind='upload'
        wb.file_path=SimpleNamespace(value='')
        wb.upload=SimpleNamespace(value={'a.csv': {'name':'a.csv','content':b't,a\n0,1\n1,2\n'}})
        wb.delim=SimpleNamespace(value='comma'); wb.drop_nan=SimpleNamespace(value=False)
        wb.observable=SimpleNamespace(value=None,options=[]); wb.export_button=SimpleNamespace(disabled=True)
        wb.load_status=SimpleNamespace(value=''); wb.status=SimpleNamespace(value='')
        class DummyOutput:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def clear_output(self,wait=False): pass
        wb.output=DummyOutput()
        wb.file_path.value=str(path_file)
        wb._on_path_changed({'new':str(path_file)})
        self.assertEqual(wb._active_source_kind,'path')
        self.assertEqual(Path(wb._resolve_file()).resolve(),path_file.resolve())

    def test_ess_mode_ignores_invalid_unused_manual_and_stationarity_fields(self):
        f=self.data/'synthetic_stationary_ar1.csv'
        wb=self._headless_path_workbench(f,mode='ess')
        wb.alpha.value='not-used'
        wb.trend_grid.value='not-used'
        wb.corr_grid.value='not-used'
        wb.stride.value='not-used'
        wb.manual_n.value='not-an-integer'
        wb.manual_m.value='not-used'
        req=wb._request()
        self.assertEqual(req.mode,'ess')
        self.assertEqual(req.manual_n,None)
        self.assertEqual(req.alpha,0.05)

    def test_analysis_change_invalidates_exportable_result(self):
        f=self.data/'synthetic_stationary_ar1.csv'
        wb=self._headless_path_workbench(f,mode='ess')
        completed=wb._request(); wb._completed_request=completed; wb.result=object(); wb.export_button.disabled=False
        wb.observable.value=1
        wb._on_analysis_changed({'new':1})
        self.assertIsNone(wb.result)
        self.assertIsNone(wb._completed_request)
        self.assertTrue(wb.export_button.disabled)

    def test_file_dependent_figures_refuse_changed_input_bytes(self):
        f=self.data/'synthetic_stationary_ar1.csv'
        r=mdtest.manual(f,col=1,ts=0.0,m=10,n='max')
        original=f.read_text()
        lines=original.splitlines()
        fields=lines[1].split(',')
        fields[1]=str(float(fields[1])+1000.0)
        lines[1]=','.join(fields)
        f.write_text('\n'.join(lines)+'\n')
        with self.assertRaises(InputProvenanceError):
            create_diagnostic_figures(r)

    def test_deleted_loaded_source_clears_stale_workbench_state(self):
        f=self.data/'synthetic_stationary_ar1.csv'
        wb=self._headless_path_workbench(f,mode='ess')
        wb.result=object(); wb._completed_request=wb._request(); wb.export_button.disabled=False
        f.unlink()
        with self.assertRaises(FileNotFoundError):
            wb._request()
        self.assertIsNone(wb.current_file)
        self.assertIsNone(wb._loaded_source_signature)
        self.assertIsNone(wb.result)
        self.assertIsNone(wb._completed_request)
        self.assertTrue(wb.export_button.disabled)

    def test_workbench_dependency_check_never_crashes(self):
        s=workbench_status()
        self.assertIn('available',s); self.assertIn('message',s)

if __name__=='__main__': unittest.main()
