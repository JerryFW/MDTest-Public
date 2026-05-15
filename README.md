# MDTest

## Application Description
**MDTest** is a lightweight, standalone Python 3 program for post-processing scalar molecular dynamics (MD) time series. It is designed to provide statistically robust analysis while remaining accessible to both new and experienced users. 
The statistical analysis follows a four-test framework proposed by Schiferl and Wallace for diagnosing equilibration and correlation in MD-derived time series. This includes
- Two Mann--Kendall (MK) tests to check for lack of trend in mean and estimated standard error
- A normality test on coarse-grained (block-averaged) samples
- A one-tailed von Neumann test for positive serial correlation
Furthermore, in addition to statistical outputs, **MDTest** provides diagnostic plots to help users interpret results and visually confirm equilibriation. 

---

## Features
- Interactive walkthrough mode for guided analysis
- Scriptable command-line modes for quick execution
- Configuration-file execution modes for batch jobs
- Support for `.csv`, `.dat`, and `.txt` trajectory files
- Saves inputs and statistical outputs for future reference

---

## Requirements

### Python Version

- Python **3.11+**

### Dependencies

MDTest uses standard scientific Python libraries:

- NumPy — array operations and vectorized statistics
- SciPy — statistical routines
- Pandas — file I/O and column handling
- Matplotlib — plotting and diagnostics

### Installation

Install dependencies manually:

```bash
pip install numpy scipy pandas matplotlib
```

Or allow MDTest to attempt automatic installation at startup.


---

## Execution Modes

MDTest supports three execution modes.

---

### 1. Interactive Walkthrough Mode

Launch by running:

```bash
python MDTest.py
```

The walkthrough mode:

- Prompts users for required parameters
- Explains invalid entries before continuing

The early plotting step helps verify that the correct observable has been loaded before statistical analysis begins.

After completion, MDTest prints and saves:

- Input parameters
- Analysis settings
- Statistical test outcomes
- Relevant warnings/disclaimers

If the normality guard fails, the software warns that subsequent von Neumann testing may not be formally valid.

---

### 2. Command-Line Mode

Run directly with parameters:

```bash
python MDTest.py <file> <delim> <colRead> <ts> <m> <n> <alphaValue>
```


| Argument | Description |
|---|---|
| `file` | Input trajectory file |
| `delim` | Delimiter |
| `colRead` | Column index to analyze |
| `ts` | Start time index |
| `m` | Block size |
| `n` | Number of blocks (optional - defaults to maximum feasible number of blocks given `(ts, m)`) |
| `alphaValue` | Statistical significance level (optional - defaults to 0.05) |


---

### 3. Configuration File Mode

Run using:

```bash
python MDTest.py <pathOfInputFile>
```

The configuration file must:

- Be a `.txt` file
- Begin with the header:

```text
MD Test Format
```

- Use strict key-value formatting:

```text
key-value
```

with no extra spaces.

#### Example Configuration File

```text
MD Test Format
file-data.csv
colRead-1
ts-1000
m-50
n-20
alphaValue-0.05
```

## Example Usage

### Interactive

```bash
python MDTest.py
```

### Command-Line

```bash
python MDTest.py data.csv comma 1 1000 50 20 0.05
```

### Configuration File

```bash
python MDTest.py example_input.txt
```

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
