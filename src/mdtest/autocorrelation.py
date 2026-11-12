"""ESS/IACT comparator used by MDTest."""
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
from .results import ESSResult


def autocorrelation_fft(x: np.ndarray) -> np.ndarray:
    'Estimate the normalized autocorrelation sequence using an FFT convolution.'
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return np.array([1.0])
    x = x - x.mean()
    var = np.dot(x, x)
    if var <= 0:
        return np.ones(1)
    nfft = 1 << (2 * n - 1).bit_length()
    fx = np.fft.rfft(x, n=nfft)
    acf = np.fft.irfft(fx * np.conjugate(fx), n=nfft)[:n]
    # Unbiased normalization for covariance, then normalize by lag-0.
    acf = acf / np.arange(n, 0, -1)
    acf = acf / acf[0]
    return np.real(acf)


def statistical_inefficiency_fft(x: np.ndarray, min_lag: int = 3, max_lag: Optional[int] = None) -> float:
    """PyMBAR-style FFT estimate of statistical inefficiency.

    This follows the logic used in pymbar.timeseries.statistical_inefficiency_fft:
    compute an adjusted normalized autocorrelation function, accumulate
    2*C(t)*(1 - t/N), and truncate at the first non-positive autocorrelation
    after the requested minimum lag.  The returned value is constrained to
    be at least 1.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return 1.0
    if float(np.std(x)) == 0.0:
        return 1.0
    acf = autocorrelation_fft(x)
    n = len(acf)
    if n <= 1:
        return 1.0

    last = n - 1 if max_lag is None else min(int(max_lag), n - 1)
    if last < 1:
        return 1.0

    stop = last + 1
    for k in range(1, last + 1):
        # PyMBAR uses t > mintime, not t >= mintime.  This matters for
        # oscillatory data with an early negative lobe.
        if k > min_lag and float(acf[k]) <= 0.0:
            stop = k
            break

    t = np.arange(n, dtype=float)
    weights = 1.0 - t / float(n)
    g = 1.0 + float(np.sum(2.0 * acf[1:stop] * weights[1:stop]))
    return float(max(1.0, g))


def detect_ess_start(
    arr: np.ndarray,
    col: int,
    min_blocks: int = 24,
    scan_stride_points: Optional[int] = None,
    min_lag: int = 3,
    max_lag: Optional[int] = None,
) -> ESSResult:
    """Detect a PyMBAR-style ESS start by maximizing retained effective samples.

    This is an internal implementation of the Chodera/PyMBAR heuristic: for
    candidate starts t0 on a scan grid, estimate g for the retained segment
    and choose the t0 that maximizes N_eff = N_retained/g.  The scan stride
    plays the same role as PyMBAR's nskip.

    The min_blocks argument is retained for API compatibility with MDTest's
    other modes, but the ESS scan itself follows the PyMBAR-style retained
    sample criterion rather than the block-test minimum.
    """
    times = arr[:, 0]
    values = np.asarray(arr[:, col], dtype=float)
    values = values[np.isfinite(values)]
    n_total = len(values)
    if n_total < 2:
        return ESSResult(float(times[0]), 0, 1.0, 1.0, [], "series too short for ESS scan")
    if float(np.std(values)) == 0.0:
        return ESSResult(float(times[0]), 0, 1.0, 1.0, [], "constant series; PyMBAR-style detector reports Neff=1")
    if scan_stride_points is None or scan_stride_points <= 0:
        scan_stride_points = max(1, n_total // 150)

    candidate_indices = list(range(0, n_total - 1, int(scan_stride_points)))
    if not candidate_indices:
        candidate_indices = [0]
    if candidate_indices[-1] != n_total - 2:
        candidate_indices.append(n_total - 2)

    table: List[Dict[str, float]] = []
    best = None
    for idx in candidate_indices:
        suffix = values[idx:]
        g = statistical_inefficiency_fft(suffix, min_lag=min_lag, max_lag=max_lag)
        # PyMBAR's source uses (T - t + 1)/g; len(suffix)/g is the same
        # heuristic up to an immaterial one-sample offset.  We report the
        # physically transparent retained-count version here.
        neff = len(suffix) / g
        row = {"start_index": float(idx), "ts": float(times[idx]), "g": float(g), "neff": float(neff)}
        table.append(row)
        if best is None or neff > best["neff"]:
            best = row
    assert best is not None
    return ESSResult(
        selected_ts_ess=float(best["ts"]),
        selected_start_index_ess=int(best["start_index"]),
        selected_g=float(best["g"]),
        selected_neff=float(best["neff"]),
        scan_table=table,
        note="PyMBAR-style ESS/IACT comparator; not a replacement for stationarity tests",
    )
