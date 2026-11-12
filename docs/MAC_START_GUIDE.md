# Starting MDTest on macOS

**For the illustrated, larger-font version, open [MAC_START_GUIDE.html](MAC_START_GUIDE.html).**

**Common Mac problems (from user testing):** [Mac troubleshooting FAQ](MAC_FAQ.html), including the correct executable permission command and how to avoid older Anaconda kernels.

1. Install Python **3.13 or 3.12** from <https://www.python.org/downloads/macos/>. Python 3.15 is recognized by the START launcher, but the complete MDTest/Jupyter setup has not yet been independently tested on it; multiple Python versions can coexist.
2. Extract the entire MDTest ZIP in Finder.
3. Open **Terminal**, type `cd ` (with a space), drag the extracted MDTest folder into Terminal, then press Return.
4. Run `sh START_MDTEST_MAC.command`.
5. Follow the output to open the local JupyterLab page. Keep Terminal open while using MDTest.

**Gatekeeper:** MDTest's `.command` file is an unsigned research script. macOS may warn when double-clicked. If you trust the source and wish to open in Finder, macOS offers a per-file **System Settings → Privacy & Security → Open Anyway** action following a blocked attempt. Never disable Gatekeeper globally. Terminal steps above are an alternative.

**Diagnostic:** The improved installer prints specific package-import and installation-path failures if the post-install check fails. Please capture those lines.

**Email:** Gmail blocks compressed archives containing `.bat` files. Send a GitHub Release or cloud-drive link rather than mailing the ZIP as an attachment.
