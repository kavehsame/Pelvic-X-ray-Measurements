"""Shared pytest configuration for Pelvic X-ray Measurements unit tests."""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "PelvicXrayMeasurements" / "PelvicXrayMeasurementsLib"
REPLAY_DIR = REPO_ROOT / "Testing" / "Python" / "end_to_end_replay"
if REPO_ROOT.name == 'PelvicXrayMeasurementsVerification':
    LIB_DIR = REPO_ROOT.parent / 'PelvicXrayMeasurementsLib'

for path in [str(REPLAY_DIR), str(LIB_DIR)]:
    if path not in sys.path:
        sys.path.insert(0, path)
