"""MDTest stationarity-screening and block-selection algorithms.

Scientific logic in this module is preserved from the Round-1 implementation.
I/O and plotting helpers are imported from dedicated modules so later interface
work can evolve independently of the statistical calculations.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
from .results import TestOutcome, ManualResult, AutoSafeResult, RunProvenance, RunSettings
from .io import validate_observable_column, ensure_uniform_time, time_to_start_index, max_blocks
from .diagnostics import block_series, mann_kendall_test, shapiro_test, von_neumann_positive_test, confidence_interval_t
from .plotting import plot_raw_and_blocks
from .reporting import write_result_files


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
    write_outputs: bool = True,
    settings: Optional[RunSettings] = None,
    provenance: Optional[RunProvenance] = None,
) -> ManualResult:
    'Evaluate the four-test MDTest protocol for one retained window and block size.'
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

    out_prefix = outdir / prefix
    if write_outputs:
        outdir.mkdir(parents=True, exist_ok=True)
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
        settings=settings,
        provenance=provenance,
    )
    if write_outputs:
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
    'Evaluate the mean and dispersion trend tests at one candidate start and block size.'
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
    'Find the earliest scan-grid start passing trend tests at every diagnostic block size.'
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
    write_outputs: bool = True,
    settings: Optional[RunSettings] = None,
    provenance: Optional[RunProvenance] = None,
) -> Optional[ManualResult]:
    'Choose the smallest candidate block size passing the full four-test protocol.'
    times = arr[:, 0]
    ts = float(times[start_index])
    for m in sorted(set(int(x) for x in m_candidates if int(x) >= 2)):
        n = max_blocks(len(times) - start_index, m)
        if n < min_blocks:
            continue
        result = evaluate_four_tests(
            file=file, arr=arr, titles=titles, col=col, ts=ts, m=m, n=None,
            alpha=alpha, outdir=outdir, prefix=f"{prefix}_m{m}", make_plots=make_plots,
            min_blocks=min_blocks, display_plots=display_plots, write_outputs=write_outputs,
            settings=settings, provenance=provenance,
        )
        # For m_corr selection, require normality and local correlation, while
        # preserving stationarity tests at the selected start.
        if result.overall_pass:
            return result
    return None


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
