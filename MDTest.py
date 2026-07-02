
"""
MDTest: stationarity and uncertainty diagnostics for scalar MD time series.

Revised Version 2

Main modes
----------
manual        Evaluate the four-test protocol at a user-specified (ts, m, n).
auto-safe     Find a conservative start time that passes trend tests on a fixed
              diagnostic grid of block sizes, then choose a block length for
              normality and local positive serial-correlation diagnostics.
auto-compare  Run auto-safe and an ESS/IACT-style comparator, then use the
              conservative start max(ts_SW, ts_ESS).
sensitivity   Run a legacy sequential search over several initial m values to
              diagnose smoothing sensitivity.
make-data     Generate synthetic designed benchmark data sets.
config        Run any of the above modes from a key-value configuration file.

Now, the code now does not install dependencies at runtime (to avoid messing with existing environments).  Install them
with:  pip install -r requirements.txt
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import warnings

import numpy as np
import pandas as pd
import matplotlib
# Use a noninteractive backend automatically on headless Linux, but do not
# force Agg on desktop Python or in Jupyter.  This keeps batch/script runs
# safe while allowing walkthrough mode to display figures interactively.
if os.environ.get("MDTEST_MPL_BACKEND"):
    matplotlib.use(os.environ["MDTEST_MPL_BACKEND"])
elif not os.environ.get("MPLBACKEND") and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from scipy.stats import shapiro, norm


PROGRAM_BANNER = (
    "MDTest revised: stationarity and uncertainty diagnostics for scalar MD time series\n"
    "Jerry F. Wang, Haobin Wang, and Hai Lin\n"
)


# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------

@dataclass
class TestOutcome:
    statistic: Optional[float]
    p_value: Optional[float]
    passed: bool
    note: str = ""


@dataclass
class ManualResult:
    file: str
    column: int
    column_name: str
    ts: float
    start_index: int
    m: int
    n: int
    alpha: float
    mean: float
    se: float
    ci_low: float
    ci_high: float
    tests: Dict[str, TestOutcome]
    overall_pass: bool
    recommendation: str
    output_prefix: str


@dataclass
class AutoSafeResult:
    file: str
    column: int
    column_name: str
    alpha: float
    min_blocks: int
    m_trend_grid: List[int]
    selected_ts_sw: Optional[float]
    selected_start_index_sw: Optional[int]
    selected_m_corr: Optional[int]
    selected_n_corr: Optional[int]
    manual_result: Optional[ManualResult]
    trend_table: List[Dict[str, Any]]
    status: str
    note: str


@dataclass
class ESSResult:
    selected_ts_ess: float
    selected_start_index_ess: int
    selected_g: float
    selected_neff: float
    scan_table: List[Dict[str, float]]
    note: str


@dataclass
class AutoCompareResult:
    auto_safe: AutoSafeResult
    ess: ESSResult
    selected_ts_star: Optional[float]
    selected_start_index_star: Optional[int]
    selected_m_corr_star: Optional[int]
    selected_n_corr_star: Optional[int]
    manual_result_star: Optional[ManualResult]
    status: str
    note: str


# -----------------------------------------------------------------------------
# I/O helpers
# -----------------------------------------------------------------------------

def _normalize_delim(delim: str) -> Optional[str]:
    d = (delim or "comma").strip().lower()
    if d in {"comma", ",", "csv"}:
        return ","
    if d in {"space", "whitespace", "white", " "}:
        return r"\s+"
    if d in {"tab", "\\t"}:
        return "\t"
    return delim


def read_timeseries(file: str, delim: str = "comma", drop_nan: bool = False) -> Tuple[np.ndarray, List[str]]:
    """Read a time-series file. Column 0 is assumed to be time."""
    path = Path(file)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file}")

    sep = _normalize_delim(delim)
    if path.suffix.lower() == ".csv" or sep == ",":
        df = pd.read_csv(path)
    else:
        df = pd.read_csv(path, sep=sep, engine="python")

    # If pandas interpreted a no-header numeric file as headers, recover by rereading.
    def _all_numeric_labels(labels: Sequence[Any]) -> bool:
        try:
            [float(x) for x in labels]
            return True
        except Exception:
            return False

    if _all_numeric_labels(list(df.columns)):
        if path.suffix.lower() == ".csv" or sep == ",":
            df = pd.read_csv(path, header=None)
        else:
            df = pd.read_csv(path, sep=sep, engine="python", header=None)
        titles = ["time"] + [f"observable_{j}" for j in range(1, df.shape[1])]
    else:
        titles = [str(c) for c in df.columns]

    # Convert data cells to numeric values.  Some MD outputs include a units
    # row after the header (for example: fs, kcal/mol, bar); such rows are
    # metadata, not data, and are removed with a warning.
    numeric_df = df.apply(pd.to_numeric, errors="coerce")
    nonnumeric_rows = numeric_df.isna().any(axis=1)
    if nonnumeric_rows.any():
        n_bad = int(nonnumeric_rows.sum())
        if drop_nan or n_bad <= 3:
            warnings.warn(f"Dropping {n_bad} nonnumeric or incomplete row(s) from input data.")
            numeric_df = numeric_df.loc[~nonnumeric_rows].copy()
        else:
            raise ValueError(
                f"Input file contains {n_bad} nonnumeric/NaN rows. "
                "Use --drop-nan to drop affected rows after manual inspection."
            )

    if numeric_df.replace([np.inf, -np.inf], np.nan).isna().any().any():
        if drop_nan:
            warnings.warn("Missing values detected; dropping rows containing NaN/Inf.")
            numeric_df = numeric_df.replace([np.inf, -np.inf], np.nan).dropna(axis=0)
        else:
            raise ValueError("Input file contains NaN/Inf values. Use --drop-nan to drop affected rows.")

    arr = numeric_df.to_numpy(dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError("Input file must contain at least two columns: time and one observable.")
    if len(arr) < 3:
        raise ValueError("Input series is too short.")
    return arr, titles


def ensure_uniform_time(times: np.ndarray, rtol: float = 1e-6, atol: float = 1e-12) -> float:
    dt = np.diff(times)
    if np.any(dt <= 0):
        raise ValueError("Time column must be strictly increasing.")
    median_dt = float(np.median(dt))
    if not np.allclose(dt, median_dt, rtol=rtol, atol=atol):
        warnings.warn("Time steps are not exactly uniform; using median dt for indexing.")
    return median_dt



def validate_observable_column(arr: np.ndarray, col: int, titles: Sequence[str]) -> None:
    if col < 1 or col >= arr.shape[1]:
        names = ", ".join(f"{i}:{name}" for i, name in enumerate(titles))
        raise ValueError(
            f"Observable column index {col} is invalid. Column 0 is time; "
            f"choose an index from 1 to {arr.shape[1]-1}. Available columns: {names}"
        )

def time_to_start_index(times: np.ndarray, ts: float) -> int:
    if ts <= times[0]:
        return 0
    idx = int(np.searchsorted(times, ts, side="left"))
    return min(max(idx, 0), len(times) - 1)


def max_blocks(n_points_after_start: int, m: int) -> int:
    if m <= 0:
        raise ValueError("m must be positive.")
    return int(n_points_after_start // m)


def parse_int_list(value: str) -> List[int]:
    if value is None or str(value).strip() == "":
        return []
    out = []
    for part in str(value).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return sorted(set(out))


def parse_n(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"", "max", "none", "auto"}:
        return None
    return int(value)


def sanitize_prefix(path: Path) -> str:
    return str(path).replace(os.sep, "_").replace(" ", "_")


# -----------------------------------------------------------------------------
# Statistical core
# -----------------------------------------------------------------------------

def block_series(values: np.ndarray, times: np.ndarray, start_index: int, m: int, n: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return block times, block means, and within-block variances."""
    if m < 1:
        raise ValueError("m must be at least 1.")
    available = len(values) - start_index
    nmax = available // m
    if n is None:
        n = nmax
    if n < 1:
        raise ValueError("No complete blocks are available for the requested start and m.")
    if n > nmax:
        raise ValueError(f"Requested n={n}, but only n={nmax} complete blocks are available.")
    cut_values = values[start_index:start_index + n * m]
    cut_times = times[start_index:start_index + n * m]
    blocks = cut_values.reshape(n, m)
    time_blocks = cut_times.reshape(n, m)
    means = blocks.mean(axis=1)
    block_times = time_blocks.mean(axis=1)
    if m >= 2:
        variances = blocks.var(axis=1, ddof=1)
    else:
        variances = np.full(n, np.nan)
    return block_times, means, variances


def mann_kendall_test(data: Sequence[float], alpha: float = 0.05) -> TestOutcome:
    """Two-sided Mann--Kendall trend test with tie correction.

    The statistic is computed with a Fenwick tree over value ranks, giving
    O(n log u) complexity where u is the number of distinct finite values.
    This avoids the quadratic pairwise loop during automated sweeps.
    """
    x = np.asarray(data, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 4:
        return TestOutcome(None, None, False, "not enough finite data for Mann--Kendall test")

    unique, inv = np.unique(x, return_inverse=True)
    u = len(unique)
    tree = np.zeros(u + 1, dtype=np.int64)

    def bit_add(i: int, value: int = 1) -> None:
        i += 1
        while i <= u:
            tree[i] += value
            i += i & -i

    def bit_sum(i: int) -> int:
        # inclusive prefix sum over ranks 0..i
        if i < 0:
            return 0
        total = 0
        i += 1
        while i > 0:
            total += int(tree[i])
            i -= i & -i
        return total

    s_stat = 0
    seen = 0
    for r in inv:
        r = int(r)
        less = bit_sum(r - 1)
        equal = bit_sum(r) - less
        greater = seen - less - equal
        s_stat += less - greater
        bit_add(r, 1)
        seen += 1

    _, counts = np.unique(x, return_counts=True)
    tie_term = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return TestOutcome(0.0, 1.0, True, "all values tied; no monotone trend detected")
    if s_stat > 0:
        z = (s_stat - 1) / math.sqrt(var_s)
    elif s_stat < 0:
        z = (s_stat + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * norm.sf(abs(z))
    return TestOutcome(float(z), float(p), bool(p > alpha), "two-sided Mann--Kendall")

def shapiro_test(data: Sequence[float], alpha: float) -> TestOutcome:
    x = np.asarray(data, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return TestOutcome(None, None, False, "not enough finite data for Shapiro--Wilk test")
    if len(x) > 5000:
        note = "Shapiro--Wilk p-value may be inaccurate for n>5000; SciPy warning suppressed"
    else:
        note = "Shapiro--Wilk normality test"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, p = shapiro(x)
    return TestOutcome(float(stat), float(p), bool(p > alpha), note)


def von_neumann_positive_test(data: Sequence[float], alpha: float) -> TestOutcome:
    """One-tailed von Neumann ratio test for positive adjacent correlation.

    Positive serial correlation decreases successive differences, so the
    lower tail is the relevant tail.
    """
    y = np.asarray(data, dtype=float)
    y = y[np.isfinite(y)]
    n = len(y)
    if n < 4:
        return TestOutcome(None, None, False, "not enough finite data for von Neumann test")
    denom = 2.0 * np.sum((y - y.mean()) ** 2)
    if denom <= 0:
        return TestOutcome(0.0, 1.0, True, "zero variance in block means")
    r = float(np.sum(np.diff(y) ** 2) / denom)
    sigma_r = math.sqrt((1.0 + 1.0 / (n - 1.0)) / (n + 1.0))
    z = (r - 1.0) / sigma_r
    p_lower = norm.cdf(z)
    return TestOutcome(float(z), float(p_lower), bool(p_lower > alpha), f"von Neumann ratio r={r:.6g}; lower-tail positive-correlation test")


def confidence_interval_t(block_means: np.ndarray, level: float = 0.95) -> Tuple[float, float, float, float]:
    n = len(block_means)
    mean = float(np.mean(block_means))
    if n < 2:
        return mean, float("nan"), float("nan"), float("nan")
    se = float(np.std(block_means, ddof=1) / math.sqrt(n))
    q = stats.t(df=n - 1).ppf(0.5 + level / 2.0)
    return mean, se, mean - q * se, mean + q * se


def evaluate_four_tests(
    file: str,
    arr: np.ndarray,
    titles: List[str],
    col: int,
    ts: float,
    m: int,
    n: Optional[int],
    alpha: float,
    outdir: Path,
    prefix: str,
    make_plots: bool = True,
    min_blocks: int = 24,
    display_plots: bool = False,
) -> ManualResult:
    validate_observable_column(arr, col, titles)
    times = arr[:, 0]
    values = arr[:, col]
    dt = ensure_uniform_time(times)
    start_index = time_to_start_index(times, ts)
    nmax = max_blocks(len(values) - start_index, m)
    if n is None:
        n = nmax
    if n > nmax:
        raise ValueError(f"Requested n={n}, but max feasible n={nmax} for ts={ts}, m={m}.")
    if n < 1:
        raise ValueError("No blocks available.")

    block_t, y, v = block_series(values, times, start_index, m, n)
    mk_mean = mann_kendall_test(y, alpha=alpha)

    if m >= 2:
        disp = np.sqrt(v / m)
        mk_disp = mann_kendall_test(disp, alpha=alpha)
    else:
        mk_disp = TestOutcome(None, None, False, "dispersion trend undefined for m=1; use m>=2")

    shap = shapiro_test(y, alpha)
    vn = von_neumann_positive_test(y, alpha)
    mean, se, ci_low, ci_high = confidence_interval_t(y)
    tests = {
        "mean_trend_mk": mk_mean,
        "dispersion_trend_mk": mk_disp,
        "normality_shapiro": shap,
        "positive_serial_von_neumann": vn,
    }
    overall = all(t.passed for t in tests.values()) and n >= min_blocks
    if n < min_blocks:
        recommendation = f"increase data length or reduce m; only n={n} blocks (<{min_blocks})"
    elif not (mk_mean.passed and mk_disp.passed):
        recommendation = "increase ts or inspect the observable for residual nonstationarity"
    elif not shap.passed:
        recommendation = "increase m, extend trajectory, or use a nonparametric uncertainty model"
    elif not vn.passed:
        recommendation = "increase m or extend trajectory; adjacent block means remain positively correlated"
    else:
        recommendation = "all tests passed under the selected diagnostic assumptions"

    outdir.mkdir(parents=True, exist_ok=True)
    out_prefix = outdir / prefix
    if make_plots:
        plot_raw_and_blocks(times, values, block_t, y, ts, m, out_prefix, title=titles[col], display=display_plots)

    result = ManualResult(
        file=file,
        column=col,
        column_name=titles[col] if col < len(titles) else f"column_{col}",
        ts=float(ts),
        start_index=int(start_index),
        m=int(m),
        n=int(n),
        alpha=float(alpha),
        mean=mean,
        se=se,
        ci_low=ci_low,
        ci_high=ci_high,
        tests=tests,
        overall_pass=bool(overall),
        recommendation=recommendation,
        output_prefix=str(out_prefix),
    )
    write_result_files(result, out_prefix)
    return result


def trend_pass_for_start(
    arr: np.ndarray,
    col: int,
    start_index: int,
    m: int,
    alpha: float,
    min_blocks: int,
) -> Dict[str, Any]:
    times = arr[:, 0]
    values = arr[:, col]
    n = max_blocks(len(values) - start_index, m)
    row: Dict[str, Any] = {"start_index": int(start_index), "ts": float(times[start_index]), "m": int(m), "n": int(n)}
    if n < min_blocks:
        row.update({"admissible": False, "mean_p": None, "dispersion_p": None, "pass": False, "note": "too few blocks"})
        return row
    _, y, v = block_series(values, times, start_index, m, n)
    mk_y = mann_kendall_test(y, alpha=alpha)
    if m >= 2:
        mk_v = mann_kendall_test(np.sqrt(v / m), alpha=alpha)
    else:
        mk_v = TestOutcome(None, None, False, "m=1 has no dispersion proxy")
    passed = (mk_y.p_value is not None and mk_y.p_value > alpha and mk_v.p_value is not None and mk_v.p_value > alpha)
    row.update({
        "admissible": True,
        "mean_p": mk_y.p_value,
        "mean_z": mk_y.statistic,
        "dispersion_p": mk_v.p_value,
        "dispersion_z": mk_v.statistic,
        "pass": bool(passed),
        "note": "",
    })
    return row


def find_multiresolution_stationarity(
    arr: np.ndarray,
    col: int,
    alpha: float,
    m_grid: Sequence[int],
    min_blocks: int,
    stride_points: Optional[int] = None,
) -> Tuple[Optional[int], List[Dict[str, Any]], str]:
    times = arr[:, 0]
    values = arr[:, col]
    n_total = len(values)
    m_grid = sorted(set(int(m) for m in m_grid if int(m) >= 2))
    if not m_grid:
        raise ValueError("m_trend_grid must contain at least one integer >= 2.")
    max_m = max(m_grid)
    max_start_allowed = n_total - min_blocks * max_m
    if max_start_allowed < 0:
        return None, [], f"series too short for min_blocks={min_blocks} at max m={max_m}"
    if stride_points is None or stride_points <= 0:
        stride_points = max(1, n_total // 150)
    candidate_indices = list(range(0, max_start_allowed + 1, stride_points))
    if candidate_indices[-1] != max_start_allowed:
        candidate_indices.append(max_start_allowed)

    table: List[Dict[str, Any]] = []
    for idx in candidate_indices:
        rows = [trend_pass_for_start(arr, col, idx, m, alpha, min_blocks) for m in m_grid]
        all_pass = all(r["pass"] for r in rows)
        summary = {
            "start_index": int(idx),
            "ts": float(times[idx]),
            "all_pass": bool(all_pass),
            "m_results": rows,
        }
        table.append(summary)
        if all_pass:
            return idx, table, "found earliest candidate on scan grid passing all trend tests"
    return None, table, "no start index passed the multi-resolution trend screen"


def choose_correlation_block(
    file: str,
    arr: np.ndarray,
    titles: List[str],
    col: int,
    start_index: int,
    alpha: float,
    min_blocks: int,
    m_candidates: Sequence[int],
    outdir: Path,
    prefix: str,
    make_plots: bool,
    display_plots: bool = False,
) -> Optional[ManualResult]:
    times = arr[:, 0]
    ts = float(times[start_index])
    for m in sorted(set(int(x) for x in m_candidates if int(x) >= 2)):
        n = max_blocks(len(times) - start_index, m)
        if n < min_blocks:
            continue
        result = evaluate_four_tests(
            file=file, arr=arr, titles=titles, col=col, ts=ts, m=m, n=None,
            alpha=alpha, outdir=outdir, prefix=f"{prefix}_m{m}", make_plots=make_plots,
            min_blocks=min_blocks, display_plots=display_plots,
        )
        # For m_corr selection, require normality and local correlation, while
        # preserving stationarity tests at the selected start.
        if result.overall_pass:
            return result
    return None


# -----------------------------------------------------------------------------
# ESS / IACT-style comparator
# -----------------------------------------------------------------------------

def autocorrelation_fft(x: np.ndarray) -> np.ndarray:
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


# -----------------------------------------------------------------------------
# Main algorithms
# -----------------------------------------------------------------------------

def run_manual(args: argparse.Namespace) -> ManualResult:
    arr, titles = read_timeseries(args.file, args.delim, args.drop_nan)
    validate_observable_column(arr, args.col, titles)
    outdir = Path(args.outdir)
    prefix = args.prefix or f"manual_col{args.col}_ts{str(args.ts).replace('.', 'p')}_m{args.m}"
    res = evaluate_four_tests(
        file=args.file, arr=arr, titles=titles, col=args.col, ts=args.ts,
        m=args.m, n=parse_n(args.n), alpha=args.alpha, outdir=outdir,
        prefix=prefix, make_plots=not args.no_plots, min_blocks=args.min_blocks,
        display_plots=getattr(args, "display_plots", False),
    )
    print_manual_summary(res)
    return res


def run_auto_safe(args: argparse.Namespace) -> AutoSafeResult:
    arr, titles = read_timeseries(args.file, args.delim, args.drop_nan)
    validate_observable_column(arr, args.col, titles)
    m_grid = parse_int_list(args.m_trend_grid) or [2, 5, 10, 20, 40]
    m_corr_candidates = parse_int_list(args.m_corr_grid) or [5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480]
    idx, trend_table, note = find_multiresolution_stationarity(
        arr, col=args.col, alpha=args.alpha, m_grid=m_grid,
        min_blocks=args.min_blocks, stride_points=args.stride_points,
    )
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manual = None
    selected_m = None
    selected_n = None
    if idx is not None:
        manual = choose_correlation_block(
            file=args.file, arr=arr, titles=titles, col=args.col, start_index=idx,
            alpha=args.alpha, min_blocks=args.min_blocks, m_candidates=m_corr_candidates,
            outdir=outdir, prefix=args.prefix or "auto_safe", make_plots=not args.no_plots,
            display_plots=getattr(args, "display_plots", False),
        )
        if manual is not None:
            selected_m = manual.m
            selected_n = manual.n
            status = "pass"
            note2 = note
        else:
            status = "stationarity-pass-correlation-not-found"
            note2 = note + "; no m_corr candidate passed normality and local correlation tests"
    else:
        status = "stationarity-not-found"
        note2 = note

    times = arr[:, 0]
    res = AutoSafeResult(
        file=args.file,
        column=args.col,
        column_name=titles[args.col] if args.col < len(titles) else f"column_{args.col}",
        alpha=args.alpha,
        min_blocks=args.min_blocks,
        m_trend_grid=m_grid,
        selected_ts_sw=float(times[idx]) if idx is not None else None,
        selected_start_index_sw=int(idx) if idx is not None else None,
        selected_m_corr=selected_m,
        selected_n_corr=selected_n,
        manual_result=manual,
        trend_table=trend_table,
        status=status,
        note=note2,
    )
    write_json(outdir / f"{args.prefix or 'auto_safe'}_summary.json", res)
    write_trend_table(outdir / f"{args.prefix or 'auto_safe'}_trend_table.csv", trend_table)
    print_auto_safe_summary(res)
    return res


def run_auto_compare(args: argparse.Namespace) -> AutoCompareResult:
    arr, titles = read_timeseries(args.file, args.delim, args.drop_nan)
    validate_observable_column(arr, args.col, titles)
    # auto-safe part
    safe_args = argparse.Namespace(**vars(args))
    safe = run_auto_safe(safe_args)
    # ESS part
    ess = detect_ess_start(
        arr, col=args.col, min_blocks=args.min_blocks,
        scan_stride_points=args.ess_stride_points or args.stride_points,
        min_lag=args.ess_min_lag,
        max_lag=args.ess_max_lag,
    )
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_csv(outdir / f"{args.prefix or 'auto_compare'}_ess_scan.csv", ess.scan_table)

    if safe.selected_start_index_sw is None:
        idx_star = ess.selected_start_index_ess
        note = "multi-resolution stationarity start not found; reporting ESS start but not treating it as stationarity-certified"
        status = "ess-only-no-stationarity-certification"
    else:
        idx_star = max(safe.selected_start_index_sw, ess.selected_start_index_ess)
        note = "selected conservative start max(start_SW, start_ESS)"
        status = "pass" if idx_star is not None else "failed"

    m_corr_candidates = parse_int_list(args.m_corr_grid) or [5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480]
    manual_star = None
    selected_m = None
    selected_n = None
    if idx_star is not None:
        manual_star = choose_correlation_block(
            file=args.file, arr=arr, titles=titles, col=args.col, start_index=idx_star,
            alpha=args.alpha, min_blocks=args.min_blocks, m_candidates=m_corr_candidates,
            outdir=outdir, prefix=f"{args.prefix or 'auto_compare'}_star", make_plots=not args.no_plots,
            display_plots=getattr(args, "display_plots", False),
        )
        if manual_star is not None:
            selected_m = manual_star.m
            selected_n = manual_star.n
        else:
            status = "start-found-correlation-not-found"
            note += "; no m_corr candidate passed all four tests at selected start"

    times = arr[:, 0]
    res = AutoCompareResult(
        auto_safe=safe,
        ess=ess,
        selected_ts_star=float(times[idx_star]) if idx_star is not None else None,
        selected_start_index_star=int(idx_star) if idx_star is not None else None,
        selected_m_corr_star=selected_m,
        selected_n_corr_star=selected_n,
        manual_result_star=manual_star,
        status=status,
        note=note,
    )
    write_json(outdir / f"{args.prefix or 'auto_compare'}_summary.json", res)
    print_auto_compare_summary(res)
    return res


def legacy_sequential_search(
    arr: np.ndarray,
    col: int,
    ts0: float,
    m0: int,
    alpha: float,
    min_blocks: int,
    max_steps: int = 10000,
) -> Dict[str, Any]:
    """Simplified legacy sequential logic for sensitivity diagnosis.

    It follows the old coupling: first increase ts until trend tests pass at the
    current m; once trend passes, increase m until normality and local
    correlation pass.  This mode is intentionally retained for diagnostic
    comparison and is not the recommended default.
    """
    times = arr[:, 0]
    values = arr[:, col]
    dt = ensure_uniform_time(times)
    ts = float(ts0)
    m = int(m0)
    step_ts = dt * len(values) / 300.0
    history: List[Dict[str, Any]] = []
    for step in range(max_steps):
        idx = time_to_start_index(times, ts)
        n = max_blocks(len(values) - idx, m)
        if n < min_blocks:
            return {"status": "failed_n_below_min", "ts": ts, "m": m, "n": n, "history": history}
        _, y, v = block_series(values, times, idx, m, n)
        mk_y = mann_kendall_test(y, alpha=alpha)
        if m >= 2:
            mk_v = mann_kendall_test(np.sqrt(v / m), alpha=alpha)
        else:
            mk_v = TestOutcome(None, None, False, "m=1")
        trend_ok = (mk_y.p_value is not None and mk_y.p_value > alpha and mk_v.p_value is not None and mk_v.p_value > alpha)
        shap = shapiro_test(y, alpha)
        vn = von_neumann_positive_test(y, alpha)
        corr_ok = shap.passed and vn.passed
        history.append({"step": step, "ts": ts, "m": m, "n": n, "trend_ok": trend_ok, "corr_ok": corr_ok})
        if trend_ok and corr_ok:
            return {"status": "pass", "ts": ts, "m": m, "n": n, "history": history}
        if not trend_ok:
            ts += step_ts
        else:
            m += 1
    return {"status": "failed_max_steps", "ts": ts, "m": m, "n": n, "history": history}


def run_sensitivity(args: argparse.Namespace) -> Dict[str, Any]:
    arr, titles = read_timeseries(args.file, args.delim, args.drop_nan)
    validate_observable_column(arr, args.col, titles)
    m_values = parse_int_list(args.m_values) or [2, 10, 20, 25, 30]
    rows = []
    for m0 in m_values:
        res = legacy_sequential_search(arr, args.col, args.ts, m0, args.alpha, args.min_blocks)
        rows.append({"m_init": m0, "status": res["status"], "ts": res["ts"], "m_final": res["m"], "n_final": res["n"]})
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_csv = outdir / f"{args.prefix or 'legacy_sensitivity'}_table.csv"
    write_csv(out_csv, rows)
    out_json = outdir / f"{args.prefix or 'legacy_sensitivity'}_summary.json"
    write_json(out_json, {"file": args.file, "column": args.col, "m_values": m_values, "rows": rows})
    print("Legacy sequential m_init sensitivity table")
    for r in rows:
        print(f"  m_init={r['m_init']:>4}  status={r['status']:<20}  ts={r['ts']:.6g}  m_final={r['m_final']}  n={r['n_final']}")
    print(f"Saved {out_csv}")
    return {"rows": rows, "out_csv": str(out_csv), "out_json": str(out_json)}


# -----------------------------------------------------------------------------
# Designed data
# -----------------------------------------------------------------------------

def generate_benchmark_data(outdir: Path, n: int = 100000, seed: int = 20260627) -> Dict[str, str]:
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
    df = pd.DataFrame({"time": t, name: x})
    df.to_csv(path, index=False)
    return str(path)


def run_make_data(args: argparse.Namespace) -> Dict[str, str]:
    files = generate_benchmark_data(Path(args.outdir), n=args.n_points, seed=args.seed)
    print("Generated designed benchmark data sets:")
    for k, v in files.items():
        print(f"  {k}: {v}")
    return files


# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------

def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(obj), f, indent=2, sort_keys=True)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False)
    else:
        pd.DataFrame().to_csv(path, index=False)


def write_trend_table(path: Path, table: List[Dict[str, Any]]) -> None:
    rows = []
    for entry in table:
        for mr in entry.get("m_results", []):
            row = {"candidate_start_index": entry["start_index"], "candidate_ts": entry["ts"], "candidate_all_pass": entry["all_pass"]}
            row.update(mr)
            rows.append(row)
    write_csv(path, rows)


def write_result_files(result: ManualResult, prefix: Path) -> None:
    write_json(prefix.with_suffix(".json"), result)
    with prefix.with_suffix(".txt").open("w", encoding="utf-8") as f:
        f.write(format_manual_result(result))


def format_manual_result(r: ManualResult) -> str:
    lines = []
    lines.append("MDTest four-test diagnostic report")
    lines.append(f"file: {r.file}")
    lines.append(f"column: {r.column} ({r.column_name})")
    lines.append(f"ts: {r.ts}  start_index: {r.start_index}  m: {r.m}  n: {r.n}  alpha: {r.alpha}")
    lines.append("")
    for name, t in r.tests.items():
        stat = "NA" if t.statistic is None else f"{t.statistic:.8g}"
        p = "NA" if t.p_value is None else f"{t.p_value:.8g}"
        lines.append(f"{name}: statistic={stat}, p={p}, pass={t.passed}, note={t.note}")
    lines.append("")
    lines.append(f"mean: {r.mean:.10g}")
    lines.append(f"standard error from block means: {r.se:.10g}")
    lines.append(f"95% t confidence interval: [{r.ci_low:.10g}, {r.ci_high:.10g}]")
    lines.append(f"overall_pass: {r.overall_pass}")
    lines.append(f"recommendation: {r.recommendation}")
    return "\n".join(lines) + "\n"


def print_manual_summary(r: ManualResult) -> None:
    print(format_manual_result(r))
    print(f"Saved report prefix: {r.output_prefix}")


def print_auto_safe_summary(r: AutoSafeResult) -> None:
    print("MDTest auto-safe summary")
    print(f"status: {r.status}")
    print(f"file: {r.file}")
    print(f"column: {r.column} ({r.column_name})")
    print(f"m_trend_grid: {r.m_trend_grid}; min_blocks={r.min_blocks}; alpha={r.alpha}")
    print(f"selected_ts_SW: {r.selected_ts_sw}; selected_start_index_SW: {r.selected_start_index_sw}")
    print(f"selected_m_corr: {r.selected_m_corr}; selected_n_corr: {r.selected_n_corr}")
    print(f"note: {r.note}")
    if r.manual_result:
        print("Final four-test result:")
        print(format_manual_result(r.manual_result))


def print_auto_compare_summary(r: AutoCompareResult) -> None:
    print("MDTest auto-compare summary")
    print(f"status: {r.status}")
    print(f"start_SW: {r.auto_safe.selected_ts_sw} (index {r.auto_safe.selected_start_index_sw})")
    print(f"start_ESS: {r.ess.selected_ts_ess} (index {r.ess.selected_start_index_ess}), g={r.ess.selected_g:.6g}, Neff={r.ess.selected_neff:.6g}")
    print(f"selected_ts_star: {r.selected_ts_star} (index {r.selected_start_index_star})")
    print(f"selected_m_corr_star: {r.selected_m_corr_star}; selected_n_corr_star: {r.selected_n_corr_star}")
    print(f"note: {r.note}")
    if r.manual_result_star:
        print("Final conservative four-test result:")
        print(format_manual_result(r.manual_result_star))


def _show_saved_or_live_figure(fig: Any, image_path: Path, display: bool) -> None:
    if not display:
        return

    # If in a Jupyter notebook, display the saved PNG inline.
    try:
        from IPython import get_ipython
        from IPython.display import Image, display as ipy_display

        shell = get_ipython()
        if shell is not None and shell.__class__.__name__ == "ZMQInteractiveShell":
            ipy_display(Image(filename=str(image_path)))
            return
    except Exception:
        pass

    # Otherwise, just use Matplotlib's normal GUI display.
    try:
        plt.show(block=True)
    except Exception:
        print(f"Plot saved to {image_path}")


def plot_initial_raw(times: np.ndarray, values: np.ndarray, out_path: Path, title: str = "observable", display: bool = False) -> None:
    """Save and optionally display the initial raw time-series preview."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(times, values, linewidth=0.8)
    ax.set_xlabel("time")
    ax.set_ylabel(title)
    ax.set_title("Initial raw time-series preview")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    _show_saved_or_live_figure(fig, out_path, display)
    plt.close(fig)


def plot_raw_and_blocks(times: np.ndarray, values: np.ndarray, block_t: np.ndarray, block_y: np.ndarray, ts: float, m: int, prefix: Path, title: str = "observable", display: bool = False) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw_path = prefix.with_name(prefix.name + "_raw.png")
    blocks_path = prefix.with_name(prefix.name + "_blocks.png")

    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(times, values, linewidth=0.8)
    ax.axvline(ts, linestyle="--", linewidth=1.0)
    ax.set_xlabel("time")
    ax.set_ylabel(title)
    ax.set_title(f"Raw time series; selected start ts={ts:g}")
    fig.tight_layout()
    fig.savefig(raw_path, dpi=180)
    _show_saved_or_live_figure(fig, raw_path, display)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(block_t, block_y, marker="o", markersize=3.0, linewidth=0.8)
    ax.set_xlabel("time")
    ax.set_ylabel(f"block mean of {title}")
    ax.set_title(f"Block means after coarse graining (m={m})")
    fig.tight_layout()
    fig.savefig(blocks_path, dpi=180)
    _show_saved_or_live_figure(fig, blocks_path, display)
    plt.close(fig)


# -----------------------------------------------------------------------------
# Config handling and CLI
# -----------------------------------------------------------------------------

def parse_config_file(path: str) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        first = f.readline().strip()
        if first.lower() != "md test format":
            raise ValueError("Configuration file must begin with 'MD Test Format'.")
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "-" not in s:
                continue
            key, value = s.split("-", 1)
            cfg[key.strip().lower().replace(" ", "_")] = value.strip()
    return cfg


def config_to_argv(cfg: Dict[str, str]) -> List[str]:
    aliases = {
        "run_type": "mode", "run": "mode", "type": "mode", "runtype": "mode",
        "file_name": "file", "file_path": "file",
        "delimination": "delim", "delimitation": "delim", "separation": "delim", "sep": "delim",
        "colread": "col", "column_read": "col", "col_read": "col",
        "start_time": "ts", "starting_time": "ts",
        "mvalue": "m", "m_value": "m", "m-value": "m",
        "nvalue": "n", "n_value": "n", "n-value": "n",
        "alpha_value": "alpha", "alphavalue": "alpha",
    }
    norm = {aliases.get(k, k): v for k, v in cfg.items()}
    mode = norm.get("mode", "manual").lower()
    # Support old 'auto-binary' and 'auto-sequential' spellings by mapping to safer implementation.
    mode_map = {
        "auto": "auto-safe",
        "auto-binary": "auto-safe",
        "auto-sequential": "auto-safe",
        "manual": "manual",
        "auto-safe": "auto-safe",
        "auto_compare": "auto-compare",
        "auto-compare": "auto-compare",
        "sensitivity": "sensitivity",
    }
    mode = mode_map.get(mode, mode)
    argv = [mode]
    def add(flag: str, key: str):
        if key in norm and norm[key] != "":
            argv.extend([flag, norm[key]])
    add("--file", "file")
    add("--delim", "delim")
    add("--col", "col")
    add("--ts", "ts")
    add("--m", "m")
    add("--n", "n")
    add("--alpha", "alpha")
    add("--min-blocks", "min_blocks")
    add("--m-trend-grid", "m_trend_grid")
    add("--m-corr-grid", "m_corr_grid")
    add("--outdir", "outdir")
    add("--prefix", "prefix")
    add("--m-values", "m_values")
    if norm.get("no_plots", "false").lower() in {"1", "true", "yes"}:
        argv.append("--no-plots")
    return argv


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--file", required=True, help="Input CSV/TXT/DAT file; column 0 is time.")
    p.add_argument("--delim", default="comma", help="Delimiter: comma, space, tab. CSV uses comma by default.")
    p.add_argument("--col", type=int, default=1, help="Observable column index to analyze (time is column 0).")
    p.add_argument("--alpha", type=float, default=0.05, help="Significance level.")
    p.add_argument("--min-blocks", type=int, default=24, help="Minimum number of block samples for diagnostic tests.")
    p.add_argument("--outdir", default="results", help="Directory for reports and plots.")
    p.add_argument("--prefix", default=None, help="Output filename prefix.")
    p.add_argument("--drop-nan", action="store_true", help="Drop rows containing NaN/Inf instead of rejecting the file.")
    p.add_argument("--no-plots", action="store_true", help="Do not generate PNG diagnostic plots.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MDTest revised stationarity and uncertainty diagnostics")
    sub = parser.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("manual", help="Evaluate the four-test protocol at specified ts, m, n.")
    add_common_args(p)
    p.add_argument("--ts", type=float, default=0.0, help="Start time.")
    p.add_argument("--m", type=int, required=True, help="Block size.")
    p.add_argument("--n", default="max", help="Number of blocks, or 'max'.")
    p.set_defaults(func=run_manual)

    p = sub.add_parser("auto-safe", help="Multi-resolution stationarity search plus block-length selection.")
    add_common_args(p)
    p.add_argument("--m-trend-grid", default="2,5,10,20,40", help="Fixed diagnostic m grid for stationarity tests.")
    p.add_argument("--m-corr-grid", default="5,10,20,30,40,60,80,120,160,240,320,480", help="Candidate m values for final normality/correlation tests.")
    p.add_argument("--stride-points", type=int, default=None, help="Candidate-start stride in raw data points; default N/150.")
    p.set_defaults(func=run_auto_safe)

    p = sub.add_parser("auto-compare", help="auto-safe plus ESS/IACT-style comparator and conservative max start.")
    add_common_args(p)
    p.add_argument("--m-trend-grid", default="2,5,10,20,40", help="Fixed diagnostic m grid for stationarity tests.")
    p.add_argument("--m-corr-grid", default="5,10,20,30,40,60,80,120,160,240,320,480", help="Candidate m values for final normality/correlation tests.")
    p.add_argument("--stride-points", type=int, default=None, help="Candidate-start stride in raw data points; default N/150.")
    p.add_argument("--ess-stride-points", type=int, default=None, help="ESS scan stride; default same as stationarity stride or N/150.")
    p.add_argument("--ess-min-lag", type=int, default=3, help="Minimum lag before first-negative ACF truncation.")
    p.add_argument("--ess-max-lag", type=int, default=None, help="Maximum ACF lag for ESS comparator.")
    p.set_defaults(func=run_auto_compare)

    p = sub.add_parser("sensitivity", help="Legacy m_init sensitivity diagnostic.")
    add_common_args(p)
    p.add_argument("--ts", type=float, default=0.0, help="Initial start time for legacy search.")
    p.add_argument("--m-values", default="2,10,20,25,30", help="Initial m values to test.")
    p.set_defaults(func=run_sensitivity)

    p = sub.add_parser("make-data", help="Generate designed synthetic benchmark data sets.")
    p.add_argument("--outdir", default="examples/data", help="Output directory for generated data.")
    p.add_argument("--n-points", type=int, default=100000, help="Number of points per synthetic data set.")
    p.add_argument("--seed", type=int, default=20260627, help="Random seed.")
    p.set_defaults(func=run_make_data)

    p = sub.add_parser("config", help="Run from MD Test Format key-value configuration file.")
    p.add_argument("config_file", help="Configuration file path.")
    return parser



# -----------------------------------------------------------------------------
# Conservative interactive walkthrough wrapper
# -----------------------------------------------------------------------------

def _prompt_text(prompt: str, default: Optional[str] = None, allow_empty: bool = False) -> str:
    """Prompt for text with a default.  This helper is intentionally small so
    the walkthrough remains a thin wrapper around the tested command-line paths.
    """
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value == "" and default is not None:
            return str(default)
        if value != "" or allow_empty:
            return value
        print("Please enter a value, or press Ctrl-C to exit.")


def _prompt_int(prompt: str, default: Optional[int] = None, minimum: Optional[int] = None) -> int:
    while True:
        raw = _prompt_text(prompt, None if default is None else str(default))
        try:
            value = int(raw)
            if minimum is not None and value < minimum:
                raise ValueError
            return value
        except ValueError:
            if minimum is None:
                print("Please enter an integer.")
            else:
                print(f"Please enter an integer >= {minimum}.")


def _prompt_float(prompt: str, default: Optional[float] = None) -> float:
    while True:
        raw = _prompt_text(prompt, None if default is None else str(default))
        try:
            return float(raw)
        except ValueError:
            print("Please enter a numeric value.")


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    default_text = "yes" if default else "no"
    while True:
        raw = _prompt_text(prompt, default_text).strip().lower()
        if raw in {"y", "yes", "true", "1"}:
            return True
        if raw in {"n", "no", "false", "0"}:
            return False
        print("Please answer yes or no.")


def _show_columns(titles: Sequence[str]) -> None:
    print("\nDetected columns:")
    for i, name in enumerate(titles):
        role = "time" if i == 0 else "observable"
        print(f"  {i:>3}: {name} ({role})")
    print("Column 0 is treated as time; choose an observable column >= 1.\n")


def run_walkthrough() -> Any:
    """Interactive no-argument walkthrough.

    This function restores the original MDTest user-facing behavior while
    keeping the revised, reviewer-testable implementation unchanged.  The
    walkthrough only gathers inputs and then calls the same run_manual,
    run_auto_safe, run_auto_compare, or run_sensitivity functions used by the
    command-line interface.  Batch modes still save PNG files by default;
    walkthrough mode also displays the initial and result plots when the
    local Python/Jupyter environment supports interactive display.
    """
    print(PROGRAM_BANNER)
    print("Interactive walkthrough mode")
    print("Press Ctrl-C at any prompt to exit.  Reports and plots are saved to the output directory; plots are also displayed when possible.\n")

    file = _prompt_text("Input data file")
    delim = _prompt_text("Delimiter for input file (comma, space, or tab)", "comma")
    drop_nan = _prompt_yes_no("Drop nonnumeric/NaN/Inf rows after warning", False)

    # Read once here only to validate the file and show column choices.  The
    # selected command re-reads the file through the normal tested path.
    arr, titles = read_timeseries(file, delim, drop_nan)
    _show_columns(titles)
    col = _prompt_int("Observable column index", 1, minimum=1)
    validate_observable_column(arr, col, titles)

    display_plots = _prompt_yes_no("Display plots interactively during walkthrough", True)
    if display_plots:
        preview_path = Path("results/walkthrough_preview") / f"preview_col{col}_initial_raw.png"
        print(f"Saving initial raw preview to {preview_path}")
        plot_initial_raw(arr[:, 0], arr[:, col], preview_path, title=titles[col], display=True)

    print("Available run modes:")
    print("  manual       Evaluate the four-test protocol at a chosen (ts, m, n).")
    print("  auto-safe    Multi-resolution stationarity search plus block selection.")
    print("  auto-compare auto-safe plus Chodera/PyMBAR-style ESS/IACT comparator.")
    print("  sensitivity  Legacy m_init sensitivity diagnostic.")
    mode = _prompt_text("Run mode", "manual").strip().lower().replace("_", "-")
    mode_map = {
        "manual": "manual",
        "auto": "auto-safe",
        "auto-safe": "auto-safe",
        "auto-binary": "auto-safe",
        "auto-sequential": "auto-safe",
        "auto-compare": "auto-compare",
        "compare": "auto-compare",
        "sensitivity": "sensitivity",
        "legacy": "sensitivity",
    }
    if mode not in mode_map:
        raise ValueError(f"Unknown walkthrough mode '{mode}'.")
    mode = mode_map[mode]

    alpha = _prompt_float("Significance level alpha", 0.05)
    min_blocks = _prompt_int("Minimum number of blocks", 24, minimum=2)
    outdir = _prompt_text("Output directory", "results/walkthrough")
    prefix_default = f"walkthrough_{mode.replace('-', '_')}_col{col}"
    prefix = _prompt_text("Output filename prefix", prefix_default)
    make_plots = _prompt_yes_no("Save diagnostic PNG plots", True)

    common = dict(
        file=file,
        delim=delim,
        col=col,
        alpha=alpha,
        min_blocks=min_blocks,
        outdir=outdir,
        prefix=prefix,
        drop_nan=drop_nan,
        no_plots=not make_plots,
        display_plots=display_plots and make_plots,
    )

    if mode == "manual":
    # users can try different (ts, m, n)
    # values without restarting the program. Each run gets a distinct
    # prefix to avoid overwriting reports/plots from earlier trials.
        run_count = 1
        last_result = None
        while True:
            print(f"\nManual test #{run_count}")
            ts = _prompt_float("Start time ts", 0.0)
            m = _prompt_int("Block size m", 10, minimum=1)
            n = _prompt_text("Number of blocks n (integer or max)", "max")

            trial_common = dict(common)
            trial_common["prefix"] = f"{prefix}_trial{run_count:02d}"
            args = argparse.Namespace(**trial_common, ts=ts, m=m, n=n)
            last_result = run_manual(args)

            if not _prompt_yes_no("Run another manual test with different parameters", True):
                return last_result
            run_count += 1

    if mode == "auto-safe":
        m_trend_grid = _prompt_text("Trend-test m grid", "2,5,10,20,40")
        m_corr_grid = _prompt_text("Correlation/normality m grid", "5,10,20,30,40,60,80,120,160,240,320,480")
        stride_raw = _prompt_text("Candidate-start stride in raw points (blank for default)", "", allow_empty=True)
        stride_points = int(stride_raw) if stride_raw.strip() else None
        args = argparse.Namespace(**common, m_trend_grid=m_trend_grid, m_corr_grid=m_corr_grid, stride_points=stride_points)
        return run_auto_safe(args)

    if mode == "auto-compare":
        m_trend_grid = _prompt_text("Trend-test m grid", "2,5,10,20,40")
        m_corr_grid = _prompt_text("Correlation/normality m grid", "5,10,20,30,40,60,80,120,160,240,320,480")
        stride_raw = _prompt_text("Stationarity scan stride in raw points (blank for default)", "", allow_empty=True)
        ess_stride_raw = _prompt_text("ESS scan stride in raw points (blank for default)", "", allow_empty=True)
        ess_min_lag = _prompt_int("ESS minimum lag before nonpositive truncation", 3, minimum=0)
        ess_max_lag_raw = _prompt_text("ESS maximum lag (blank for no cap)", "", allow_empty=True)
        args = argparse.Namespace(
            **common,
            m_trend_grid=m_trend_grid,
            m_corr_grid=m_corr_grid,
            stride_points=int(stride_raw) if stride_raw.strip() else None,
            ess_stride_points=int(ess_stride_raw) if ess_stride_raw.strip() else None,
            ess_min_lag=ess_min_lag,
            ess_max_lag=int(ess_max_lag_raw) if ess_max_lag_raw.strip() else None,
        )
        return run_auto_compare(args)

    if mode == "sensitivity":
        ts = _prompt_float("Initial start time ts", 0.0)
        m_values = _prompt_text("Initial m values to test", "2,10,20,25,30")
        args = argparse.Namespace(**common, ts=ts, m_values=m_values)
        return run_sensitivity(args)

    raise ValueError(f"Unhandled walkthrough mode '{mode}'.")

def main(argv: Optional[Sequence[str]] = None) -> Any:
    if argv is None and len(sys.argv) == 1:
        return run_walkthrough()
    parser = build_parser()
    args = parser.parse_args(argv)
    print(PROGRAM_BANNER)
    if args.mode == "config":
        cfg = parse_config_file(args.config_file)
        new_argv = config_to_argv(cfg)
        args2 = parser.parse_args(new_argv)
        return args2.func(args2)
    return args.func(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"MDTest ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
