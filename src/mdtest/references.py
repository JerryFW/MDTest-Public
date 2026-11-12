"""Curated references used by the MDTest educational/presentation layer.

This module is deliberately presentation-only.  Reference selection never
changes a statistical result or recommendation produced by the frozen engine.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Reference:
    """One human-readable literature reference."""
    key: str
    citation: str
    url: str
    topics: tuple[str, ...]


REFERENCES: dict[str, Reference] = {
    "schiferl_wallace_1985": Reference(
        key="schiferl_wallace_1985",
        citation=("S. K. Schiferl and D. C. Wallace, 'Statistical errors in molecular dynamics "
                  "averages,' J. Chem. Phys. 83, 5203-5209 (1985)."),
        url="https://doi.org/10.1063/1.449733",
        topics=("mdtest", "stationarity", "blocking", "molecular_dynamics"),
    ),
    "mann_1945": Reference(
        key="mann_1945",
        citation=("H. B. Mann, 'Nonparametric Tests Against Trend,' Econometrica 13, "
                  "245-259 (1945)."),
        url="https://doi.org/10.2307/1907187",
        topics=("mann_kendall", "trend"),
    ),
    "kendall_1975": Reference(
        key="kendall_1975",
        citation="M. G. Kendall, Rank Correlation Methods, 4th ed. (Griffin, London, 1975).",
        url="https://search.worldcat.org/title/3827024",
        topics=("mann_kendall", "trend"),
    ),
    "shapiro_wilk_1965": Reference(
        key="shapiro_wilk_1965",
        citation=("S. S. Shapiro and M. B. Wilk, 'An analysis of variance test for normality "
                  "(complete samples),' Biometrika 52, 591-611 (1965)."),
        url="https://doi.org/10.1093/biomet/52.3-4.591",
        topics=("shapiro_wilk", "normality"),
    ),
    "von_neumann_1941": Reference(
        key="von_neumann_1941",
        citation=("J. von Neumann, 'Distribution of the Ratio of the Mean Square Successive "
                  "Difference to the Variance,' Ann. Math. Stat. 12, 367-395 (1941)."),
        url="https://doi.org/10.1214/aoms/1177731677",
        topics=("von_neumann", "serial_correlation"),
    ),
    "chodera_2016": Reference(
        key="chodera_2016",
        citation=("J. D. Chodera, 'A Simple Method for Automated Equilibration Detection in "
                  "Molecular Simulations,' J. Chem. Theory Comput. 12, 1799-1805 (2016)."),
        url="https://doi.org/10.1021/acs.jctc.5b00784",
        topics=("ess", "iact", "equilibration"),
    ),
    "flyvbjerg_petersen_1989": Reference(
        key="flyvbjerg_petersen_1989",
        citation=("H. Flyvbjerg and H. G. Petersen, 'Error estimates on averages of correlated "
                  "data,' J. Chem. Phys. 91, 461-466 (1989)."),
        url="https://doi.org/10.1063/1.457480",
        topics=("blocking", "correlated_data", "uncertainty"),
    ),
}


def references_for_topics(topics: Iterable[str]) -> list[Reference]:
    """Return unique references matching any requested topic, in curated order."""
    wanted = {str(t).strip().lower() for t in topics}
    return [ref for ref in REFERENCES.values() if wanted.intersection(ref.topics)]


def references_by_key(keys: Sequence[str]) -> list[Reference]:
    """Return known references in the requested order, silently skipping unknown keys."""
    return [REFERENCES[k] for k in keys if k in REFERENCES]
