#!/usr/bin/env python3
"""Focused Round-2A.1 interface/provenance regression checks.

These checks complement, rather than replace, the Round-1 scientific
differential and manuscript-scale regression suites.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import mdtest
from mdtest.benchmarks import generate_benchmark_data
from mdtest.io import validate_integer


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data = base / "data"
        mdtest.make_benchmark_data(data, n_points=3000, seed=12345)
        f = data / "synthetic_stationary_ar1.csv"

        r = mdtest.auto_compare(f, col=1, stride_points=137, ess_stride_points=None)
        require(r.settings.ess_stride_points == 137, "top-level effective ESS stride")
        require(r.ess.settings.ess_stride_points == 137, "nested effective ESS stride")
        print("effective ESS stride metadata: PASS")

        seed = 2**53 + 1
        require(validate_integer(seed, "seed") == seed, "exact Python integer seed")
        require(validate_integer(str(seed), "seed") == seed, "exact integer string seed")
        api_dir = base / "seed_api"
        direct_dir = base / "seed_direct"
        mdtest.make_benchmark_data(api_dir, n_points=50, seed=seed)
        generate_benchmark_data(direct_dir, n=50, seed=seed)
        for p in sorted(api_dir.glob("*.csv")):
            require(p.read_bytes() == (direct_dir / p.name).read_bytes(), f"large-seed dataset {p.name}")
        print("exact large integer seed preservation: PASS")

        out = base / "reports"
        r = mdtest.auto_compare(f, col=1, stride_points=150, outdir=out, write_outputs=True, make_plots=False)
        require(r.auto_safe.manual_result is not None, "auto-safe manual result exists")
        require(r.manual_result_star is not None, "star manual result exists")
        for label, child in [("auto-safe", r.auto_safe.manual_result), ("star", r.manual_result_star)]:
            require(child.settings is not None, f"{label} settings")
            require(child.provenance is not None, f"{label} provenance")
            require(child.provenance.input_sha256 == r.provenance.input_sha256, f"{label} input hash")

        reports = sorted(out.glob("auto_safe_m*.json")) + sorted(out.glob("auto_compare_star_m*.json"))
        require(reports, "automatic manual subreport JSON files exist")
        for p in reports:
            payload = json.loads(p.read_text())
            require(payload.get("settings") is not None, f"settings in {p.name}")
            require(payload.get("provenance") is not None, f"provenance in {p.name}")
            require(payload["provenance"].get("input_sha256") == r.provenance.input_sha256, f"input hash in {p.name}")
        print(f"automatic manual subreport metadata: PASS ({len(reports)} JSON reports checked)")

    print("Round-2A.1 focused freeze-patch checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
