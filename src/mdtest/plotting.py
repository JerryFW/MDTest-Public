"""Plotting helpers.  Plotting is presentation-only and does not affect inference.

Importing :mod:`mdtest` never calls ``matplotlib.use`` and therefore never
overrides a backend already selected by the calling Python/Jupyter process.
Batch users who need a specific backend should use Matplotlib's standard
``MPLBACKEND`` environment variable before Python starts.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import matplotlib.pyplot as plt


def _show_saved_or_live_figure(fig: Any, image_path: Path, display: bool) -> None:
    'Display a saved figure in Jupyter or a GUI when interactive display is requested.'
    if not display:
        return

    # If in a Jupyter notebook, display the saved PNG inline.
    try:
        from IPython import get_ipython
        from IPython.display import Image, display as ipy_display

        shell = get_ipython()
        if shell is not None and shell.__class__.__name__ == "ZMQInteractiveShell":
            ipy_display(Image(filename=str(image_path)))
            return
    except Exception:
        pass

    # Otherwise, just use Matplotlib's normal GUI display.
    try:
        plt.show(block=True)
    except Exception:
        print(f"Plot saved to {image_path}")


def plot_initial_raw(times: np.ndarray, values: np.ndarray, out_path: Path, title: str = "observable", display: bool = False) -> None:
    """Save and optionally display the initial raw time-series preview."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(times, values, linewidth=0.8)
    ax.set_xlabel("time")
    ax.set_ylabel(title)
    ax.set_title("Initial raw time-series preview")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    _show_saved_or_live_figure(fig, out_path, display)
    plt.close(fig)


def plot_raw_and_blocks(times: np.ndarray, values: np.ndarray, block_t: np.ndarray, block_y: np.ndarray, ts: float, m: int, prefix: Path, title: str = "observable", display: bool = False) -> None:
    'Save the raw-series/start-time and block-mean diagnostic figures.'
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw_path = prefix.with_name(prefix.name + "_raw.png")
    blocks_path = prefix.with_name(prefix.name + "_blocks.png")

    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(times, values, linewidth=0.8)
    ax.axvline(ts, linestyle="--", linewidth=1.0)
    ax.set_xlabel("time")
    ax.set_ylabel(title)
    ax.set_title(f"Raw time series; selected start ts={ts:g}")
    fig.tight_layout()
    fig.savefig(raw_path, dpi=180)
    _show_saved_or_live_figure(fig, raw_path, display)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(block_t, block_y, marker="o", markersize=3.0, linewidth=0.8)
    ax.set_xlabel("time")
    ax.set_ylabel(f"block mean of {title}")
    ax.set_title(f"Block means after coarse graining (m={m})")
    fig.tight_layout()
    fig.savefig(blocks_path, dpi=180)
    _show_saved_or_live_figure(fig, blocks_path, display)
    plt.close(fig)
