#!/usr/bin/env python3
"""
Wrapper for human-readable MDTest-vs-ESS comparison report.


Typical usage from the MDTest package root:

  python mdtest_clear_benchmarks.py

can also call with:

  python mdtest_clear_benchmarks.py --package-root /path/to/MDTest-Public-main


Can parse an existing results folder without rerunning MDTest:

  python mdtest_clear_benchmarks.py --parse-existing results --data-root examples/data
"""
from __future__ import annotations

import argparse
import csv
import json
import hashlib
import importlib.util
import math
import os
import shutil
import subprocess
import tempfile
import uuid
import sys
from dataclasses import dataclass, asdict
from pathlib import Path, PureWindowsPath
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
            "The underlying AR(2) model admits a stationary distribution, but this "
            "finite generated trajectory uses specified initial values and whole-record "
            "normalization. ESS estimates a "
            "correlation penalty under its chosen IACT convention, but oscillatory "
            "autocorrelation can complicate its uncertainty calibration; stationarity "
            "alone does not guarantee a zero finite-sample ESS-selected start."
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
    observable_column: int = 1
    input_delimiter: str = "comma"
    input_drop_nan: bool = False
    provenance_status: str = "verified_cleaned_data"


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


def _recorded_input_settings(summary: Dict[str, Any]) -> tuple[int, str, bool]:
    """Require consistent source-column and parser metadata from saved analysis.

    The start indices in JSON refer to the *cleaned rows*, not physical CSV
    lines; guessing defaults would silently corrupt a multicolumn report.
    """
    auto = summary.get("auto_safe") or {}
    ess = summary.get("ess") or {}
    manual = auto.get("manual_result") or {}
    star = summary.get("manual_result_star") or {}
    settings = [summary.get("settings"), auto.get("settings"),
                ess.get("settings"), manual.get("settings"), star.get("settings")]
    holders = [summary, auto, manual, star] + [obj for obj in settings if isinstance(obj, dict)]

    def consistent(key: str, *, required: bool = True):
        values = [obj[key] for obj in holders if isinstance(obj, dict) and obj.get(key) is not None]
        if not values:
            if required:
                raise ValueError(f"Summary lacks recorded {key!r} metadata; refusing to guess input parsing.")
            return None
        if any(value != values[0] for value in values[1:]):
            raise ValueError(f"Inconsistent {key!r} metadata across summary subresults: {values!r}")
        return values[0]

    col = consistent("column")
    delim = consistent("delimiter")
    drop_nan = consistent("drop_nan")
    if isinstance(col, bool) or not isinstance(col, int) or col < 1:
        raise ValueError(f"Invalid recorded observable-column index: {col!r}")
    if not isinstance(delim, str) or not delim.strip():
        raise ValueError(f"Invalid recorded delimiter: {delim!r}")
    if not isinstance(drop_nan, bool):
        raise ValueError(f"Invalid recorded drop_nan setting: {drop_nan!r}")
    return col, delim, drop_nan


def read_recorded_observable(path: Path, package_root: Path, *, col: int,
                             delim: str, drop_nan: bool) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Use this package's own loader; no independent CSV parsing rules."""
    io_path = package_root / "src" / "mdtest" / "io.py"
    if not io_path.is_file():
        raise FileNotFoundError(f"MDTest input loader not found at {io_path}")
    spec = importlib.util.spec_from_file_location("_mdtest_benchmark_report_io", io_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arr, titles = module.read_timeseries(str(path), delim, drop_nan)
    if col >= arr.shape[1]:
        raise ValueError(f"Recorded observable column {col} is missing from {path} ({arr.shape[1]} columns).")
    return arr[:, 0], arr[:, col], titles


def _saved_input_hash(summary: Dict[str, Any]) -> Optional[str]:
    """Retrieve the single expected input hash from the saved analysis."""
    # Follow the known nested result structure, not just top-level summaries.
    # Imported/older summaries may retain the only hash under Manual.
    observed = []
    todo = [summary]
    while todo:
        obj = todo.pop()
        if not isinstance(obj, dict):
            continue
        provenance = obj.get("provenance")
        if isinstance(provenance, dict):
            sha = provenance.get("input_sha256")
            if sha:
                observed.append(sha)
        for key in ("auto_safe", "ess", "manual_result", "manual_result_star"):
            child = obj.get(key)
            if isinstance(child, dict):
                todo.append(child)
    if len(set(observed)) > 1:
        raise ValueError("Conflicting input hashes in summary metadata.")
    return observed[0] if observed else None


def verify_input_fingerprint(summary: Dict[str, Any], data_path: Path) -> None:
    """Avoid pairing a saved start index with a different input file."""
    expected = _saved_input_hash(summary)
    if expected is not None:
        actual = hashlib.sha256(data_path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Input file does not match saved result SHA-256: {data_path}")


class IncompatibleSavedResultError(ValueError):
    """Saved row positions/times no longer describe the cleaned input."""


def _exact_saved_index(value: Any, n_rows: int, label: str) -> int:
    """Accept JSON integer or integer-valued float, never rounding a cutoff.

    ESS scan tables historically encode integer indices as floats (e.g. 133.0).
    A Boolean, fractional number, numeric string, or out-of-range integer is
    not an admissible observation index.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IncompatibleSavedResultError(f"Invalid {label}: expected integer observation index.")
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        raise IncompatibleSavedResultError(f"Invalid {label}: fractional/nonfinite index.")
    index = int(value)
    if not 0 <= index < n_rows:
        raise IncompatibleSavedResultError(f"Invalid {label}: index {index} outside {n_rows} cleaned rows.")
    return index


def _finite_saved_timestamp(value: Any, label: str) -> int | float:
    """Validate a JSON timestamp without rounding its integer representation.

    A JSON integer beyond 2**53 can differ from an IEEE-754 timestamp while
    rounding to the same float. We check float representability solely for
    validation, then return the *original* integer for exact identity checks.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IncompatibleSavedResultError(f'Invalid {label}: expected finite JSON number.')
    try:
        finite = math.isfinite(float(value))
    except (OverflowError, ValueError, TypeError):
        finite = False
    if not finite:
        raise IncompatibleSavedResultError(f'Invalid {label}: timestamp cannot be represented as a finite float.')
    return value


def _saved_time_matches(actual: float, recorded: Any, times: np.ndarray, index: int) -> bool:
    """Match original JSON timestamps against the cleaned float64 time axis.

    Integer JSON values must agree as exact integers; converting them to
    float first could alias e.g. 2**53 and 2**53+1. JSON floating-point values
    continue to require exact finite float64 equality, including legacy saves.
    """
    try:
        saved = _finite_saved_timestamp(recorded, 'saved timestamp')
        actual_float = float(actual)
    except (IncompatibleSavedResultError, OverflowError, ValueError, TypeError):
        return False
    if not math.isfinite(actual_float):
        return False
    if isinstance(saved, int):
        return actual_float.is_integer() and int(actual_float) == saved
    return actual_float == saved


def validate_comparison_structure(summary: Dict[str, Any]) -> None:
    """Validate the required *saved-result* schema, not the science.

    Missing keys must not become apparently legitimate null selections via
    dict.get().  Explicit null is permitted for unavailable SW or Manual
    choices, but ESS always returns a selection for supported auto-compare
    saves (including a constant/short-series fallback).
    """
    if not isinstance(summary, dict):
        raise IncompatibleSavedResultError('Auto Compare summary root must be an object.')
    for name, keys in (
        ('combined result', ('selected_start_index_star', 'selected_ts_star',
                             'selected_m_corr_star', 'selected_n_corr_star', 'manual_result_star')),
        ('auto_safe', ('selected_start_index_sw', 'selected_ts_sw',
                       'selected_m_corr', 'selected_n_corr', 'manual_result', 'trend_table')),
        ('ess', ('selected_start_index_ess', 'selected_ts_ess', 'selected_g',
                 'selected_neff', 'scan_table')),
    ):
        obj = summary if name == 'combined result' else summary.get(name)
        if not isinstance(obj, dict):
            raise IncompatibleSavedResultError(f'Invalid {name}: required object is missing.')
        absent = [key for key in keys if key not in obj]
        if absent:
            raise IncompatibleSavedResultError(f'Invalid {name}: missing required field(s) {absent}.')
    if not isinstance(summary['ess']['scan_table'], list):
        raise IncompatibleSavedResultError('Invalid ESS scan table: expected list.')
    if not isinstance(summary['auto_safe']['trend_table'], list):
        raise IncompatibleSavedResultError('Invalid SW trend table: expected list.')


def _finite_saved_float(value: Any, label: str) -> float:
    """Turn malformed/overflowing JSON numerics into reportable failures.

    Python's JSON decoder accepts large integers beyond float64 range. Every
    saved numeric conversion must fail via IncompatibleSavedResultError so
    --keep-going can retain other valid benchmark cases.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IncompatibleSavedResultError(f'Invalid {label}: required finite numeric value.')
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise IncompatibleSavedResultError(f'Invalid {label}: numeric value cannot be represented.') from exc
    if not math.isfinite(converted):
        raise IncompatibleSavedResultError(f'Invalid {label}: nonfinite numeric value.')
    return converted


def _finite_metric(value: Any, label: str, *, minimum: float, strictly: bool = False) -> float:
    x = _finite_saved_float(value, label)
    if x <= minimum if strictly else x < minimum:
        raise IncompatibleSavedResultError(f'Invalid {label}: value outside admissible range.')
    return x


def _positive_int(value: Any, label: str) -> int:
    converted = _finite_saved_float(value, label)
    # Keep the original exact-integer comparison: no fractional rounding.
    if value < 1 or not converted.is_integer() or int(converted) != value:
        raise IncompatibleSavedResultError(f'Invalid {label}: expected positive integral value.')
    return int(value)


def verify_saved_result_consistency(summary: Dict[str, Any], n_rows: int) -> None:
    """Check invariants of the serialized selections against each other.

    Does NOT recompute SW, IACT, or ESS: the input digest authenticates only
    cleaned data, while these consistency checks reject internally corrupted
    or incomplete result metadata. It is not a cryptographic result signature.
    """
    validate_comparison_structure(summary)
    auto, ess = summary['auto_safe'], summary['ess']
    sw_raw, ess_raw = auto['selected_start_index_sw'], ess['selected_start_index_ess']
    sw = None if sw_raw is None else _exact_saved_index(sw_raw, n_rows, 'SW selection')
    if ess_raw is None:
        raise IncompatibleSavedResultError('Missing ESS selection: supported Auto Compare results always select ESS.')
    selected_ess = _exact_saved_index(ess_raw, n_rows, 'ESS selection')
    expected_star = max(sw, selected_ess) if sw is not None else selected_ess
    star = summary['selected_start_index_star']
    if star is None or _exact_saved_index(star, n_rows, 'combined selection') != expected_star:
        raise IncompatibleSavedResultError('Combined selection conflicts with max(SW, ESS).')

    g = _finite_metric(ess['selected_g'], 'selected ESS g', minimum=1.0)
    neff = _finite_metric(ess['selected_neff'], 'selected ESS Neff', minimum=0.0, strictly=True)
    if neff > n_rows - selected_ess + 1e-8:
        raise IncompatibleSavedResultError('Selected ESS Neff exceeds retained observation count.')

    scan = ess['scan_table']
    if scan:
        by_index = {}
        best_index, best_neff = None, -math.inf
        for row_no, row in enumerate(scan):
            if not isinstance(row, dict) or not all(key in row for key in ('start_index','ts','g','neff')):
                raise IncompatibleSavedResultError(f'Incomplete ESS scan row {row_no}.')
            ix = _exact_saved_index(row['start_index'], n_rows, f'ESS scan row {row_no}')
            if ix in by_index:
                raise IncompatibleSavedResultError('Duplicate ESS scan start index.')
            row_g = _finite_metric(row['g'], f'ESS scan row {row_no} g', minimum=1.0)
            row_neff = _finite_metric(row['neff'], f'ESS scan row {row_no} Neff', minimum=0.0, strictly=True)
            expected_neff = (n_rows - ix) / row_g
            if not math.isclose(row_neff, expected_neff, rel_tol=1e-9, abs_tol=1e-9):
                raise IncompatibleSavedResultError(f'ESS scan row {row_no}: Neff and g are inconsistent.')
            by_index[ix] = (row_g, row_neff)
            if row_neff > best_neff:
                best_neff, best_index = row_neff, ix
        if selected_ess not in by_index:
            raise IncompatibleSavedResultError('Selected ESS start is absent from saved scan table.')
        row_g, row_neff = by_index[selected_ess]
        if (not math.isclose(g, row_g, rel_tol=1e-9, abs_tol=1e-9) or
                not math.isclose(neff, row_neff, rel_tol=1e-9, abs_tol=1e-9)):
            raise IncompatibleSavedResultError('Selected ESS metrics conflict with saved scan row.')
        if selected_ess != best_index:
            raise IncompatibleSavedResultError('Selected ESS start does not maximize saved scan Neff.')
    else:
        # The frozen detector returns no scan only for constant/very-short
        # sequences, selecting row zero with g=Neff=1 as its sentinel.
        if selected_ess != 0 or g != 1.0 or neff != 1.0:
            raise IncompatibleSavedResultError('ESS selection conflicts with empty-scan sentinel.')

    def check_blocks(name: str, selected_m: Any, selected_n: Any,
                     manual: Any, start: Optional[int]) -> None:
        if (selected_m is None) != (selected_n is None):
            raise IncompatibleSavedResultError(f'{name}: block size and block count must both be present or null.')
        if manual is None:
            if selected_m is not None:
                raise IncompatibleSavedResultError(f'{name}: block metadata without Manual result.')
            return
        if not isinstance(manual, dict):
            raise IncompatibleSavedResultError(f'{name}: invalid Manual result object.')
        if selected_m is None or start is None:
            raise IncompatibleSavedResultError(f'{name}: Manual result without selected start and block metadata.')
        for field in ('m', 'n', 'start_index', 'ts'):
            if field not in manual:
                raise IncompatibleSavedResultError(f'{name}: Manual result lacks {field}.')
        m = _positive_int(selected_m, f'{name} selected m')
        n = _positive_int(selected_n, f'{name} selected n')
        if (m != _positive_int(manual['m'], f'{name} Manual m') or
                n != _positive_int(manual['n'], f'{name} Manual n') or
                _exact_saved_index(manual['start_index'], n_rows, f'{name} Manual start') != start):
            raise IncompatibleSavedResultError(f'{name}: block metadata differs from saved Manual result.')
        if m * n > n_rows - start:
            raise IncompatibleSavedResultError(f'{name}: block count exceeds retained data.')

    check_blocks('SW', auto['selected_m_corr'], auto['selected_n_corr'], auto['manual_result'], sw)
    check_blocks('combined', summary['selected_m_corr_star'], summary['selected_n_corr_star'],
                 summary['manual_result_star'], expected_star)


def _saved_index_time_pairs(summary: Dict[str, Any], n_rows: int) -> List[Tuple[int, int | float]]:
    """Check selected, scan, trend and nested Manual index/time consistency.

    Both fields may be null for legitimate unavailable selections; otherwise
    both must be present and the saved index must refer to exactly one row.
    """
    pairs: List[Tuple[int, int | float]] = []

    def pair(obj: Dict[str, Any], index_key: str, time_key: str, label: str) -> None:
        idx, stamp = obj.get(index_key), obj.get(time_key)
        if idx is None and stamp is None:
            return
        if idx is None or stamp is None:
            raise IncompatibleSavedResultError(f"Incomplete {label}: index/time must both be set or null.")
        index = _exact_saved_index(idx, n_rows, label)
        saved_time = _finite_saved_timestamp(stamp, f'{label} timestamp')
        pairs.append((index, saved_time))

    auto, ess, star = summary.get("auto_safe"), summary.get("ess"), summary.get("manual_result_star")
    pair(auto, 'selected_start_index_sw', 'selected_ts_sw', 'SW selection')
    pair(ess, 'selected_start_index_ess', 'selected_ts_ess', 'ESS selection')
    pair(summary, 'selected_start_index_star', 'selected_ts_star', 'combined selection')
    for label, manual in (('SW Manual result', auto.get('manual_result')), ('combined Manual result', star)):
        if manual is not None:
            if not isinstance(manual, dict):
                raise IncompatibleSavedResultError(f"Invalid {label}: expected object or null.")
            pair(manual, 'start_index', 'ts', label)

    def entries(container: Dict[str, Any], key: str, label: str) -> list:
        sequence = container.get(key, [])
        if not isinstance(sequence, list):
            raise IncompatibleSavedResultError(f"Invalid {label}: expected list.")
        return sequence

    for row_no, item in enumerate(entries(ess, 'scan_table', 'ESS scan table')):
        if not isinstance(item, dict):
            raise IncompatibleSavedResultError(f"Invalid ESS scan row {row_no}.")
        pair(item, 'start_index', 'ts', f'ESS scan row {row_no}')
    for row_no, item in enumerate(entries(auto, 'trend_table', 'SW trend table')):
        if not isinstance(item, dict):
            raise IncompatibleSavedResultError(f"Invalid SW trend row {row_no}.")
        pair(item, 'start_index', 'ts', f'SW trend row {row_no}')
        for sub_no, sub in enumerate(entries(item, 'm_results', 'SW trend m_results')):
            if not isinstance(sub, dict):
                raise IncompatibleSavedResultError(f"Invalid SW trend row {row_no} m_result {sub_no}.")
            pair(sub, 'start_index', 'ts', f'SW trend row {row_no} m_result {sub_no}')
    return pairs


def saved_provenance_status(summary: Dict[str, Any]) -> str:
    """Classify provenance without equating content hashes to signatures."""
    observations = []
    for obj in (summary, summary.get('auto_safe'), summary.get('ess'),
                (summary.get('auto_safe') or {}).get('manual_result'), summary.get('manual_result_star')):
        if isinstance(obj, dict) and isinstance(obj.get('provenance'), dict):
            observations.append(obj['provenance'])
    if any(p.get('parsed_array_sha256') is not None for p in observations):
        return 'verified_cleaned_data'
    if _saved_input_hash(summary) is not None:
        return 'legacy_raw_sha_verified'
    return 'unverified_legacy'


def verify_cleaned_result_identity(summary: Dict[str, Any], times: np.ndarray,
                                   values: np.ndarray, titles: List[str], col: int,
                                   *, allow_unverified_legacy: bool = False) -> None:
    """Never apply a saved positional cutoff to a differently parsed input.

    Contemporary results carry a digest over *cleaned, ordered* time and
    selected-observable values. Earlier summaries lack that digest, so use
    their recorded observable labels and every available time/index pair.
    This provides a conservative compatibility check, not an assertion that
    old summaries have modern full-array provenance.
    """
    auto = summary.get("auto_safe") or {}
    ess = summary.get("ess") or {}
    manual = auto.get("manual_result") or {}
    star = summary.get("manual_result_star") or {}
    candidates = [summary, auto, ess, manual, star]
    observed = {}
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        provenance = obj.get("provenance")
        if not isinstance(provenance, dict):
            continue
        for field in ("parser_schema", "parsed_n_rows", "parsed_array_sha256"):
            value = provenance.get(field)
            if value is not None:
                observed.setdefault(field, []).append(value)
    for field, readings in observed.items():
        if any(v != readings[0] for v in readings[1:]):
            raise IncompatibleSavedResultError(
                f"Conflicting {field} metadata; rerun the analysis before reporting."
            )
    if "parsed_array_sha256" in observed:
        schema = observed.get("parser_schema", [None])[0]
        if schema != "mdtest-cleaned-time-observable-v1":
            raise IncompatibleSavedResultError("Unknown saved parser schema; rerun the analysis.")
        recorded_n = observed.get("parsed_n_rows", [None])[0]
        if recorded_n != len(times):
            raise IncompatibleSavedResultError("Cleaned input row count differs from saved analysis; rerun.")
        data = np.ascontiguousarray(np.column_stack((times, values)), dtype="<f8")
        hasher = hashlib.sha256()
        hasher.update(b"mdtest-cleaned-time-observable-v1\0")
        hasher.update(str(data.shape).encode("ascii") + b"\0")
        hasher.update(data.tobytes(order="C"))
        if hasher.hexdigest() != observed["parsed_array_sha256"][0]:
            raise IncompatibleSavedResultError(
                "Cleaned input differs from saved analysis despite matching source bytes; "
                "rerun the analysis with the current parser."
            )
    elif observed:
        # Partially populated future metadata must not be silently ignored.
        raise IncompatibleSavedResultError("Incomplete parsed-input provenance; rerun analysis.")

    # Check the selected observable label.  The old pandas header inference
    # could silently lose a numeric first observation, changing both this
    # label and the indexing.  A raw-file hash alone cannot detect that.
    names = [o.get("column_name") for o in (auto, manual, star)
             if isinstance(o, dict) and o.get("column_name") is not None]
    if names and any(name != titles[col] for name in names):
        raise IncompatibleSavedResultError(
            "Saved observable/header metadata disagree with current parsing; "
            "rerun the original analysis rather than reusing old start indices."
        )

    pairs = _saved_index_time_pairs(summary, len(times))
    verify_saved_result_consistency(summary, len(times))
    if not observed and not pairs:
        raise IncompatibleSavedResultError(
            "Legacy summary lacks cleaned-data identity and indexed-time evidence; "
            "rerun the analysis before reporting."
        )
    if not observed and _saved_input_hash(summary) is None and not allow_unverified_legacy:
        raise IncompatibleSavedResultError(
            "Legacy summary lacks both source and cleaned-array hashes; regenerate "
            "the analysis or explicitly pass --allow-unverified-legacy."
        )
    for index, saved_time in pairs:
        if not _saved_time_matches(float(times[index]), saved_time, times, index):
            raise IncompatibleSavedResultError(
                "Saved indices/times do not match the current cleaned timeline; "
                "rerun analysis rather than mixing parser versions."
            )


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
    # The saved-index validator runs before any statistic; never silently clamp.
    i = _exact_saved_index(start, len(values), "retained cutoff")
    tail = values[i:]
    if len(tail) < 2:
        return None, None
    return float(np.mean(tail)), float(np.var(tail, ddof=1))


def nominal_true_start(case_id: str, n: int, variance_error_threshold: float) -> Tuple[Optional[int], str]:
    spec = CASE_SPECS.get(case_id, {})
    kind = spec.get("true_kind")
    if kind == "zero":
        return 0, "stationary reference model; finite record is initialized and sampled"
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
    """Find original input, prioritizing the caller's data root and SHA match.

    Saved summaries may contain Windows paths even when parsed on POSIX (and
    vice versa). The saved hash, when available, remains mandatory; we search
    the candidate set instead of failing on the first existing wrong file.
    """
    file_field = None
    auto = summary.get("auto_safe", {}) if isinstance(summary, dict) else {}
    manual = auto.get("manual_result", {}) if isinstance(auto, dict) else {}
    for obj in (manual, auto, summary.get("manual_result_star", {}) if isinstance(summary, dict) else {}):
        if isinstance(obj, dict) and obj.get("file"):
            file_field = str(obj["file"])
            break

    filenames = []
    if file_field:
        for name in (Path(file_field).name, PureWindowsPath(file_field).name):
            if name and name not in filenames:
                filenames.append(name)
    if case_id in CASE_SPECS:
        filenames.append(CASE_SPECS[case_id]["file"])
    elif case_id == "nark_volume":
        filenames.append("NarK_TimeSeriesData.csv")

    candidates: List[Path] = []
    # An explicit --data-root overrides bundled examples, including for saved
    # Windows paths on Linux. Do not turn a recorded absolute path into a new
    # location by treating its drive or parent segments as subdirectories.
    if data_root is not None:
        candidates.extend(data_root / name for name in filenames)
    if file_field:
        p = Path(file_field)
        candidates.extend((p, package_root / p))
    for name in filenames:
        candidates.extend((package_root / "examples" / "data" / name,
                           package_root / "manuscript_examples" / "data" / name))

    existing = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved not in seen and resolved.is_file():
                seen.add(resolved)
                existing.append(resolved)
        except OSError:
            continue
    if not existing:
        return None
    expected = _saved_input_hash(summary)
    if expected:
        for candidate in existing:
            if hashlib.sha256(candidate.read_bytes()).hexdigest() == expected:
                return candidate
        # Let the caller's standard fingerprint guard produce the error;
        # never use a mismatched data file for statistical reporting.
    return existing[0]


class MissingSourceDataError(FileNotFoundError):
    """A recognized saved summary cannot be linked to its source dataset."""


def parse_summary_json(path: Path, package_root: Path, data_root: Optional[Path], variance_error_threshold: float,
                       *, allow_unverified_legacy: bool = False) -> Optional[ComparisonRow]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(summary, dict) or not isinstance(summary.get("ess"), dict) or not isinstance(summary.get("auto_safe"), dict):
        return None
    validate_comparison_structure(summary)
    case_id = case_id_from_summary(path, summary)
    if not case_id:
        return None
    data_path = resolve_data_path(summary, case_id, package_root, data_root)
    if data_path is None or not data_path.exists():
        raise MissingSourceDataError(
            f"Could not find source data for recognized case {case_id} from {path}"
        )

    col, delim, drop_nan = _recorded_input_settings(summary)
    verify_input_fingerprint(summary, data_path)
    times, values, titles = read_recorded_observable(data_path, package_root, col=col,
                                                     delim=delim, drop_nan=drop_nan)
    verify_cleaned_result_identity(summary, times, values, titles, col,
                                   allow_unverified_legacy=allow_unverified_legacy)
    provenance_status = saved_provenance_status(summary)
    n_total = len(values)
    true_start, true_note = nominal_true_start(case_id, n_total, variance_error_threshold)

    auto = summary.get("auto_safe", {})
    ess = summary.get("ess", {})
    # Strict validation has already established integral, in-bounds indices;
    # never round a value when using it for retained-sample statistics.
    mdtest_start = (None if auto.get("selected_start_index_sw") is None else
                    _exact_saved_index(auto["selected_start_index_sw"], n_total, "SW selection"))
    conservative_start = (None if summary.get("selected_start_index_star") is None else
                          _exact_saved_index(summary["selected_start_index_star"], n_total, "combined selection"))
    ess_start = (None if ess.get("selected_start_index_ess") is None else
                 _exact_saved_index(ess["selected_start_index_ess"], n_total, "ESS selection"))
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
        observable_column=col,
        input_delimiter=delim,
        input_drop_nan=drop_nan,
        provenance_status=provenance_status,
    )


def discover_summaries(results_root: Path) -> Tuple[List[Path], List[Dict[str, str]], List[Dict[str, str]], int]:
    """Inventory summary candidates, including malformed and unsupported files."""
    candidates = sorted(p for p in results_root.rglob("*.json")
                        if p.name.lower().endswith("summary.json"))
    accepted: List[Path] = []
    malformed: List[Dict[str, str]] = []
    ignored: List[Dict[str, str]] = []
    for p in candidates:
        try:
            with p.open("r", encoding="utf-8") as f:
                obj = json.load(f)
        except (OSError, ValueError) as exc:
            malformed.append({"summary": str(p), "reason": f"Unreadable JSON: {exc}"})
            continue
        if not isinstance(obj, dict):
            malformed.append({"summary": str(p), "reason": "Summary JSON root is not an object"})
            continue
        mode = (obj.get('settings') or {}).get('mode') if isinstance(obj.get('settings'), dict) else None
        recognized_shape = mode in ('auto-compare', 'auto_compare') or 'ess' in obj and 'auto_safe' in obj
        # A partial required section is also evidence of an intended comparison,
        # unless its mode explicitly identifies a genuine single-analysis result.
        noncomparison_mode = mode in ('manual', 'auto-safe', 'auto_safe', 'ess', 'sensitivity')
        if not noncomparison_mode and ('ess' in obj or 'auto_safe' in obj):
            recognized_shape = True
        if not isinstance(obj.get('ess'), dict) or not isinstance(obj.get('auto_safe'), dict):
            if recognized_shape:
                malformed.append({"summary": str(p), "reason":
                                  "Invalid auto-compare structure: required ess and auto_safe objects"})
            else:
                ignored.append({"summary": str(p), "reason": "Not an auto-compare result"})
            continue
        try:
            validate_comparison_structure(obj)
        except IncompatibleSavedResultError as exc:
            malformed.append({'summary': str(p), 'reason': str(exc)})
            continue
        if case_id_from_summary(p, obj) is None:
            ignored.append({"summary": str(p), "reason": "Unknown comparison case"})
            continue
        accepted.append(p)
    return accepted, malformed, ignored, len(candidates)


def find_summaries(results_root: Path) -> List[Path]:
    """Backward-compatible discovery of readable recognized summaries."""
    return discover_summaries(results_root)[0]


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


def run_examples(package_root: Path, outdir: Path, n_points: int, seed: int, no_mdtest_plots: bool,
                 keep_going: bool) -> Tuple[Path, List[Dict[str, Any]]]:
    mdtest = package_root / "MDTest.py"
    if not mdtest.exists():
        raise FileNotFoundError(f"Could not find MDTest.py under {package_root}")
    raw = outdir / "raw_mdtest_outputs"
    data_dir = outdir / "data"
    raw.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    ledger: List[Dict[str, Any]] = []
    generated = run([sys.executable, str(mdtest), "make-data", "--outdir", str(data_dir),
                     "--n-points", str(n_points), "--seed", str(seed)],
                    package_root, keep_going=keep_going)
    ledger.append({'case_id': 'make-data', 'command_success': bool(generated),
                   'expected_summary': None, 'summary_present': None})

    def attempt(case_id: str, command: List[str], case_out: Path) -> None:
        ok = run(command, package_root, keep_going=keep_going)
        expected = case_out / f'{case_id}_summary.json'
        ledger.append({'case_id': case_id, 'command_success': bool(ok),
                       'expected_summary': str(expected), 'summary_present': expected.is_file()})

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
        attempt(cid, cmd, case_out)

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
        attempt('nark_volume', cmd, case_out)
    else:
        print("NarK example file not found; skipping NarK auto-compare.")
    return raw, ledger


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
    lines.append("This report is generated by `mdtest_clear_benchmarks.py`.")
    lines.append("")
    unauthenticated = [r.label for r in rows if r.provenance_status == 'unverified_legacy']
    if unauthenticated:
        lines.append("**PROVENANCE WARNING — UNAUTHENTICATED LEGACY RESULTS:** "
                     + ", ".join(unauthenticated) + ". "
                     "These results lack both source and cleaned-data hashes; "
                     "they were included only by explicit operator opt-in.")
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


def make_plots(rows: List[ComparisonRow], outdir: Path, package_root: Path) -> None:
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
        times, values, _ = read_recorded_observable(data_path, package_root,
            col=r.observable_column, delim=r.input_delimiter, drop_nan=r.input_drop_nan)
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

            # Starts are cleaned-row indices, while this graph uses physical
            # time from the CSV's first column; never plot an index as time.
            if not (0 <= int(s) < len(times)):
                continue
            ax.axvline(
                float(times[int(s)]),
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
    axes[-1].set_xlabel("Time (input column)")
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
    ap.add_argument("--allow-unverified-legacy", action="store_true",
                    help="Opt in to reporting old summaries with neither raw nor cleaned-data hashes; output is marked unauthenticated.")
    return ap.parse_args()


# Every new attempt retires previous published results and invalidates the
# success marker before reading inputs. Staged artifacts are published only
# after the final figure/table generation succeeds.
REPORT_ARTIFACTS = (
    'human_report.md', 'comparison_table.md', 'comparison_table.csv',
    'comparison_table.json', 'comparison_table.tex',
    'fig_start_index_comparison.png', 'fig_start_error_comparison.png',
    'fig_retained_variance_comparison.png', 'fig_timeseries_start_overlay.png',
    'missing_summary_diagnostic.txt',
)


def _atomic_completeness(outdir: Path, status: Dict[str, Any]) -> None:
    marker = outdir / 'report_completeness.json'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=outdir,
                                     prefix='.completeness-', suffix='.tmp', delete=False) as f:
        tmp = Path(f.name)
        json.dump(status, f, indent=2)
        f.write('\n')
    try:
        os.replace(tmp, marker)
    finally:
        tmp.unlink(missing_ok=True)


def _retire_old_report(outdir: Path, attempt_id: str, *, rerun_examples: bool = False,
                       previous_status: Optional[bytes] = None) -> Optional[Path]:
    previous_names = list(REPORT_ARTIFACTS)
    if rerun_examples:
        # Reusing earlier raw summaries after a failed fresh computation would
        # make a new report appear valid even when some MDTest commands failed.
        previous_names += ['raw_mdtest_outputs', 'data']
    present = [outdir / name for name in previous_names if (outdir / name).exists()]
    if not present and previous_status is None:
        return None
    archived = outdir / 'previous_reports' / attempt_id
    archived.mkdir(parents=True, exist_ok=False)
    for original in present:
        os.replace(original, archived / original.name)
    if previous_status is not None:
        (archived / 'report_completeness.json').write_bytes(previous_status)
    return archived


def main() -> int:
    args = parse_args()
    package_root = Path(args.package_root).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    attempt_id = uuid.uuid4().hex
    old_status = (outdir / 'report_completeness.json')
    old_status_bytes = old_status.read_bytes() if old_status.is_file() else None
    status: Dict[str, Any] = {'complete': False, 'status': 'in_progress',
                              'attempt_id': attempt_id, 'reported_cases': 0}
    _atomic_completeness(outdir, status)
    staging = Path(tempfile.mkdtemp(prefix='.report_staging-', dir=outdir))
    try:
        archived = _retire_old_report(outdir, attempt_id,
                                      rerun_examples=not bool(args.parse_existing),
                                      previous_status=old_status_bytes)
        if archived:
            status['previous_report_archive'] = str(archived)
        data_root = Path(args.data_root).expanduser().resolve() if args.data_root else None
        if args.parse_existing:
            results_root = Path(args.parse_existing).expanduser().resolve()
            print(f"Parsing existing result folder: {results_root}")
        else:
            print(f"Running examples with package root: {package_root}")
            results_root, execution_ledger = run_examples(
                package_root=package_root, outdir=outdir,
                n_points=args.n_points, seed=args.seed,
                no_mdtest_plots=args.no_mdtest_plots,
                keep_going=args.keep_going,
            )
            data_root = outdir / 'data'

        if not args.parse_existing:
            status['execution_ledger'] = execution_ledger
            status['failed_commands'] = [entry['case_id'] for entry in execution_ledger
                                         if not entry['command_success']]
            status['missing_expected_summaries'] = [entry['case_id'] for entry in execution_ledger
                if entry['expected_summary'] is not None and not entry['summary_present']]
        summaries, malformed, ignored, candidate_count = discover_summaries(results_root)
        status.update({'summary_candidates': candidate_count,
                       'recognized_summaries': len(summaries),
                       'malformed_summaries': malformed,
                       'ignored_noncomparison': ignored,
                       'skipped_missing_source': []})
        if malformed and not args.keep_going:
            raise ValueError(
                f"Found {len(malformed)} malformed summary file(s); "
                "fix them or use --keep-going for an explicitly incomplete report. "
                f"First: {malformed[0]['summary']}"
            )
        if not summaries:
            diagnostic = explain_missing_summaries(results_root)
            (staging / 'missing_summary_diagnostic.txt').write_text(diagnostic + '\n', encoding='utf-8')
            raise RuntimeError(diagnostic)

        rows: List[ComparisonRow] = []
        missing_sources: List[Dict[str, str]] = []
        for p in summaries:
            try:
                row = parse_summary_json(p, package_root=package_root, data_root=data_root,
                                         variance_error_threshold=args.variance_error_threshold,
                                         allow_unverified_legacy=args.allow_unverified_legacy)
            except MissingSourceDataError as exc:
                if not args.keep_going:
                    raise
                print(f"WARNING: {exc}", file=sys.stderr)
                missing_sources.append({'summary': str(p), 'reason': str(exc)})
                continue
            except (ValueError, TypeError, KeyError) as exc:
                if not args.keep_going:
                    raise
                print(f"WARNING: malformed saved summary {p}: {exc}", file=sys.stderr)
                malformed.append({'summary': str(p), 'reason': str(exc)})
                continue
            if row:
                rows.append(row)
        rows = select_unique_rows(rows)
        if not args.parse_existing:
            expected_case_ids = [entry['case_id'] for entry in status['execution_ledger']
                                 if entry['expected_summary'] is not None]
            reported_case_ids = {row.case_id for row in rows}
            status['missing_reported_cases'] = [cid for cid in expected_case_ids
                                                if cid not in reported_case_ids]
        status.update({'reported_cases': len(rows), 'skipped_missing_source': missing_sources,
                       'unauthenticated_legacy_summaries': [r.source_summary for r in rows
                           if r.provenance_status == 'unverified_legacy']})
        if not rows:
            raise RuntimeError('No usable comparison rows could be parsed.')

        write_csv_table(rows, staging / 'comparison_table.csv', package_root)
        write_json_summary(rows, staging / 'comparison_table.json', package_root)
        write_latex_table(rows, staging / 'comparison_table.tex')
        if not args.no_summary_plots:
            make_plots(rows, staging, package_root)
        write_human_report(rows, staging, args)
        if (missing_sources or malformed or status.get('failed_commands') or
                status.get('missing_expected_summaries') or status.get('missing_reported_cases')):
            human = staging / 'human_report.md'
            warning = ('# INCOMPLETE BENCHMARK REPORT\n\n'
                       'One or more requested analyses failed, were missing, or contained '
                       'invalid saved results. Consult `report_completeness.json` for the '
                       'execution ledger and missing cases.\n\n')
            human.write_text(warning + human.read_text(encoding='utf-8'), encoding='utf-8')
        required = ('human_report.md', 'comparison_table.md', 'comparison_table.csv',
                    'comparison_table.json', 'comparison_table.tex')
        if not args.no_summary_plots and plt is not None and any(r.case_id in CASE_SPECS for r in rows):
            required += ('fig_start_index_comparison.png', 'fig_start_error_comparison.png',
                         'fig_retained_variance_comparison.png', 'fig_timeseries_start_overlay.png')
        for name in required:
            artifact = staging / name
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise RuntimeError(f'Report artifact missing or empty: {artifact}')

        # Publishing is not a directory-level atomic transaction, but the
        # completion marker remains false throughout publication and is written
        # last. Any mid-publication failure is thus explicitly incomplete.
        for artifact in staging.iterdir():
            if artifact.is_file():
                os.replace(artifact, outdir / artifact.name)
        complete = (not missing_sources and not malformed and
                    not status.get('failed_commands') and
                    not status.get('missing_expected_summaries') and
                    not status.get('missing_reported_cases'))
        status.update({'complete': bool(complete),
                       'status': 'complete' if complete else 'incomplete',
                       'published_artifacts': list(required)})
        _atomic_completeness(outdir, status)
        print('\nWrote clear comparison report:')
        for name in required:
            print('  ', outdir / name)
        print('\nOpen human_report.md first.')
        return 0
    except Exception as exc:
        diagnostic_file = staging / 'missing_summary_diagnostic.txt'
        if diagnostic_file.exists():
            os.replace(diagnostic_file, outdir / diagnostic_file.name)
        status.update({'complete': False, 'status': 'failed',
                       'failure_reason': str(exc)})
        _atomic_completeness(outdir, status)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
