# MDTest - START HERE

This guide is for someone who wants to analyze an MD time series **without learning Python packaging**.

**You do not need to edit Python files, link `src`, set `PYTHONPATH`, or activate a virtual environment.** The START launcher does setup for you.

## A. See what MDTest looks like (no installation)

Open `examples/workbench_demo/variance_relaxation_guided.html` by double-clicking it. This is a **saved example report**, not the live analysis interface; it requires only a web browser.

## B. First-time setup (three steps)

1. **Download and extract the entire ZIP.** On Windows, right-click the ZIP and choose **Extract All...**. Open the extracted `MDTest_2.2.0.dev7` folder. Do not run the launcher from inside the ZIP preview.
2. **Start MDTest using the file for your system:**
   - **Windows:** double-click `START_MDTEST_WINDOWS.bat`.
   - **macOS:** double-click `START_MDTEST_MAC.command`. If Finder blocks it, use *right-click → Open* (if permitted by your administrator). Alternatively in Terminal: `sh START_MDTEST_MAC.command`.
   - **Linux:** open a terminal in the extracted folder and run `bash START_MDTEST_LINUX.sh`.
3. **Use the browser window that opens.** On **Windows**, START creates a private environment at `%LOCALAPPDATA%\MDTest\e` (outside the extracted ZIP) to avoid JupyterLab's deep-file Windows path limit. On macOS/Linux, it uses `.venv` beside the source. START installs MDTest and JupyterLab on first run, then opens `MDTestWorkbench.ipynb`. Later starts reuse the installation. Moving the MDTest source folder on Windows only updates the source link; JupyterLab is not moved or reinstalled. **Keep the terminal/command window open** while using MDTest. When finished, close JupyterLab and press **Ctrl+C** in that window to stop the server.

**First-run prerequisites:** Python **3.11 or newer** and internet access to download Python packages. Python is not bundled. Windows installer: <https://www.python.org/downloads/windows/> (select **Add Python to PATH** if offered). macOS/Linux Python: <https://www.python.org/downloads/> or your system package manager. If a university proxy blocks package downloads, consult your IT team or `docs/INSTALL_HELP.md`.

**Windows security note:** Only open a downloaded batch file after inspecting/trusting its source. The launcher is plain text; it creates a private Python environment (under `%LOCALAPPDATA%\MDTest\e` on Windows) and installs MDTest and JupyterLab there. It does not require administrator rights and does not change the system's Python environment.

## C. Your first analysis (five clicks in the Workbench)

1. In JupyterLab, open `MDTestWorkbench.ipynb` if it is not already open, and choose **Run → Run All Cells**. If JupyterLab asks for a kernel, select the local **Python 3** kernel.
2. In **Choose data**, use **Load columns** on the demonstration input `examples/data/synthetic_variance_relaxation_independent.csv` (or enter its path); then select observable column **1**.
3. Under **Choose analysis**, choose **Auto Compare**. Leave the advanced settings at their defaults for initial exploration.
4. Click **Run analysis**. The integrated dashboard shows stationarity and ESS/IACT starts, diagnostic plots, and interpretation; failure of a statistical test is a diagnostic result, not necessarily a program error.
5. Click **Export** to save a reproducible text/JSON/HTML report and diagnostic figures. Open the HTML report in a browser to examine or share it.

*Reproducible benchmark note:* The protected variance-relaxation results (`start_SW=10374`, `start_ESS=0`, combined start `10374`) use the full-scale settings documented in the manual; do not assume the Workbench's defaults will give exactly those values. The demonstration report is provided separately in `examples/workbench_demo/`.

## D. Frequent questions

**"Fatal error in launcher: ... Downloads ... Documents"**: this was caused by moving a location-dependent old `.venv`. Use the updated Windows launcher; it keeps JupyterLab in a separate stable location and updates the MDTest source link automatically.

**"No module named mdtest"**: open the repository root (the folder containing `pyproject.toml` and `START_MDTEST_WINDOWS.bat`) and run START; do not double-click the `.ipynb` file directly before setup. If using an already-open notebook, shut down JupyterLab and restart it with START so that the notebook uses the private Python environment.

**"Windows long-path error during JupyterLab installation"**: the updated launcher installs into a much shorter per-user environment. Download the ShortPathFix package (or replace `tools/launch_mdtest.py`), then double-click START again. Do not change Windows Registry settings.

**"Python was not found"**: install Python 3.11+ from python.org, reopen the terminal, run START again. You do **not** need to move or link `src`.

**The browser does not open**: look in the launcher window for an `http://localhost:...` link; copy it into your browser. The local Jupyter server runs only while that window stays open.

**Installation fails (network / SSL / proxy)**: first check that internet access works and that you can reach the Python package index. See `docs/INSTALL_HELP.md`; enterprise/university-managed systems may require an IT-approved package index.

**I already use conda or my own Python environment**: optional advanced instructions appear in `README.md` and `docs/MDTest_User_Manual.pdf`. The START workflow is specifically designed for users who do not want to manage Python environments.

## E. What is installed and where?

On Windows, the launcher puts installed Python packages in **`%LOCALAPPDATA%\MDTest\e`** instead of the extracted ZIP folder, which avoids Windows path-length errors and moved-folder failures. On macOS/Linux, it uses **`.venv/` inside the extracted folder**. Both are private environments, not system-wide changes. The editable installation points at the included `src/mdtest` package, without changing scientific code. For a Windows long-path installation error, use the new START file rather than changing Windows settings.

## Other documentation

- `docs/MDTest_User_Manual.pdf` - detailed traditional manual: methods, algorithms, screenshots, data preparation, interpretation, results, and troubleshooting.
- `docs/WORKBENCH_GUIDE.md` - detailed widget workflow.
- `docs/API_REFERENCE.md` - advanced Python programming.
- `docs/INSTALL_HELP.md` - setup problems and solutions.

### Select a data file

Inside the Workbench, the easiest option is **Local file** for sample data or a file already in the JupyterLab folder. **Choose file** transfers a file from your computer and now automatically loads the column names, displaying the received filename and number of bytes. If no **File received** confirmation appears, upload with JupyterLab's **left file browser**, click **Refresh list** in MDTest, and choose the file. You may also type its full path and click **Load columns**.


## F. Which notebook should I open?

- **`MDTestWorkbench.ipynb` (recommended):** the main graphical application, with upload/local-file selection, four analysis modes, plots, and report export. No coding required. Open it from the repository root in JupyterLab.
- **`tutorials/MDTest_Tutorial.ipynb` (optional):** an educational Python walkthrough with NarK and synthetic benchmark examples. Use it to learn the API, not as the usual GUI. In JupyterLab open the `tutorials` folder and run the notebook. It finds `examples/data` automatically.

For a more readable, larger-font version of this guide, open `docs/START_HERE.html` in a browser or choose **Full quick-start** from the main `START_HERE.html` page.


**Mac-specific installation problems:** The [Mac troubleshooting FAQ](MAC_FAQ.html) covers Gatekeeper, executable permission, and existing Anaconda/Jupyter kernels.
