"""Deterministic synthetic benchmark generators distributed with MDTest."""
from __future__ import annotations
import math
from pathlib import Path
from typing import Dict
import numpy as np
import pandas as pd


def generate_benchmark_data(outdir: Path, n: int = 100000, seed: int = 20260627) -> Dict[str, str]:
    'Generate the deterministic synthetic benchmark suite used by MDTest.'
    rng = np.random.default_rng(seed)
    outdir.mkdir(parents=True, exist_ok=True)
    t = np.arange(n, dtype=float)
    files: Dict[str, str] = {}

    # A. Weak monotone mean drift with independent noise.
    t_relax = int(0.45 * n)
    mu0 = 1.25
    mu = np.zeros(n)
    mu[:t_relax] = mu0 * (1.0 - t[:t_relax] / max(1, t_relax))
    x = mu + rng.normal(0.0, 1.0, n)
    files["mean_drift_independent"] = _write_dataset(outdir / "synthetic_mean_drift_independent.csv", t, x, "mean_drift")

    # B. Variance relaxation with zero mean and independent samples.
    sigma_inf = 1.0
    sigma0 = 3.0
    tau = 0.18 * n
    sigma = sigma_inf + (sigma0 - sigma_inf) * np.exp(-t / tau)
    x = sigma * rng.normal(0.0, 1.0, n)
    files["variance_relaxation_independent"] = _write_dataset(outdir / "synthetic_variance_relaxation_independent.csv", t, x, "variance_relaxation")

    # C. One rare metastable switch.
    switch = int(0.52 * n)
    x = np.empty(n)
    x[:switch] = -1.0 + rng.normal(0.0, 0.25, switch)
    x[switch:] = 1.0 + rng.normal(0.0, 0.25, n - switch)
    files["metastable_switch"] = _write_dataset(outdir / "synthetic_metastable_switch.csv", t, x, "metastable_switch")

    # D. Underdamped AR(2) process with oscillatory autocorrelation.
    r = 0.995
    omega = 0.38 * math.pi
    x = np.zeros(n)
    noise = rng.normal(0.0, 0.25, n)
    x[0] = noise[0]
    x[1] = noise[1]
    a1 = 2.0 * r * math.cos(omega)
    a2 = -r * r
    for i in range(2, n):
        x[i] = a1 * x[i - 1] + a2 * x[i - 2] + noise[i]
    x = (x - x.mean()) / x.std(ddof=1)
    files["underdamped_ar2"] = _write_dataset(outdir / "synthetic_underdamped_ar2.csv", t, x, "underdamped_ar2")

    # E. Stationary AR(1) positive-correlated reference.
    rho = 0.95
    x = np.zeros(n)
    noise = rng.normal(0.0, math.sqrt(1.0 - rho * rho), n)
    for i in range(1, n):
        x[i] = rho * x[i - 1] + noise[i]
    files["stationary_ar1"] = _write_dataset(outdir / "synthetic_stationary_ar1.csv", t, x, "stationary_ar1")

    return files


def _write_dataset(path: Path, t: np.ndarray, x: np.ndarray, name: str) -> str:
    'Write one synthetic time series to CSV and return its path.'
    df = pd.DataFrame({"time": t, name: x})
    df.to_csv(path, index=False)
    return str(path)
