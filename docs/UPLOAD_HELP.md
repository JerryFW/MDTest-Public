# MDTest: loading a data file

1. **Local file**: Choose a file from the dropdown. The included sample CSVs appear immediately. MDTest loads its columns automatically.
2. **Choose file**: Select a CSV/TXT/DAT/TSV on your computer. A successful transfer shows **File received** with its filename and byte count and automatically loads its columns. Use **Clear** if you need to choose the same filename again.
3. **When Choose file does not respond**: Use JupyterLab's **left file browser** (the folder panel) to choose **Upload Files** and send the data file to the MDTest folder. Return to the Workbench, click **Refresh list**, and choose the file under **Local file**. This does not depend on the browser's `ipywidgets.FileUpload` transfer.
4. **File path**: You may enter the complete file path and click **Load columns**, without uploading file bytes through the browser.

If **File received** appears but **Could not load data** is shown, the file transfer succeeded and parsing failed. Check whether the first column is time, whether there are at least two numeric columns and at least three rows, and whether the delimiter matches the data. Files ending with `.csv` are parsed as comma-delimited by the frozen loader.

