# macOS troubleshooting FAQ — MDTest Easy-Start

**Use this page when MDTest will not start on a Mac.** These questions are based on a real first-installation experience involving an Apple Silicon Mac, an older Anaconda installation, and multiple Python versions. This FAQ explains what was observed and distinguishes the supported Easy-Start workflow from optional advanced setup.

## 1. macOS says “Apple could not verify this file is free of malware.” Is MDTest infected?

**Not necessarily.** This message is a macOS Gatekeeper verification warning for a downloaded script that has not been Apple-signed/notarized. It is **not proof that the file is safe**, either. Download MDTest from the trusted project release and verify its source if appropriate before running anything.

**Recommended approach:** Extract the complete ZIP. Open Terminal, type `cd ` (with the trailing space), drag the extracted `MDTest-Public-2.2.0.dev13` folder into Terminal, press Return, and enter:

```sh
sh START_MDTEST_MAC.command
```

Alternatively, after a blocked attempt, users who trust the download can follow Apple's **System Settings → Privacy & Security → Open Anyway** per-file exception. Do **not** disable Gatekeeper for the entire Mac.

A previous tester got past the warning with `xattr -d com.apple.quarantine START_MDTEST_MAC.command`. That removes the quarantine marker and bypasses an important security check, so **this is not our standard recommendation**. Prefer the supported Terminal procedure or Apple's per-file exception.

Apple's instructions: <https://support.apple.com/en-us/102445>.

## 2. I get “Permission denied” after unzipping. Does `chmod 644` help?

**No. `chmod 644` removes execute permission.** An early troubleshooting note contained that mistaken command. The correct ways are:

```sh
sh START_MDTEST_MAC.command
```

This runs the script through the shell, even if the ZIP extractor lost the execute bit. If you prefer to execute it directly:

```sh
chmod +x START_MDTEST_MAC.command
./START_MDTEST_MAC.command
```

The official release ZIP includes the script's executable file mode, but unzip utilities may not preserve it. Apple's reference: <https://support.apple.com/en-lamr/guide/terminal/apdd100908f-06b3-4e63-8a87-32e71241bab4/mac>.

## 3. The Mac already has Anaconda and Python 3.7. Do I need to uninstall them?

**No.** Anaconda and older Python installations can remain installed. Python 3.7 is too old for MDTest. For this release, install **Python 3.13 or 3.12** from <https://www.python.org/downloads/macos/> and run the supplied Mac START launcher. The launcher searches for compatible installed interpreters, creates a separate `.venv` next to the MDTest sources, and installs MDTest/JupyterLab there. It does not need to modify Anaconda.

You do **not** need to install Python 3.15 to repair an old Python 3.7 installation. The Mac launcher now recognizes Python 3.15, but selects 3.13/3.12 first where available; full Jupyter/MDTest validation on 3.15 remains pending.

## 4. MDTest installs, but the notebook says `No module named mdtest` or uses the wrong Python.

This commonly means the notebook was opened from an existing Anaconda Jupyter server/kernel rather than from MDTest's private environment. **A Jupyter server and its selected notebook kernel can use different Python installations.**

**Simplest fix:** Close the notebook and start Jupyter through `sh START_MDTEST_MAC.command` in the extracted MDTest folder. Then open `MDTestWorkbench.ipynb` in the browser window opened by START. Restart the kernel if you changed environments.

To check the active notebook kernel, run this in a new notebook cell:

```python
import sys, mdtest
print(sys.executable)
print(mdtest.__file__)
```

The interpreter should be inside the MDTest `.venv`, and `mdtest.__file__` should point to this release's `src/mdtest` directory (the software is installed in editable mode).

## 5. I deliberately want to keep my existing Anaconda Jupyter interface. Can I use MDTest in it?

**Yes, as an optional advanced setup.** Do this only after the ordinary Mac START setup has succeeded. Open Terminal in the extracted MDTest directory, then run:

```sh
sh START_MDTEST_MAC.command --setup-only
./.venv/bin/python -m pip install ipykernel
./.venv/bin/python -m ipykernel install --user --name mdtest-private --display-name "MDTest (private Python)"
```

Open the notebook in your existing Jupyter interface, then select **Kernel → Change Kernel → MDTest (private Python)**. The notebook should now use MDTest's own Python rather than Anaconda's older interpreter. Kernel menu wording can vary by Jupyter version.

Do **not** rely on an unqualified `pip install notebook` command: it may install into the wrong Python environment. Likewise, a command such as `python3.15 -m ipykernel install --user` registers a Python 3.15 kernel; it does not make that version the recommended MDTest environment. No username-specific kernel name is needed.

## 6. Installation finishes, but the launcher says the “notebook check” failed. What should I send for diagnosis?

Use the **latest** launcher, which prints a **Detailed notebook check** with Python version, dependency imports, and the location/version of `mdtest`. Copy that section along with the traceback and report which Python version appears. Do not reinstall the system Python repeatedly without first inspecting the actual error.

You can run a non-launching inspection from the MDTest folder with:

```sh
sh START_MDTEST_MAC.command --check
```

A failed check can mean a missing Jupyter package, an incompatible Python dependency, or an editable installation pointing to a different folder. It does **not** by itself mean that MDTest's statistical calculations are defective.

## 7. What if macOS uses an Apple Silicon (M-series) processor?

The report motivating this FAQ came from an M4 MacBook Pro. Use a current **Apple Silicon-compatible** Python installer (3.13/3.12 recommended here) and let the private environment obtain compatible binary dependencies. Avoid mixing ARM-native and Intel/Rosetta package environments unless you explicitly manage them.

---

**Recommended order:** trusted ZIP → extract → Python 3.13/3.12 → `sh START_MDTEST_MAC.command` → open `MDTestWorkbench.ipynb` → run all cells. Existing Anaconda/Jupyter/kernel registration is an *optional advanced route*, not part of the normal MDTest installation.

[Mac start guide](MAC_START_GUIDE.html) · [General installation help](INSTALL_HELP.html) · [Getting started](../START_HERE.html)
