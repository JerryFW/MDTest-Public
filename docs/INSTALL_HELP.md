# Installation and startup troubleshooting

**Use the launcher before trying to install MDTest by hand.** On Windows, double-click `START_MDTEST_WINDOWS.bat`. On macOS use `sh START_MDTEST_MAC.command` in Terminal (see [Mac guide](MAC_START_GUIDE.html)); on Linux run `bash START_MDTEST_LINUX.sh`.

### "No module named mdtest"

This means the notebook or interpreter did not start from the package's private environment. Close other notebook kernels and launch Jupyter using the START file in the top-level MDTest folder. Do not try to "link the src directory" manually. The program uses a standard Python `src/` package layout; START installs it into its own private Python environment automatically.

### Python not found / Python too old

Install a supported Python version: for the Mac Easy-Start launcher, **Python 3.13 or 3.12 is recommended** (Python 3.15 is also recognized, but complete Jupyter/MDTest testing on it is still pending). In general, MDTest requires Python **3.11 or later**. On Windows download the official Python installer from <https://www.python.org/downloads/windows/> and enable **Add python.exe to PATH** if offered. Close and reopen the terminal after installation. On macOS use python.org or your package manager; on Linux use your distro's Python packages. Run START again.

### A terminal window opens and installation takes time

On first run, JupyterLab, NumPy, SciPy, pandas and Matplotlib might have to be downloaded into its private environment. This is a normal one-time setup and requires internet. Do not close the window during installation. Later starts normally reuse the environment.

### Network, package index, SSL, or proxy error

The launcher cannot bypass restricted networks. University or corporate systems sometimes block package index access or use SSL inspection. Ask your IT administrator how Python package installations are authorized. Re-run START once the issue is resolved. You do not need administrator rights for a user-writable MDTest folder.

### Browser doesn't open / cannot connect

Keep the launcher terminal open. Look for Jupyter's printed local `http://localhost:...` link; copy it into your browser. If the terminal closes, the local server stops. On managed computers the firewall or browser policy may restrict local ports.

### The notebook launches but widgets are missing

Start it via the supplied launcher instead of another Jupyter environment. The launcher checks `ipywidgets`, JupyterLab, nbconvert and that the installed `mdtest` resolves to this folder. If a notebook kernel was already running before setup, restart the kernel.

### I accidentally installed MDTest somewhere else

That is fine. The launcher uses its own private environment and does not rely on your globally installed `mdtest`. On Windows the environment is at `%LOCALAPPDATA%\MDTest\e`. To inspect its state without installing, run `python tools/launch_mdtest.py --check` from the repository root; this requires a system Python 3.11+. To create the environment without launching the browser, use `python tools/launch_mdtest.py --setup-only`.

### Windows error: `No such file or directory` / `Windows Long Path support`

This can occur when JupyterLab is installed deep under a Downloads folder, for example a path containing `\.venv\Lib\site-packages\jupyterlab\galata\...`. **Do not change Windows Registry settings or enable system-wide long-path support just to run MDTest.** The updated launcher installs JupyterLab in a much shorter user-owned location:

`%LOCALAPPDATA%\MDTest\e` (typically `C:\Users\yourname\AppData\Local\MDTest\e`).

**Recovery:** Download the updated package or replace the single `tools/launch_mdtest.py` file with the matching ShortPathFix launcher, then double-click `START_MDTEST_WINDOWS.bat` again. The launcher ignores any incomplete old `.venv` under Downloads and installs into the short location. Python 3.11+ and first-run internet access are still required. Your existing MDTest scripts, input files, and reports remain unchanged. If the old `.venv` exists, you may delete it **after the new Workbench launches successfully**; it is no longer used by the Windows START command.

If your computer's username is exceptionally long or IT policies prohibit `%LOCALAPPDATA%` installs, contact your IT administrator. The launcher never alters Windows system settings or asks for administrator privileges.

### Error mentioning two different MDTest folders (Downloads / Documents)

Older launchers installed a private `.venv` beside the source, making Windows executable wrappers depend on that folder's location. The updated Windows launcher uses the **same short, stable user-owned environment** regardless of whether your MDTest sources are under Downloads or Documents. When the source moves, START updates the local editable source link rather than trying to run an old `jupyter-lab.exe` wrapper. No copying or linking of `src` is needed.

### Starting over

Close JupyterLab first. On Windows the private installation is under `%LOCALAPPDATA%\MDTest\e`; if you ever need a complete reinstall, rename only that `e` folder and run START again (internet needed). On macOS/Linux, the private installation is `.venv` in the MDTest directory. Do not delete your source files, inputs, or analysis reports. For normal Windows path errors, **do not delete anything**: use the new START launcher.

### macOS Gatekeeper, Anaconda and Jupyter kernel FAQ

A colleague using an M4 Mac with an older Anaconda/Python 3.7 installation reported a Gatekeeper warning, missing executable permissions, and a Jupyter kernel mismatch. These are distinct from MDTest scientific errors. See the [Mac troubleshooting FAQ](MAC_FAQ.html) or [Mac start guide](MAC_START_GUIDE.html). **`chmod 644` does not grant execute permission**; use `sh START_MDTEST_MAC.command`, or `chmod +x` for direct execution. To avoid using Anaconda's older kernel, open Jupyter through the MDTest launcher; optionally register MDTest's `.venv` as a kernel in your existing Jupyter interface (instructions in the FAQ).

### Linux/macOS permissions

Run `bash START_MDTEST_LINUX.sh` (Linux) or `sh START_MDTEST_MAC.command` (macOS). Terminal execution works even if executable permission was lost during ZIP extraction. On macOS use Terminal and run `sh START_MDTEST_MAC.command` from the extracted MDTest folder. The downloaded `.command` is not Apple-notarized; if Finder blocks it, follow Apple’s per-file **System Settings → Privacy & Security → Open Anyway** instructions only when you trust the download. See [Mac guide](MAC_START_GUIDE.html). Do not globally disable Gatekeeper.

### Manual/advanced installation (optional)

Users who already manage Python environments can still install from the directory containing `pyproject.toml` using `python -m pip install -e ".[notebook]"` and then `python -m jupyterlab MDTestWorkbench.ipynb`. For ordinary users the launcher performs these steps automatically.

### Safety / privacy

The launcher contains only standard-library Python plus a shell/batch wrapper. It does not upload your MD trajectories or change the statistical engine. JupyterLab runs a local server; browser/extension settings are controlled by your environment. Do not publicly expose or share the local Jupyter access URL/token.

### Email attachments blocked by Gmail

The release ZIP contains a Windows `.bat` launcher. Gmail blocks this file type even inside ZIP archives. Send a GitHub Releases or cloud-storage link; renaming the ZIP is not a fix.

### Installation appears successful but notebook check fails

Earlier MDTest launchers suppressed the real error from `installed_ok()`. The revised launcher prints a detailed notebook check with import results for NumPy, SciPy, pandas, Matplotlib, ipywidgets, JupyterLab, nbconvert, and MDTest itself, including imported paths and versions. Share this diagnostic section when seeking assistance. If you installed Python 3.15 on a Mac, install Python 3.13/3.12 and start again; a different-version private environment will be archived and recreated, without changing the analysis code.
