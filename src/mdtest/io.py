"""Input parsing and small shared utilities for MDTest."""
from __future__ import annotations
import os
import warnings
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd


def _normalize_delim(delim: str) -> Optional[str]:
    'Translate user-friendly delimiter names into pandas separator values.'
    d = (delim or "comma").strip().lower()
    if d in {"comma", ",", "csv"}:
        return ","
    if d in {"space", "whitespace", "white", " "}:
        return r"\s+"
    if d in {"tab", "\\t"}:
        return "\t"
    return delim


def read_timeseries(file: str, delim: str = "comma", drop_nan: bool = False) -> Tuple[np.ndarray, List[str]]:
    """Read a time-series file. Column 0 is assumed to be time."""
    path = Path(file)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file}")

    if not isinstance(drop_nan, (bool, np.bool_)):
        raise ValueError("drop_nan must be a Boolean (True or False); string values are not accepted.")
    sep = _normalize_delim(delim)
    # Inspect the *raw* first record before pandas promotes it to column
    # names.  Duplicate numeric names are mangled ("0...e+00.1") by pandas,
    # which previously caused a headerless file to lose its first sample.
    options = {"sep": sep, "engine": "python"} if sep != "," else {"sep": sep}
    first = pd.read_csv(path, header=None, nrows=1, dtype=str,
                        keep_default_na=False, **options)
    if first.empty:
        raise ValueError("Input file is empty.")
    tokens = [str(x).strip() for x in first.iloc[0]]

    def _numeric(token: str) -> bool:
        try:
            float(token)
            return bool(token)
        except (TypeError, ValueError):
            return False

    # A mixed first record has no unambiguous header interpretation.
    # This includes a malformed/missing *time* token (NA,10, ,10) as well
    # as a malformed/missing observable (0,NA).  Requiring a wholly textual
    # header prevents silently deleting sample zero.  A header containing a
    # numeric column label should use a descriptive textual name instead.
    numeric_tokens = [_numeric(x) for x in tokens]
    missing_time_token = tokens and tokens[0].strip().lower() in {
        "", "na", "n/a", "null", "none", "nan", "missing", "?"
    }
    if (any(numeric_tokens) and not all(numeric_tokens)) or (missing_time_token and not all(numeric_tokens)):
        raise ValueError(
            "Ambiguous first CSV row: mixed numeric/nonnumeric fields or "
            "missing/invalid time token. Use an all-text header (e.g. "
            "'time,observable') or repair the first data record; "
            "no observation has been silently discarded."
        )
    headerless = bool(tokens) and all(_numeric(x) for x in tokens)
    df = pd.read_csv(path, header=None if headerless else "infer", **options)
    if headerless:
        titles = ["time"] + [f"observable_{j}" for j in range(1, df.shape[1])]
    else:
        titles = [str(c) for c in df.columns]

    # Convert data cells to numeric values.  Some MD outputs include a units
    # row after the header (for example: fs, kcal/mol, bar); such rows are
    # metadata, not data, and are removed with a warning.
    numeric_df = df.apply(pd.to_numeric, errors="coerce")
    nonnumeric_rows = numeric_df.isna().any(axis=1)
    if nonnumeric_rows.any():
        n_bad = int(nonnumeric_rows.sum())
        if drop_nan or n_bad <= 3:
            warnings.warn(f"Dropping {n_bad} nonnumeric or incomplete row(s) from input data.")
            numeric_df = numeric_df.loc[~nonnumeric_rows].copy()
        else:
            raise ValueError(
                f"Input file contains {n_bad} nonnumeric/NaN rows. "
                "Use --drop-nan to drop affected rows after manual inspection."
            )

    if numeric_df.replace([np.inf, -np.inf], np.nan).isna().any().any():
        if drop_nan:
            warnings.warn("Missing values detected; dropping rows containing NaN/Inf.")
            numeric_df = numeric_df.replace([np.inf, -np.inf], np.nan).dropna(axis=0)
        else:
            raise ValueError("Input file contains NaN/Inf values. Use --drop-nan to drop affected rows.")

    arr = numeric_df.to_numpy(dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError("Input file must contain at least two columns: time and one observable.")
    if len(arr) < 3:
        raise ValueError("Input series is too short.")
    # Validate the cleaned timeline before any public API branch, ESS scan,
    # early return, or Workbench column inspection.  Never reorder samples.
    ensure_uniform_time(arr[:, 0])
    return arr, titles


def ensure_uniform_time(times: np.ndarray, rtol: float = 1e-6, atol: float = 1e-12) -> float:
    'Validate increasing time values and return the median time step.'
    dt = np.diff(times)
    if np.any(dt <= 0):
        raise ValueError("Time column must be strictly increasing.")
    median_dt = float(np.median(dt))
    if not np.allclose(dt, median_dt, rtol=rtol, atol=atol):
        warnings.warn("Time steps are not exactly uniform; using median dt for indexing.")
    return median_dt


def validate_observable_column(arr: np.ndarray, col: int, titles: Sequence[str]) -> None:
    'Validate that an observable column is present and is not the time column.'
    if col < 1 or col >= arr.shape[1]:
        names = ", ".join(f"{i}:{name}" for i, name in enumerate(titles))
        raise ValueError(
            f"Observable column index {col} is invalid. Column 0 is time; "
            f"choose an index from 1 to {arr.shape[1]-1}. Available columns: {names}"
        )


def time_to_start_index(times: np.ndarray, ts: float) -> int:
    'Convert a physical start time to the first retained sample index.'
    if ts <= times[0]:
        return 0
    idx = int(np.searchsorted(times, ts, side="left"))
    return min(max(idx, 0), len(times) - 1)


def max_blocks(n_points_after_start: int, m: int) -> int:
    'Return the maximum number of complete blocks available.'
    if m <= 0:
        raise ValueError("m must be positive.")
    return int(n_points_after_start // m)


def validate_integer(value: Any, name: str, *, minimum: Optional[int] = None, allow_none: bool = False) -> Optional[int]:
    """Return an integer-valued argument without lossy coercion.

    Exact Python/NumPy integer inputs are preserved exactly, including values
    beyond binary64's exact-integer range. Integer-valued finite floats (for
    example ``10.0``) remain accepted for convenience, while fractional
    values, booleans, NaN, and infinities are rejected. String inputs are
    parsed through :class:`decimal.Decimal` so large exact integers do not
    round through ``float``.
    """
    from decimal import Decimal, InvalidOperation
    from numbers import Integral, Real

    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{name} must be an integer.")
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be an integer, not boolean.")

    if isinstance(value, Integral):
        result = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{name} must be an integer; got {value!r}.")
        try:
            numeric = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"{name} must be an integer; got {value!r}.") from None
        if not numeric.is_finite() or numeric != numeric.to_integral_value():
            raise ValueError(f"{name} must be integer-valued; got {value!r}.")
        result = int(numeric)
    elif isinstance(value, Real) or isinstance(value, np.floating):
        numeric = float(value)
        if not np.isfinite(numeric) or not numeric.is_integer():
            raise ValueError(f"{name} must be integer-valued; got {value!r}.")
        result = int(value)
    else:
        raise ValueError(f"{name} must be an integer; got {value!r}.")

    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}; got {result}.")
    return result


def validate_integer_sequence(values: Sequence[Any], name: str, *, minimum: Optional[int] = None) -> List[int]:
    """Validate, deduplicate, and sort an integer-valued Python sequence."""
    return sorted(set(validate_integer(v, name, minimum=minimum) for v in values))


def parse_int_list(value: str) -> List[int]:
    'Parse a comma/semicolon-separated integer grid into sorted unique values.'
    if value is None or str(value).strip() == "":
        return []
    out = []
    for part in str(value).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(validate_integer(part, "integer-list entry"))
    return sorted(set(out))


def parse_n(value: Any) -> Optional[int]:
    'Parse a block-count value, mapping max/auto/none to all available blocks.'
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"", "max", "none", "auto"}:
        return None
    return validate_integer(value, "n", minimum=1)


def sanitize_prefix(path: Path) -> str:
    'Return a filesystem-neutral text form of a path-like output prefix.'
    return str(path).replace(os.sep, "_").replace(" ", "_")
