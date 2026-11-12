"""Guided text/HTML reporting built on frozen MDTest result objects."""
from __future__ import annotations
from html import escape
import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from .education import EducationalNote, explain_result, references_for_result
from .references import Reference
from .reporting import write_json
from .results import AutoCompareResult, AutoSafeResult, ESSResult, ManualResult
from .visualization import create_diagnostic_figures, save_figures


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "not available"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)




def _display_status(result) -> str:
    """Translate frozen internal status codes into cautious user-facing text."""
    status = getattr(result, "status", None)
    if isinstance(result, AutoSafeResult):
        return {
            "pass": "configured MDTest screens passed",
            "stationarity-not-found": "no candidate start passed the configured stationarity screens",
            "stationarity-pass-correlation-not-found": "trend screens passed; no reporting block passed all four checks",
        }.get(status, str(status))
    if isinstance(result, AutoCompareResult):
        return {
            "pass": "MDTest and ESS/IACT starts available",
            "ess-only-no-stationarity-certification": "ESS/IACT start available; no candidate passed the configured MDTest stationarity screens",
            "start-found-correlation-not-found": "start selected; no reporting block passed all four checks",
        }.get(status, str(status))
    return str(status)

def result_headline(result) -> list[tuple[str, str]]:
    """Return key-value fields for a compact results dashboard."""
    if isinstance(result, ManualResult):
        return [
            ("Mode", "Manual four-test analysis"), ("Selected start", _fmt(result.ts)),
            ("Block size", str(result.m)), ("Number of blocks", str(result.n)),
            ("Mean", _fmt(result.mean)), ("Standard error", _fmt(result.se)),
            ("95% interval", f"[{_fmt(result.ci_low)}, {_fmt(result.ci_high)}]"),
            ("Overall", "PASS" if result.overall_pass else "ATTENTION"),
        ]
    if isinstance(result, AutoSafeResult):
        return [
            ("Mode", "Automatic multi-resolution MDTest"), ("Status", _display_status(result)),
            ("MDTest start", _fmt(result.selected_ts_sw)), ("Start index", _fmt(result.selected_start_index_sw)),
            ("Reporting block size", _fmt(result.selected_m_corr)), ("Number of blocks", _fmt(result.selected_n_corr)),
        ]
    if isinstance(result, ESSResult):
        return [
            ("Mode", "ESS/IACT only"), ("ESS start", _fmt(result.selected_ts_ess)),
            ("Start index", str(result.selected_start_index_ess)), ("g", _fmt(result.selected_g)),
            ("Neff", _fmt(result.selected_neff)),
        ]
    if isinstance(result, AutoCompareResult):
        return [
            ("Mode", "MDTest + ESS/IACT"), ("Status", _display_status(result)),
            ("MDTest start", _fmt(result.auto_safe.selected_ts_sw)),
            ("ESS start", _fmt(result.ess.selected_ts_ess)),
            ("Reported start", _fmt(result.selected_ts_star)),
            ("g at ESS start", _fmt(result.ess.selected_g)),
            ("Neff at ESS start", _fmt(result.ess.selected_neff)),
            ("Reporting block size", _fmt(result.selected_m_corr_star)),
        ]
    return [("Result", type(result).__name__)]


def format_guided_text(result, *, level: str = "guided", include_references: bool = True) -> str:
    """Return a plain-text report suitable for terminals or notebook text cells."""
    level = str(level).lower().strip()
    lines = [f"MDTest {level} analysis summary", "=" * 30]
    for key, value in result_headline(result):
        lines.append(f"{key}: {value}")
    lines.extend(["", "Interpretation"])
    for note in explain_result(result, level=level):
        lines.append(f"- {note.title}: {note.verdict}")
        if note.explanation:
            lines.append(f"  {note.explanation}")
        if note.why_it_matters:
            lines.append(f"  Why it matters: {note.why_it_matters}")
    if include_references:
        lines.extend(["", "Learn more"])
        for ref in references_for_result(result, level=level):
            lines.append(f"- {ref.citation} {ref.url}")
    return "\n".join(lines) + "\n"


def _note_html(note: EducationalNote) -> str:
    body = ""
    if note.explanation:
        body += f"<p>{escape(note.explanation)}</p>"
    if note.why_it_matters:
        body += f"<p><strong>Why it matters:</strong> {escape(note.why_it_matters)}</p>"
    return ("<section class='mdtest-note'>"
            f"<h4>{escape(note.title)}</h4><p class='verdict'>{escape(note.verdict)}</p>{body}</section>")


def _refs_html(refs: list[Reference]) -> str:
    if not refs:
        return ""
    items = "".join(f"<li>{escape(r.citation)} <a href='{escape(r.url)}' target='_blank'>link</a></li>" for r in refs)
    return f"<details><summary>Learn more: references</summary><ol>{items}</ol></details>"


def _provenance_html(result) -> str:
    prov = getattr(result, "provenance", None)
    if prov is None:
        return ""
    fields = []
    for label, attr in [
        ("MDTest", "mdtest_version"), ("Python", "python_version"),
        ("NumPy", "numpy_version"), ("SciPy", "scipy_version"),
    ]:
        value = getattr(prov, attr, None)
        if value:
            fields.append(f"<span><strong>{escape(label)}:</strong> {escape(str(value))}</span>")
    digest = getattr(prov, "input_sha256", None)
    if digest:
        fields.append(f"<span><strong>Input SHA-256:</strong> <code>{escape(str(digest)[:16])}...</code></span>")
    if not fields:
        return ""
    return "<details class='mdtest-provenance'><summary>Reproducibility metadata</summary><div>" + "".join(fields) + "</div></details>"



def _figure_object_sources(figures: dict[str, Any]) -> dict[str, str]:
    """Encode Matplotlib figures as in-memory PNG data URIs for notebook display."""
    sources: dict[str, str] = {}
    for name, fig in figures.items():
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        payload = base64.b64encode(buf.getvalue()).decode("ascii")
        sources[name] = f"data:image/png;base64,{payload}"
    return sources


def _figure_cards_html(sources: dict[str, str]) -> str:
    rendered = []
    captions = {
        "trajectory": ("Trajectory & selected start", "Raw observable with the relevant MDTest/ESS start markers."),
        "multiresolution": ("Multi-resolution stationarity map", "Mean- and dispersion-trend p-values over the evaluated candidate-start grid."),
        "ess_scan": ("ESS / IACT scan", "Effective sample count and statistical inefficiency across candidate starts."),
        "block_means": ("Selected block means", "Coarse-grained samples used for the final reported uncertainty."),
        "four_tests": ("Final four-test diagnostics", "Stored p-values and pass/attention status at the reporting scale."),
    }
    for name, src in sources.items():
        title, subtitle = captions.get(name, (name.replace("_", " ").title(), "Diagnostic visualization"))
        rendered.append(
            "<figure class='mdtest-figure-card'>"
            f"<div class='mdtest-figure-head'><strong>{escape(title)}</strong><span>{escape(subtitle)}</span></div>"
            f"<img src='{escape(src)}' alt='{escape(title)}'>"
            "</figure>"
        )
    if not rendered:
        return ""
    return "<section class='mdtest-visuals'><div class='mdtest-section-head'><div><span class='mdtest-section-kicker'>Diagnostics</span><h3>Visual checks</h3></div><span class='mdtest-section-meta'>presentation only</span></div><div class='mdtest-figure-grid'>" + "".join(rendered) + "</div></section>"

def result_to_html(result, *, level: str = "guided", include_references: bool = True,
                   figure_paths: dict[str, str] | None = None,
                   figure_sources: dict[str, str] | None = None,
                   standalone: bool = False) -> str:
    """Render a polished, compact HTML dashboard for one result."""
    metrics = "".join(
        f"<div class='mdtest-metric'><div class='mdtest-metric-label'>{escape(k)}</div>"
        f"<div class='mdtest-metric-value'>{escape(v)}</div></div>"
        for k, v in result_headline(result)
    )
    notes = "".join(_note_html(n) for n in explain_result(result, level=level))
    refs = _refs_html(references_for_result(result, level=level)) if include_references else ""
    resolved_sources: dict[str, str] = dict(figure_sources or {})
    if figure_paths:
        for name, p in figure_paths.items():
            path = Path(p)
            if standalone:
                if not path.is_file():
                    raise FileNotFoundError(f"Cannot embed missing report figure: {path}")
                payload = base64.b64encode(path.read_bytes()).decode("ascii")
                suffix = path.suffix.lower()
                mime = "image/png" if suffix == ".png" else "application/octet-stream"
                resolved_sources[name] = f"data:{mime};base64,{payload}"
            else:
                resolved_sources[name] = path.name
    figures = _figure_cards_html(resolved_sources)
    css = """
<style>
.mdtest-dashboard{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;max-width:1140px;line-height:1.48;margin:0 auto}
.mdtest-reportbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 16px;border-radius:14px 14px 0 0;background:linear-gradient(135deg,#102f4c,#174b78 62%,#1c5a8d);color:#fff;border:1px solid #234f78}.mdtest-reportbrand{display:flex;align-items:center;gap:10px;font-weight:760}.mdtest-reportmark{display:grid;place-items:center;width:31px;height:31px;border-radius:8px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);font-weight:800}.mdtest-reportmeta{font-size:.73rem;border:1px solid rgba(255,255,255,.24);border-radius:999px;padding:4px 8px;color:#eaf2f8}
.mdtest-hero{border:1px solid #d9e0e8;border-top:0;border-radius:0 0 14px 14px;padding:18px 20px;margin:0 0 16px;background:linear-gradient(180deg,#fff,#fbfcfe);box-shadow:0 6px 18px rgba(16,24,40,.035)}.mdtest-hero-row{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.mdtest-hero h2{margin:0 0 4px;font-size:1.42rem;letter-spacing:-.02em;color:#101828}.mdtest-hero .subtle{margin:0;color:#667085;max-width:820px}.mdtest-resultchip{font-size:.72rem;white-space:nowrap;font-weight:700;color:#067647;background:#ecfdf3;border:1px solid #abefc6;border-radius:999px;padding:5px 9px}
.mdtest-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin:22px 0 10px}.mdtest-section-head h3{margin:1px 0 0;font-size:1.09rem;color:#101828}.mdtest-section-kicker{font-size:.68rem;text-transform:uppercase;letter-spacing:.075em;color:#667085;font-weight:760}.mdtest-section-meta{font-size:.72rem;color:#98a2b3}
.mdtest-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:9px;margin:0 0 18px}.mdtest-metric{border:1px solid #e1e6ed;border-radius:10px;padding:11px 12px;background:#fff;min-height:58px;box-shadow:0 1px 2px rgba(16,24,40,.025)}.mdtest-metric-label{font-size:.68rem;color:#667085;text-transform:uppercase;letter-spacing:.055em;font-weight:700;margin-bottom:5px}.mdtest-metric-value{font-size:1.01rem;font-weight:710;color:#101828;overflow-wrap:anywhere}
.mdtest-notes{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:9px}.mdtest-note{border:1px solid #e1e6ed;border-radius:10px;padding:11px 13px;margin:0;background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.02)}.mdtest-note h4{margin:0 0 5px;font-size:.92rem;color:#344054}.mdtest-note p{margin:5px 0;font-size:.86rem;color:#475467}.mdtest-note .verdict{font-weight:700;color:#172033}
.mdtest-visuals{margin-top:4px}.mdtest-figure-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}.mdtest-figure-card{margin:0;border:1px solid #dfe5ec;border-radius:11px;background:#fff;overflow:hidden;box-shadow:0 3px 10px rgba(16,24,40,.035)}.mdtest-figure-head{padding:10px 12px 8px;border-bottom:1px solid #edf0f4;background:#fbfcfd}.mdtest-figure-head strong{display:block;font-size:.86rem;color:#344054}.mdtest-figure-head span{display:block;margin-top:2px;font-size:.72rem;color:#98a2b3}.mdtest-figure-card img{display:block;width:100%;height:auto;background:#fff;padding:5px}
.mdtest-dashboard details{margin:15px 0;padding:9px 12px;background:#f8fafc;border:1px solid #e4e7ec;border-radius:9px}.mdtest-dashboard summary{cursor:pointer;font-weight:650;color:#344054;font-size:.86rem}.mdtest-provenance div{display:flex;flex-wrap:wrap;gap:7px 17px;margin-top:8px;font-size:.8rem;color:#667085}.mdtest-dashboard code{font-size:.9em}.mdtest-reportfooter{margin:18px 0 4px;padding-top:10px;border-top:1px solid #edf0f4;color:#98a2b3;font-size:.72rem;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@media(max-width:760px){.mdtest-figure-grid{grid-template-columns:1fr}.mdtest-metrics{grid-template-columns:1fr 1fr}.mdtest-notes{grid-template-columns:1fr}.mdtest-reportmeta{display:none}.mdtest-hero-row{display:block}.mdtest-resultchip{display:inline-block;margin-top:9px}}
</style>
"""
    core = f"""
{css}
<div class='mdtest-dashboard'>
  <div class='mdtest-reportbar'>
    <div class='mdtest-reportbrand'><span class='mdtest-reportmark'>M</span><span>MDTest</span></div>
    <span class='mdtest-reportmeta'>structured scientific report</span>
  </div>
  <div class='mdtest-hero'>
    <div class='mdtest-hero-row'><div><h2>Analysis summary</h2>
    <p class='subtle'>Numerical result, interpretation, diagnostics, and provenance rendered from one structured result object.</p></div>
    <span class='mdtest-resultchip'>result ready</span></div>
  </div>
  <div class='mdtest-section-head'><div><span class='mdtest-section-kicker'>Result</span><h3>Key metrics</h3></div><span class='mdtest-section-meta'>stored values</span></div>
  <div class='mdtest-metrics'>{metrics}</div>
  <div class='mdtest-section-head'><div><span class='mdtest-section-kicker'>Interpretation</span><h3>What the result means</h3></div><span class='mdtest-section-meta'>{escape(str(level))} view</span></div>
  <div class='mdtest-notes'>{notes}</div>
  {figures}
  {_provenance_html(result)}
  {refs}
  <div class='mdtest-reportfooter'><span>MDTest report presentation</span><span>Inference is produced by the public computational API.</span></div>
</div>
"""
    if not standalone:
        return core
    page_css = """
body{margin:0;background:#eef2f6}.mdtest-page{max-width:1180px;margin:28px auto;padding:20px;background:white;border:1px solid #dfe5ec;border-radius:16px;box-shadow:0 12px 34px rgba(16,24,40,.07)}
"""
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MDTest report</title><style>{page_css}</style></head><body><div class='mdtest-page'>{core}</div></body></html>"

def display_result(result, *, level: str = "guided", include_figures: bool = True,
                   include_references: bool = True):
    """Display one integrated guided dashboard in a Jupyter/IPython environment."""
    try:
        from IPython.display import HTML, display
    except Exception as exc:
        raise RuntimeError("display_result requires IPython/Jupyter; use format_guided_text instead.") from exc
    figures: dict[str, Any] = {}
    sources: dict[str, str] = {}
    if include_figures:
        figures = create_diagnostic_figures(result)
        sources = _figure_object_sources(figures)
    display(HTML(result_to_html(result, level=level, include_references=include_references,
                                figure_sources=sources)))
    if figures:
        try:
            import matplotlib.pyplot as plt
            for fig in figures.values():
                plt.close(fig)
        except Exception:
            pass
    return result


def export_guided_report(result, outdir: str | Path = "results/workbench", *, prefix: str = "mdtest_workbench",
                         level: str = "guided", include_figures: bool = True) -> dict[str, Any]:
    """Export result JSON, guided text, self-contained HTML, and diagnostic PNG figures."""
    outdir = Path(outdir)
    figures: dict[str, Any] = {}
    if include_figures:
        # Build figures before writing report files.  Raw-data-dependent plots
        # verify the current input bytes against result provenance, so a stale
        # or modified source fails clearly instead of leaving a mixed report.
        figures = create_diagnostic_figures(result)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / f"{prefix}_result.json"
    text_path = outdir / f"{prefix}_guided.txt"
    html_path = outdir / f"{prefix}_guided.html"
    write_json(json_path, result)
    text_path.write_text(format_guided_text(result, level=level, include_references=True), encoding="utf-8")
    figure_paths: dict[str, str] = {}
    if figures:
        figure_paths = save_figures(figures, outdir, prefix=prefix)
        try:
            import matplotlib.pyplot as plt
            for fig in figures.values():
                plt.close(fig)
        except Exception:
            pass
    html_path.write_text(result_to_html(result, level=level, include_references=True,
                                        figure_paths=figure_paths, standalone=True), encoding="utf-8")
    return {"json": str(json_path), "text": str(text_path), "html": str(html_path), "figures": figure_paths}
