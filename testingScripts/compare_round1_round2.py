#!/usr/bin/env python3
"""Run the frozen Round-1 script and Round-2 package on identical inputs.

This is an audit test rather than a routine smoke test.  It generates the
3,000-point deterministic audit data with the preserved Round-1 program,
runs three representative analyses through both implementations, and compares
all JSON scientific fields recursively.  Only output-path strings are ignored.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "audit" / "reference" / "MDTest_round1_original.py"
NEW = ROOT / "MDTest.py"
PYTHON = sys.executable


def run(script: Path, args: list[str], cwd: Path) -> None:
    subprocess.run([PYTHON, str(script), *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL)


def compare(a, b, path=""):
    differences = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key in {"output_prefix", "settings", "provenance"}:
                continue
            if key not in a or key not in b:
                differences.append((f"{path}/{key}", a.get(key, "<missing>"), b.get(key, "<missing>")))
            else:
                differences.extend(compare(a[key], b[key], f"{path}/{key}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            differences.append((f"{path}/length", len(a), len(b)))
        for index, (left, right) in enumerate(zip(a, b)):
            differences.extend(compare(left, right, f"{path}[{index}]"))
    elif isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        if not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-14):
            differences.append((path, a, b))
    elif a != b:
        differences.append((path, a, b))
    return differences


def load(path: Path):
    return json.loads(path.read_text())


def check_legacy_output_compatibility(old_dir: Path, new_dir: Path, label: str) -> list[str]:
    """Require every legacy output filename to remain available in Round 2A.

    New explicitly documented aliases are allowed, so this is a legacy-subset
    check rather than byte-for-byte directory identity.
    """
    old_files = {p.relative_to(old_dir).as_posix() for p in old_dir.rglob("*") if p.is_file()}
    new_files = {p.relative_to(new_dir).as_posix() for p in new_dir.rglob("*") if p.is_file()}
    missing = sorted(old_files - new_files)
    if missing:
        return [f"{label}: missing legacy output {name}" for name in missing]
    return []


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mdtest_round2_equivalence_") as tmp_text:
        tmp = Path(tmp_text)
        data = tmp / "data"
        old_out = tmp / "old"
        new_out = tmp / "new"
        run(OLD, ["make-data", "--outdir", str(data), "--n-points", "3000", "--seed", "12345"], ROOT)

        cases = [
            (
                "manual",
                ["manual", "--file", str(data / "synthetic_variance_relaxation_independent.csv"), "--delim", "comma", "--col", "1", "--ts", "0", "--m", "10", "--n", "max", "--prefix", "manual_var", "--no-plots"],
                "manual_var.json",
            ),
            (
                "safe",
                ["auto-safe", "--file", str(data / "synthetic_mean_drift_independent.csv"), "--delim", "comma", "--col", "1", "--m-trend-grid", "2,5,10", "--m-corr-grid", "5,10,20,40", "--stride-points", "150", "--min-blocks", "24", "--prefix", "safe_mean", "--no-plots"],
                "safe_mean_summary.json",
            ),
            (
                "compare",
                ["auto-compare", "--file", str(data / "synthetic_variance_relaxation_independent.csv"), "--delim", "comma", "--col", "1", "--m-trend-grid", "2,5,10", "--m-corr-grid", "5,10,20,40", "--stride-points", "150", "--ess-stride-points", "150", "--min-blocks", "24", "--prefix", "compare_var", "--no-plots"],
                "compare_var_summary.json",
            ),
        ]

        for label, base_args, json_name in cases:
            oo = old_out / label
            nn = new_out / label
            args_old = [*base_args, "--outdir", str(oo)]
            args_new = [*base_args, "--outdir", str(nn)]
            run(OLD, args_old, ROOT)
            run(NEW, args_new, ROOT)
            differences = compare(load(oo / json_name), load(nn / json_name))
            footprint = check_legacy_output_compatibility(oo, nn, label)
            if differences or footprint:
                print(f"{label}: FAIL ({len(differences)} JSON differences, {len(footprint)} output-footprint differences)")
                for item in differences[:20]: print(" ", item)
                for item in footprint[:20]: print(" ", item)
                return 1
            print(f"{label}: PASS")

    print("Round-1 / Round-2 equivalence test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
