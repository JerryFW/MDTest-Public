#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python MDTest.py make-data --outdir examples/data --n-points 20000
python MDTest.py config examples/configs/manual_nark_volume.txt
python MDTest.py config examples/configs/auto_safe_nark_volume.txt
python MDTest.py config examples/configs/legacy_sensitivity_nark_volume.txt
python MDTest.py config examples/configs/auto_compare_mean_drift.txt
python MDTest.py config examples/configs/auto_compare_variance_relaxation.txt
python MDTest.py config examples/configs/auto_compare_metastable_switch.txt
python MDTest.py config examples/configs/auto_compare_underdamped_ar2.txt
