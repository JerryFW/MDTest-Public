"""Reproducibility metadata helpers.  No statistical logic lives here."""
from __future__ import annotations
import hashlib
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional
import numpy as np
from ._version import __version__
from .results import RunProvenance


def _dist_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def sha256_file(path: str | Path) -> Optional[str]:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


PARSER_SCHEMA = "mdtest-cleaned-time-observable-v1"


def parsed_observable_hash(data: np.ndarray) -> str:
    """Digest of exactly the cleaned time/observable pairs in their order."""
    arr = np.ascontiguousarray(data, dtype="<f8")
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError("Parsed identity requires time and one observable.")
    h = hashlib.sha256()
    h.update(PARSER_SCHEMA.encode("ascii") + b"\0")
    h.update(str(arr.shape).encode("ascii") + b"\0")
    h.update(arr.tobytes(order="C"))
    return h.hexdigest()


def collect_provenance(path: str | Path, *, parsed_array: Optional[np.ndarray] = None) -> RunProvenance:
    return RunProvenance(
        mdtest_version=__version__,
        python_version=platform.python_version(),
        numpy_version=_dist_version("numpy"),
        scipy_version=_dist_version("scipy"),
        pandas_version=_dist_version("pandas"),
        matplotlib_version=_dist_version("matplotlib"),
        input_sha256=sha256_file(path),
        parser_schema=PARSER_SCHEMA if parsed_array is not None else None,
        parsed_n_rows=int(len(parsed_array)) if parsed_array is not None else None,
        parsed_array_sha256=parsed_observable_hash(parsed_array) if parsed_array is not None else None,
    )
