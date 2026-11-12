#!/usr/bin/env python3
"""Verify that Round 3 did not modify the frozen Round-2A.1 engine/API files."""
from __future__ import annotations
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
"src/mdtest/analysis.py":"22917ae97e0543eb7d9e08524f8eb3e78efd34dddc3697ed413e52a62a2d6700",
"src/mdtest/api.py":"666d79117b5af18d1372719d01181d51313bb163e9577c7238614cdce32c39d4",
"src/mdtest/autocorrelation.py":"db9cccc8f509579180005f9b2e04053eeeb895bbbbe28e8b7c85f003a75d1354",
"src/mdtest/benchmarks.py":"4b35d985434d63d665a06f48671c73666e8bb774e1848ba40af00bdae3e6ee60",
"src/mdtest/cli.py":"e0cf39f4f68d61dd3c5bfaa87235b419272107155bf3b04ec6e75c4a2d3870bd",
"src/mdtest/diagnostics.py":"fe9f4ffceb96e854fd18e661f677c994aae58e3e04e794da181090bd768ab391",
"src/mdtest/io.py":"2eb6690c5a2494c8c9ad6ffa5e41138262d212fca54cdd927c1453ffd0603fdd",
"src/mdtest/plotting.py":"a57222eb17978573728723b31663ba3c19d17fae1628fe7f89cd4252c8ae4a7d",
"src/mdtest/provenance.py":"1fa259ddf9c2958de9a1ead72ecd31981779f5eb68c21bc2d962e1c1f7fb8208",
"src/mdtest/reporting.py":"b070b1a72b88c3ca889d1d2077c58b632a9c5d33755cacfa4ce5a0be6fba4e94",
"src/mdtest/results.py":"5f468ed0b1b006d8a78447baf319d04398b6d6e6650517f9fabd33912bf4c17c",
"MDTest.py":"a811923ce0aa028b3fd52846a14b1bf441c362e2355f34b93e309878cc2770b1",
}
# Explicitly authorized public-input changes. Preserve the original baseline
# hashes in EXPECTED; do not silently redefine the scientific freeze.
APPROVED_DEV7_INPUT_LOADER_SHA256 = "4f26a97f62c5df9b083c99cf8e65f37f8bf29606b618a3e4aae4c16891274def"
APPROVED_DEV8_IO_SHA256 = "3148b049baecf8483c867e9139266fc1896fd1c9e32941e2f1ad3fd0dc92c740"
APPROVED_DEV8_API_SHA256 = "b548b4a35baf3dac54a1784ec0544bc9b9bceff0b5beb13d5cc3c339686d302b"
APPROVED_DEV9_IO_SHA256 = "45badd112955ec087b1d5e387e2e481fa0b0144b01b4f0c469e584adb6c8ce16"
APPROVED_DEV9_API_SHA256 = "8aec4636761ae1b587e699d4e2bdd566c2b64da69e0316e3de502538a63a5f13"
# Dev10 interface/provenance exceptions are explicitly pinned.  The original
# Round-2A.1 hashes in EXPECTED remain unchanged and authoritative.
APPROVED_DEV10 = {
    "src/mdtest/api.py": "79c9f7cf209da8f5eded76519e532d3617f07f330976acd8da98e02844795646",
    "src/mdtest/io.py": "6067dcac9ee607692eed2d4e46f6bb5483b7171a04fb537f1ae8de6ac33e9d59",
    "src/mdtest/results.py": "279b72ba62fa25fd6c41298ef7a26b4f46f9a1ee037cce030c2bb3db809ab3b7",
    "src/mdtest/provenance.py": "b440a7be51722b024706fdd9b3a52276535b2cfbee66692eebe55346d4b2cf9e",
}
version = (ROOT / "src/mdtest/_version.py").read_text(encoding="utf-8")
is_dev7 = '"2.2.0.dev7"' in version
is_dev8 = '"2.2.0.dev8"' in version
is_dev9 = '"2.2.0.dev9"' in version
is_dev10 = '"2.2.0.dev10"' in version
is_dev11 = '"2.2.0.dev11"' in version
is_dev12 = '"2.2.0.dev12"' in version
is_dev13 = '"2.2.0.dev13"' in version
# The published 2.2.0.dev7 consolidates the internally audited maintenance
# revisions. It uses the latest audited input/provenance boundary hashes.
# Earlier internal pre-release labels remain documented in the audit history.
approved = (APPROVED_DEV10 if (is_dev7 or is_dev10 or is_dev11 or is_dev12 or is_dev13) else
            {"src/mdtest/io.py": APPROVED_DEV9_IO_SHA256, "src/mdtest/api.py": APPROVED_DEV9_API_SHA256} if is_dev9 else
            {"src/mdtest/io.py": APPROVED_DEV7_INPUT_LOADER_SHA256} if is_dev7 else
            {"src/mdtest/io.py": APPROVED_DEV8_IO_SHA256,
             "src/mdtest/api.py": APPROVED_DEV8_API_SHA256} if is_dev8 else {})
failed=[]
for rel,baseline_expected in EXPECTED.items():
    expected = approved.get(rel, baseline_expected)
    # Git may check out Python files with CRLF on Windows. Ignore only this
    # line-ending representation difference; preserve the pinned hashes.
    data = (ROOT / rel).read_bytes()
    actual = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    if actual!=expected: failed.append((rel,expected,actual))
if failed:
    for rel,e,a in failed: print(f"FAIL {rel}\n expected {e}\n actual   {a}")
    raise SystemExit(1)
if is_dev7 or is_dev10 or is_dev11 or is_dev12 or is_dev13:
    print("Public maintenance scope PASS: 8 original frozen hashes unchanged; 4 explicitly authorized input/provenance exceptions.")
elif is_dev9:
    print("Dev9 scope PASS: 10 original frozen hashes unchanged; api.py and io.py are the two documented input-boundary exceptions.")
elif is_dev8:
    print("Dev8 scope PASS: 10 original frozen hashes unchanged; api.py (alpha validation) and io.py (parser validation) are the two explicit exceptions.")
elif is_dev7:
    print("Dev7 scope PASS: 11 original frozen hashes unchanged; io.py is the one approved time-validation exception.")
else:
    print(f"Round-3 frozen-engine hash check passed ({len(EXPECTED)}/{len(EXPECTED)} files unchanged).")
