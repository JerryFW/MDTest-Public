> **New to Python?** Start with `START_HERE.html` in the repository root. On Windows double-click `START_MDTEST_WINDOWS.bat`; on macOS double-click `START_MDTEST_MAC.command`; on Linux run `bash START_MDTEST_LINUX.sh`. These prepare a private installation automatically. Do not manually link `src` or start the notebook from an unrelated Python environment.

# MDTest Workbench guide

MDTest 2.2.0.dev7 presents the final polished notebook-first user interface **above the frozen Round-2A.1 computational engine**. The Workbench does not contain its own statistical formulas. It gathers user choices, calls the public `mdtest.api` functions, and then renders the returned structured result.

## Install

Base package:

```bash
pip install .
```

Interactive Jupyter Workbench:

```bash
pip install ".[workbench]"
```

For a full local Jupyter environment:

```bash
pip install ".[notebook]"
```

## Launch from Jupyter

Open `MDTestWorkbench.ipynb`, or use:

```python
from mdtest.workbench import launch
workbench = launch()
```

The Workbench is designed for a user who does not want to write Python code. The normal flow is:

1. Choose **Choose file** to transfer a CSV/text file from your computer. The Workbench displays the filename and byte count and then loads columns automatically. If this browser widget does not receive the file, upload it with JupyterLab's **left file browser** (its Upload Files button), click **Refresh list**, and choose it under **Local file**. You may also enter an absolute or relative **File path** and click **Load columns**. If both path and upload are populated, the most recently edited control is effective.
2. Verify the effective source and selected observable. A new successful file selection loads columns without an extra click;
3. if the source bytes, delimiter, or NaN-handling setting changes, load the columns again before analysis;
4. choose an analysis mode;
5. optionally expand **Advanced settings**;
6. click **Run analysis**;
7. inspect the dashboard, explanations, and plots;
8. export a reproducibility bundle if desired.

## Product-style workspace

The final Workbench is intentionally organized like a small scientific application rather than a collection of independent notebook widgets. A branded header and three-step workflow rail lead into separate **Data**, **Analysis**, and **Results** cards. Primary and secondary actions, mode guidance, advanced settings, status feedback, and report export use one consistent visual system. The notebook result surface embeds metrics, interpretation, diagnostic figures, references, and reproducibility metadata in one dashboard. The visual redesign changes presentation only; it does not alter a request sent to the public API or a returned result.

## Modes

- **Auto compare**: recommended comparison of multi-resolution MDTest and ESS/IACT. Both starts are displayed separately; the current conservative combined start is also displayed.
- **Auto safe**: multi-resolution MDTest stationarity search without the ESS comparator.
- **ESS/IACT only**: correlation/sampling-efficiency analysis. The interface explicitly reminds the user that this is not a stationarity test.
- **Manual**: evaluate the four-test protocol at a user-selected production start and block length.

## Explanation levels

- **Minimal**: verdicts only.
- **Guided**: short chemist-friendly explanations and why each diagnostic matters.
- **Technical**: includes the guided interpretation plus recorded inference settings, test statistics, p-values, significance level, selected ESS start information, and ESS scan controls already stored in the structured result. It does not recompute inference.

The educational text is generated from `mdtest.education`; it does not alter any pass/fail result.

## Diagnostic visualizations

Depending on the selected mode, the Workbench can show:

- raw trajectory with non-duplicated MDTest, ESS, and/or reported-start markers;
- multi-resolution mean-trend and dispersion-trend p-value maps with the selected MDTest start marked;
- ESS candidate-start curves for `Neff` and statistical inefficiency `g`;
- selected block means with the reported mean overlaid;
- final four-test p-values with the alpha threshold and explicit pass/attention labels.

These plots consume frozen result objects and frozen parsing/block helpers. They do not define new statistical rules.

## Export

The Workbench **Export report** action writes a small reproducibility bundle:

- structured result JSON;
- plain-text guided report;
- self-contained HTML guided report with diagnostic PNGs embedded directly in the HTML;
- separate PNG diagnostic figures for convenient reuse.

The result JSON retains engine-generated settings and provenance, including input SHA-256. Before raw trajectory or block-mean plots reread a source file, the presentation layer verifies that the current SHA-256 still matches the analyzed input. Changed/missing source bytes fail clearly. Changing an inference control after a run disables Export until MDTest is rerun.

## Programmatic use without widgets

The Workbench controller is separately testable:

```python
from mdtest.workbench import WorkbenchRequest, run_request

req = WorkbenchRequest(
    file="trajectory.csv",
    col=1,
    mode="auto-compare",
)
result = run_request(req)
```

`run_request` dispatches to the same public API used by CLI and ordinary Python users.

## Upload troubleshooting

If you select a file but see no **File received** message, the notebook/browser FileUpload widget has not delivered its data to Python. This can depend on the Jupyter frontend, browser, or upload size. **You do not need to reinstall MDTest.** Use JupyterLab's left file browser to upload the file into the MDTest folder; then choose **Refresh list** and select it under **Local file**. This alternative does not use the `ipywidgets.FileUpload` transfer channel. Files already in `data/`, `uploads/`, or `examples/data/` are listed too. If the file is elsewhere on disk, enter its full path under **File path** and click **Load columns**. Use **Clear** before selecting the same filename again.


## Workbench versus the Python tutorial

Open **`MDTestWorkbench.ipynb`** for day-to-day analysis using graphical controls.
The optional **`tutorials/MDTest_Tutorial.ipynb`** demonstrates the public Python API in worked examples for users who want to learn how the calculations are called. Start the launcher, browse to the `tutorials` folder in JupyterLab, and run the tutorial there. The startup cell handles example-data paths automatically.
