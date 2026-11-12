"""Serialization and human-readable reporting helpers for MDTest."""
from __future__ import annotations
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from .results import ManualResult, AutoSafeResult, AutoCompareResult


def to_jsonable(obj: Any) -> Any:
    'Recursively convert MDTest result objects and NumPy scalars to JSON-compatible values.'
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
    'Serialize an MDTest result or mapping as indented JSON.'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(obj), f, indent=2, sort_keys=True)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    'Write a list of row dictionaries to CSV.'
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False)
    else:
        pd.DataFrame().to_csv(path, index=False)


def write_trend_table(path: Path, table: List[Dict[str, Any]]) -> None:
    'Flatten the multi-resolution trend scan into a CSV table.'
    rows = []
    for entry in table:
        for mr in entry.get("m_results", []):
            row = {"candidate_start_index": entry["start_index"], "candidate_ts": entry["ts"], "candidate_all_pass": entry["all_pass"]}
            row.update(mr)
            rows.append(row)
    write_csv(path, rows)


def write_result_files(result: ManualResult, prefix: Path) -> None:
    'Write JSON and text reports for a manual four-test result.'
    write_json(prefix.with_suffix(".json"), result)
    with prefix.with_suffix(".txt").open("w", encoding="utf-8") as f:
        f.write(format_manual_result(result))


def format_manual_result(r: ManualResult) -> str:
    'Format a manual result as a human-readable text report.'
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
    'Print a manual result and its output location.'
    print(format_manual_result(r))
    print(f"Saved report prefix: {r.output_prefix}")


def print_auto_safe_summary(r: AutoSafeResult) -> None:
    'Print the main fields of an auto-safe result.'
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
    'Print the main fields of an auto-compare result.'
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
