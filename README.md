# MDTest - Molecular Dynamics Time-Series Analysis

**Official public software version: 2.2.0.dev7.** This release retains the existing scientific methods and includes the audited maintenance and saved-reporting fixes.

> **Mac first-time users:** See [Mac installation guide](docs/MAC_START_GUIDE.html) and [Mac troubleshooting FAQ](docs/MAC_FAQ.html) for security prompts, executable permissions, Anaconda/Jupyter kernels, and Python 3.13/3.12 guidance. Gmail blocks ZIP attachments containing `.bat` files; share a GitHub Release download link instead.


> **FIRST-TIME USERS — START HERE:** Download and **extract the entire ZIP** (Windows: right-click the ZIP → **Extract All...**). Open the extracted `MDTest_2.2.0.dev7` folder and **double-click [`START_HERE.html`](START_HERE.html)**. It is the large-font visual guide. Do not open the notebook directly or run anything inside the ZIP preview. If you prefer reading on GitHub, this README provides the same starting instructions.

**For most users: no command-line installation is required.** Extract the ZIP and launch the guided Workbench using the file for your operating system. The launcher prepares a private Python environment (in a short user-local folder on Windows) and opens the notebook in JupyterLab.

| Your computer | Start MDTest |
| --- | --- |
| **Windows** | Double-click **`START_MDTEST_WINDOWS.bat`** |
| **macOS** | Double-click **`START_MDTEST_MAC.command`**, or `sh START_MDTEST_MAC.command` in Terminal |
| **Linux** | Open a terminal in the extracted folder and run **`bash START_MDTEST_LINUX.sh`** |

**First-run requirements:** Python **3.11+**, internet access for downloading dependencies, and an extracted (not ZIP-preview) folder. Python installer: <https://www.python.org/downloads/>. **No administrator rights are normally needed.** On **Windows**, installed packages are kept in a short, user-owned location (`%LOCALAPPDATA%\MDTest\e`) to avoid Windows long-path errors when installing JupyterLab. The extracted repository can remain under Downloads or be moved later; START updates the source link without moving JupyterLab. On macOS/Linux the private environment remains `.venv` beside the source. Later starts reuse the installation. The launcher does not modify system-wide Python or the scientific engine.

**Beginner instructions:** [START_HERE.html](START_HERE.html) (large-font browser guide), [full quick-start HTML](docs/START_HERE.html), [installation help HTML](docs/INSTALL_HELP.html), [Workbench guide HTML](docs/WORKBENCH_GUIDE.html), or [traditional User Manual (PDF)](docs/MDTest_User_Manual.pdf). The Markdown sources remain in `docs/` for GitHub readers.

**Want to see the software without installation?** Double-click `examples/workbench_demo/variance_relaxation_guided.html`. It is a saved report, not the live program.

> **If you see `No module named mdtest`:** Start the notebook using the START file, not by opening `.ipynb` directly from some other Jupyter environment. You do *not* need to link the `src` directory or set `PYTHONPATH`.

## What MDTest does

MDTest diagnoses whether scalar MD time series are compatible with stationarity and assesses statistical uncertainty from correlated sampling. It combines Schiferl-Wallace four-test diagnostics with multi-resolution start selection and optional ESS/IACT comparison. It does not prove global equilibration.

## First analysis in the browser

1. On the opened `MDTestWorkbench.ipynb`, click **Run → Run All Cells** to display the Workbench.
2. In **Local file**, select `examples/data/synthetic_variance_relaxation_independent.csv` (the columns load immediately). Alternatively choose **Choose file** to upload a CSV from your computer; the filename and byte count appear when received and columns load automatically. If the browser upload does not respond, use JupyterLab's left file browser to upload your CSV, then click **Refresh list** and select it from **Local file**.
3. Choose **Auto Compare** and click **Run analysis**.
4. Inspect stationarity/ESS starts, figures, and diagnostic interpretation. Then click **Export** to save a portable result.

For complex input or a scientific interpretation, consult the detailed manual. The START launcher is intentionally a thin installation/launch layer; it has **no statistical logic**.

## Advanced or server/HPC installation (optional)

From the folder containing `pyproject.toml`, users who prefer to manage Python themselves can run:

```bash
python -m pip install -e ".[notebook]"
python -m jupyterlab MDTestWorkbench.ipynb
```

Other interfaces (API, CLI, config) and documentation follow below. The package uses a normal `src/mdtest` layout and returns structured result objects. The scientific algorithms and established numerical results remain unchanged in this maintenance release.

## Python interface

A normal scientific Python user can call MDTest directly:

```python
import mdtest

result = mdtest.auto_safe(
    "examples/data/NarK_TimeSeriesData.csv",
    col=6,
    drop_nan=True,
    m_trend_grid=[2, 5, 10, 20, 40],
)

print(result.selected_ts_sw)
print(result.selected_m_corr)
print(result.status)
```

Programmatic calls return structured dataclass results and, by default, do
not create files. To write the usual reports and plots:

```python
result = mdtest.auto_compare(
    "examples/data/synthetic_variance_relaxation_independent.csv",
    col=1,
    write_outputs=True,
    make_plots=True,
    outdir="results/variance_compare",
)
```

ESS/IACT can also be run independently:

```python
ess = mdtest.ess("trajectory.csv", col=1)
print(ess.selected_g, ess.selected_neff)
```

See `docs/PYTHON_INTERFACE.md` for more examples.

## Jupyter Workbench

Open `MDTestWorkbench.ipynb` for the guided three-stage workflow:

```text
Choose data -> Choose analysis -> Run, interpret, and export
```

The Workbench supports Manual, Auto Safe, ESS/IACT-only, and Auto Compare
modes. It calls the same public Python API shown above; the widget layer does
not contain a second statistical implementation. See `docs/WORKBENCH_GUIDE.md`.

## Command-line interface

After installation:

```bash
mdtest auto-safe \
  --file examples/data/NarK_TimeSeriesData.csv \
  --delim comma --col 6 \
  --m-trend-grid 2,5,10,20,40 \
  --m-corr-grid 10,20,25,30,40,50,60 \
  --outdir results/nark_auto_safe
```

The historical source-checkout command remains valid:

```bash
python MDTest.py auto-safe ...
```

Other modes are `manual`, `auto-compare`, `sensitivity`, `make-data`, and
`config`.

## Two Jupyter notebooks: which one to open?

- **`MDTestWorkbench.ipynb`** (repository root): the normal **graphical Workbench** for chemists. Start here: no Python programming is required.
- **`tutorials/MDTest_Tutorial.ipynb`**: an **optional educational notebook** showing Python API commands, worked NarK/synthetic examples, and figures. Open the `tutorials` folder in JupyterLab. Its startup cell locates the repository data automatically, even when the notebook runs from `tutorials/`. It calls the same public engine directly, without `subprocess`.


Advanced users may also launch the Workbench programmatically from an existing configured notebook:

```python
from mdtest.workbench import launch
workbench = launch()
```

The Workbench supports acknowledged automatic file uploads, a local-workspace file selector, typed path input, observable selection, four analysis modes, collapsible advanced settings, result dashboards, contextual explanations, diagnostic plots, references, and report export. Loaded columns are bound to the exact source bytes (including SHA-256), source kind, delimiter, and NaN-handling setting. The most recently edited path/upload control is the effective source. Changing inference controls invalidates stale Export state, and raw-data plots verify current input bytes against analyzed provenance. The exported HTML report is self-contained. See `docs/WORKBENCH_GUIDE.md`.

A pre-generated end-user demonstration is included in `examples/workbench_demo/`; open `variance_relaxation_guided.html` to see the dashboard/report and the associated PNG diagnostics without launching Jupyter.

## What the diagnostics do

The core workflow contains:

- Mann-Kendall trend test on block means;
- Mann-Kendall trend test on block dispersion;
- Shapiro-Wilk normality check on block means;
- one-tailed von Neumann test for residual positive serial correlation;
- optional Chodera/PyMBAR-style ESS/IACT start-time comparison.

`auto-safe` searches candidate starts over a fixed grid of diagnostic block
sizes. `auto-compare` reports the stationarity and ESS starts separately and
also reports the current conservative combined start `max(start_SW,start_ESS)`.

## Output

CLI calls write JSON, text summaries, CSV scan tables, and PNG plots unless
`--no-plots` is specified. Batch modes do not open blocking Matplotlib windows.

The direct Python interface returns structured objects first; filesystem
outputs are opt-in with `write_outputs=True`.

## Testing and scientific regression

Quick CLI smoke test:

```bash
python testingScripts/smoke_test.py
```

Direct Python API tests after installation/editable installation:

```bash
python -m unittest discover -s tests -v
```

Manuscript-scale scientific regression:

```bash
python testingScripts/regression_round2.py
```

## Documentation

- `docs/MDTest_User_Manual.pdf` - traditional chemist-facing installation, theory, algorithms, usage, diagnostics, interpretation, and troubleshooting manual
- `docs/API_REFERENCE.md` - public Python functions, parameters, and structured result fields
- `docs/PYTHON_INTERFACE.md` - script/notebook usage
- `docs/WORKBENCH_GUIDE.md` - guided Jupyter Workbench workflow
- `docs/CONFIG_REFERENCE.md` - configuration-file keys and validation behavior
- `docs/ARCHITECTURE.md` - package structure and interface boundaries
- `docs/EDUCATIONAL_LAYER.md` - interpretation/reference design
- `docs/SCIENTIFIC_FREEZE.md` - audited statistical definitions and protected benchmark behavior
- `CHANGELOG.md` - version history

## License

MIT License; see `LICENSE`.

## Citation

If you use MDTest in academic work, please cite the associated manuscript:

*MDTest: stationarity-aware diagnostics and statistical-error assessment for
molecular-dynamics time series.*

See also `CITATION.cff`.

## Contact

Primary developer: Jerry F. Wang (`jerryf.w.1024@gmail.com`)

Project authors:
- Haobin Wang (`HAOBIN.WANG@ucdenver.edu`)
- Hai Lin (`Hai.Lin@ucdenver.edu`)

### Saved results across parser versions

Dev10 now verifies both the raw-file hash and the identity of the **cleaned,
ordered observations** when comparing saved MDTest results. Older saved results
without cleaned-data fingerprints undergo observable-label and saved-time/index
checks; if incompatible, rerun the analysis instead of reusing old indices.
Malformed `*_summary.json` files cause a reporting error by default; use
`--keep-going` only when an explicitly incomplete report is acceptable.
Mixed numeric/text first-record schemas are rejected rather than silently
assuming a header. Public Python APIs require a real Boolean for `drop_nan`.
The statistical methods and protected reference outputs are unchanged.


### Saved-result integrity

Saved comparison reports now reject invalid cutoff indices and mismatched time
pairs, including fractional scan indices and off-by-one legacy timestamps.
Malformed intended comparison summaries cause an error by default. Reports are
staged and published only after all required outputs are generated; earlier
reports are moved to `previous_reports/` on rerun. `report_completeness.json`
records `complete: false` on any failure or partial result.

Very old summaries with no raw-data checksum and no cleaned-data fingerprint
are rejected by default. To inspect these without claiming authentication, use
`testingScripts/mdtest_clear_benchmarks.py --allow-unverified-legacy` along with
the normal `--parse-existing`, `--data-root`, and `--outdir` options; the JSON
and human report explicitly flag such results. Regeneration from original raw
data is the preferred route. A checksum is an identity check, not a cryptographic
signature of scientific result contents.
