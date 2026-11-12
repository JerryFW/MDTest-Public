#!/usr/bin/env python3
"""Manuscript-scale scientific-regression check for the Round-2A engine."""
from __future__ import annotations
import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
import mdtest
DATA = ROOT / "examples" / "data"

def require(condition, message):
    if not condition: raise AssertionError(message)

def close(a,b,tol=1e-12): return math.isclose(float(a),float(b),rel_tol=0.0,abs_tol=tol)

def main():
    mean=mdtest.auto_safe(DATA/"synthetic_mean_drift_independent.csv",col=1,m_trend_grid=[2,5,10,20,40],m_corr_grid=[10,20,40,80,160,320])
    require(mean.selected_start_index_sw==9709, f"mean-drift SW start changed: {mean.selected_start_index_sw}")
    require(mean.selected_m_corr==10, f"mean-drift m changed: {mean.selected_m_corr}")
    require(close(mean.manual_result.mean,-0.001293179522,5e-13), f"mean changed: {mean.manual_result.mean}")
    var=mdtest.auto_compare(DATA/"synthetic_variance_relaxation_independent.csv",col=1,m_trend_grid=[2,5,10,20,40],m_corr_grid=[10,20,40,80,160,320])
    require(var.auto_safe.selected_start_index_sw==10374, f"variance SW start changed: {var.auto_safe.selected_start_index_sw}")
    require(var.ess.selected_start_index_ess==0, f"variance ESS start changed: {var.ess.selected_start_index_ess}")
    require(var.selected_start_index_star==10374, f"variance combined start changed: {var.selected_start_index_star}")
    require(var.selected_m_corr_star==10, f"variance m changed: {var.selected_m_corr_star}")
    require(close(var.ess.selected_g,1.0285490983959442,1e-12), f"g changed: {var.ess.selected_g}")
    print("Round-2A scientific regression passed.")
    return 0
if __name__=="__main__": raise SystemExit(main())
