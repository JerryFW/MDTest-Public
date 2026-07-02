# MDTest

## Application Description
**MDTest** is a lightweight, standalone Python 3 program for post-processing scalar molecular dynamics (MD) time series. It is designed to provide statistically robust analysis while remaining accessible to both new and experienced users.
The automated analysis has been reorganized around
- a four-test manual diagnostic for a user-selected `(ts, m, n)`;
- a **multi-resolution stationarity** search (`auto-safe`) using a fixed grid of diagnostic block sizes;
- an optional **Chodera/PyMBAR-style ESS/IACT comparator** (`auto-compare`) and a conservative production start `max(ts_SW, ts_ESS)`;
- a legacy sensitivity diagnostic showing how the old sequential logic depends on the initial block size;
- designed synthetic data sets for the mathematical examples discussed in the manuscript.


The statistical analysis follows the four-test framework proposed by Schiferl and Wallace for diagnosing equilibration and correlation in MD-derived time series.  
This includes
- Two Mann--Kendall (MK) tests to check for lack of trend in mean and estimated standard error
- A normality test on coarse-grained (block-averaged) samples
- A one-tailed von Neumann test for positive serial correlation

Furthermore, in addition to statistical outputs, **MDTest** provides diagnostic plots to help users interpret results and visually confirm equilibriation. 

---


## Installation

Use Python 3.11+ when possible.

Requirements are installed by running
```bash
python -m venv .venv
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```


---

## Quick start

Interactive walkthrough mode (restored no-argument behavior):

```bash
python MDTest.py
```

The walkthrough prompts for the input file, observable column, run mode, and analysis parameters, then calls the same internal routines as the command-line modes.  Diagnostic plots are saved to PNG files; batch runs do not open blocking plot windows.

Manual four-test diagnostic:

```bash
python MDTest.py manual \
  --file examples/data/NarK_TimeSeriesData.csv \
  --delim comma --col 6 --ts 600000 --m 30 --n max \
  --outdir results/nark_manual
```

Multi-resolution stationarity search:

```bash
python MDTest.py auto-safe \
  --file examples/data/NarK_TimeSeriesData.csv \
  --delim comma --col 6 \
  --m-trend-grid 2,5,10,20,25 \
  --m-corr-grid 10,20,25,30,40,50,60 \
  --outdir results/nark_auto_safe
```

Auto-safe plus Chodera/PyMBAR-style ESS/IACT comparison:

```bash
python MDTest.py auto-compare \
  --file examples/data/synthetic_variance_relaxation_independent.csv \
  --delim comma --col 1 \
  --m-trend-grid 2,5,10,20,40 \
  --m-corr-grid 10,20,40,80,160,320 \
  --outdir results/variance_compare
```

Legacy sensitivity diagnostic:

```bash
python MDTest.py sensitivity \
  --file examples/data/NarK_TimeSeriesData.csv \
  --delim comma --col 6 --m-values 2,10,20,25,30 \
  --outdir results/nark_sensitivity
```

Generate designed synthetic data:

```bash
python MDTest.py make-data --outdir examples/data --n-points 100000
```

## Configuration-file mode

Configuration files begin with `MD Test Format` and then use `key-value` lines.

```bash
python MDTest.py config examples/configs/auto_compare_variance_relaxation.txt
```

The new parser accepts older spellings such as `run type-auto-sequential`, but maps them to the safer `auto-safe` implementation.  The original sequential logic is retained only through the explicit `sensitivity` mode.

## Output

Each run writes machine-readable JSON, text summaries, CSV scan tables, and PNG plots unless `--no-plots` is given.  Batch runs do not call blocking `plt.show()`.

## Smoke test

A small smoke test exercises the main paths and one controlled failure mode:

```bash
python scripts/smoke_test.py
```

## Notes on the ESS/IACT comparator

`auto-compare` implements the same core heuristic used by `pymbar.timeseries.detect_equilibration`: scan candidate production starts, estimate the statistical inefficiency `g` of the retained segment from an FFT autocorrelation estimate, and choose the start maximizing retained effective sample size.  The statistical-inefficiency estimate follows the PyMBAR-style accumulation `1 + sum_t 2 C(t) (1 - t/N)` with first-nonpositive truncation after the minimum lag.  The comparator is included for comparison and conservative combination with MDTest stationarity diagnostics; it is not treated as a stationarity certificate.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Citation

If you use MDTest in academic work, please cite the associated manuscript:

MDTest: A practical program for diagnosing equilibration and statistical error in molecular-dynamics time series

---

## Contact

For questions, bug reports, or feature requests, please contact the primary developer:

- **Primary developer:** Jerry Wang (`jerryf.w.1024@gmail.com`)

Additional project authors:
- Haobin Wang (`HAOBIN.WANG@ucdenver.edu`)
- Hai Lin (`Hai.Lin@ucdenver.edu`)
