"""Public programmatic Python interface for MDTest.

Round 2A keeps the statistical algorithms frozen while consolidating the
auto-safe orchestration into one private engine and strengthening interface
validation/reproducibility metadata.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import math
from typing import Any, Dict, Optional, Sequence, Union

from .analysis import choose_correlation_block, evaluate_four_tests, find_multiresolution_stationarity, legacy_sequential_search
from .autocorrelation import detect_ess_start
from .benchmarks import generate_benchmark_data
from .io import parse_int_list, parse_n, read_timeseries, validate_integer, validate_integer_sequence, validate_observable_column
from .provenance import collect_provenance
from .reporting import write_csv, write_json, write_trend_table
from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult, RunSettings

PathLike = Union[str, Path]
DEFAULT_TREND_GRID = (2, 5, 10, 20, 40)
DEFAULT_CORR_GRID = (5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480)


def _int_grid(values: Optional[Sequence[int] | str], default: Sequence[int], name: str, *, minimum: int = 1) -> list[int]:
    if values is None:
        return list(default)
    if isinstance(values, str):
        parsed = parse_int_list(values)
        if any(v < minimum for v in parsed):
            raise ValueError(f"{name} entries must be >= {minimum}.")
    else:
        parsed = validate_integer_sequence(values, name, minimum=minimum)
    return parsed or list(default)


def _validate_start_time(ts: Any) -> float:
    """Reject nonfinite start times before indexing, with finite behavior unchanged."""
    if isinstance(ts, bool):
        raise ValueError("ts must be a finite physical start time.")
    try:
        value = float(ts)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("ts must be a finite physical start time.") from exc
    if not math.isfinite(value):
        raise ValueError("ts must be a finite physical start time.")
    return value


def _validate_drop_nan(value: Any) -> bool:
    """Prevent a string such as 'False' from enabling data-row deletion."""
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError("drop_nan must be a Boolean (True or False), not a string or number.")
    return bool(value)


def _validate_alpha(alpha: Any) -> float:
    """Validate the public significance level without changing the tests.

    Invalid thresholds, notably zero or negative values, can turn a clearly
    rejected trend into a misleading PASS.  Valid thresholds are unchanged.
    """
    if isinstance(alpha, bool):
        raise ValueError("alpha must be a finite number strictly between 0 and 1.")
    try:
        value = float(alpha)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("alpha must be a finite number strictly between 0 and 1.") from None
    if not (math.isfinite(value) and 0.0 < value < 1.0):
        raise ValueError("alpha must be a finite number strictly between 0 and 1.")
    return value


def _run_auto_safe_engine(
    *, file: str, arr, titles, col: int, alpha: float, min_blocks: int,
    trend_grid: list[int], corr_grid: list[int], stride_points: Optional[int],
    output_dir: Path, output_prefix: str, write_outputs: bool, make_plots: bool,
    display_plots: bool, settings: RunSettings, provenance,
) -> AutoSafeResult:
    """Single implementation of the multi-resolution SW/stationarity branch."""
    idx, trend_table, note = find_multiresolution_stationarity(
        arr, col=col, alpha=alpha, m_grid=trend_grid, min_blocks=min_blocks, stride_points=stride_points
    )
    manual_result = None
    selected_m = None
    selected_n = None
    if idx is not None:
        manual_result = choose_correlation_block(
            file=file, arr=arr, titles=titles, col=col, start_index=idx, alpha=alpha,
            min_blocks=min_blocks, m_candidates=corr_grid, outdir=output_dir, prefix=output_prefix,
            make_plots=make_plots, display_plots=display_plots, write_outputs=write_outputs,
            settings=settings, provenance=provenance,
        )
        if manual_result is not None:
            selected_m, selected_n = manual_result.m, manual_result.n
            status, note2 = "pass", note
        else:
            status = "stationarity-pass-correlation-not-found"
            note2 = note + "; no m_corr candidate passed normality and local correlation tests"
    else:
        status, note2 = "stationarity-not-found", note

    times = arr[:, 0]
    result = AutoSafeResult(
        file=file, column=col, column_name=titles[col] if col < len(titles) else f"column_{col}",
        alpha=alpha, min_blocks=min_blocks, m_trend_grid=trend_grid,
        selected_ts_sw=float(times[idx]) if idx is not None else None,
        selected_start_index_sw=int(idx) if idx is not None else None,
        selected_m_corr=selected_m, selected_n_corr=selected_n, manual_result=manual_result,
        trend_table=trend_table, status=status, note=note2, settings=settings, provenance=provenance,
    )
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / f"{output_prefix}_summary.json", result)
        write_trend_table(output_dir / f"{output_prefix}_trend_table.csv", trend_table)
    return result


def manual(file: PathLike, *, col: int = 1, ts: float = 0.0, m: int, n: Optional[int | str] = None,
           delim: str = "comma", alpha: float = 0.05, min_blocks: int = 24, drop_nan: bool = False,
           outdir: PathLike = "results", prefix: Optional[str] = None, write_outputs: bool = False,
           make_plots: bool = False, display_plots: bool = False) -> ManualResult:
    """Run the four-test MDTest diagnostic at a user-selected window."""
    ts = _validate_start_time(ts)
    alpha = _validate_alpha(alpha)
    file = str(file)
    col = validate_integer(col, "col", minimum=1)
    m = validate_integer(m, "m", minimum=1)
    min_blocks = validate_integer(min_blocks, "min_blocks", minimum=1)
    n_value = parse_n(n)
    drop_nan = _validate_drop_nan(drop_nan)
    arr, titles = read_timeseries(file, delim, drop_nan)
    validate_observable_column(arr, col, titles)
    output_prefix = prefix or f"manual_col{col}_ts{str(ts).replace('.', 'p')}_m{m}"
    settings = RunSettings(mode="manual", column=col, delimiter=delim, drop_nan=bool(drop_nan), alpha=float(alpha),
                           min_blocks=min_blocks, ts=float(ts), m=m, n=n_value)
    provenance = collect_provenance(file, parsed_array=arr[:, [0, col]])
    return evaluate_four_tests(file=file, arr=arr, titles=titles, col=col, ts=float(ts), m=m, n=n_value,
        alpha=float(alpha), outdir=Path(outdir), prefix=output_prefix, make_plots=bool(make_plots),
        min_blocks=min_blocks, display_plots=bool(display_plots), write_outputs=bool(write_outputs),
        settings=settings, provenance=provenance)


def auto_safe(file: PathLike, *, col: int = 1, delim: str = "comma", alpha: float = 0.05, min_blocks: int = 24,
              m_trend_grid: Optional[Sequence[int] | str] = None, m_corr_grid: Optional[Sequence[int] | str] = None,
              stride_points: Optional[int] = None, drop_nan: bool = False, outdir: PathLike = "results",
              prefix: Optional[str] = None, write_outputs: bool = False, make_plots: bool = False,
              display_plots: bool = False) -> AutoSafeResult:
    """Run the multi-resolution stationarity search and final block selection."""
    alpha = _validate_alpha(alpha)
    file = str(file)
    col = validate_integer(col, "col", minimum=1)
    min_blocks = validate_integer(min_blocks, "min_blocks", minimum=1)
    stride_points = validate_integer(stride_points, "stride_points", minimum=1, allow_none=True)
    trend_grid = _int_grid(m_trend_grid, DEFAULT_TREND_GRID, "m_trend_grid", minimum=2)
    corr_grid = _int_grid(m_corr_grid, DEFAULT_CORR_GRID, "m_corr_grid", minimum=2)
    drop_nan = _validate_drop_nan(drop_nan)
    arr, titles = read_timeseries(file, delim, drop_nan)
    validate_observable_column(arr, col, titles)
    settings = RunSettings(mode="auto-safe", column=col, delimiter=delim, drop_nan=bool(drop_nan), alpha=float(alpha),
                           min_blocks=min_blocks, m_trend_grid=trend_grid, m_corr_grid=corr_grid, stride_points=stride_points)
    return _run_auto_safe_engine(file=file, arr=arr, titles=titles, col=col, alpha=float(alpha), min_blocks=min_blocks,
        trend_grid=trend_grid, corr_grid=corr_grid, stride_points=stride_points, output_dir=Path(outdir),
        output_prefix=prefix or "auto_safe", write_outputs=bool(write_outputs), make_plots=bool(make_plots),
        display_plots=bool(display_plots), settings=settings, provenance=collect_provenance(file, parsed_array=arr[:, [0, col]]))


def ess(file: PathLike, *, col: int = 1, delim: str = "comma", drop_nan: bool = False, min_blocks: int = 24,
        scan_stride_points: Optional[int] = None, min_lag: int = 3, max_lag: Optional[int] = None) -> ESSResult:
    """Run only the Chodera/PyMBAR-style ESS/IACT start-time comparator."""
    file = str(file)
    col = validate_integer(col, "col", minimum=1)
    min_blocks = validate_integer(min_blocks, "min_blocks", minimum=1)
    scan_stride_points = validate_integer(scan_stride_points, "scan_stride_points", minimum=1, allow_none=True)
    min_lag = validate_integer(min_lag, "min_lag", minimum=0)
    max_lag = validate_integer(max_lag, "max_lag", minimum=0, allow_none=True)
    drop_nan = _validate_drop_nan(drop_nan)
    arr, titles = read_timeseries(file, delim, drop_nan)
    validate_observable_column(arr, col, titles)
    result = detect_ess_start(arr, col=col, min_blocks=min_blocks, scan_stride_points=scan_stride_points, min_lag=min_lag, max_lag=max_lag)
    result.settings = RunSettings(mode="ess", column=col, delimiter=delim, drop_nan=bool(drop_nan), min_blocks=min_blocks,
                                  ess_stride_points=scan_stride_points, ess_min_lag=min_lag, ess_max_lag=max_lag)
    result.provenance = collect_provenance(file, parsed_array=arr[:, [0, col]])
    return result


def auto_compare(file: PathLike, *, col: int = 1, delim: str = "comma", alpha: float = 0.05, min_blocks: int = 24,
                 m_trend_grid: Optional[Sequence[int] | str] = None, m_corr_grid: Optional[Sequence[int] | str] = None,
                 stride_points: Optional[int] = None, ess_stride_points: Optional[int] = None, ess_min_lag: int = 3,
                 ess_max_lag: Optional[int] = None, drop_nan: bool = False, outdir: PathLike = "results",
                 prefix: Optional[str] = None, write_outputs: bool = False, make_plots: bool = False,
                 display_plots: bool = False) -> AutoCompareResult:
    """Run MDTest stationarity screening and ESS/IACT side by side."""
    alpha = _validate_alpha(alpha)
    file = str(file)
    col = validate_integer(col, "col", minimum=1)
    min_blocks = validate_integer(min_blocks, "min_blocks", minimum=1)
    stride_points = validate_integer(stride_points, "stride_points", minimum=1, allow_none=True)
    ess_stride_points = validate_integer(ess_stride_points, "ess_stride_points", minimum=1, allow_none=True)
    ess_min_lag = validate_integer(ess_min_lag, "ess_min_lag", minimum=0)
    ess_max_lag = validate_integer(ess_max_lag, "ess_max_lag", minimum=0, allow_none=True)
    trend_grid = _int_grid(m_trend_grid, DEFAULT_TREND_GRID, "m_trend_grid", minimum=2)
    corr_grid = _int_grid(m_corr_grid, DEFAULT_CORR_GRID, "m_corr_grid", minimum=2)
    drop_nan = _validate_drop_nan(drop_nan)
    arr, titles = read_timeseries(file, delim, drop_nan)
    validate_observable_column(arr, col, titles)
    provenance = collect_provenance(file, parsed_array=arr[:, [0, col]])
    actual_ess_stride = ess_stride_points if ess_stride_points is not None else stride_points
    compare_settings = RunSettings(mode="auto-compare", column=col, delimiter=delim, drop_nan=bool(drop_nan), alpha=float(alpha),
        min_blocks=min_blocks, m_trend_grid=trend_grid, m_corr_grid=corr_grid, stride_points=stride_points,
        ess_stride_points=actual_ess_stride, ess_min_lag=ess_min_lag, ess_max_lag=ess_max_lag)
    safe_settings = RunSettings(mode="auto-safe", column=col, delimiter=delim, drop_nan=bool(drop_nan), alpha=float(alpha),
        min_blocks=min_blocks, m_trend_grid=trend_grid, m_corr_grid=corr_grid, stride_points=stride_points)
    output_dir = Path(outdir)
    final_prefix = prefix or "auto_compare"
    # Legacy CLI compatibility: without an explicit prefix Round 1 emitted the
    # auto-safe subanalysis under 'auto_safe_*'.  Keep those aliases while also
    # writing the clearer auto-compare trend table below.
    safe_prefix = prefix or "auto_safe"
    safe = _run_auto_safe_engine(file=file, arr=arr, titles=titles, col=col, alpha=float(alpha), min_blocks=min_blocks,
        trend_grid=trend_grid, corr_grid=corr_grid, stride_points=stride_points, output_dir=output_dir,
        output_prefix=safe_prefix, write_outputs=bool(write_outputs), make_plots=bool(make_plots),
        display_plots=bool(display_plots), settings=safe_settings, provenance=provenance)

    ess_result = detect_ess_start(arr, col=col, min_blocks=min_blocks, scan_stride_points=actual_ess_stride,
                                  min_lag=ess_min_lag, max_lag=ess_max_lag)
    ess_result.settings = RunSettings(mode="ess", column=col, delimiter=delim, drop_nan=bool(drop_nan), min_blocks=min_blocks,
        ess_stride_points=actual_ess_stride, ess_min_lag=ess_min_lag, ess_max_lag=ess_max_lag)
    ess_result.provenance = provenance

    if safe.selected_start_index_sw is None:
        idx_star = ess_result.selected_start_index_ess
        note = "multi-resolution stationarity start not found; reporting ESS start but not treating it as stationarity-certified"
        status = "ess-only-no-stationarity-certification"
    else:
        idx_star = max(safe.selected_start_index_sw, ess_result.selected_start_index_ess)
        note, status = "selected conservative start max(start_SW, start_ESS)", "pass"

    manual_star = None
    selected_m = None
    selected_n = None
    if idx_star is not None:
        manual_star = choose_correlation_block(file=file, arr=arr, titles=titles, col=col, start_index=idx_star,
            alpha=float(alpha), min_blocks=min_blocks, m_candidates=corr_grid, outdir=output_dir,
            prefix=f"{final_prefix}_star", make_plots=bool(make_plots), display_plots=bool(display_plots),
            write_outputs=bool(write_outputs), settings=compare_settings, provenance=provenance)
        if manual_star is not None:
            selected_m, selected_n = manual_star.m, manual_star.n
        else:
            status = "start-found-correlation-not-found"
            note += "; no m_corr candidate passed all four tests at selected start"

    times = arr[:, 0]
    result = AutoCompareResult(auto_safe=safe, ess=ess_result,
        selected_ts_star=float(times[idx_star]) if idx_star is not None else None,
        selected_start_index_star=int(idx_star) if idx_star is not None else None,
        selected_m_corr_star=selected_m, selected_n_corr_star=selected_n, manual_result_star=manual_star,
        status=status, note=note, settings=compare_settings, provenance=provenance)
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / f"{final_prefix}_summary.json", result)
        # New explicit alias, while legacy auto_safe_* files above remain available.
        write_trend_table(output_dir / f"{final_prefix}_trend_table.csv", safe.trend_table)
        write_csv(output_dir / f"{final_prefix}_ess_scan.csv", ess_result.scan_table)
    return result


def sensitivity(file: PathLike, *, col: int = 1, ts: float = 0.0, m_values: Optional[Sequence[int] | str] = None,
                delim: str = "comma", alpha: float = 0.05, min_blocks: int = 24, drop_nan: bool = False,
                outdir: PathLike = "results", prefix: Optional[str] = None, write_outputs: bool = False) -> Dict[str, Any]:
    """Run the retained legacy sequential m-initialization sensitivity diagnostic."""
    ts = _validate_start_time(ts)
    alpha = _validate_alpha(alpha)
    file = str(file)
    col = validate_integer(col, "col", minimum=1)
    min_blocks = validate_integer(min_blocks, "min_blocks", minimum=1)
    grid = _int_grid(m_values, (2, 10, 20, 25, 30), "m_values", minimum=1)
    drop_nan = _validate_drop_nan(drop_nan)
    arr, titles = read_timeseries(file, delim, drop_nan)
    validate_observable_column(arr, col, titles)
    rows = []
    for m0 in grid:
        res = legacy_sequential_search(arr, col, float(ts), m0, float(alpha), min_blocks)
        rows.append({"m_init": m0, "status": res["status"], "ts": res["ts"], "m_final": res["m"], "n_final": res["n"]})
    output_dir = Path(outdir)
    output_prefix = prefix or "legacy_sensitivity"
    out_csv = str(output_dir / f"{output_prefix}_table.csv")
    out_json = str(output_dir / f"{output_prefix}_summary.json")
    result = {"file": file, "column": col, "m_values": grid, "rows": rows, "out_csv": out_csv, "out_json": out_json,
              "settings": RunSettings(mode="sensitivity", column=col, delimiter=delim, drop_nan=bool(drop_nan), alpha=float(alpha),
                                       min_blocks=min_blocks, ts=float(ts), m_values=grid),
              "provenance": collect_provenance(file, parsed_array=arr[:, [0, col]])}
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(Path(out_csv), rows)
        write_json(Path(out_json), result)
    return result


def make_benchmark_data(outdir: PathLike = "examples/data", *, n_points: int = 100000, seed: int = 20260627) -> Dict[str, str]:
    """Generate the deterministic synthetic benchmark files used by the manuscript."""
    n_points = validate_integer(n_points, "n_points", minimum=3)
    seed = validate_integer(seed, "seed", minimum=0)
    return generate_benchmark_data(Path(outdir), n=n_points, seed=seed)


def analyze(file: PathLike, *, mode: str = "auto-safe", **kwargs: Any) -> Any:
    """Convenience dispatcher for common programmatic use."""
    normalized = mode.strip().lower().replace("_", "-")
    if normalized == "manual": return manual(file, **kwargs)
    if normalized in {"auto-safe", "auto"}: return auto_safe(file, **kwargs)
    if normalized in {"auto-compare", "compare"}: return auto_compare(file, **kwargs)
    if normalized in {"ess", "iact", "ess-iact"}: return ess(file, **kwargs)
    if normalized in {"sensitivity", "legacy"}: return sensitivity(file, **kwargs)
    raise ValueError(f"Unknown MDTest analysis mode: {mode!r}")
