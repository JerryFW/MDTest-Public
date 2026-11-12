MDTest - START HERE AFTER EXTRACTING (v2.2.0.dev7)

FIRST: You should already have extracted the whole ZIP to a normal folder.
Double-click START_HERE.html in this folder to open the illustrated, large-font
getting-started guide. It explains installation, launching, and first analysis.
README.md gives the same entry point for users browsing the source on GitHub.

QUICK SUMMARY:
1. EXTRACT this entire ZIP to a normal folder. Do not run it from the ZIP preview.
2. Windows: double-click START_MDTEST_WINDOWS.bat
   macOS: open Terminal and run sh START_MDTEST_MAC.command
   Linux: run bash START_MDTEST_LINUX.sh in a terminal.
3. The launcher installs its own private Python environment and opens the
   MDTestWorkbench.ipynb notebook in JupyterLab. In the notebook choose
   Run > Run All Cells to display the application.

FIRST RUN: Python 3.11+ and internet access are required; Python is not bundled.
For detailed instructions open START_HERE.html in your browser.
For technical help read docs/INSTALL_HELP.md.
You do NOT need to link the src folder or set PYTHONPATH.

This official dev7 maintenance release preserves the frozen statistical methods and
benchmark results. It adds strict saved-result numeric overflow handling to
the reporting boundary, on top of the previously audited integrity fixes.

Moved MDTest after the first installation? The updated launcher detects and repairs
the private environment automatically. Keep the folder in its final location if possible.


WHICH NOTEBOOK?
- MDTestWorkbench.ipynb: main graphical software (recommended, no Python coding).
- tutorials/MDTest_Tutorial.ipynb: optional step-by-step Python tutorial.
  In JupyterLab open the tutorials folder to find it.
- Open START_HERE.html for large-font guides; its support links now open
  offline HTML pages instead of raw Markdown files.

MAC USERS: Read docs/MAC_START_GUIDE.html. The Mac script is not Apple-signed;
macOS Gatekeeper may block a double-click. Python 3.12/3.13 recommended.

EMAIL DISTRIBUTION: Gmail blocks ZIPs containing Windows .bat launchers.
Send a GitHub Release link rather than attaching the ZIP to an email.

MAC TROUBLESHOOTING FAQ: docs/MAC_FAQ.html (browser) or docs/MAC_FAQ.md.
The FAQ corrects a reported chmod 644 error and helps Anaconda users select the right Jupyter kernel.
