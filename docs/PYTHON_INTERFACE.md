# Programmatic Python interface

The public Python interface is intended for scientists using scripts or
Jupyter notebooks; it is not only a developer interface.

## Installation from a source checkout

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .
```

## Auto-safe

```python
import mdtest

result = mdtest.auto_safe(
    "examples/data/NarK_TimeSeriesData.csv",
    col=6,
    drop_nan=True,
    m_trend_grid=[2, 5, 10, 20, 40],
    m_corr_grid=[10, 20, 30, 40, 50, 60],
)

print(result.selected_ts_sw)
print(result.selected_m_corr)
print(result.status)
```

By default the programmatic interface returns a result without creating files.
Set `write_outputs=True` and `make_plots=True` when publication-style reports
and PNG files are desired.

## MDTest and ESS/IACT side by side

```python
result = mdtest.auto_compare(
    "examples/data/synthetic_variance_relaxation_independent.csv",
    col=1,
)

print(result.auto_safe.selected_ts_sw)
print(result.ess.selected_ts_ess)
print(result.selected_ts_star)
```

## ESS/IACT only

```python
ess = mdtest.ess("trajectory.csv", col=2)
print(ess.selected_g, ess.selected_neff)
```

## Generic dispatcher

```python
result = mdtest.analyze("trajectory.csv", mode="auto-safe", col=2)
```

Dedicated functions are preferred in reusable code because their signatures
are explicit and easier for editors and IDEs to inspect.


## Round 2A validation and provenance

Integer-valued arguments are validated before conversion. For example, `m=10.9` raises `ValueError` rather than silently becoming 10. Integer-valued NumPy scalars and values such as `10.0` are accepted.

Structured top-level results expose:

```python
result.settings
result.provenance
```

`settings` records the inference-controlling arguments actually used. `provenance` records the MDTest/Python/dependency versions and SHA-256 of the input file. These are descriptive records and do not enter the statistical calculations.

MDTest does not choose or override the Matplotlib backend when imported. Notebook/GUI or batch environments should use the normal Matplotlib mechanisms (for example `MPLBACKEND`) when a specific backend is desired.
