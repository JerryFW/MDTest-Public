#!/usr/bin/env python3
"""Small smoke test for MDTest.

This is not a statistical validation suite.  It checks that the main CLI paths
execute on small bundled/generated examples and that key fields are present and
sensible.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
OUT = ROOT / "results" / "smoke_test"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    data_dir = OUT / "data"
    run([PYTHON, "MDTest.py", "make-data", "--outdir", str(data_dir), "--n-points", "3000", "--seed", "12345"])

    manual_dir = OUT / "manual"
    run([
        PYTHON, "MDTest.py", "manual",
        "--file", str(data_dir / "synthetic_variance_relaxation_independent.csv"),
        "--delim", "comma", "--col", "1", "--ts", "0", "--m", "10", "--n", "max",
        "--outdir", str(manual_dir), "--prefix", "manual_var", "--no-plots",
    ])
    manual = read_json(manual_dir / "manual_var.json")
    assert manual["n"] > 0
    assert "mean_trend_mk" in manual["tests"]

    safe_dir = OUT / "auto_safe"
    run([
        PYTHON, "MDTest.py", "auto-safe",
        "--file", str(data_dir / "synthetic_mean_drift_independent.csv"),
        "--delim", "comma", "--col", "1", "--m-trend-grid", "2,5,10", "--m-corr-grid", "5,10,20,40",
        "--stride-points", "150", "--outdir", str(safe_dir), "--prefix", "safe_mean", "--no-plots",
    ])
    safe = read_json(safe_dir / "safe_mean_summary.json")
    assert safe["selected_start_index_sw"] is None or safe["selected_start_index_sw"] >= 0

    comp_dir = OUT / "auto_compare"
    run([
        PYTHON, "MDTest.py", "auto-compare",
        "--file", str(data_dir / "synthetic_variance_relaxation_independent.csv"),
        "--delim", "comma", "--col", "1", "--m-trend-grid", "2,5,10", "--m-corr-grid", "5,10,20,40",
        "--stride-points", "150", "--ess-stride-points", "150", "--outdir", str(comp_dir), "--prefix", "compare_var", "--no-plots",
    ])
    comp = read_json(comp_dir / "compare_var_summary.json")
    assert comp["ess"]["selected_g"] >= 1.0
    assert comp["selected_start_index_star"] is None or comp["selected_start_index_star"] >= 0

    # No-argument walkthrough should remain available for interactive users.
    walk_dir = OUT / "walkthrough"
    walk_input = "\n".join([
        str(data_dir / "synthetic_variance_relaxation_independent.csv"),
        "comma",
        "no",
        "1",
        "no",
        "manual",
        "0.05",
        "24",
        str(walk_dir),
        "walk_manual",
        "no",
        "0",
        "10",
        "max",
        "no",
    ]) + "\n"
    walk = subprocess.run([PYTHON, "MDTest.py"], cwd=ROOT, input=walk_input, text=True, capture_output=True, check=True)
    assert (walk_dir / "walk_manual_trial01.json").exists()
    assert "Interactive walkthrough mode" in walk.stdout

    # Controlled bad-column failure should return nonzero and a user-facing error.
    bad = subprocess.run([
        PYTHON, "MDTest.py", "manual",
        "--file", str(data_dir / "synthetic_mean_drift_independent.csv"),
        "--delim", "comma", "--col", "99", "--ts", "0", "--m", "10", "--n", "max",
        "--outdir", str(OUT / "bad"), "--no-plots",
    ], cwd=ROOT, text=True, capture_output=True)
    assert bad.returncode != 0
    assert "MDTest ERROR" in bad.stderr

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
