from __future__ import annotations

import json
from pathlib import Path

from nodi_foundation import SimulationState, simulate_state
from nodi_foundation.profiles import FAST_CONTROL_PROFILE

ROOT = Path(__file__).resolve().parents[1]


def test_compact_m1_golden_regression() -> None:
    golden = json.loads((ROOT / "tests/golden/m1_baseline_v1.json").read_text(encoding="utf-8"))
    result = simulate_state(SimulationState(physics_profile_id=FAST_CONTROL_PROFILE)).to_payload()
    for field in ("B_bg_W", "S_W", "C_r_W", "C_i_W", "eta_real", "eta_imag"):
        assert result[field] == golden[field]
    assert result["physics_profile_id"] == FAST_CONTROL_PROFILE
    assert result["fidelity_class"] == "SCALING_CONTROL_ONLY"


def test_parity_report_binds_golden_bytes() -> None:
    import hashlib

    golden_path = ROOT / "tests/golden/m1_baseline_v1.json"
    report = json.loads((ROOT / "canonical_parity_report.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(golden_path.read_bytes()).hexdigest() == report["golden_file_sha256"]
    assert report["status"] == "PASS_BASELINE_CANONICAL_PARITY"
