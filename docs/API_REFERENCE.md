# Public Python API reference

MDTest intentionally exposes a small programmatic interface. These functions accept ordinary Python values and return structured dataclass results; command-line parsing is not required. The CLI, configuration-file mode, and Jupyter Workbench call the same public API rather than reimplementing the statistical procedures.

For a short introduction, see `docs/PYTHON_INTERFACE.md`. For full scientific background and worked examples, see `docs/MDTest_User_Manual.pdf`.

## Common conventions

| Parameter | Meaning |
|---|---|
| `file` | Path to the scalar time-series table. Column 0 is the time/step coordinate. |
| `col` | Observable-column index; must be at least 1. |
| `delim` | Input delimiter policy: normally `"comma"`, `"space"`, or `"tab"`. Files ending in `.csv` are read as comma-delimited by the frozen loader. |
| `drop_nan` | When `True`, allow rows containing missing/non-finite values to be dropped with warnings. The loader also removes up to three metadata-like nonnumeric/incomplete rows with a warning even when this is `False`; see the User Manual. |
| `alpha` | Significance level used by MDTest diagnostics, default 0.05. |
| `min_blocks` | Minimum number of complete block samples required for MDTest block diagnostics, default 24. |
| `outdir` | Output directory used only when an API call is asked to write files. |
| `prefix` | Optional filename prefix for written outputs. |
| `write_outputs` | When `True`, write the result/report files supported by that mode. API calls otherwise return objects without writing by default. |
| `make_plots` | When `True`, generate diagnostic plots for modes that support them. |
| `display_plots` | When `True`, permit interactive display in addition to file generation. Normally `False` for batch/notebook-safe operation. |

Integer-valued parameters are validated before conversion. Fractional values such as `m=10.9` raise `ValueError` instead of being silently truncated.

## `mdtest.manual(...) -> ManualResult`

```python
mdtest.manual(
    file, *, col=1, ts=0.0, m, n=None, delim="comma", alpha=0.05,
    min_blocks=24, drop_nan=False, outdir="results", prefix=None,
    write_outputs=False, make_plots=False, display_plots=False,
)
```

Evaluate the complete four-test MDTest protocol at a user-selected production start and block size.

Additional parameters:

- `ts`: requested physical start time. MDTest maps this to the first retained sample at or after that time.
- `m`: block length in stored samples; required.
- `n`: number of complete blocks. `None`, `"max"`, `"auto"`, or `"none"` uses all available complete blocks.

Important returned fields (`ManualResult`):

- `ts`, `start_index`, `m`, `n`: actual retained window/blocking used;
- `mean`, `se`, `ci_low`, `ci_high`: block-mean estimate and Student-t uncertainty summary;
- `tests`: mapping of the four diagnostics to `TestOutcome` objects (`statistic`, `p_value`, `passed`, `note`);
- `overall_pass`: `True` only when the complete four-test protocol passes at this reporting scale;
- `recommendation`: human-readable engine recommendation;
- `settings`, `provenance`: recorded inference settings and software/input provenance.

Example:

```python
r = mdtest.manual("trajectory.csv", col=1, ts=600000, m=30, n="max")
print(r.overall_pass, r.mean, r.se)
```

## `mdtest.auto_safe(...) -> AutoSafeResult`

```python
mdtest.auto_safe(
    file, *, col=1, delim="comma", alpha=0.05, min_blocks=24,
    m_trend_grid=None, m_corr_grid=None, stride_points=None,
    drop_nan=False, outdir="results", prefix=None,
    write_outputs=False, make_plots=False, display_plots=False,
)
```

Run the multi-resolution MDTest stationarity search, then select a reporting block size.

Additional parameters:

- `m_trend_grid`: diagnostic block sizes used for the multi-resolution mean/dispersion trend screen. Default: `[2, 5, 10, 20, 40]`.
- `m_corr_grid`: candidate reporting block sizes. Default: `[5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480]`.
- `stride_points`: spacing in raw samples between candidate starts. `None` uses the frozen automatic stride.

Important returned fields (`AutoSafeResult`):

- `selected_ts_sw`, `selected_start_index_sw`: earliest scan-grid start passing the mean- and dispersion-trend tests at every diagnostic block size;
- `selected_m_corr`, `selected_n_corr`: first feasible reporting block size/count for which the complete four-test protocol passes;
- `manual_result`: the corresponding `ManualResult` at the selected reporting scale, or `None` if no reporting scale passes;
- `trend_table`: evaluated candidate-start p-value records. The search stops at the earliest passing start, so this table covers the evaluated prefix through that candidate, not every later admissible start;
- `status`, `note`, `settings`, `provenance`: structured status/metadata.

Example:

```python
r = mdtest.auto_safe("trajectory.csv", col=1)
print(r.selected_ts_sw, r.selected_m_corr)
```

## `mdtest.ess(...) -> ESSResult`

```python
mdtest.ess(
    file, *, col=1, delim="comma", drop_nan=False, min_blocks=24,
    scan_stride_points=None, min_lag=3, max_lag=None,
)
```

Run only the ESS/IACT candidate-start comparator. This is a correlation/sampling-efficiency analysis; by itself it is not a stationarity test.

Additional parameters:

- `scan_stride_points`: spacing between ESS candidate starts; `None` uses the frozen automatic stride;
- `min_lag`: earliest lag after which the first non-positive autocorrelation can terminate the finite-lag sum;
- `max_lag`: optional hard maximum lag for autocorrelation integration.

Important returned fields (`ESSResult`):

- `selected_ts_ess`, `selected_start_index_ess`: start maximizing retained effective samples;
- `selected_g`: statistical inefficiency at that start;
- `selected_neff`: effective sample size at that start;
- `scan_table`: candidate-start ESS/IACT records;
- `note`, `settings`, `provenance`: status/metadata.

## `mdtest.auto_compare(...) -> AutoCompareResult`

```python
mdtest.auto_compare(
    file, *, col=1, delim="comma", alpha=0.05, min_blocks=24,
    m_trend_grid=None, m_corr_grid=None, stride_points=None,
    ess_stride_points=None, ess_min_lag=3, ess_max_lag=None,
    drop_nan=False, outdir="results", prefix=None,
    write_outputs=False, make_plots=False, display_plots=False,
)
```

Run MDTest stationarity screening and the ESS/IACT comparator side by side, then report the conservative combined start.

Additional parameters combine the `auto_safe` and `ess` controls. When `ess_stride_points` is `None`, it inherits `stride_points`.

**Result nesting matters.** `AutoCompareResult` contains the component results under `.auto_safe` and `.ess`. The separate start values are therefore accessed as:

```python
r = mdtest.auto_compare("trajectory.csv", col=1)
print(r.auto_safe.selected_ts_sw)
print(r.ess.selected_ts_ess)
print(r.selected_ts_star)
```

Important returned fields (`AutoCompareResult`):

- `auto_safe`: complete `AutoSafeResult`;
- `ess`: complete `ESSResult`;
- `selected_ts_star`, `selected_start_index_star`: conservative combined start, `max(SW, ESS)` when both are available;
- `selected_m_corr_star`, `selected_n_corr_star`: reporting block size/count for the combined retained suffix;
- `manual_result_star`: complete `ManualResult` at the combined start/reporting scale when available;
- `status`, `note`, `settings`, `provenance`: structured status/metadata.

## `mdtest.sensitivity(...) -> dict`

```python
mdtest.sensitivity(
    file, *, col=1, ts=0.0, m_values=None, delim="comma", alpha=0.05,
    min_blocks=24, drop_nan=False, outdir="results", prefix=None,
    write_outputs=False,
)
```

Run the retained legacy sequential-search sensitivity diagnostic over a set of initial block lengths. This is not a Workbench mode and is retained mainly for historical/sensitivity analysis.

- `m_values`: initial block sizes to test; default `[2, 10, 20, 25, 30]`.
- Return value: a dictionary containing the requested grid, per-grid result rows, output paths, settings, and provenance.

## `mdtest.analyze(...)`

```python
mdtest.analyze(file, *, mode="auto-safe", **kwargs)
```

Convenience dispatcher. `mode` may be `"manual"`, `"auto-safe"`, `"auto-compare"`, `"ess"`, or `"sensitivity"`. Dedicated functions are preferred when explicit signatures or static type checking are important.

## `mdtest.make_benchmark_data(...) -> dict[str, str]`

```python
mdtest.make_benchmark_data(outdir="examples/data", *, n_points=100000, seed=20260627)
```

Generate the deterministic synthetic benchmark files used by the manuscript. `n_points` and `seed` are exact integer-valued parameters. The returned dictionary maps benchmark names to written file paths.

## Shared metadata classes

`RunSettings` records inference-controlling arguments actually used by a public call, including mode, column, delimiter, significance level, block grids, start/block controls, and ESS lag/stride controls where applicable.

`RunProvenance` records MDTest, Python, NumPy, SciPy, pandas, and Matplotlib versions plus the SHA-256 identity of the analyzed input file. These fields are descriptive metadata and do not alter statistical inference.

## Result-serialization note

Structured results are Python dataclasses (except the legacy sensitivity dictionary). Reporting/export utilities serialize these objects to JSON/text/HTML without changing the stored statistical decisions. Raw-data-dependent figure generation verifies the current input SHA-256 against the analyzed-file provenance before export.
