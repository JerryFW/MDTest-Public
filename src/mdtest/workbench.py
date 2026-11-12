"""Jupyter Workbench front end for MDTest.

The widget layer calls only the public :mod:`mdtest.api` functions for
analysis.  It does not contain statistical formulas.  ``ipywidgets`` is an
optional dependency imported only when the interactive interface is launched.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
import hashlib
import tempfile
from html import escape

from . import api
from ._version import __version__
from .io import read_timeseries
from .messages import completion_message, loaded_message
from .presentation import display_result, export_guided_report
from .provenance import sha256_file


@dataclass(frozen=True)
class WorkbenchRequest:
    """Serializable controller request used by the notebook GUI."""
    file: str
    col: int
    mode: str = "auto-compare"
    delim: str = "comma"
    drop_nan: bool = False
    alpha: float = 0.05
    min_blocks: int = 24
    m_trend_grid: tuple[int, ...] = (2, 5, 10, 20, 40)
    m_corr_grid: tuple[int, ...] = (5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480)
    stride_points: Optional[int] = None
    ess_stride_points: Optional[int] = None
    ess_min_lag: int = 3
    ess_max_lag: Optional[int] = None
    manual_ts: float = 0.0
    manual_m: int = 10
    manual_n: Optional[int | str] = None


def list_observables(file: str | Path, *, delim: str = "comma", drop_nan: bool = False) -> dict[str, Any]:
    """Inspect a file for the Workbench without performing statistical analysis."""
    arr, titles = read_timeseries(str(file), delim, drop_nan)
    return {
        "n_rows": int(arr.shape[0]),
        "n_columns": int(arr.shape[1]),
        "titles": list(titles),
        "observables": [(i, titles[i] if i < len(titles) else f"column_{i}") for i in range(1, arr.shape[1])],
        "time_min": float(arr[0, 0]),
        "time_max": float(arr[-1, 0]),
    }


def run_request(req: WorkbenchRequest):
    """Execute one Workbench request exclusively through the frozen public API."""
    common = dict(file=req.file, col=req.col, delim=req.delim, drop_nan=req.drop_nan)
    mode = req.mode.strip().lower().replace("_", "-")
    if mode == "manual":
        return api.manual(**common, ts=req.manual_ts, m=req.manual_m, n=req.manual_n,
                          alpha=req.alpha, min_blocks=req.min_blocks)
    if mode in {"auto-safe", "auto"}:
        return api.auto_safe(**common, alpha=req.alpha, min_blocks=req.min_blocks,
                             m_trend_grid=req.m_trend_grid, m_corr_grid=req.m_corr_grid,
                             stride_points=req.stride_points)
    if mode in {"auto-compare", "compare"}:
        return api.auto_compare(**common, alpha=req.alpha, min_blocks=req.min_blocks,
                                m_trend_grid=req.m_trend_grid, m_corr_grid=req.m_corr_grid,
                                stride_points=req.stride_points, ess_stride_points=req.ess_stride_points,
                                ess_min_lag=req.ess_min_lag, ess_max_lag=req.ess_max_lag)
    if mode in {"ess", "iact", "ess-iact"}:
        return api.ess(**common, min_blocks=req.min_blocks, scan_stride_points=req.ess_stride_points,
                       min_lag=req.ess_min_lag, max_lag=req.ess_max_lag)
    raise ValueError(f"Unsupported Workbench mode: {req.mode!r}")


def list_workspace_files(directory: str | Path | None = None) -> list[tuple[str, str]]:
    """List ordinary data files near the running notebook as an upload fallback.

    This scans only selected local folders; it does not read files, search a
    user's home directory, or follow links into an unrelated filesystem.
    """
    root = Path(directory or Path.cwd()).resolve()
    folders = (root, root / "data", root / "uploads", root / "examples" / "data")
    seen: set[Path] = set()
    found: list[tuple[str, str]] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            candidates = sorted(folder.iterdir(), key=lambda f: f.name.lower())
        except OSError:
            continue
        for candidate in candidates:
            if (candidate.suffix.lower() not in {".csv", ".txt", ".dat", ".tsv"}
                    or not candidate.is_file() or candidate.is_symlink()):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            found.append((candidate.relative_to(root).as_posix(), str(candidate)))
    return found


def workbench_status() -> dict[str, Any]:
    """Report whether the optional widget dependency is available."""
    try:
        import ipywidgets as widgets  # noqa: F401
        return {"available": True, "message": "ipywidgets is available; the interactive Workbench can be launched."}
    except Exception:
        return {"available": False,
                "message": "Interactive widgets are optional. Install with: pip install 'mdtest[workbench]' (or pip install ipywidgets)."}


class MDTestWorkbench:
    """Stateful Jupyter GUI wrapper around the frozen MDTest public API."""
    def __init__(self):
        try:
            import ipywidgets as widgets
            from IPython.display import display
        except Exception as exc:
            raise RuntimeError("MDTest Workbench requires ipywidgets. Install with: pip install 'mdtest[workbench]'") from exc
        self.widgets = widgets
        self._display = display
        self._tmp = tempfile.TemporaryDirectory(prefix="mdtest_workbench_")
        self.result = None
        self.current_file: Optional[str] = None
        self._active_source_kind: Optional[str] = None
        self._loaded_source_signature: Optional[tuple[Any, ...]] = None
        self._completed_request: Optional[WorkbenchRequest] = None
        self._build()

    @staticmethod
    def _parse_grid(text: str) -> tuple[int, ...]:
        vals = []
        for p in str(text).replace(";", ",").split(","):
            p = p.strip()
            if p:
                vals.append(int(p))
        return tuple(sorted(set(vals)))

    @staticmethod
    def _optional_int(value) -> Optional[int]:
        s = str(value).strip()
        return None if s in {"", "None", "none", "auto"} else int(s)

    def _build(self):
        w = self.widgets

        # Presentation-only design system.  The Workbench deliberately uses
        # plain CSS + ipywidgets so it remains portable across classic Notebook,
        # JupyterLab, VS Code notebooks, and hosted notebook environments.
        css = w.HTML("""
<style>
:root{
  --md-ink:#172033; --md-muted:#667085; --md-border:#d9e0e8; --md-soft:#f6f8fb;
  --md-panel:#ffffff; --md-brand:#123a63; --md-brand2:#1c5a8d; --md-accent:#087a6a;
  --md-success:#067647; --md-success-bg:#ecfdf3; --md-warn:#9a6700; --md-warn-bg:#fffaeb;
  --md-error:#b42318; --md-error-bg:#fef3f2; --md-shadow:0 10px 28px rgba(16,24,40,.065);
}
.mdtest-wb-shell{max-width:1180px;margin:0 auto 24px;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--md-ink)}
.mdtest-productbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 18px;border:1px solid #234f78;border-radius:16px 16px 0 0;background:linear-gradient(135deg,#102f4c 0%,#174b78 58%,#1c5a8d 100%);color:#fff;box-shadow:var(--md-shadow)}
.mdtest-brand{display:flex;align-items:center;gap:12px}.mdtest-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.24);font-weight:800;font-size:19px;letter-spacing:-.04em}
.mdtest-brandname{font-weight:760;font-size:1.08rem;line-height:1.05}.mdtest-brandtag{display:block;margin-top:4px;font-size:.76rem;color:#d6e4f0;font-weight:500}
.mdtest-productmeta{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.mdtest-chip{font-size:.72rem;font-weight:650;border:1px solid rgba(255,255,255,.26);background:rgba(255,255,255,.10);border-radius:999px;padding:5px 9px;white-space:nowrap}.mdtest-chip-accent{background:rgba(94,234,212,.12);border-color:rgba(153,246,228,.36);color:#d9fff7}
.mdtest-wb-hero{border:1px solid var(--md-border);border-top:0;border-radius:0 0 16px 16px;padding:22px 22px 19px;margin-bottom:14px;background:linear-gradient(180deg,#fff 0%,#fbfcfe 100%);box-shadow:0 6px 18px rgba(16,24,40,.035)}
.mdtest-wb-eyebrow{font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;color:var(--md-brand2);font-weight:760}.mdtest-wb-hero h2{margin:4px 0 6px;font-size:1.65rem;letter-spacing:-.025em;color:#101828}.mdtest-wb-hero p{margin:0;color:var(--md-muted);max-width:880px;line-height:1.5}
.mdtest-workflow{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 14px}.mdtest-workflow-step{display:flex;align-items:center;gap:9px;padding:9px 12px;border:1px solid var(--md-border);background:#fff;border-radius:10px;color:#475467;font-size:.82rem;font-weight:650}.mdtest-workflow-step b{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#eaf2f8;color:var(--md-brand);font-size:.72rem}
.mdtest-card{border:1px solid var(--md-border)!important;border-radius:14px!important;padding:0!important;margin:0 0 14px!important;background:var(--md-panel)!important;box-shadow:0 5px 16px rgba(16,24,40,.035);overflow:hidden}
.mdtest-card-head{display:flex;gap:12px;align-items:flex-start;padding:15px 17px 12px;border-bottom:1px solid #edf0f4;background:linear-gradient(180deg,#fff,#fbfcfd)}.mdtest-stepnum{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:9px;background:#eaf2f8;color:var(--md-brand);font-size:.78rem;font-weight:800}.mdtest-card-head h3{margin:0 0 3px;color:#101828;font-size:1.02rem}.mdtest-card-head p{margin:0;color:var(--md-muted);font-size:.84rem;line-height:1.4}
.mdtest-card-body{padding:14px 17px 16px}.mdtest-subhead{font-size:.69rem;text-transform:uppercase;letter-spacing:.075em;color:#667085;font-weight:750;margin:3px 0 8px}.mdtest-divider{height:1px;background:#eef1f4;margin:12px 0}
.mdtest-wb-help{color:var(--md-muted);font-size:.82rem;line-height:1.45}.mdtest-modehelp{padding:10px 12px;border-radius:9px;background:#f7f9fc;border:1px solid #e1e6ed;color:#475467;font-size:.84rem;line-height:1.45;margin:7px 0 2px}
.mdtest-status{display:flex;gap:9px;align-items:flex-start;border-radius:9px;padding:10px 12px;margin:8px 0;font-size:.84rem;line-height:1.4;border:1px solid var(--md-border);background:#f8fafc;color:#344054}.mdtest-status b{color:inherit}.mdtest-status-ready{background:var(--md-success-bg);border-color:#abefc6;color:var(--md-success)}.mdtest-status-warn{background:var(--md-warn-bg);border-color:#fedf89;color:var(--md-warn)}.mdtest-status-error{background:var(--md-error-bg);border-color:#fecdca;color:var(--md-error)}.mdtest-status-running{background:#eff8ff;border-color:#b2ddff;color:#175cd3}.mdtest-dot{width:8px;height:8px;border-radius:50%;background:currentColor;margin-top:5px;flex:0 0 auto}
.mdtest-securityline{display:flex;gap:9px;align-items:center;margin-top:8px;padding:8px 10px;border-radius:8px;background:#f8fafc;color:#667085;font-size:.76rem;border:1px solid #edf0f4}.mdtest-lock{font-size:.86rem;color:var(--md-brand2)}
.mdtest-actionnote{font-size:.76rem;color:#667085;margin:6px 0 0}.mdtest-footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:2px 4px 0;color:#98a2b3;font-size:.72rem}
.mdtest-wb-shell .widget-label{font-weight:620;color:#344054}.mdtest-wb-shell .widget-text input,.mdtest-wb-shell .widget-dropdown select,.mdtest-wb-shell .widget-float-text input,.mdtest-wb-shell .widget-int-text input{border-radius:7px!important;border-color:#cfd7e3!important;min-height:34px}.mdtest-wb-shell .widget-text input:focus,.mdtest-wb-shell .widget-dropdown select:focus,.mdtest-wb-shell .widget-float-text input:focus,.mdtest-wb-shell .widget-int-text input:focus{border-color:#5b8db8!important;box-shadow:0 0 0 2px rgba(28,90,141,.10)!important}
.mdtest-primary-btn button{background:var(--md-brand2)!important;border-color:var(--md-brand2)!important;color:white!important;border-radius:8px!important;font-weight:700!important;box-shadow:0 1px 2px rgba(16,24,40,.08)}.mdtest-primary-btn button:hover{background:#164a75!important}.mdtest-run-btn button{background:var(--md-accent)!important;border-color:var(--md-accent)!important;color:white!important;border-radius:8px!important;font-weight:750!important;box-shadow:0 1px 2px rgba(16,24,40,.08)}.mdtest-run-btn button:hover{background:#056b5d!important}.mdtest-secondary-btn button{background:#fff!important;border:1px solid #b8c2cf!important;color:#344054!important;border-radius:8px!important;font-weight:650!important}.mdtest-secondary-btn button:hover{background:#f8fafc!important}.mdtest-secondary-btn button:disabled{opacity:.52!important}
.mdtest-mode-selector .widget-toggle-button{border-color:#cfd7e3!important;background:#fff!important;color:#475467!important;font-weight:650!important}.mdtest-mode-selector .widget-toggle-button.mod-active{background:#eaf2f8!important;color:var(--md-brand)!important;border-color:#7ca6c8!important;box-shadow:inset 0 0 0 1px #7ca6c8!important}
.mdtest-advanced{border:1px solid #e5e9ef!important;border-radius:9px!important;overflow:hidden;margin-top:10px}.mdtest-advanced .p-Accordion-header{background:#f8fafc!important}.mdtest-advanced-group{border:1px solid #edf0f4;border-radius:9px;padding:10px;background:#fbfcfd;min-width:250px;flex:1}.mdtest-advanced-group-title{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#667085;font-weight:750;margin-bottom:7px}
.mdtest-output{border:0!important;padding:0!important;margin-top:8px!important;background:transparent!important}.mdtest-export-row{padding:10px 12px;border-radius:9px;background:#f8fafc;border:1px solid #edf0f4}
@media(max-width:760px){.mdtest-productbar{align-items:flex-start}.mdtest-productmeta{display:none}.mdtest-workflow{grid-template-columns:1fr}.mdtest-card-body{padding:12px}.mdtest-wb-hero{padding:18px}.mdtest-wb-shell{max-width:100%}}
</style>
""")

        self.title = w.HTML(
            f"<div class='mdtest-productbar'><div class='mdtest-brand'><div class='mdtest-mark'>M</div>"
            f"<div><div class='mdtest-brandname'>MDTest</div><span class='mdtest-brandtag'>Stationarity-aware MD time-series analysis</span></div></div>"
            f"<div class='mdtest-productmeta'><span class='mdtest-chip'>v{__version__}</span>"
            f"<span class='mdtest-chip mdtest-chip-accent'>Presentation layer &middot; frozen inference core</span></div></div>"
            "<div class='mdtest-wb-hero'><div class='mdtest-wb-eyebrow'>Scientific analysis workspace</div>"
            "<h2>Workbench</h2><p>Choose a scalar molecular-dynamics observable, run the audited MDTest workflow, "
            "inspect stationarity and correlation diagnostics, and export a reproducible report from one workspace.</p></div>"
        )
        self.workflow = w.HTML(
            "<div class='mdtest-workflow'>"
            "<div class='mdtest-workflow-step'><b>1</b>Data &amp; observable</div>"
            "<div class='mdtest-workflow-step'><b>2</b>Analysis protocol</div>"
            "<div class='mdtest-workflow-step'><b>3</b>Results &amp; report</div>"
            "</div>"
        )

        common_style = {"description_width": "100px"}
        wide_style = {"description_width": "88px"}
        self.file_path = w.Text(description="File path", placeholder="trajectory.csv", layout=w.Layout(width="100%"), style=common_style)
        self.upload = w.FileUpload(accept=".csv,.txt,.dat,.tsv", multiple=False, description="Choose file", layout=w.Layout(width="190px"))
        self.clear_upload_button = w.Button(description="Clear", icon="times", tooltip="Allow another upload, including the same filename", layout=w.Layout(width="82px"))
        self.upload_status = w.HTML("<div class='mdtest-wb-help'>Choose a file above. MDTest will confirm its name and load the columns automatically.</div>")
        self.workspace_files = w.Dropdown(options=[("Select a file from the Jupyter workspace", "")], description="Local file", style=common_style, layout=w.Layout(width="100%"))
        self.refresh_files_button = w.Button(description="Refresh list", icon="refresh", tooltip="Include files uploaded through the JupyterLab left file browser", layout=w.Layout(width="140px"))
        self.delim = w.Dropdown(options=[("Comma / CSV", "comma"), ("Whitespace", "space"), ("Tab", "tab")], value="comma", description="Delimiter", style=wide_style, layout=w.Layout(width="260px"))
        self.drop_nan = w.Checkbox(value=False, description="Drop NaN/bad rows after inspection", indent=False, layout=w.Layout(width="260px"))
        self.load_button = w.Button(description="Load columns", icon="folder-open", layout=w.Layout(width="150px", height="36px"))
        self.load_button.add_class("mdtest-primary-btn")
        self.observable = w.Dropdown(options=[], description="Observable", layout=w.Layout(width="100%"), style=common_style)
        self.load_status = w.HTML("<div class='mdtest-status'><span class='mdtest-dot'></span><div><b>No data loaded.</b> Choose a path or upload a file, then load columns.</div></div>")
        self.source_hint = w.HTML("<div class='mdtest-securityline'><span class='mdtest-lock'>&#9632;</span><span>The analyzed source is content-hashed. If both path and upload are populated, the most recently edited source is used and identified explicitly.</span></div>")

        self.mode = w.ToggleButtons(
            options=[("Auto compare", "auto-compare"), ("Auto safe", "auto-safe"), ("ESS/IACT only", "ess"), ("Manual", "manual")],
            value="auto-compare", description="", layout=w.Layout(width="100%")
        )
        self.mode.add_class("mdtest-mode-selector")
        self.mode_help = w.HTML("")
        self.alpha = w.FloatText(value=0.05, description="alpha", style=wide_style, layout=w.Layout(width="245px"))
        self.min_blocks = w.IntText(value=24, description="min blocks", style=wide_style, layout=w.Layout(width="245px"))
        self.trend_grid = w.Text(value="2,5,10,20,40", description="trend m grid", style=common_style, layout=w.Layout(width="100%"))
        self.corr_grid = w.Text(value="5,10,20,30,40,60,80,120,160,240,320,480", description="report m grid", style=common_style, layout=w.Layout(width="100%"))
        self.stride = w.Text(value="", description="SW stride", placeholder="auto", style=wide_style, layout=w.Layout(width="245px"))
        self.ess_stride = w.Text(value="", description="ESS stride", placeholder="inherit SW stride", style=wide_style, layout=w.Layout(width="245px"))
        self.ess_min_lag = w.IntText(value=3, description="ESS min lag", style=wide_style, layout=w.Layout(width="245px"))
        self.ess_max_lag = w.Text(value="", description="ESS max lag", placeholder="auto", style=wide_style, layout=w.Layout(width="245px"))
        self.manual_ts = w.FloatText(value=0.0, description="manual ts", style=wide_style, layout=w.Layout(width="245px"))
        self.manual_m = w.IntText(value=10, description="manual m", style=wide_style, layout=w.Layout(width="245px"))
        self.manual_n = w.Text(value="max", description="manual n", style=wide_style, layout=w.Layout(width="245px"))
        self.explanation_level = w.Dropdown(options=[("Minimal", "minimal"), ("Guided", "guided"), ("Technical", "technical")], value="guided", description="Explanation", style=common_style, layout=w.Layout(width="290px"))
        self.show_figures = w.Checkbox(value=True, description="Show diagnostic figures", indent=False, layout=w.Layout(width="220px"))
        self.run_button = w.Button(description="Run analysis", icon="play", layout=w.Layout(width="150px", height="38px"))
        self.run_button.add_class("mdtest-run-btn")
        self.export_dir = w.Text(value="results/workbench", description="Report folder", layout=w.Layout(width="100%"), style=common_style)
        self.export_button = w.Button(description="Export report", icon="save", disabled=True, layout=w.Layout(width="150px", height="38px"))
        self.export_button.add_class("mdtest-secondary-btn")
        self.status = w.HTML("")
        self.output = w.Output(layout=w.Layout(width="100%"))
        self.output.add_class("mdtest-output")

        shared_group = w.VBox([
            w.HTML("<div class='mdtest-advanced-group-title'>Shared / stationarity</div>"),
            self.alpha, self.min_blocks, self.trend_grid, self.corr_grid, self.stride,
        ])
        shared_group.add_class("mdtest-advanced-group")
        ess_group = w.VBox([
            w.HTML("<div class='mdtest-advanced-group-title'>ESS / IACT</div>"),
            self.ess_stride, self.ess_min_lag, self.ess_max_lag,
        ])
        ess_group.add_class("mdtest-advanced-group")
        manual_group = w.VBox([
            w.HTML("<div class='mdtest-advanced-group-title'>Manual mode</div>"),
            self.manual_ts, self.manual_m, self.manual_n,
        ])
        manual_group.add_class("mdtest-advanced-group")
        advanced = w.HBox([shared_group, ess_group, manual_group], layout=w.Layout(gap="10px", align_items="stretch", flex_flow="row wrap"))
        self.advanced = w.Accordion(children=[advanced], titles=("Advanced settings",), selected_index=None)
        self.advanced.add_class("mdtest-advanced")

        self.load_button.on_click(self._on_load)
        self.run_button.on_click(self._on_run)
        self.export_button.on_click(self._on_export)
        self.file_path.observe(self._on_path_changed, names="value")
        self.upload.observe(self._on_upload_changed, names="value")
        self.clear_upload_button.on_click(self._on_clear_upload)
        self.refresh_files_button.on_click(self._on_refresh_files)
        self.workspace_files.observe(self._on_workspace_selected, names="value")
        self._refresh_workspace_files()
        for control in (self.delim, self.drop_nan):
            control.observe(self._on_source_option_changed, names="value")
        for control in (self.observable, self.mode, self.alpha, self.min_blocks, self.trend_grid, self.corr_grid,
                        self.stride, self.ess_stride, self.ess_min_lag, self.ess_max_lag,
                        self.manual_ts, self.manual_m, self.manual_n):
            control.observe(self._on_analysis_changed, names="value")
        self.mode.observe(self._on_mode_changed, names="value")
        self._update_mode_controls()

        source_row = w.HBox([self.upload, self.clear_upload_button], layout=w.Layout(width="100%", gap="10px", align_items="center", flex_flow="row wrap"))
        local_row = w.HBox([self.workspace_files, self.refresh_files_button], layout=w.Layout(width="100%", gap="10px", align_items="center", flex_flow="row wrap"))
        parse_row = w.HBox([self.delim, self.drop_nan, self.load_button], layout=w.Layout(gap="10px", align_items="center", flex_flow="row wrap"))
        input_body = w.VBox([
            w.HTML("<div class='mdtest-subhead'>Option A &middot; Choose a file on this computer</div>"), source_row, self.upload_status,
            w.HTML("<div class='mdtest-subhead'>Option B &middot; File already in JupyterLab</div>"), local_row,
            w.HTML("<div class='mdtest-subhead'>Option C &middot; Enter a file path</div>"), self.file_path, self.source_hint,
            w.HTML("<div class='mdtest-divider'></div><div class='mdtest-subhead'>Parsing &amp; observable</div>"),
            parse_row, self.observable, self.load_status,
        ])
        input_body.add_class("mdtest-card-body")
        input_card = w.VBox([
            w.HTML("<div class='mdtest-card-head'><span class='mdtest-stepnum'>01</span><div><h3>Choose data</h3><p>Select the exact analyzed bytes and confirm the physical observable before statistical interpretation.</p></div></div>"),
            input_body,
        ])
        input_card.add_class("mdtest-card")

        analysis_body = w.VBox([self.mode, self.mode_help, self.advanced])
        analysis_body.add_class("mdtest-card-body")
        analysis_card = w.VBox([
            w.HTML("<div class='mdtest-card-head'><span class='mdtest-stepnum'>02</span><div><h3>Choose analysis</h3><p>Auto compare is the recommended default; each protocol remains independently accessible.</p></div></div>"),
            analysis_body,
        ])
        analysis_card.add_class("mdtest-card")

        run_options = w.HBox([self.explanation_level, self.show_figures], layout=w.Layout(gap="14px", align_items="center", flex_flow="row wrap"))
        run_actions = w.HBox([self.run_button, self.export_button], layout=w.Layout(gap="9px", align_items="center"))
        export_box = w.VBox([self.export_dir, w.HTML("<div class='mdtest-actionnote'>Export is enabled only for a successful result that still matches the current source and analysis controls.</div>")])
        export_box.add_class("mdtest-export-row")
        result_body = w.VBox([run_options, run_actions, export_box, self.status, self.output])
        result_body.add_class("mdtest-card-body")
        result_card = w.VBox([
            w.HTML("<div class='mdtest-card-head'><span class='mdtest-stepnum'>03</span><div><h3>Run, interpret, and export</h3><p>Numerical results, explanation, diagnostics, and provenance are rendered from the same structured result object.</p></div></div>"),
            result_body,
        ])
        result_card.add_class("mdtest-card")

        self.footer = w.HTML(
            f"<div class='mdtest-footer'><span>MDTest {__version__}</span>"
            "<span>One computational engine &middot; Python API &middot; CLI &middot; Jupyter Workbench</span></div>"
        )
        self.widget = w.VBox([css, self.title, self.workflow, input_card, analysis_card, result_card, self.footer], layout=w.Layout(width="100%"))
        self.widget.add_class("mdtest-wb-shell")

    @staticmethod
    def _upload_item(upload_value):
        """Normalize both ipywidgets 7 dict and ipywidgets 8 tuple uploads."""
        if not upload_value:
            return None
        if isinstance(upload_value, dict):
            if "content" in upload_value:
                return upload_value
            name, value = next(iter(upload_value.items()))
            if isinstance(value, dict) and "name" not in value:
                return {**value, "name": str(name)}
            return value
        return next(iter(upload_value))

    def _upload_payload(self) -> tuple[str, bytes, str]:
        item = self._upload_item(self.upload.value)
        if item is None:
            raise ValueError("No uploaded file is currently selected.")
        if isinstance(item, dict):
            name, content = item.get("name", "uploaded_data.csv"), item.get("content")
        else:
            name, content = getattr(item, "name", "uploaded_data.csv"), getattr(item, "content", None)
        if content is None:
            raise ValueError("The browser did not transfer file data. Try the JupyterLab file-browser upload and choose the file from 'Local file'.")
        if hasattr(content, "tobytes"):
            content = content.tobytes()
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError("The uploaded file has an unsupported data format. Use the JupyterLab file browser as an alternative.")
        data = bytes(content)
        if not data:
            raise ValueError("The selected file is empty. Choose a data file with a time column and at least one observable.")
        filename = Path(str(name).replace("\\", "/")).name or "uploaded_data.csv"
        digest = hashlib.sha256(data).hexdigest()
        return filename, data, digest

    def _refresh_workspace_files(self):
        files = list_workspace_files()
        self.workspace_files.options = [("Select a file from the Jupyter workspace", ""), *files]

    def _on_refresh_files(self, _button=None):
        self._refresh_workspace_files()
        if not self.workspace_files.options or len(self.workspace_files.options) == 1:
            self.upload_status.value = "<div class='mdtest-wb-help'>No data files were found in the workspace folders. Upload through JupyterLab's left file browser, then select Refresh list.</div>"

    def _on_workspace_selected(self, change=None):
        chosen = str((change or {}).get("new", getattr(self.workspace_files, "value", "")) or "")
        if not chosen:
            return
        self.file_path.value = chosen
        self._active_source_kind = "path"
        self._on_load()

    def _on_clear_upload(self, _button=None):
        # ipywidgets 8 uses a tuple and ipywidgets 7 uses a mapping.
        self.upload.value = {} if isinstance(self.upload.value, dict) else ()
        self.upload_status.value = "<div class='mdtest-wb-help'>Upload cleared. You can choose the same filename again.</div>"

    def _effective_source_kind(self) -> str:
        path_present = bool(str(self.file_path.value).strip())
        upload_present = bool(self.upload.value)
        if self._active_source_kind == "path" and path_present:
            return "path"
        if self._active_source_kind == "upload" and upload_present:
            return "upload"
        if path_present and not upload_present:
            return "path"
        if upload_present and not path_present:
            return "upload"
        if path_present and upload_present:
            raise ValueError("Both a data-file path and an upload are present. Edit the source you intend to use, then click Load columns again.")
        raise ValueError("Provide a data-file path or upload a file.")

    def _resolve_file(self) -> str:
        kind = self._effective_source_kind()
        if kind == "upload":
            name, data, digest = self._upload_payload()
            path = Path(self._tmp.name) / f"{digest[:16]}__{name}"
            if not path.exists() or path.read_bytes() != data:
                path.write_bytes(data)
            return str(path)
        return str(self.file_path.value).strip()

    @staticmethod
    def _canonical_file(file: str | Path) -> str:
        return str(Path(file).expanduser().resolve())

    def _current_source_signature(self) -> tuple[Any, ...]:
        kind = self._effective_source_kind()
        file = self._resolve_file()
        canonical = self._canonical_file(file)
        digest = sha256_file(canonical)
        if digest is None:
            raise FileNotFoundError(f"Input file is unavailable: {canonical}")
        return (kind, canonical, digest, str(self.delim.value), bool(self.drop_nan.value))

    @staticmethod
    def _status_block(kind: str, title: str, detail: str = "") -> str:
        cls = {
            "ready": "mdtest-status-ready", "warn": "mdtest-status-warn",
            "error": "mdtest-status-error", "running": "mdtest-status-running",
        }.get(kind, "")
        detail_html = f"<div>{detail}</div>" if detail else ""
        return f"<div class='mdtest-status {cls}'><span class='mdtest-dot'></span><div><b>{title}</b>{detail_html}</div></div>"

    def _invalidate_result(self, message: str = "Analysis settings changed. Run MDTest again before exporting."):
        had_result = self.result is not None or self._completed_request is not None
        self.result = None
        self._completed_request = None
        self.export_button.disabled = True
        if had_result:
            self.status.value = self._status_block('warn', 'Result is out of date.', message)

    def _invalidate_loaded_source(self, message: str = "Data source changed. Click Load columns again before running analysis."):
        self.current_file = None
        self._loaded_source_signature = None
        self._invalidate_result(message)
        self.observable.options = []
        self.load_status.value = self._status_block('warn', 'Reload required.', message)
        try:
            with self.output:
                self.output.clear_output(wait=True)
        except Exception:
            pass

    def _on_path_changed(self, change=None):
        new = str((change or {}).get("new", getattr(self.file_path, "value", ""))).strip()
        if new:
            self._active_source_kind = "path"
        elif self._active_source_kind == "path":
            self._active_source_kind = "upload" if bool(self.upload.value) else None
        if self.current_file is not None or self._loaded_source_signature is not None:
            self._invalidate_loaded_source()

    def _on_upload_changed(self, change=None):
        new = (change or {}).get("new", getattr(self.upload, "value", None))
        if new:
            self._active_source_kind = "upload"
        elif self._active_source_kind == "upload":
            self._active_source_kind = "path" if str(self.file_path.value).strip() else None
        if self.current_file is not None or self._loaded_source_signature is not None:
            self._invalidate_loaded_source()
        if not new:
            self.upload_status.value = "<div class='mdtest-wb-help'>No file selected. Choose a file or use the workspace file list.</div>"
            return
        try:
            name, data, _digest = self._upload_payload()
            self.upload_status.value = self._status_block(
                'ready', 'File received.',
                f'{escape(name)} ({len(data):,} bytes). Loading columns automatically.')
            self._on_load()
            # _on_load communicates parsing errors via load_status.
        except Exception as exc:
            self.upload_status.value = self._status_block('error', 'Upload could not be read.', escape(str(exc)))

    def _on_source_option_changed(self, change=None):
        if self.current_file is not None or self._loaded_source_signature is not None:
            self._invalidate_loaded_source()

    def _on_analysis_changed(self, change=None):
        self._invalidate_result()

    def _on_mode_changed(self, change=None):
        self._update_mode_controls()

    def _update_mode_controls(self):
        mode = str(self.mode.value).strip().lower().replace("_", "-")
        is_manual = mode == "manual"
        uses_stationarity = mode in {"auto-safe", "auto", "auto-compare", "compare"}
        uses_ess = mode in {"ess", "iact", "ess-iact", "auto-compare", "compare"}
        self.alpha.disabled = mode in {"ess", "iact", "ess-iact"}
        for control in (self.trend_grid, self.corr_grid, self.stride):
            control.disabled = not uses_stationarity
        for control in (self.ess_stride, self.ess_min_lag, self.ess_max_lag):
            control.disabled = not uses_ess
        for control in (self.manual_ts, self.manual_m, self.manual_n):
            control.disabled = not is_manual
        help_text = {
            "auto-compare": "<b>Auto compare:</b> runs the multi-resolution MDTest stationarity screen and ESS/IACT scan side by side, then reports both starts and the conservative later start.",
            "compare": "<b>Auto compare:</b> runs the multi-resolution MDTest stationarity screen and ESS/IACT scan side by side, then reports both starts and the conservative later start.",
            "auto-safe": "<b>Auto safe:</b> runs the multi-resolution MDTest stationarity search and final block-level reporting diagnostics without the ESS comparator.",
            "auto": "<b>Auto safe:</b> runs the multi-resolution MDTest stationarity search and final block-level reporting diagnostics without the ESS comparator.",
            "ess": "<b>ESS/IACT only:</b> estimates correlation-related sampling efficiency and an ESS-optimized start. It does not by itself establish stationarity.",
            "iact": "<b>ESS/IACT only:</b> estimates correlation-related sampling efficiency and an ESS-optimized start. It does not by itself establish stationarity.",
            "ess-iact": "<b>ESS/IACT only:</b> estimates correlation-related sampling efficiency and an ESS-optimized start. It does not by itself establish stationarity.",
            "manual": "<b>Manual:</b> evaluates the four-test protocol at a start time and block length selected by the user.",
        }.get(mode, "")
        if hasattr(self, "mode_help"):
            self.mode_help.value = f"<div class='mdtest-wb-modehelp'>{help_text}</div>"

    def _on_load(self, _button=None):
        try:
            signature = self._current_source_signature()
            _kind, canonical, _digest, _delim, _drop_nan = signature
            info = list_observables(canonical, delim=self.delim.value, drop_nan=self.drop_nan.value)
            self.current_file = canonical
            self._loaded_source_signature = signature
            self.result = None
            self._completed_request = None
            self.export_button.disabled = True
            self.observable.options = [(f"{i}: {name}", i) for i, name in info["observables"]]
            if self.observable.options:
                self.observable.value = self.observable.options[0][1]
            source_label = "uploaded snapshot" if signature[0] == "upload" else "path"
            self.load_status.value = (
                self._status_block('ready', f'Loaded {source_label}.', f'<code>{escape(canonical)}</code><br>{loaded_message(info["n_rows"], info["titles"])}')
            )
            self.status.value = ""
        except Exception as exc:
            self.current_file = None
            self._loaded_source_signature = None
            self.result = None
            self._completed_request = None
            self.observable.options = []
            self.export_button.disabled = True
            self.load_status.value = self._status_block('error', 'Could not load data.', str(exc))

    def _request(self) -> WorkbenchRequest:
        if not self.current_file or self._loaded_source_signature is None or self.observable.value is None:
            raise ValueError("Load the data and choose an observable before running analysis.")
        try:
            current_signature = self._current_source_signature()
        except FileNotFoundError:
            self._invalidate_loaded_source("The previously loaded input is unavailable. Choose the source and load columns again.")
            raise
        if current_signature != self._loaded_source_signature:
            self._invalidate_loaded_source()
            raise ValueError("The data source, file contents, or parsing options changed after columns were loaded. Click Load columns again before running analysis.")

        mode = str(self.mode.value).strip().lower().replace("_", "-")
        kwargs: dict[str, Any] = {
            "file": self.current_file,
            "col": int(self.observable.value),
            "mode": mode,
            "delim": self.delim.value,
            "drop_nan": bool(self.drop_nan.value),
            "min_blocks": int(self.min_blocks.value),
        }
        if mode in {"manual", "auto-safe", "auto", "auto-compare", "compare"}:
            kwargs["alpha"] = float(self.alpha.value)
        if mode in {"auto-safe", "auto", "auto-compare", "compare"}:
            kwargs.update(
                m_trend_grid=self._parse_grid(self.trend_grid.value),
                m_corr_grid=self._parse_grid(self.corr_grid.value),
                stride_points=self._optional_int(self.stride.value),
            )
        if mode in {"ess", "iact", "ess-iact", "auto-compare", "compare"}:
            kwargs.update(
                ess_stride_points=self._optional_int(self.ess_stride.value),
                ess_min_lag=int(self.ess_min_lag.value),
                ess_max_lag=self._optional_int(self.ess_max_lag.value),
            )
        if mode == "manual":
            n_text = self.manual_n.value.strip()
            n_value: Optional[int | str] = "max" if n_text.lower() in {"", "max", "auto", "none"} else int(n_text)
            kwargs.update(
                manual_ts=float(self.manual_ts.value),
                manual_m=int(self.manual_m.value),
                manual_n=n_value,
            )
        return WorkbenchRequest(**kwargs)

    def _on_run(self, _button=None):
        self.status.value = self._status_block('running', 'Running analysis...', 'The numerical engine is evaluating the selected protocol.')
        self.export_button.disabled = True
        with self.output:
            self.output.clear_output(wait=True)
        try:
            req = self._request()
            result = run_request(req)
            self.result = result
            self._completed_request = req
            self.status.value = self._status_block('ready', 'Analysis complete.', completion_message(self.result))
            with self.output:
                display_result(self.result, level=self.explanation_level.value, include_figures=self.show_figures.value)
            self.export_button.disabled = False
        except Exception as exc:
            self.result = None
            self._completed_request = None
            self.status.value = self._status_block('error', 'Analysis could not be completed.', str(exc))

    def _on_export(self, _button=None):
        if self.result is None or self._completed_request is None:
            return
        try:
            current_req = self._request()
            if current_req != self._completed_request:
                self._invalidate_result()
                raise ValueError("Analysis controls changed after the last run. Run MDTest again before exporting.")
            exported = export_guided_report(self.result, self.export_dir.value.strip() or "results/workbench",
                                            prefix="mdtest_workbench", level=self.explanation_level.value,
                                            include_figures=True)
            self.status.value = self._status_block('ready', 'Report exported.', f"<code>{exported['html']}</code>")
        except Exception as exc:
            self.status.value = self._status_block('error', 'Export failed.', str(exc))


def launch():
    """Create and display the interactive Jupyter Workbench; return its controller."""
    wb = MDTestWorkbench()
    wb._display(wb.widget)
    return wb
