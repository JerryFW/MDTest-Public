#!/usr/bin/env python3
"""
Wrapper for human-readable MDTest-vs-ESS comparison report.


Typical usage from the MDTest package root:

  python mdtest_clear_comparison_report.py

can also call with:

  python mdtest_clear_comparison_report.py --package-root /path/to/MDTest-Public-main


Can parse an existing results folder without rerunning MDTest:

  python mdtest_clear_comparison_report.py --parse-existing results --data-root examples/data
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None


CASE_SPECS: Dict[str, Dict[str, Any]] = {
    "mean_drift_independent": {
        "label": "Independent mean drift",
        "column_name": "mean_drift",
        "file": "synthetic_mean_drift_independent.csv",
        "true_kind": "hard_fraction",
        "true_fraction": 0.45,
        "expected_mean": 0.0,
        "expected_variance": 1.0,
        "message": (
            "Mean relaxation creates a covariance footprint, so ESS often discards some "
            "early data, but it can stop before the retained-window mean is fully unbiased."
        ),
    },
    "variance_relaxation_independent": {
        "label": "Independent variance relaxation",
        "column_name": "variance_relaxation",
        "file": "synthetic_variance_relaxation_independent.csv",
        "true_kind": "variance_threshold",
        "expected_mean": 0.0,
        "expected_variance": 1.0,
        "message": (
            "This is the cleanest ESS failure mode: the samples are independent, so g is near "
            "one, but the marginal variance is still changing. MDTest sees this through its "
            "dispersion-trend screen."
        ),
    },
    "metastable_switch": {
        "label": "Single metastable switch",
        "column_name": "metastable_switch",
        "file": "synthetic_metastable_switch.csv",
        "true_kind": "hard_fraction",
        "true_fraction": 0.52,
        "expected_mean": 1.0,
        "expected_variance": 0.25**2,
        "message": (
            "A sharp switch leaves a strong covariance footprint, so ESS can appear to detect "
            "the correct start. This is a real success on this case, but for an artifact-based reason."
        ),
    },
    "underdamped_ar2": {
        "label": "Stationary underdamped AR(2)",
        "column_name": "underdamped_ar2",
        "file": "synthetic_underdamped_ar2.csv",
        "true_kind": "zero",
        "expected_mean": 0.0,
        "expected_variance": 1.0,
        "message": (
            "This process is stationary but oscillatory/correlated. ESS is the appropriate tool "
            "for the correlation penalty; stationarity screens should not over-truncate it."
        ),
    },
    "stationary_ar1": {
        "label": "Stationary AR(1)",
        "column_name": "stationary_ar1",
        "file": "synthetic_stationary_ar1.csv",
        "true_kind": "zero",
        "expected_mean": 0.0,
        "expected_variance": 1.0,
        "message": (
            "This is a stationary positive-correlation reference. The correct production start "
            "is zero; the useful quantity is the correlation penalty g, not equilibration truncation."
        ),
    },
}

SYNTHETIC_ORDER = [
    "mean_drift_independent",
    "variance_relaxation_independent",
    "metastable_switch",
    "underdamped_ar2",
    "stationary_ar1",
]


@dataclass
class ComparisonRow:
    case_id: str
    label: str
    n_total: int
    true_start: Optional[int]
    true_start_note: str
    ess_start: Optional[int]
    mdtest_start: Optional[int]
    conservative_start: Optional[int]
    ess_g: Optional[float]
    ess_neff: Optional[float]
    mdtest_m: Optional[int]
    mdtest_nblocks: Optional[int]
    expected_mean: Optional[float]
    expected_variance: Optional[float]
    ess_retained_mean: Optional[float]
    ess_retained_variance: Optional[float]
    mdtest_retained_mean: Optional[float]
    mdtest_retained_variance: Optional[float]
    conservative_retained_mean: Optional[float]
    conservative_retained_variance: Optional[float]
    interpretation: str
    source_summary: str
    source_data: str


def fmt(x: Any, digits: int = 4) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return "—"
        if abs(x) >= 1000:
            return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.{digits}g}"
        return f"{x:.{digits}g}"
    return str(x)


def run(cmd: List[str], cwd: Path, keep_going: bool = False) -> bool:
    print("$", " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        msg = f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}"
        if keep_going:
            print("WARNING:", msg, file=sys.stderr)
            return False
        raise RuntimeError(msg)
    return True


def read_csv_two_columns(path: Path) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        times: List[float] = []
        values: List[float] = []
        for row in reader:
            if not row or len(row) < 2:
                continue
            try:
                times.append(float(row[0]))
                values.append(float(row[1]))
            except ValueError:
                continue
    return np.asarray(times, dtype=float), np.asarray(values, dtype=float), header


def safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(round(float(x)))
    except Exception:
        return None


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        y = float(x)
    except Exception:
        return None
    if math.isnan(y) or math.isinf(y):
        return None
    return y


def retained_stats(values: np.ndarray, start: Optional[int]) -> Tuple[Optional[float], Optional[float]]:
    if start is None:
        return None, None
    i = max(0, min(int(start), len(values) - 1))
    tail = values[i:]
    if len(tail) < 2:
        return None, None
    return float(np.mean(tail)), float(np.var(tail, ddof=1))


def nominal_true_start(case_id: str, n: int, variance_error_threshold: float) -> Tuple[Optional[int], str]:
    spec = CASE_SPECS.get(case_id, {})
    kind = spec.get("true_kind")
    if kind == "zero":
        return 0, "stationary by construction"
    if kind == "hard_fraction":
        frac = float(spec["true_fraction"])
        return int(round(frac * n)), f"known construction: {frac:.0%} of trajectory"
    if kind == "variance_threshold":
        # MDTest.py generator uses sigma(t)=1+2 exp(-t/(0.18 N)).
        # Report a nominal rather than exact start: Var <= (1+threshold)*Var_eq.
        sigma_inf = 1.0
        sigma0_minus_inf = 2.0
        tau = 0.18 * n
        target_sigma = math.sqrt(1.0 + variance_error_threshold)
        if target_sigma <= sigma_inf:
            return None, "variance relaxation has no sharp true start"
        ratio = (target_sigma - sigma_inf) / sigma0_minus_inf
        if ratio <= 0:
            return None, "variance relaxation has no sharp true start"
        start = int(math.ceil(-tau * math.log(ratio)))
        start = min(max(start, 0), n - 1)
        return start, f"nominal: Var within {100*variance_error_threshold:.0f}% of equilibrium"
    return None, "no known true start"


def case_id_from_summary(path: Path, summary: Dict[str, Any]) -> Optional[str]:
    # Use explicit file/column names when available.
    candidates = []
    auto = summary.get("auto_safe", {}) if isinstance(summary, dict) else {}
    manual = auto.get("manual_result", {}) if isinstance(auto, dict) else {}
    for obj in (manual, auto, summary.get("manual_result_star", {}) if isinstance(summary, dict) else {}):
        if isinstance(obj, dict):
            for key in ("file", "column_name"):
                val = str(obj.get(key, ""))
                if val:
                    candidates.append(val)
    candidates.append(str(path))
    joined = " ".join(candidates).lower()
    for cid, spec in CASE_SPECS.items():
        if cid.lower() in joined or str(spec.get("file", "")).lower() in joined or str(spec.get("column_name", "")).lower() in joined:
            return cid
    if "nark" in joined:
        return "nark_volume"
    return None


def resolve_data_path(summary: Dict[str, Any], case_id: str, package_root: Path, data_root: Optional[Path]) -> Optional[Path]:
    file_field = None
    auto = summary.get("auto_safe", {}) if isinstance(summary, dict) else {}
    manual = auto.get("manual_result", {}) if isinstance(auto, dict) else {}
    for obj in (manual, auto, summary.get("manual_result_star", {}) if isinstance(summary, dict) else {}):
        if isinstance(obj, dict) and obj.get("file"):
            file_field = str(obj["file"])
            break
    candidates: List[Path] = []
    if file_field:
        p = Path(file_field)
        candidates.append(p)
        candidates.append(package_root / p)
        if data_root:
            candidates.append(data_root / p.name)
    if case_id in CASE_SPECS:
        fname = CASE_SPECS[case_id]["file"]
        candidates.append(package_root / "examples" / "data" / fname)
        candidates.append(package_root / "manuscript_examples" / "data" / fname)
        if data_root:
            candidates.append(data_root / fname)
    if case_id == "nark_volume":
        candidates.append(package_root / "examples" / "data" / "NarK_TimeSeriesData.csv")
        if data_root:
            candidates.append(data_root / "NarK_TimeSeriesData.csv")
    for c in candidates:
        try:
            if c.exists():
                return c.resolve()
        except OSError:
            pass
    return None


def parse_summary_json(path: Path, package_root: Path, data_root: Optional[Path], variance_error_threshold: float) -> Optional[ComparisonRow]:
    try:
        summary = json.load(open(path, "r"))
    except Exception:
        return None
    if not isinstance(summary, dict) or "ess" not in summary or "auto_safe" not in summary:
        return None
    case_id = case_id_from_summary(path, summary)
    if not case_id:
        return None
    data_path = resolve_data_path(summary, case_id, package_root, data_root)
    if data_path is None or not data_path.exists():
        print(f"WARNING: could not find source data for {case_id} from {path}", file=sys.stderr)
        return None

    _, values, _ = read_csv_two_columns(data_path)
    n_total = len(values)
    true_start, true_note = nominal_true_start(case_id, n_total, variance_error_threshold)

    auto = summary.get("auto_safe", {})
    ess = summary.get("ess", {})
    mdtest_start = safe_int(auto.get("selected_start_index_sw"))
    conservative_start = safe_int(summary.get("selected_start_index_star"))
    ess_start = safe_int(ess.get("selected_start_index_ess"))
    ess_g = safe_float(ess.get("selected_g"))
    ess_neff = safe_float(ess.get("selected_neff"))
    mdtest_m = safe_int(auto.get("selected_m_corr"))
    mdtest_nblocks = safe_int(auto.get("selected_n_corr"))

    spec = CASE_SPECS.get(case_id, {})
    expected_mean = safe_float(spec.get("expected_mean"))
    expected_var = safe_float(spec.get("expected_variance"))
    if case_id == "nark_volume":
        label = "NarK volume"
        interpretation = "Real MD example: no constructed true start; compare only MDTest and ESS recommendations."
    else:
        label = spec.get("label", case_id)
        interpretation = spec.get("message", "")

    e_mean, e_var = retained_stats(values, ess_start)
    m_mean, m_var = retained_stats(values, mdtest_start)
    c_mean, c_var = retained_stats(values, conservative_start)

    return ComparisonRow(
        case_id=case_id,
        label=label,
        n_total=n_total,
        true_start=true_start,
        true_start_note=true_note,
        ess_start=ess_start,
        mdtest_start=mdtest_start,
        conservative_start=conservative_start,
        ess_g=ess_g,
        ess_neff=ess_neff,
        mdtest_m=mdtest_m,
        mdtest_nblocks=mdtest_nblocks,
        expected_mean=expected_mean,
        expected_variance=expected_var,
        ess_retained_mean=e_mean,
        ess_retained_variance=e_var,
        mdtest_retained_mean=m_mean,
        mdtest_retained_variance=m_var,
        conservative_retained_mean=c_mean,
        conservative_retained_variance=c_var,
        interpretation=interpretation,
        source_summary=str(path),
        source_data=str(data_path),
    )


def find_summaries(results_root: Path) -> List[Path]:
    """Find usable auto-compare summary JSON files.
    """
    paths = sorted(set(results_root.rglob("*.json")))
    out: List[Path] = []
    for p in paths:
        if not p.name.lower().endswith("summary.json"):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("ess"), dict) and isinstance(obj.get("auto_safe"), dict):
            out.append(p)
    return out


def explain_missing_summaries(results_root: Path) -> str:
    """Return a human-readable diagnostic for an empty result folder."""
    lines: List[str] = []
    lines.append(f"No usable auto-compare summary JSON files were found under: {results_root}")
    if not results_root.exists():
        lines.append("The folder does not exist, so the MDTest raw runs probably did not start.")
        return "\n".join(lines)
    json_files = sorted(results_root.rglob("*.json"))
    summary_files = [p for p in json_files if p.name.lower().endswith("summary.json")]
    lines.append(f"JSON files found: {len(json_files)}; summary-like JSON files found: {len(summary_files)}.")
    if summary_files:
        lines.append("Summary-like files were present, but none had both top-level `ess` and `auto_safe` blocks.")
        lines.append("First few summary-like files:")
        for p in summary_files[:10]:
            lines.append(f"  - {p}")
    else:
        txt_files = sorted(results_root.rglob("*.txt"))
        csv_files = sorted(results_root.rglob("*.csv"))
        png_files = sorted(results_root.rglob("*.png"))
        lines.append(f"Other outputs found: {len(txt_files)} txt, {len(csv_files)} csv, {len(png_files)} png.")
        children = sorted([p for p in results_root.iterdir()]) if results_root.exists() else []
        if children:
            lines.append("Top-level contents:")
            for p in children[:20]:
                kind = "dir" if p.is_dir() else "file"
                lines.append(f"  - [{kind}] {p.name}")
    lines.append("")
    lines.append("Common causes:")
    lines.append("  1. You ran an older helper with the filename filter bug; use this updated script.")
    lines.append("  2. Your MDTest.py does not support the `auto-compare` command; use the current MDTest source package.")
    lines.append("  3. MDTest commands failed earlier but the helper was run with --keep-going.")
    lines.append("  4. You used --parse-existing on a folder containing only auto-safe/manual results, not auto-compare results.")
    return "\n".join(lines)


def run_examples(package_root: Path, outdir: Path, n_points: int, seed: int, no_mdtest_plots: bool, keep_going: bool) -> Path:
    mdtest = package_root / "MDTest.py"
    if not mdtest.exists():
        raise FileNotFoundError(f"Could not find MDTest.py under {package_root}")
    raw = outdir / "raw_mdtest_outputs"
    data_dir = outdir / "data"
    raw.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    run([sys.executable, str(mdtest), "make-data", "--outdir", str(data_dir), "--n-points", str(n_points), "--seed", str(seed)], package_root, keep_going=keep_going)

    for cid in SYNTHETIC_ORDER:
        spec = CASE_SPECS[cid]
        f = data_dir / spec["file"]
        case_out = raw / cid
        case_out.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(mdtest), "auto-compare",
            "--file", str(f),
            "--delim", "comma",
            "--col", "1",
            "--outdir", str(case_out),
            "--prefix", cid,
            "--m-trend-grid", "2,5,10,20,40",
            "--m-corr-grid", "10,20,40,80,120,160,200",
        ]
        if no_mdtest_plots:
            cmd.append("--no-plots")
        run(cmd, package_root, keep_going=keep_going)

    # NarK is optional; include it if the package has the file.
    nark = package_root / "examples" / "data" / "NarK_TimeSeriesData.csv"
    if nark.exists():
        case_out = raw / "nark_volume"
        case_out.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(mdtest), "auto-compare",
            "--file", str(nark),
            "--delim", "comma",
            "--drop-nan",
            "--col", "6",
            "--outdir", str(case_out),
            "--prefix", "nark_volume",
            "--m-trend-grid", "2,5,10,20,25",
            "--m-corr-grid", "10,20,25,30,40,50,60",
        ]
        if no_mdtest_plots:
            cmd.append("--no-plots")
        run(cmd, package_root, keep_going=keep_going)
    else:
        print("NarK example file not found; skipping NarK auto-compare.")
    return raw


def select_unique_rows(rows: List[ComparisonRow]) -> List[ComparisonRow]:
    # Prefer rows in the synthetic order, one per case_id. If there are duplicates,
    # use the one with the shortest source path under a newly generated outdir first.
    by_case: Dict[str, List[ComparisonRow]] = {}
    for r in rows:
        by_case.setdefault(r.case_id, []).append(r)
    ordered_ids = SYNTHETIC_ORDER + [cid for cid in by_case if cid not in SYNTHETIC_ORDER]
    final: List[ComparisonRow] = []
    for cid in ordered_ids:
        candidates = by_case.get(cid, [])
        if not candidates:
            continue
        candidates.sort(key=lambda r: ("raw_mdtest_outputs" not in r.source_summary, len(r.source_summary)))
        final.append(candidates[0])
    return final


def make_relative_path(path_text: str, base_dir: Path) -> str:
    """Return a readable relative path when possible."""
    if not path_text:
        return path_text

    p = Path(path_text)

    try:
        return str(p.resolve().relative_to(base_dir.resolve()))
    except Exception:
        try:
            return os.path.relpath(str(p), str(base_dir))
        except Exception:
            return path_text

def write_csv_table(rows: List[ComparisonRow], path: Path, base_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else []

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in rows:
            d = asdict(r)
            d["source_summary"] = make_relative_path(d["source_summary"], base_dir)
            d["source_data"] = make_relative_path(d["source_data"], base_dir)
            writer.writerow(d)


def md_table(headers: List[str], records: List[List[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for rec in records:
        out.append("| " + " | ".join(rec) + " |")
    return "\n".join(out)


def latex_escape(s: str) -> str:
    repl = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}",
    }
    return "".join(repl.get(ch, ch) for ch in str(s))


def write_latex_table(rows: List[ComparisonRow], path: Path) -> None:
    cols = [
        ("Case", lambda r: r.label),
        ("True", lambda r: fmt(r.true_start)),
        ("ESS", lambda r: fmt(r.ess_start)),
        (r"\MDTest{}", lambda r: fmt(r.mdtest_start)),
        ("Max", lambda r: fmt(r.conservative_start)),
        (r"$\hat g_{ESS}$", lambda r: fmt(r.ess_g, 3)),
        (r"$m$", lambda r: fmt(r.mdtest_m)),
        (r"$n_{blk}$", lambda r: fmt(r.mdtest_nblocks)),
    ]
    lines = []
    lines.append(r"\begin{tabular}{lrrrrrrr}")
    lines.append(r"\hline")
    lines.append(" & ".join(c[0] for c in cols) + r" \\")
    lines.append(r"\hline")
    for r in rows:
        vals = []
        for i, (_, fn) in enumerate(cols):
            val = fn(r)
            vals.append(latex_escape(val) if i == 0 else val)
        lines.append(" & ".join(vals) + r" \\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    path.write_text("\n".join(lines) + "\n")


def write_human_report(rows: List[ComparisonRow], outdir: Path, args: argparse.Namespace) -> None:
    compact_records = []
    for r in rows:
        compact_records.append([
            r.label,
            fmt(r.true_start),
            fmt(r.ess_start),
            fmt(r.mdtest_start),
            fmt(r.conservative_start),
            fmt(r.ess_g, 3),
            fmt(r.mdtest_m),
            fmt(r.mdtest_nblocks),
        ])
    headers = ["Case", "True / nominal start", "ESS start", "MDTest start", "Max start", "ESS g", "m", "n blocks"]

    lines = []
    lines.append("# MDTest vs ESS/IACT comparison report")
    lines.append("")
    lines.append("This report is generated by `mdtest_clear_comparison_report.py`.")
    lines.append("")
    lines.append("## Compact start-time comparison")
    lines.append("")
    lines.append(md_table(headers, compact_records))
    lines.append("")
    lines.append("Relevant figures:")
    for fig in [
        "fig_start_index_comparison.png",
        "fig_start_error_comparison.png",
        "fig_retained_variance_comparison.png",
        "fig_timeseries_start_overlay.png",
    ]:
        if (outdir / fig).exists():
            lines.append(f"- `{fig}`")
    lines.append("")
    lines.append("## Case-by-case interpretation")
    lines.append("")
    for r in rows:
        lines.append(f"### {r.label}")
        lines.append("")
        lines.append(md_table(
            ["Quantity", "Value"],
            [
                ["Data points", fmt(r.n_total)],
                ["True/nominal start", f"{fmt(r.true_start)} ({r.true_start_note})"],
                ["ESS start", fmt(r.ess_start)],
                ["MDTest start", fmt(r.mdtest_start)],
                ["Conservative max start", fmt(r.conservative_start)],
                ["ESS statistical inefficiency g", fmt(r.ess_g, 4)],
                ["ESS effective samples", fmt(r.ess_neff, 4)],
                ["MDTest selected m", fmt(r.mdtest_m)],
                ["MDTest selected block count", fmt(r.mdtest_nblocks)],
                ["Expected equilibrium mean", fmt(r.expected_mean, 5)],
                ["Expected equilibrium variance", fmt(r.expected_variance, 5)],
                ["ESS retained mean", fmt(r.ess_retained_mean, 5)],
                ["ESS retained variance", fmt(r.ess_retained_variance, 5)],
                ["MDTest retained mean", fmt(r.mdtest_retained_mean, 5)],
                ["MDTest retained variance", fmt(r.mdtest_retained_variance, 5)],
            ]
        ))
        lines.append("")
        lines.append(r.interpretation)
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- For variance relaxation there is no mathematically sharp true start, because the variance relaxes exponentially. The script therefore reports a configurable nominal start: by default, the first index where the constructed variance is within 10% of equilibrium.")
    lines.append("- `MDTest start` is the Schiferl--Wallace/MDTest stationarity-admissible start (`selected_start_index_sw`).")
    lines.append("- `Max start` is the conservative start used by `auto-compare`, i.e. `max(MDTest start, ESS start)`. This is useful for a combined workflow, but it should not be confused with a pure stationarity diagnostic.")
    lines.append("")
    (outdir / "human_report.md").write_text("\n".join(lines), encoding="utf-8")
    (outdir / "comparison_table.md").write_text(md_table(headers, compact_records) + "\n", encoding="utf-8")


def make_plots(rows: List[ComparisonRow], outdir: Path) -> None:
    if plt is None:
        print("Matplotlib unavailable; skipping plots.", file=sys.stderr)
        return
    outdir.mkdir(parents=True, exist_ok=True)
    synthetic = [r for r in rows if r.case_id in CASE_SPECS]
    if not synthetic:
        return

    # 1. Grouped start-index comparison.
    labels = [r.label.replace("Independent ", "").replace("Stationary ", "") for r in synthetic]
    x = np.arange(len(synthetic))
    width = 0.20
    series = [
        ("True/nominal", [np.nan if r.true_start is None else r.true_start for r in synthetic], -1.5),
        ("ESS", [np.nan if r.ess_start is None else r.ess_start for r in synthetic], -0.5),
        ("MDTest", [np.nan if r.mdtest_start is None else r.mdtest_start for r in synthetic], 0.5),
        ("Max", [np.nan if r.conservative_start is None else r.conservative_start for r in synthetic], 1.5),
    ]
    fig, ax = plt.subplots(figsize=(max(9, 1.6 * len(synthetic)), 5.5))
    for name, vals, off in series:
        ax.bar(x + off * width, vals, width, label=name)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("Start index")
    ax.set_title("Start index selected by true construction, ESS, MDTest, and conservative max")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(outdir / "fig_start_index_comparison.png", dpi=200)
    plt.close(fig)

    # 2. Start error relative to true/nominal start.
    err_rows = [r for r in synthetic if r.true_start is not None]
    if err_rows:
        labels2 = [r.label.replace("Independent ", "").replace("Stationary ", "") for r in err_rows]
        x2 = np.arange(len(err_rows))
        fig, ax = plt.subplots(figsize=(max(9, 1.6 * len(err_rows)), 5.5))
        for name, attr, off in [("ESS", "ess_start", -0.5), ("MDTest", "mdtest_start", 0.5), ("Max", "conservative_start", 1.5)]:
            vals = []
            for r in err_rows:
                s = getattr(r, attr)
                vals.append(np.nan if s is None or r.true_start is None else s - r.true_start)
            ax.bar(x2 + off * width, vals, width, label=name)
        ax.axhline(0, linewidth=1.0)
        ax.set_xticks(x2)
        ax.set_xticklabels(labels2, rotation=25, ha="right")
        ax.set_ylabel("Selected start minus true/nominal start")
        ax.set_title("Start-index error: negative means too early, positive means later than necessary")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(outdir / "fig_start_error_comparison.png", dpi=200)
        plt.close(fig)

    # 3. Retained variance comparison.
    var_rows = [r for r in synthetic if r.expected_variance is not None]
    labels3 = [r.label.replace("Independent ", "").replace("Stationary ", "") for r in var_rows]
    x3 = np.arange(len(var_rows))
    fig, ax = plt.subplots(figsize=(max(9, 1.6 * len(var_rows)), 5.5))
    for name, attr, off in [("Expected", "expected_variance", -1.5), ("ESS tail", "ess_retained_variance", -0.5), ("MDTest tail", "mdtest_retained_variance", 0.5), ("Max tail", "conservative_retained_variance", 1.5)]:
        vals = [np.nan if getattr(r, attr) is None else getattr(r, attr) for r in var_rows]
        ax.bar(x3 + off * width, vals, width, label=name)
    ax.set_xticks(x3)
    ax.set_xticklabels(labels3, rotation=25, ha="right")
    ax.set_ylabel("Retained-sample variance")
    ax.set_title("Variance of retained tail under each selected start")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(outdir / "fig_retained_variance_comparison.png", dpi=200)
    plt.close(fig)

    # 4. Time series overlays with vertical start lines.
    nrows = len(synthetic)
    fig_h = max(8, 2.2 * nrows)
    fig, axes = plt.subplots(nrows=nrows, ncols=1, figsize=(11, fig_h), sharex=False)
    if nrows == 1:
        axes = [axes]
    for ax, r in zip(axes, synthetic):
        data_path = Path(r.source_data)
        times, values, _ = read_csv_two_columns(data_path)
        if len(values) > 5000:
            idx = np.linspace(0, len(values) - 1, 5000).astype(int)
            times_p = times[idx]
            values_p = values[idx]
        else:
            times_p, values_p = times, values
        ax.plot(times_p, values_p, linewidth=0.7, alpha=0.85)

        start_styles = {
            "True": {
                "start": r.true_start,
                "color": "tab:green",
                "linestyle": "-",
                "linewidth": 1.4,
            },
            "ESS": {
                "start": r.ess_start,
                "color": "tab:orange",
                "linestyle": "--",
                "linewidth": 1.4,
            },
            "MDTest": {
                "start": r.mdtest_start,
                "color": "tab:blue",
                "linestyle": "-.",
                "linewidth": 1.4,
            },
            "Max": {
                "start": r.conservative_start,
                "color": "tab:red",
                "linestyle": ":",
                "linewidth": 1.8,
            },
        }

        for name, style in start_styles.items():
            s = style["start"]
            if s is None:
                continue

            ax.axvline(
                s,
                color=style["color"],
                linestyle=style["linestyle"],
                linewidth=style["linewidth"],
                alpha=0.95,
                label=name,
            )

        ax.set_title(r.label)
        ax.set_ylabel("Observable")
        ax.grid(alpha=0.2)
        # Avoid repeated legend clutter by using compact per-panel legend.
        ax.legend(loc="upper right", fontsize=8, ncol=4)
    axes[-1].set_xlabel("Sample index / time column")
    fig.suptitle("Synthetic benchmark trajectories with true/nominal, ESS, MDTest, and max starts", y=0.995)
    fig.tight_layout()
    fig.savefig(outdir / "fig_timeseries_start_overlay.png", dpi=200)
    plt.close(fig)


def make_relative_path(path_text: str, base_dir: Path) -> str:
    """Return a readable relative path when possible."""
    if not path_text:
        return path_text

    p = Path(path_text)

    try:
        return str(p.resolve().relative_to(base_dir.resolve()))
    except Exception:
        try:
            return os.path.relpath(str(p), str(base_dir))
        except Exception:
            return path_text


def write_json_summary(rows: List[ComparisonRow], path: Path, base_dir: Path) -> None:
    """Write JSON summary with source paths relative to base_dir."""
    records = []

    for r in rows:
        d = asdict(r)

        d["source_summary"] = make_relative_path(d["source_summary"], base_dir)
        d["source_data"] = make_relative_path(d["source_data"], base_dir)

        records.append(d)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Clear MDTest-vs-ESS comparison report.")
    ap.add_argument("--package-root", default=".", help="Folder containing MDTest.py. Default: current directory.")
    ap.add_argument("--outdir", default="clear_comparison_report", help="Output report folder.")
    ap.add_argument("--n-points", type=int, default=20000, help="Synthetic points per benchmark when running MDTest.")
    ap.add_argument("--seed", type=int, default=20260627, help="Random seed for MDTest make-data.")
    ap.add_argument("--parse-existing", default=None, help="Parse existing MDTest result folder instead of rerunning examples.")
    ap.add_argument("--data-root", default=None, help="Data folder to use with --parse-existing, e.g. examples/data or manuscript_examples/data.")
    ap.add_argument("--variance-error-threshold", type=float, default=0.10, help="Nominal true start for variance relaxation: Var <= (1+threshold) Var_eq.")
    ap.add_argument("--no-mdtest-plots", action="store_true", help="When running MDTest, ask MDTest to skip its own plots. This script still makes summary plots.")
    ap.add_argument("--no-summary-plots", action="store_true", help="Do not make this script's summary plots.")
    ap.add_argument("--keep-going", action="store_true", help="Continue if one MDTest command fails.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    package_root = Path(args.package_root).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    data_root = Path(args.data_root).expanduser().resolve() if args.data_root else None

    if args.parse_existing:
        results_root = Path(args.parse_existing).expanduser().resolve()
        print(f"Parsing existing result folder: {results_root}")
    else:
        print(f"Running examples with package root: {package_root}")
        results_root = run_examples(
            package_root=package_root,
            outdir=outdir,
            n_points=args.n_points,
            seed=args.seed,
            no_mdtest_plots=args.no_mdtest_plots,
            keep_going=args.keep_going,
        )
        data_root = outdir / "data"

    summaries = find_summaries(results_root)
    if not summaries:
        diagnostic = explain_missing_summaries(results_root)
        # Write the diagnostic into the output folder as well, so Windows users
        # can inspect it after a console closes.
        try:
            (outdir / "missing_summary_diagnostic.txt").write_text(diagnostic + "\n", encoding="utf-8")
        except Exception:
            pass
        raise RuntimeError(diagnostic)

    rows: List[ComparisonRow] = []
    for p in summaries:
        row = parse_summary_json(p, package_root=package_root, data_root=data_root, variance_error_threshold=args.variance_error_threshold)
        if row:
            rows.append(row)
    rows = select_unique_rows(rows)
    if not rows:
        raise RuntimeError("No usable comparison rows could be parsed.")

    write_csv_table(rows, outdir / "comparison_table.csv", package_root)
    write_json_summary(rows, outdir / "comparison_table.json", package_root)
    write_latex_table(rows, outdir / "comparison_table.tex")
    if not args.no_summary_plots:
        make_plots(rows, outdir)
    write_human_report(rows, outdir, args)

    print("\nWrote clear comparison report:")
    for name in [
        "human_report.md",
        "comparison_table.csv",
        "comparison_table.json",
        "comparison_table.tex",
        "fig_start_index_comparison.png",
        "fig_start_error_comparison.png",
        "fig_retained_variance_comparison.png",
        "fig_timeseries_start_overlay.png",
    ]:
        p = outdir / name
        if p.exists():
            print("  ", p)
    print("\nOpen human_report.md first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
