# Pre-generated MDTest Workbench demonstration

This directory demonstrates the Round-3A user-facing outputs without requiring a live Jupyter widget session.

Input: `examples/data/synthetic_variance_relaxation_independent.csv` (20,000 points).
Analysis: `auto-compare`, frozen Round-2A.1 engine/API.

Headline result:

- MDTest multi-resolution start index: **10374**
- ESS/IACT start index: **0**
- conservative combined start: **10374**
- statistical inefficiency at ESS start: **1.0285490983959442**

Open `variance_relaxation_guided.html` in a browser for the complete guided report. The HTML is self-contained and embeds the five diagnostic images; the same PNG files are also supplied separately for reuse. The JSON is the structured frozen-engine result, including the current package version/provenance; the numerical inference remains frozen.
