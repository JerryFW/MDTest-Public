"""Small user-facing messages for the notebook Workbench.

Messages are intentionally neutral and diagnostic.  They do not reinterpret
failed tests as software errors and they do not modify any inference.
"""
from __future__ import annotations

from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult


def completion_message(result) -> str:
    """Return a short completion message suitable for the Workbench status bar."""
    if isinstance(result, ManualResult):
        return ("Analysis complete: all four selected-window diagnostics passed."
                if result.overall_pass else
                "Analysis complete: one or more selected-window diagnostics need attention.")
    if isinstance(result, AutoSafeResult):
        if result.status == "pass":
            return "Analysis complete: a multi-resolution stationarity start and reporting block were identified."
        if result.status == "stationarity-not-found":
            return "Analysis complete: no candidate start passed the configured MDTest stationarity screens on the requested grid."
        return "Analysis complete: the trend screen found a candidate start, but no final reporting block passed all checks."
    if isinstance(result, AutoCompareResult):
        if result.status == "pass":
            return "Analysis complete: MDTest and ESS/IACT starts were computed and reported side by side."
        if result.status == "ess-only-no-stationarity-certification":
            return "Analysis complete: ESS/IACT produced a start, but no candidate start passed the configured MDTest stationarity screens on the requested grid."
        return "Analysis complete: a start was selected, but no final reporting block passed all four checks."
    if isinstance(result, ESSResult):
        return "ESS/IACT analysis complete. Remember that this measures correlation-related sampling efficiency, not stationarity by itself."
    return "Analysis complete."


def loaded_message(n_rows: int, titles: list[str]) -> str:
    n_obs = max(0, len(titles) - 1)
    return f"Loaded {n_rows:,} samples with {n_obs} observable column(s). No statistical analysis has been run yet."
