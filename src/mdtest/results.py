"""Structured result objects returned by MDTest analyses.

Round 2A adds explicit settings and provenance records.  These fields describe
how a result was obtained; they do not participate in any statistical decision.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RunSettings:
    """Inference-controlling settings actually used for one public API call."""
    mode: str
    column: int
    delimiter: str = "comma"
    drop_nan: bool = False
    alpha: Optional[float] = None
    min_blocks: Optional[int] = None
    ts: Optional[float] = None
    m: Optional[int] = None
    n: Optional[int] = None
    m_trend_grid: Optional[List[int]] = None
    m_corr_grid: Optional[List[int]] = None
    stride_points: Optional[int] = None
    ess_stride_points: Optional[int] = None
    ess_min_lag: Optional[int] = None
    ess_max_lag: Optional[int] = None
    m_values: Optional[List[int]] = None


@dataclass(frozen=True)
class RunProvenance:
    """Software/environment/input provenance for reproducible analysis records."""
    mdtest_version: str
    python_version: str
    numpy_version: str
    scipy_version: str
    pandas_version: str
    matplotlib_version: str
    input_sha256: Optional[str]
    # Cleaned, ordered (time, selected observable) array identity.  The raw
    # file hash alone cannot detect parser-induced changes in row indexing.
    parser_schema: Optional[str] = None
    parsed_n_rows: Optional[int] = None
    parsed_array_sha256: Optional[str] = None


@dataclass
class TestOutcome:
    """Result of one statistical diagnostic."""
    statistic: Optional[float]
    p_value: Optional[float]
    passed: bool
    note: str = ""


@dataclass
class ManualResult:
    """Complete four-test result for one user-selected analysis window."""
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
    settings: Optional[RunSettings] = None
    provenance: Optional[RunProvenance] = None


@dataclass
class AutoSafeResult:
    """Result of the multi-resolution stationarity search and block selection."""
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
    settings: Optional[RunSettings] = None
    provenance: Optional[RunProvenance] = None


@dataclass
class ESSResult:
    """Result of the ESS/IACT candidate-start scan."""
    selected_ts_ess: float
    selected_start_index_ess: int
    selected_g: float
    selected_neff: float
    scan_table: List[Dict[str, float]]
    note: str
    settings: Optional[RunSettings] = None
    provenance: Optional[RunProvenance] = None


@dataclass
class AutoCompareResult:
    """Combined MDTest stationarity and ESS/IACT comparison result."""
    auto_safe: AutoSafeResult
    ess: ESSResult
    selected_ts_star: Optional[float]
    selected_start_index_star: Optional[int]
    selected_m_corr_star: Optional[int]
    selected_n_corr_star: Optional[int]
    manual_result_star: Optional[ManualResult]
    status: str
    note: str
    settings: Optional[RunSettings] = None
    provenance: Optional[RunProvenance] = None
