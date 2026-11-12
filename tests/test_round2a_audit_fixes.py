from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src"
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
import mdtest
from mdtest.cli import config_to_argv

class Round2AAuditFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.data=self.base/"data"
        mdtest.make_benchmark_data(self.data,n_points=3000,seed=12345)
    def tearDown(self): self.tmp.cleanup()

    def test_auto_safe_branch_is_single_engine_invariant(self):
        f=self.data/"synthetic_mean_drift_independent.csv"
        kw=dict(col=1,m_trend_grid=[2,5,10],m_corr_grid=[5,10,20,40],stride_points=150)
        standalone=mdtest.auto_safe(f,**kw)
        combined=mdtest.auto_compare(f,ess_stride_points=150,**kw).auto_safe
        a=asdict(standalone); b=asdict(combined)
        a.pop("settings",None); b.pop("settings",None); a.pop("provenance",None); b.pop("provenance",None)
        if a.get("manual_result"): a["manual_result"].pop("output_prefix",None)
        if b.get("manual_result"): b["manual_result"].pop("output_prefix",None)
        self.assertEqual(a,b)

    def test_fractional_integer_arguments_are_rejected(self):
        f=self.data/"synthetic_variance_relaxation_independent.csv"
        with self.assertRaises(ValueError): mdtest.manual(f,col=1,m=10.9,n="max")
        with self.assertRaises(ValueError): mdtest.auto_safe(f,col=1,m_trend_grid=[2,5.5,10])
        with self.assertRaises(ValueError): mdtest.auto_compare(f,col=1,ess_min_lag=3.2)

    def test_result_records_settings_version_and_input_hash(self):
        f=self.data/"synthetic_stationary_ar1.csv"
        r=mdtest.ess(f,col=1,scan_stride_points=150,min_lag=3,max_lag=200)
        self.assertEqual(r.settings.ess_stride_points,150); self.assertEqual(r.settings.ess_max_lag,200)
        self.assertEqual(r.provenance.mdtest_version,mdtest.__version__)
        self.assertEqual(len(r.provenance.input_sha256),64)

    def test_config_forwards_previously_ignored_options_and_rejects_unknown(self):
        argv=config_to_argv({"mode":"auto-compare","file":"x.csv","stride_points":"11","ess_stride_points":"13","ess_min_lag":"4","ess_max_lag":"99","drop_nan":"true"})
        joined=" ".join(argv)
        for token in ["--stride-points 11","--ess-stride-points 13","--ess-min-lag 4","--ess-max-lag 99","--drop-nan"]:
            self.assertIn(token,joined)
        with self.assertRaises(ValueError): config_to_argv({"mode":"manual","file":"x.csv","m":"10","mystery_option":"7"})

    def test_sensitivity_keeps_legacy_return_paths(self):
        f=self.data/"synthetic_mean_drift_independent.csv"
        r=mdtest.sensitivity(f,col=1,m_values=[2,10])
        self.assertIn("out_csv",r); self.assertIn("out_json",r); self.assertIn("rows",r)

    def test_auto_compare_preserves_default_legacy_output_aliases(self):
        f=self.data/"synthetic_variance_relaxation_independent.csv"; out=self.base/"out"
        mdtest.auto_compare(f,col=1,m_trend_grid=[2,5,10],m_corr_grid=[5,10,20,40],stride_points=150,ess_stride_points=150,outdir=out,write_outputs=True,make_plots=False)
        for name in ["auto_safe_summary.json","auto_safe_trend_table.csv","auto_compare_summary.json","auto_compare_trend_table.csv","auto_compare_ess_scan.csv"]:
            self.assertTrue((out/name).exists(),name)

    def test_import_does_not_override_matplotlib_backend(self):
        code='import matplotlib; matplotlib.use("svg", force=True); b=matplotlib.get_backend(); import mdtest; a=matplotlib.get_backend(); print(b); print(a); raise SystemExit(0 if str(a).lower()==str(b).lower() else 7)'
        env=dict(os.environ); env["PYTHONPATH"]=str(SRC)
        cp=subprocess.run([sys.executable,"-c",code],env=env,capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr+cp.stdout)

class Round2A1FreezePatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.data=self.base/"data"
        mdtest.make_benchmark_data(self.data,n_points=3000,seed=12345)
    def tearDown(self): self.tmp.cleanup()

    def test_effective_ess_stride_is_recorded_at_top_level(self):
        f=self.data/"synthetic_stationary_ar1.csv"
        r=mdtest.auto_compare(f,col=1,stride_points=137,ess_stride_points=None)
        self.assertEqual(r.settings.ess_stride_points,137)
        self.assertEqual(r.ess.settings.ess_stride_points,137)

    def test_large_integer_seed_is_preserved_exactly(self):
        from mdtest.benchmarks import generate_benchmark_data
        from mdtest.io import validate_integer
        seed=2**53+1
        self.assertEqual(validate_integer(seed,"seed"),seed)
        self.assertEqual(validate_integer(str(seed),"seed"),seed)
        api_dir=self.base/"api_seed"; exact_dir=self.base/"exact_seed"
        mdtest.make_benchmark_data(api_dir,n_points=50,seed=seed)
        generate_benchmark_data(exact_dir,n=50,seed=seed)
        api_files=sorted(p.name for p in api_dir.glob("*.csv"))
        exact_files=sorted(p.name for p in exact_dir.glob("*.csv"))
        self.assertEqual(api_files,exact_files)
        for name in api_files:
            self.assertEqual((api_dir/name).read_bytes(),(exact_dir/name).read_bytes(),name)

    def test_automatic_manual_subreports_carry_metadata_in_memory_and_on_disk(self):
        f=self.data/"synthetic_stationary_ar1.csv"; out=self.base/"reports"
        r=mdtest.auto_compare(f,col=1,stride_points=150,outdir=out,write_outputs=True,make_plots=False)
        self.assertIsNotNone(r.auto_safe.manual_result)
        self.assertIsNotNone(r.manual_result_star)
        self.assertIsNotNone(r.auto_safe.manual_result.settings)
        self.assertIsNotNone(r.auto_safe.manual_result.provenance)
        self.assertIsNotNone(r.manual_result_star.settings)
        self.assertIsNotNone(r.manual_result_star.provenance)
        self.assertEqual(r.auto_safe.manual_result.provenance.input_sha256,r.provenance.input_sha256)
        self.assertEqual(r.manual_result_star.provenance.input_sha256,r.provenance.input_sha256)
        safe_json=out/f"auto_safe_m{r.auto_safe.selected_m_corr}.json"
        star_json=out/f"auto_compare_star_m{r.selected_m_corr_star}.json"
        for path in (safe_json,star_json):
            payload=json.loads(path.read_text())
            self.assertIsNotNone(payload["settings"],str(path))
            self.assertIsNotNone(payload["provenance"],str(path))
            self.assertEqual(payload["provenance"]["input_sha256"],r.provenance.input_sha256)

if __name__=="__main__": unittest.main()
