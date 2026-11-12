"""Command-line and interactive interfaces for MDTest.

The CLI is intentionally thin: argument parsing and prompts are translated
into calls to :mod:`mdtest.api`, which is also the interface used directly by
Python scripts and notebooks.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import api
from .io import read_timeseries, validate_observable_column
from .plotting import plot_initial_raw
from .reporting import format_manual_result, print_auto_compare_summary, print_auto_safe_summary, print_manual_summary

PROGRAM_BANNER = (
    "MDTest revised: stationarity and uncertainty diagnostics for scalar MD time series\n"
    "Jerry F. Wang, Haobin Wang, and Hai Lin\n"
)


def run_manual(args: argparse.Namespace):
    'Translate parsed CLI arguments into a direct Python manual-analysis call.'
    result = api.manual(
        args.file,
        col=args.col,
        ts=args.ts,
        m=args.m,
        n=args.n,
        delim=args.delim,
        alpha=args.alpha,
        min_blocks=args.min_blocks,
        drop_nan=args.drop_nan,
        outdir=args.outdir,
        prefix=args.prefix,
        write_outputs=True,
        make_plots=not args.no_plots,
        display_plots=getattr(args, "display_plots", False),
    )
    print_manual_summary(result)
    return result


def run_auto_safe(args: argparse.Namespace):
    'Translate parsed CLI arguments into a direct Python auto-safe call.'
    result = api.auto_safe(
        args.file,
        col=args.col,
        delim=args.delim,
        alpha=args.alpha,
        min_blocks=args.min_blocks,
        m_trend_grid=args.m_trend_grid,
        m_corr_grid=args.m_corr_grid,
        stride_points=args.stride_points,
        drop_nan=args.drop_nan,
        outdir=args.outdir,
        prefix=args.prefix,
        write_outputs=True,
        make_plots=not args.no_plots,
        display_plots=getattr(args, "display_plots", False),
    )
    print_auto_safe_summary(result)
    return result


def run_auto_compare(args: argparse.Namespace):
    'Translate parsed CLI arguments into a direct Python auto-compare call.'
    result = api.auto_compare(
        args.file,
        col=args.col,
        delim=args.delim,
        alpha=args.alpha,
        min_blocks=args.min_blocks,
        m_trend_grid=args.m_trend_grid,
        m_corr_grid=args.m_corr_grid,
        stride_points=args.stride_points,
        ess_stride_points=args.ess_stride_points,
        ess_min_lag=args.ess_min_lag,
        ess_max_lag=args.ess_max_lag,
        drop_nan=args.drop_nan,
        outdir=args.outdir,
        prefix=args.prefix,
        write_outputs=True,
        make_plots=not args.no_plots,
        display_plots=getattr(args, "display_plots", False),
    )
    print_auto_compare_summary(result)
    return result


def run_sensitivity(args: argparse.Namespace):
    'Translate parsed CLI arguments into the retained sensitivity diagnostic.'
    result = api.sensitivity(
        args.file,
        col=args.col,
        ts=args.ts,
        m_values=args.m_values,
        delim=args.delim,
        alpha=args.alpha,
        min_blocks=args.min_blocks,
        drop_nan=args.drop_nan,
        outdir=args.outdir,
        prefix=args.prefix,
        write_outputs=True,
    )
    print("Legacy sequential m_init sensitivity table")
    for row in result["rows"]:
        print(
            f"  m_init={row['m_init']:>4}  status={row['status']:<20}  "
            f"ts={row['ts']:.6g}  m_final={row['m_final']}  n={row['n_final']}"
        )
    if result.get("out_csv"):
        print(f"Saved {result['out_csv']}")
    return result


def run_make_data(args: argparse.Namespace):
    'Generate the bundled synthetic data from command-line arguments.'
    files = api.make_benchmark_data(args.outdir, n_points=args.n_points, seed=args.seed)
    print("Generated designed benchmark data sets:")
    for key, value in files.items():
        print(f"  {key}: {value}")
    return files


def parse_config_file(path: str) -> Dict[str, str]:
    'Read an MD Test Format key-value configuration file.'
    cfg: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        first = handle.readline().strip()
        if first.lower() != "md test format":
            raise ValueError("Configuration file must begin with 'MD Test Format'.")
        for line in handle:
            text = line.strip()
            if not text or text.startswith("#") or "-" not in text:
                continue
            key, value = text.split("-", 1)
            cfg[key.strip().lower().replace(" ", "_")] = value.strip()
    return cfg


def config_to_argv(cfg: Dict[str, str]) -> list[str]:
    """Translate config keys to CLI arguments and reject unknown/ignored keys."""
    aliases = {
        "run_type": "mode", "run": "mode", "type": "mode", "runtype": "mode",
        "file_name": "file", "file_path": "file",
        "delimination": "delim", "delimitation": "delim", "separation": "delim", "sep": "delim",
        "colread": "col", "column_read": "col", "col_read": "col",
        "start_time": "ts", "starting_time": "ts",
        "mvalue": "m", "m_value": "m", "m-value": "m",
        "nvalue": "n", "n_value": "n", "n-value": "n",
        "alpha_value": "alpha", "alphavalue": "alpha",
        "stride": "stride_points", "ess_stride": "ess_stride_points",
        "min_lag": "ess_min_lag", "max_lag": "ess_max_lag",
    }
    norm = {aliases.get(k, k): v for k, v in cfg.items()}
    allowed = {
        "mode", "file", "delim", "col", "ts", "m", "n", "alpha", "min_blocks",
        "m_trend_grid", "m_corr_grid", "stride_points", "ess_stride_points",
        "ess_min_lag", "ess_max_lag", "outdir", "prefix", "m_values",
        "no_plots", "drop_nan",
    }
    unknown = sorted(set(norm) - allowed)
    if unknown:
        raise ValueError("Unknown MDTest configuration key(s): " + ", ".join(unknown))
    mode = norm.get("mode", "manual").lower()
    mode_map = {
        "auto": "auto-safe", "auto-binary": "auto-safe", "auto-sequential": "auto-safe",
        "manual": "manual", "auto-safe": "auto-safe", "auto_compare": "auto-compare",
        "auto-compare": "auto-compare", "sensitivity": "sensitivity",
    }
    argv = [mode_map.get(mode, mode)]
    def add(flag: str, key: str) -> None:
        if key in norm and norm[key] != "": argv.extend([flag, norm[key]])
    for flag, key in [
        ("--file", "file"), ("--delim", "delim"), ("--col", "col"), ("--ts", "ts"),
        ("--m", "m"), ("--n", "n"), ("--alpha", "alpha"), ("--min-blocks", "min_blocks"),
        ("--m-trend-grid", "m_trend_grid"), ("--m-corr-grid", "m_corr_grid"),
        ("--stride-points", "stride_points"), ("--ess-stride-points", "ess_stride_points"),
        ("--ess-min-lag", "ess_min_lag"), ("--ess-max-lag", "ess_max_lag"),
        ("--outdir", "outdir"), ("--prefix", "prefix"), ("--m-values", "m_values"),
    ]: add(flag, key)
    true_values = {"1", "true", "yes", "y", "on"}
    if norm.get("no_plots", "false").lower() in true_values: argv.append("--no-plots")
    if norm.get("drop_nan", "false").lower() in true_values: argv.append("--drop-nan")
    return argv


def add_common_args(parser: argparse.ArgumentParser) -> None:
    'Add arguments shared by file-based analysis subcommands.'
    parser.add_argument("--file", required=True, help="Input CSV/TXT/DAT file; column 0 is time.")
    parser.add_argument("--delim", default="comma", help="Delimiter: comma, space, tab.")
    parser.add_argument("--col", type=int, default=1, help="Observable column index; column 0 is time.")
    parser.add_argument("--alpha", type=float, default=0.05, help="Significance level.")
    parser.add_argument("--min-blocks", type=int, default=24, help="Minimum number of block samples.")
    parser.add_argument("--outdir", default="results", help="Directory for reports and plots.")
    parser.add_argument("--prefix", default=None, help="Output filename prefix.")
    parser.add_argument("--drop-nan", action="store_true", help="Drop rows containing NaN/Inf.")
    parser.add_argument("--no-plots", action="store_true", help="Do not generate PNG diagnostic plots.")


def build_parser() -> argparse.ArgumentParser:
    'Construct the MDTest command-line argument parser.'
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
    p.add_argument("--m-trend-grid", default="2,5,10,20,40")
    p.add_argument("--m-corr-grid", default="5,10,20,30,40,60,80,120,160,240,320,480")
    p.add_argument("--stride-points", type=int, default=None)
    p.set_defaults(func=run_auto_safe)

    p = sub.add_parser("auto-compare", help="auto-safe plus ESS/IACT comparator and conservative max start.")
    add_common_args(p)
    p.add_argument("--m-trend-grid", default="2,5,10,20,40")
    p.add_argument("--m-corr-grid", default="5,10,20,30,40,60,80,120,160,240,320,480")
    p.add_argument("--stride-points", type=int, default=None)
    p.add_argument("--ess-stride-points", type=int, default=None)
    p.add_argument("--ess-min-lag", type=int, default=3)
    p.add_argument("--ess-max-lag", type=int, default=None)
    p.set_defaults(func=run_auto_compare)

    p = sub.add_parser("sensitivity", help="Legacy m_init sensitivity diagnostic.")
    add_common_args(p)
    p.add_argument("--ts", type=float, default=0.0)
    p.add_argument("--m-values", default="2,10,20,25,30")
    p.set_defaults(func=run_sensitivity)

    p = sub.add_parser("make-data", help="Generate designed synthetic benchmark data sets.")
    p.add_argument("--outdir", default="examples/data")
    p.add_argument("--n-points", type=int, default=100000)
    p.add_argument("--seed", type=int, default=20260627)
    p.set_defaults(func=run_make_data)

    p = sub.add_parser("config", help="Run from MD Test Format key-value configuration file.")
    p.add_argument("config_file")
    return parser


def _prompt_text(prompt: str, default: Optional[str] = None, allow_empty: bool = False) -> str:
    'Prompt interactively for a text value with an optional default.'
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value == "" and default is not None:
            return str(default)
        if value != "" or allow_empty:
            return value
        print("Please enter a value, or press Ctrl-C to exit.")


def _prompt_int(prompt: str, default: Optional[int] = None, minimum: Optional[int] = None) -> int:
    'Prompt interactively for an integer with optional lower bound.'
    while True:
        raw = _prompt_text(prompt, None if default is None else str(default))
        try:
            value = int(raw)
            if minimum is not None and value < minimum:
                raise ValueError
            return value
        except ValueError:
            print("Please enter an integer." if minimum is None else f"Please enter an integer >= {minimum}.")


def _prompt_float(prompt: str, default: Optional[float] = None) -> float:
    'Prompt interactively for a floating-point value.'
    while True:
        raw = _prompt_text(prompt, None if default is None else str(default))
        try:
            return float(raw)
        except ValueError:
            print("Please enter a numeric value.")


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    'Prompt interactively for a yes/no response.'
    default_text = "yes" if default else "no"
    while True:
        raw = _prompt_text(prompt, default_text).strip().lower()
        if raw in {"y", "yes", "true", "1"}:
            return True
        if raw in {"n", "no", "false", "0"}:
            return False
        print("Please answer yes or no.")


def _show_columns(titles: Sequence[str]) -> None:
    'Print detected input columns and their MDTest roles.'
    print("\nDetected columns:")
    for index, name in enumerate(titles):
        role = "time" if index == 0 else "observable"
        print(f"  {index:>3}: {name} ({role})")
    print("Column 0 is treated as time; choose an observable column >= 1.\n")


def run_walkthrough() -> Any:
    'Run the guided terminal interface using the same public Python API as the CLI.'
    print(PROGRAM_BANNER)
    print("Interactive walkthrough mode")
    print("Press Ctrl-C at any prompt to exit. Reports and plots are saved to the output directory; plots are also displayed when possible.\n")

    file = _prompt_text("Input data file")
    delim = _prompt_text("Delimiter for input file (comma, space, or tab)", "comma")
    drop_nan = _prompt_yes_no("Drop nonnumeric/NaN/Inf rows after warning", False)
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
    mode_map = {"manual": "manual", "auto": "auto-safe", "auto-safe": "auto-safe", "auto-binary": "auto-safe", "auto-sequential": "auto-safe", "auto-compare": "auto-compare", "compare": "auto-compare", "sensitivity": "sensitivity", "legacy": "sensitivity"}
    if mode not in mode_map:
        raise ValueError(f"Unknown walkthrough mode '{mode}'.")
    mode = mode_map[mode]

    alpha = _prompt_float("Significance level alpha", 0.05)
    min_blocks = _prompt_int("Minimum number of blocks", 24, minimum=2)
    outdir = _prompt_text("Output directory", "results/walkthrough")
    prefix_default = f"walkthrough_{mode.replace('-', '_')}_col{col}"
    prefix = _prompt_text("Output filename prefix", prefix_default)
    make_plots = _prompt_yes_no("Save diagnostic PNG plots", True)

    common = dict(file=file, delim=delim, col=col, alpha=alpha, min_blocks=min_blocks, outdir=outdir, prefix=prefix, drop_nan=drop_nan, no_plots=not make_plots, display_plots=display_plots and make_plots)

    if mode == "manual":
        run_count = 1
        while True:
            print(f"\nManual test #{run_count}")
            ts = _prompt_float("Start time ts", 0.0)
            m = _prompt_int("Block size m", 10, minimum=1)
            n = _prompt_text("Number of blocks n (integer or max)", "max")
            trial_common = dict(common)
            trial_common["prefix"] = f"{prefix}_trial{run_count:02d}"
            last_result = run_manual(argparse.Namespace(**trial_common, ts=ts, m=m, n=n))
            if not _prompt_yes_no("Run another manual test with different parameters", True):
                return last_result
            run_count += 1

    if mode == "auto-safe":
        m_trend_grid = _prompt_text("Trend-test m grid", "2,5,10,20,40")
        m_corr_grid = _prompt_text("Correlation/normality m grid", "5,10,20,30,40,60,80,120,160,240,320,480")
        stride_raw = _prompt_text("Candidate-start stride in raw points (blank for default)", "", allow_empty=True)
        return run_auto_safe(argparse.Namespace(**common, m_trend_grid=m_trend_grid, m_corr_grid=m_corr_grid, stride_points=int(stride_raw) if stride_raw.strip() else None))

    if mode == "auto-compare":
        m_trend_grid = _prompt_text("Trend-test m grid", "2,5,10,20,40")
        m_corr_grid = _prompt_text("Correlation/normality m grid", "5,10,20,30,40,60,80,120,160,240,320,480")
        stride_raw = _prompt_text("Stationarity scan stride in raw points (blank for default)", "", allow_empty=True)
        ess_stride_raw = _prompt_text("ESS scan stride in raw points (blank for default)", "", allow_empty=True)
        ess_min_lag = _prompt_int("ESS minimum lag before nonpositive truncation", 3, minimum=0)
        ess_max_lag_raw = _prompt_text("ESS maximum lag (blank for no cap)", "", allow_empty=True)
        return run_auto_compare(argparse.Namespace(**common, m_trend_grid=m_trend_grid, m_corr_grid=m_corr_grid, stride_points=int(stride_raw) if stride_raw.strip() else None, ess_stride_points=int(ess_stride_raw) if ess_stride_raw.strip() else None, ess_min_lag=ess_min_lag, ess_max_lag=int(ess_max_lag_raw) if ess_max_lag_raw.strip() else None))

    if mode == "sensitivity":
        ts = _prompt_float("Initial start time ts", 0.0)
        m_values = _prompt_text("Initial m values to test", "2,10,20,25,30")
        return run_sensitivity(argparse.Namespace(**common, ts=ts, m_values=m_values))
    raise ValueError(f"Unhandled walkthrough mode '{mode}'.")


def main(argv: Optional[Sequence[str]] = None) -> Any:
    'Dispatch command-line, config-file, or interactive walkthrough execution.'
    if argv is None and len(sys.argv) == 1:
        return run_walkthrough()
    parser = build_parser()
    args = parser.parse_args(argv)
    print(PROGRAM_BANNER)
    if args.mode == "config":
        cfg = parse_config_file(args.config_file)
        args2 = parser.parse_args(config_to_argv(cfg))
        return args2.func(args2)
    return args.func(args)


def entrypoint() -> None:
    """Console-script entry point with the same user-facing error behavior as MDTest.py."""
    try:
        main()
    except Exception as exc:
        print(f"MDTest ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
