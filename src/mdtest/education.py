"""Short chemist-friendly explanations for MDTest results.

The educational layer interprets existing result objects.  It performs no
statistical calculation and cannot change a pass/fail decision.
"""
from __future__ import annotations
from dataclasses import dataclass, fields
from typing import Iterable, Optional

from .references import Reference, references_by_key
from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult, TestOutcome


@dataclass(frozen=True)
class EducationalNote:
    """One concise explanatory item suitable for notebooks and reports."""
    title: str
    verdict: str
    explanation: str
    why_it_matters: str
    reference_keys: tuple[str, ...] = ()
    level: str = "guided"


def _p_text(outcome: TestOutcome) -> str:
    return "p unavailable" if outcome.p_value is None else f"p={outcome.p_value:.4g}"


_VALID_LEVELS = {"minimal", "guided", "technical"}

def _normalize_level(level: str) -> str:
    value = str(level).lower().strip()
    if value not in _VALID_LEVELS:
        raise ValueError(f"Unknown explanation level {level!r}; choose minimal, guided, or technical.")
    return value

def _test_suffix(outcome: TestOutcome, alpha: Optional[float], level: str) -> str:
    p = _p_text(outcome)
    if level != "technical":
        return p
    stat = "unavailable" if outcome.statistic is None else f"{outcome.statistic:.6g}"
    a = "unavailable" if alpha is None else f"{alpha:.6g}"
    return f"test statistic={stat}, {p}, alpha={a}"

def _settings_summary(result) -> str:
    settings = getattr(result, "settings", None)
    if settings is None:
        return "No structured RunSettings record is attached to this result."
    parts = []
    for f in fields(settings):
        value = getattr(settings, f.name)
        if value is not None:
            parts.append(f"{f.name}={value}")
    return "; ".join(parts) if parts else "RunSettings contains no populated fields."


def explain_test(name: str, outcome: TestOutcome, *, alpha: Optional[float] = None,
                 level: str = "guided") -> EducationalNote:
    """Explain one frozen diagnostic without changing its interpretation."""
    level = _normalize_level(level)
    passed = bool(outcome.passed)
    suffix = _test_suffix(outcome, alpha, level)

    if name == "mean_trend_mk":
        return EducationalNote(
            "Mean-trend screen",
            (f"No significant monotonic trend detected ({suffix})." if passed else
             f"Monotonic trend detected or not ruled out ({suffix})."),
            ("The Mann-Kendall test is applied to the sequence of block means. A pass means "
             "the test did not detect a systematic monotonic drift at the chosen significance level; "
             "it is not proof that every form of nonstationarity is absent."),
            "A continuing drift in the block means can bias an equilibrium average.",
            ("mann_1945", "kendall_1975"), level,
        )
    if name == "dispersion_trend_mk":
        return EducationalNote(
            "Dispersion-trend screen",
            (f"No significant monotonic change in block dispersion detected ({suffix})." if passed else
             f"Changing block dispersion detected or not ruled out ({suffix})."),
            ("MDTest applies a Mann-Kendall trend screen to a block-level fluctuation proxy. "
             "This asks whether the size of the fluctuations is still changing with time, even when "
             "the mean itself may look settled."),
            "A time-dependent fluctuation scale can bias variances and fluctuation-derived properties.",
            ("schiferl_wallace_1985", "mann_1945"), level,
        )
    if name == "normality_shapiro":
        return EducationalNote(
            "Block-mean normality screen",
            (f"Block means are not rejected as non-normal ({suffix})." if passed else
             f"Block-mean normality is rejected or not established ({suffix})."),
            ("The Shapiro-Wilk test is applied to the block means. Passing means the available block "
             "means are compatible with the normality assumption at the chosen significance level; "
             "it does not prove that the underlying molecular observable itself is Gaussian."),
            "Approximate normality of block means supports the Student-t uncertainty calculation used here.",
            ("shapiro_wilk_1965",), level,
        )
    if name == "positive_serial_von_neumann":
        return EducationalNote(
            "Residual positive-correlation screen",
            (f"No significant positive adjacent-block persistence detected ({suffix})." if passed else
             f"Positive adjacent-block persistence remains detectable ({suffix})."),
            ("The one-tailed von Neumann successive-difference diagnostic asks whether neighboring "
             "block means remain too similar. MDTest uses it as a local positive-correlation screen, "
             "not as a complete estimate of the full autocorrelation tail."),
            "Residual block-to-block correlation means the chosen blocks may still be too short for reporting uncertainty.",
            ("von_neumann_1941", "schiferl_wallace_1985"), level,
        )
    return EducationalNote(
        name, f"pass={passed} ({suffix})", outcome.note or "No additional explanation is registered.",
        "Interpret this result together with the other diagnostics.", (), level,
    )


def explain_ess(result: ESSResult, *, level: str = "guided") -> EducationalNote:
    """Explain an ESS/IACT result in language appropriate for an MD practitioner."""
    level = _normalize_level(level)
    g = float(result.selected_g)
    neff = float(result.selected_neff)
    technical = ""
    if level == "technical":
        s = result.settings
        technical = (
            f" Selected start index={result.selected_start_index_ess}; selected time={result.selected_ts_ess:g}."
            + (f" ESS scan controls: stride={s.ess_stride_points}, min_lag={s.ess_min_lag}, max_lag={s.ess_max_lag}." if s else "")
        )
    return EducationalNote(
        "ESS/IACT correlation assessment",
        f"Selected statistical inefficiency g={g:.4g}; effective sample count Neff={neff:.4g}.",
        ("Statistical inefficiency measures the variance penalty from serial correlation in the retained "
         "series. Roughly, N correlated observations carry the mean-estimation information of about N/g "
         "independent observations under the assumptions of the estimator. The ESS scan chooses a candidate "
         "start that maximizes the retained effective sample count." + technical),
        ("ESS/IACT addresses correlation and sampling efficiency. By itself it does not test whether the "
         "retained mean, variance, or distribution is stationary."),
        ("chodera_2016", "flyvbjerg_petersen_1989"), level,
    )


def explain_result(result, *, level: str = "guided") -> list[EducationalNote]:
    """Return concise explanatory notes relevant to a result object."""
    level = _normalize_level(level)
    notes: list[EducationalNote] = []
    manual: Optional[ManualResult] = None

    if isinstance(result, ManualResult):
        manual = result
        notes.append(EducationalNote(
            "Four-test MDTest result",
            "All four diagnostics passed." if result.overall_pass else "One or more diagnostics did not pass.",
            "MDTest checks stationarity-related assumptions on block-level summaries before reporting a block-based uncertainty estimate.",
            result.recommendation,
            ("schiferl_wallace_1985", "flyvbjerg_petersen_1989"), level,
        ))
    elif isinstance(result, AutoSafeResult):
        manual = result.manual_result
        if result.status == "pass":
            verdict = f"Earliest start passing the configured multi-resolution stationarity screens: ts={result.selected_ts_sw:g}."
        elif result.status == "stationarity-not-found":
            verdict = "No candidate start passed the configured multi-resolution stationarity screens on the scan grid."
        else:
            verdict = "Stationarity trend screens passed, but no reporting block passed the complete block-level checks."
        notes.append(EducationalNote(
            "Automatic multi-resolution stationarity search", verdict,
            ("The search examines candidate production starts over several diagnostic block sizes and accepts "
             "the earliest candidate for which both mean and dispersion trend screens pass across the complete grid."),
            ("Using several block sizes reduces dependence on one arbitrary smoothing choice. Failure to find a passing "
             "candidate start is a diagnostic outcome, not a program failure."),
            ("schiferl_wallace_1985", "mann_1945"), level,
        ))
    elif isinstance(result, AutoCompareResult):
        manual = result.manual_result_star
        sw = result.auto_safe.selected_ts_sw
        ess = result.ess.selected_ts_ess
        star = result.selected_ts_star
        if sw is None:
            verdict = f"ESS start ts={ess:g} is reported, but no candidate start passed the configured MDTest stationarity screens."
        else:
            verdict = f"MDTest start ts={sw:g}; ESS start ts={ess:g}; conservative reported start ts={star:g}."
        notes.append(EducationalNote(
            "Stationarity and ESS viewed together", verdict,
            ("The two analyses answer different questions. The MDTest branch screens stationarity-related block "
             "behavior; the ESS/IACT branch evaluates correlation-related sampling efficiency. Auto-compare reports "
             "both and currently uses the later start as its conservative combined start."),
            "A large disagreement between the two starts is worth inspecting physically rather than hiding behind one scalar summary.",
            ("schiferl_wallace_1985", "chodera_2016"), level,
        ))
        notes.append(explain_ess(result.ess, level=level))
    elif isinstance(result, ESSResult):
        notes.append(explain_ess(result, level=level))

    if manual is not None:
        for name, outcome in manual.tests.items():
            notes.append(explain_test(name, outcome, alpha=manual.alpha, level=level))

    if level == "technical":
        notes.append(EducationalNote(
            "Recorded inference settings",
            "Technical view of the settings stored with the frozen result.",
            _settings_summary(result),
            "These values document how the frozen engine was called; the educational layer does not recompute or alter them.",
            (), level,
        ))

    if level == "minimal":
        return [EducationalNote(n.title, n.verdict, "", "", n.reference_keys, level) for n in notes]
    return notes


def references_for_result(result, *, level: str = "guided") -> list[Reference]:
    """Return a deduplicated reference list required by the generated explanations."""
    keys: list[str] = []
    for note in explain_result(result, level=level):
        for key in note.reference_keys:
            if key not in keys:
                keys.append(key)
    return references_by_key(keys)
