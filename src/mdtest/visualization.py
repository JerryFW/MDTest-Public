"""Presentation-only diagnostic visualizations for MDTest result objects.

These functions call frozen parsing/block-construction helpers where needed;
they never recompute or modify a statistical decision.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import numpy as np
import matplotlib.pyplot as plt

from .diagnostics import block_series
from .io import read_timeseries
from .provenance import sha256_file
from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult


class InputProvenanceError(RuntimeError):
    """Raised when presentation input no longer matches analyzed input bytes."""


def _verify_input_provenance(file: str | Path, result) -> None:
    provenance = getattr(result, "provenance", None)
    expected = getattr(provenance, "input_sha256", None) if provenance is not None else None
    if not expected:
        return
    actual = sha256_file(file)
    if actual is None:
        raise InputProvenanceError(
            f"Cannot generate raw-data diagnostic figures because the analyzed input file is unavailable: {file}"
        )
    if actual != expected:
        raise InputProvenanceError(
            "Cannot generate raw-data diagnostic figures because the input file changed after analysis. "
            "The stored result/provenance refers to different bytes; rerun MDTest on the current file or restore the original input."
        )


def _settings(result):
    return getattr(result, "settings", None)


def _file_and_read_options(result):
    file = getattr(result, "file", None)
    if file is None and isinstance(result, AutoCompareResult):
        file = result.auto_safe.file
    s = _settings(result)
    delim = getattr(s, "delimiter", "comma") if s else "comma"
    drop_nan = bool(getattr(s, "drop_nan", False)) if s else False
    return file, delim, drop_nan


def _selected_manual(result) -> Optional[ManualResult]:
    if isinstance(result, ManualResult):
        return result
    if isinstance(result, AutoSafeResult):
        return result.manual_result
    if isinstance(result, AutoCompareResult):
        return result.manual_result_star
    return None


def _polish_axis(ax, *, grid_axis: str = "both") -> None:
    ax.grid(True, axis=grid_axis, linewidth=0.45, alpha=0.22)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _group_start_markers(result) -> list[tuple[float, str, str, str]]:
    """Combine coincident start markers to avoid visually duplicated lines."""
    raw: list[tuple[Optional[float], str, str, str]] = []
    if isinstance(result, ManualResult):
        raw.append((result.ts, "selected start", "--", "C1"))
    elif isinstance(result, AutoSafeResult):
        raw.append((result.selected_ts_sw, "MDTest start", "--", "C1"))
    elif isinstance(result, AutoCompareResult):
        raw.extend([
            (result.auto_safe.selected_ts_sw, "MDTest start", "--", "C1"),
            (result.ess.selected_ts_ess, "ESS start", ":", "C2"),
            (result.selected_ts_star, "reported start", "-.", "C3"),
        ])
    elif isinstance(result, ESSResult):
        raw.append((result.selected_ts_ess, "ESS start", ":", "C2"))

    grouped: list[tuple[float, list[str], str, str]] = []
    for x, label, style, color in raw:
        if x is None:
            continue
        xf = float(x)
        match = next((g for g in grouped if np.isclose(g[0], xf, rtol=0, atol=max(1e-12, abs(xf)*1e-12))), None)
        if match is None:
            grouped.append((xf, [label], style, color))
        else:
            match[1].append(label)
    return [(x, " / ".join(labels), style, color) for x, labels, style, color in grouped]


def plot_time_series(result):
    """Plot the raw observable with the relevant MDTest/ESS start markers."""
    file, delim, drop_nan = _file_and_read_options(result)
    if not file:
        raise ValueError("Result does not identify an input file.")
    _verify_input_provenance(file, result)
    arr, titles = read_timeseries(str(file), delim, drop_nan)
    col = getattr(result, "column", None)
    if col is None and isinstance(result, AutoCompareResult):
        col = result.auto_safe.column
    times, values = arr[:, 0], arr[:, int(col)]
    title = titles[int(col)] if int(col) < len(titles) else f"column_{col}"

    fig, ax = plt.subplots(figsize=(9.4, 4.25))
    ax.plot(times, values, linewidth=0.62, alpha=0.72, label=title, color="C0")
    markers = _group_start_markers(result)
    for x, label, style, color in markers:
        ax.axvline(x, linestyle=style, linewidth=1.7, color=color, label=f"{label}: {x:g}")
    ax.margins(x=0.012)
    ax.set_xlabel("Time")
    ax.set_ylabel(title)
    ax.set_title("Trajectory and selected analysis start")
    _polish_axis(ax)
    if markers:
        ax.legend(loc="upper right", fontsize=8.7, frameon=True, ncol=1)
    fig.tight_layout()
    return fig


def plot_selected_block_means(result):
    """Plot the selected block means for a manual or automatic final report."""
    manual = _selected_manual(result)
    if manual is None:
        raise ValueError("No final ManualResult is available for block-mean plotting.")
    s = manual.settings
    _verify_input_provenance(manual.file, manual)
    arr, _titles = read_timeseries(manual.file, getattr(s, "delimiter", "comma") if s else "comma",
                                   bool(getattr(s, "drop_nan", False)) if s else False)
    times, values = arr[:, 0], arr[:, manual.column]
    block_t, y, _ = block_series(values, times, manual.start_index, manual.m, manual.n)
    fig, ax = plt.subplots(figsize=(9.4, 4.25))
    ax.plot(block_t, y, marker="o", markersize=3.0, linewidth=0.85, alpha=0.9, color="C0", label="block means")
    ax.axhline(float(manual.mean), linewidth=1.35, linestyle="--", color="C1", label=f"reported mean = {manual.mean:.5g}")
    ax.set_xlabel("Time")
    ax.set_ylabel(f"Block mean of {manual.column_name}")
    ax.set_title(f"Selected block means (m={manual.m}, n={manual.n})")
    _polish_axis(ax)
    ax.legend(loc="best", fontsize=8.7)
    fig.tight_layout()
    return fig


def plot_four_test_pvalues(result):
    """Plot the four diagnostic p-values against the configured alpha threshold."""
    manual = _selected_manual(result)
    if manual is None:
        raise ValueError("No final ManualResult is available for test plotting.")
    labels = ["Mean trend", "Dispersion trend", "Normality", "Positive serial corr."]
    keys = ["mean_trend_mk", "dispersion_trend_mk", "normality_shapiro", "positive_serial_von_neumann"]
    values = [manual.tests[k].p_value if manual.tests[k].p_value is not None else np.nan for k in keys]
    colors = ["C2" if bool(manual.tests[k].passed) else "C3" for k in keys]
    fig, ax = plt.subplots(figsize=(8.8, 4.15))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, alpha=0.82)
    ax.axhline(manual.alpha, linestyle="--", linewidth=1.25, color="C1", label=f"alpha = {manual.alpha:g}")
    ax.set_xticks(x, labels, rotation=14, ha="right")
    ax.set_ylabel("p-value")
    ymax = max([v for v in values if np.isfinite(v)] + [manual.alpha])
    ax.set_ylim(0, min(1.0, max(0.14, ymax * 1.22)))
    ax.set_title("Final four-test diagnostic p-values")
    _polish_axis(ax, grid_axis="y")
    for bar, key, val in zip(bars, keys, values):
        if np.isfinite(val):
            status = "pass" if manual.tests[key].passed else "attention"
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(), f"{val:.3g}\n{status}",
                    ha="center", va="bottom", fontsize=8.2)
    ax.legend(loc="best", fontsize=8.7)
    fig.tight_layout()
    return fig


def plot_multiresolution_pvalues(result):
    """Visualize mean/dispersion trend p-values over candidate starts and block sizes."""
    safe = result.auto_safe if isinstance(result, AutoCompareResult) else result
    if not isinstance(safe, AutoSafeResult) or not safe.trend_table:
        raise ValueError("No multi-resolution trend table is available.")
    m_grid = list(safe.m_trend_grid)
    starts = [entry["ts"] for entry in safe.trend_table]
    mean = np.full((len(m_grid), len(starts)), np.nan)
    disp = np.full_like(mean, np.nan)
    for j, entry in enumerate(safe.trend_table):
        by_m = {int(row["m"]): row for row in entry.get("m_results", [])}
        for i, m in enumerate(m_grid):
            row = by_m.get(int(m))
            if row:
                mean[i, j] = np.nan if row.get("mean_p") is None else float(row["mean_p"])
                disp[i, j] = np.nan if row.get("dispersion_p") is None else float(row["dispersion_p"])

    fig, axes = plt.subplots(2, 1, figsize=(10.0, 6.6), sharex=True)
    last_im = None
    for ax, data, title in [(axes[0], mean, "Mean-trend p-values"), (axes[1], disp, "Dispersion-trend p-values")]:
        last_im = ax.imshow(data, aspect="auto", origin="lower", interpolation="nearest", vmin=0.0, vmax=1.0)
        ax.set_yticks(np.arange(len(m_grid)), [str(m) for m in m_grid])
        ax.set_ylabel("Block size m")
        ax.set_title(title, loc="left", fontsize=11)
        if safe.selected_ts_sw is not None and starts:
            jsel = int(np.argmin(np.abs(np.asarray(starts, dtype=float) - float(safe.selected_ts_sw))))
            ax.axvline(jsel, color="white", linewidth=1.5, linestyle="--")
            ax.axvline(jsel, color="black", linewidth=0.55, linestyle="--", alpha=0.7)
    n = len(starts)
    tick_count = min(8, n)
    tick_idx = np.unique(np.linspace(0, n - 1, tick_count, dtype=int))
    axes[1].set_xticks(tick_idx, [f"{starts[i]:.4g}" for i in tick_idx], rotation=22, ha="right")
    axes[1].set_xlabel("Candidate start time")
    if last_im is not None:
        cbar = fig.colorbar(last_im, ax=axes, pad=0.018, fraction=0.026)
        cbar.set_label("p-value")
    selected = "not found" if safe.selected_ts_sw is None else f"{safe.selected_ts_sw:g}"
    fig.suptitle(
        f"Multi-resolution stationarity search  |  alpha={safe.alpha:g}  |  selected MDTest start={selected}",
        y=0.995, fontsize=12,
    )
    fig.subplots_adjust(left=0.09, right=0.9, top=0.91, bottom=0.12, hspace=0.22)
    return fig


def plot_ess_scan(result):
    """Plot ESS/IACT scan curves for Neff and statistical inefficiency g."""
    ess = result.ess if isinstance(result, AutoCompareResult) else result
    if not isinstance(ess, ESSResult) or not ess.scan_table:
        raise ValueError("No ESS scan table is available.")
    ts = np.asarray([r["ts"] for r in ess.scan_table], dtype=float)
    neff = np.asarray([r["neff"] for r in ess.scan_table], dtype=float)
    g = np.asarray([r["g"] for r in ess.scan_table], dtype=float)
    fig, axes = plt.subplots(2, 1, figsize=(9.4, 6.1), sharex=True)
    axes[0].plot(ts, neff, linewidth=1.15, color="C0")
    axes[0].axvline(ess.selected_ts_ess, linestyle="--", linewidth=1.25, color="C1")
    axes[0].scatter([ess.selected_ts_ess], [ess.selected_neff], s=28, color="C1", zorder=3)
    axes[0].set_ylabel("Effective sample size, Neff")
    axes[0].set_title("ESS/IACT candidate-start scan", loc="left", fontsize=11)
    axes[1].plot(ts, g, linewidth=1.15, color="C0")
    axes[1].axvline(ess.selected_ts_ess, linestyle="--", linewidth=1.25, color="C1")
    axes[1].scatter([ess.selected_ts_ess], [ess.selected_g], s=28, color="C1", zorder=3)
    axes[1].set_ylabel("Statistical inefficiency, g")
    axes[1].set_xlabel("Candidate start time")
    for ax in axes:
        _polish_axis(ax)
    axes[0].text(0.99, 0.95, f"selected start = {ess.selected_ts_ess:g}\nNeff = {ess.selected_neff:.5g}",
                 transform=axes[0].transAxes, ha="right", va="top", fontsize=8.5)
    axes[1].text(0.99, 0.95, f"g = {ess.selected_g:.5g}",
                 transform=axes[1].transAxes, ha="right", va="top", fontsize=8.5)
    fig.tight_layout()
    return fig


def create_diagnostic_figures(result) -> dict[str, Any]:
    """Create all presentation figures supported by a result object."""
    figures: dict[str, Any] = {}
    try:
        figures["trajectory"] = plot_time_series(result)
    except InputProvenanceError:
        raise
    except Exception:
        pass
    if isinstance(result, (AutoSafeResult, AutoCompareResult)):
        try:
            figures["multiresolution"] = plot_multiresolution_pvalues(result)
        except Exception:
            pass
    if isinstance(result, (ESSResult, AutoCompareResult)):
        try:
            figures["ess_scan"] = plot_ess_scan(result)
        except Exception:
            pass
    if _selected_manual(result) is not None:
        try:
            figures["block_means"] = plot_selected_block_means(result)
        except InputProvenanceError:
            raise
        except Exception:
            pass
        try:
            figures["four_tests"] = plot_four_test_pvalues(result)
        except Exception:
            pass
    return figures


def save_figures(figures: dict[str, Any], outdir: Path | str, prefix: str = "mdtest") -> dict[str, str]:
    """Save diagnostic figures and return a mapping from figure role to path."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, fig in figures.items():
        path = outdir / f"{prefix}_{name}.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        paths[name] = str(path)
    return paths
