"""MDTest: stationarity-aware diagnostics for scalar molecular-dynamics time series."""
from ._version import __version__
from .api import analyze, auto_compare, auto_safe, ess, manual, sensitivity, make_benchmark_data
from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult, RunProvenance, RunSettings, TestOutcome

__all__ = [
    "analyze", "manual", "auto_safe", "auto_compare", "ess", "sensitivity", "make_benchmark_data",
    "TestOutcome", "RunSettings", "RunProvenance", "ManualResult", "AutoSafeResult", "ESSResult", "AutoCompareResult", "__version__",
]
