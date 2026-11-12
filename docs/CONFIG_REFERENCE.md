# MDTest configuration-file reference

Configuration files begin with the exact first line `MD Test Format`, followed by `key-value` entries. Existing underscore-style keys remain supported. Round 2A no longer silently ignores recognized analysis controls.

## Common keys

`mode`, `file`, `delim`, `col`, `alpha`, `min_blocks`, `outdir`, `prefix`, `drop_nan`, `no_plots`.

## Manual mode

`ts`, `m`, `n`.

## Auto-safe mode

`m_trend_grid`, `m_corr_grid`, `stride_points`.

## Auto-compare mode

All auto-safe keys plus `ess_stride_points`, `ess_min_lag`, `ess_max_lag`.

## Sensitivity mode

`ts`, `m_values`.

Boolean values accept `1`, `true`, `yes`, `y`, or `on` (case-insensitive) for true. Unknown keys now raise an error instead of being silently discarded. Keys that do not belong to the selected mode are forwarded to the normal CLI parser, which reports them as invalid for that mode.

Example:

```text
MD Test Format
mode-auto-compare
file-examples/data/synthetic_variance_relaxation_independent.csv
delim-comma
col-1
alpha-0.05
min_blocks-24
m_trend_grid-2,5,10,20,40
m_corr_grid-10,20,40,80,160,320
stride_points-133
ess_stride_points-133
ess_min_lag-3
ess_max_lag-500
drop_nan-false
outdir-results/example
prefix-example
```


## Dev9 input integrity

Files with all-numeric first rows are interpreted as headerless, including duplicate scientific-notation values. A first record containing a numeric time and a missing or nonnumeric observable is ambiguous and raises an error rather than silently discarding that sample. Add an explicit textual header (for example `time,value`) or inspect and repair the first record. The existing `drop_nan` option applies to data rows after the header policy is established.

The benchmark comparison reporter now fails if a recognized saved case lacks its original source data. For intentional partial reports, pass `--keep-going`; the reporter then writes `report_completeness.json` with `complete: false` and details of skipped cases. Saved source hashes, including nested Manual-result hashes, are verified.
