# MDTest traditional user manual

The distributed `MDTest_User_Manual.pdf` is intended for molecular-simulation users who prefer a conventional manual rather than API-only documentation. It contains:

1. purpose and scope;
2. system requirements and stepwise installation;
3. input-data conventions and missing-data handling;
4. statistical background: stationarity, correlation, blocking, the four tests, and uncertainty reporting;
5. algorithm/implementation details in chemist-facing language, including rank compression plus a Fenwick (binary indexed) tree for Mann-Kendall order counting, multi-resolution search, FFT autocorrelation, and ESS scanning;
6. analysis-mode selection;
7. step-by-step Jupyter Workbench use;
8. Python API examples;
9. command-line/configuration-file examples;
10. interpretation of all diagnostic figures and common outcomes;
11. worked examples;
12. troubleshooting;
13. validation, reproducibility, provenance, license, defaults, package map, and references.

The manual is distributed with the MIT-licensed software/documentation package. The CPC manuscript summarizes the software and points readers to the manual rather than reproducing these operational details in the article.
