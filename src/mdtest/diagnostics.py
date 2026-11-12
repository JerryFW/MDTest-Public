"""Statistical primitives used by the MDTest analysis engine.

The implementations in this module were moved verbatim from the Round-1
single-file program.  The refactor changes organization, not statistical
formulae or thresholds.
"""
from __future__ import annotations
import math
import warnings
from typing import Optional, Sequence, Tuple
import numpy as np
from scipy import stats
from scipy.stats import shapiro, norm
from .results import TestOutcome


def block_series(values: np.ndarray, times: np.ndarray, start_index: int, m: int, n: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return block times, block means, and within-block variances."""
    if m < 1:
        raise ValueError("m must be at least 1.")
    available = len(values) - start_index
    nmax = available // m
    if n is None:
        n = nmax
    if n < 1:
        raise ValueError("No complete blocks are available for the requested start and m.")
    if n > nmax:
        raise ValueError(f"Requested n={n}, but only n={nmax} complete blocks are available.")
    cut_values = values[start_index:start_index + n * m]
    cut_times = times[start_index:start_index + n * m]
    blocks = cut_values.reshape(n, m)
    time_blocks = cut_times.reshape(n, m)
    means = blocks.mean(axis=1)
    block_times = time_blocks.mean(axis=1)
    if m >= 2:
        variances = blocks.var(axis=1, ddof=1)
    else:
        variances = np.full(n, np.nan)
    return block_times, means, variances


def mann_kendall_test(data: Sequence[float], alpha: float = 0.05) -> TestOutcome:
    """Two-sided Mann--Kendall trend test with tie correction.

    The statistic is computed with a Fenwick tree over value ranks, giving
    O(n log u) complexity where u is the number of distinct finite values.
    This avoids the quadratic pairwise loop during automated sweeps.
    """
    x = np.asarray(data, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 4:
        return TestOutcome(None, None, False, "not enough finite data for Mann--Kendall test")

    unique, inv = np.unique(x, return_inverse=True)
    u = len(unique)
    tree = np.zeros(u + 1, dtype=np.int64)

    def bit_add(i: int, value: int = 1) -> None:
        i += 1
        while i <= u:
            tree[i] += value
            i += i & -i

    def bit_sum(i: int) -> int:
        # inclusive prefix sum over ranks 0..i
        if i < 0:
            return 0
        total = 0
        i += 1
        while i > 0:
            total += int(tree[i])
            i -= i & -i
        return total

    s_stat = 0
    seen = 0
    for r in inv:
        r = int(r)
        less = bit_sum(r - 1)
        equal = bit_sum(r) - less
        greater = seen - less - equal
        s_stat += less - greater
        bit_add(r, 1)
        seen += 1

    _, counts = np.unique(x, return_counts=True)
    tie_term = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return TestOutcome(0.0, 1.0, True, "all values tied; no monotone trend detected")
    if s_stat > 0:
        z = (s_stat - 1) / math.sqrt(var_s)
    elif s_stat < 0:
        z = (s_stat + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * norm.sf(abs(z))
    return TestOutcome(float(z), float(p), bool(p > alpha), "two-sided Mann--Kendall")


def shapiro_test(data: Sequence[float], alpha: float) -> TestOutcome:
    'Run the Shapiro-Wilk normality check with MDTest pass/fail semantics.'
    x = np.asarray(data, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return TestOutcome(None, None, False, "not enough finite data for Shapiro--Wilk test")
    if len(x) > 5000:
        note = "Shapiro--Wilk p-value may be inaccurate for n>5000; SciPy warning suppressed"
    else:
        note = "Shapiro--Wilk normality test"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, p = shapiro(x)
    return TestOutcome(float(stat), float(p), bool(p > alpha), note)


def von_neumann_positive_test(data: Sequence[float], alpha: float) -> TestOutcome:
    """One-tailed von Neumann ratio test for positive adjacent correlation.

    Positive serial correlation decreases successive differences, so the
    lower tail is the relevant tail.
    """
    y = np.asarray(data, dtype=float)
    y = y[np.isfinite(y)]
    n = len(y)
    if n < 4:
        return TestOutcome(None, None, False, "not enough finite data for von Neumann test")
    denom = 2.0 * np.sum((y - y.mean()) ** 2)
    if denom <= 0:
        return TestOutcome(0.0, 1.0, True, "zero variance in block means")
    r = float(np.sum(np.diff(y) ** 2) / denom)
    sigma_r = math.sqrt((1.0 + 1.0 / (n - 1.0)) / (n + 1.0))
    z = (r - 1.0) / sigma_r
    p_lower = norm.cdf(z)
    return TestOutcome(float(z), float(p_lower), bool(p_lower > alpha), f"von Neumann ratio r={r:.6g}; lower-tail positive-correlation test")


def confidence_interval_t(block_means: np.ndarray, level: float = 0.95) -> Tuple[float, float, float, float]:
    'Return mean, standard error, and two-sided Student-t confidence interval.'
    n = len(block_means)
    mean = float(np.mean(block_means))
    if n < 2:
        return mean, float("nan"), float("nan"), float("nan")
    se = float(np.std(block_means, ddof=1) / math.sqrt(n))
    q = stats.t(df=n - 1).ppf(0.5 + level / 2.0)
    return mean, se, mean - q * se, mean + q * se
