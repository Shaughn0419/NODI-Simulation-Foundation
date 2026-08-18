from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nodi_foundation import ObservationOperatorState, SimulationState, simulate_state
from nodi_foundation._physics.formal_m1 import evaluate_formal_m1
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import canonical_sha256
from nodi_foundation.profiles import (
    FAST_CONTROL_PROFILE,
    FORMAL_IMPLEMENTATION_SHA256,
    FORMAL_QUALIFICATION_REPORT_SHA256,
)

ROOT = Path(__file__).resolve().parents[1]


def test_declared_pupil_refinement_converges() -> None:
    state = SimulationState()
    production = evaluate_formal_m1(state, pupil_order=(32, 64), reference_order=96)
    strict = evaluate_formal_m1(state, pupil_order=(40, 80), reference_order=128)
    for name in ("B_bg_W", "S_W", "C_r_W", "C_i_W"):
        expected = getattr(strict, name)
        assert getattr(production, name) == pytest.approx(
            expected, rel=1.0e-2, abs=1.0e-24
        )


def test_absolute_incident_power_scales_all_quadratic_primitives() -> None:
    base = SimulationState()
    doubled = replace(base, source=replace(base.source, incident_power_W=2.0))
    first = simulate_state(base)
    second = simulate_state(doubled)
    for name in ("B_bg_W", "S_W", "C_r_W", "C_i_W"):
        assert getattr(second, name) == pytest.approx(2.0 * getattr(first, name), rel=2.0e-12)


def test_common_field_coupling_obeys_cauchy_bound() -> None:
    result = simulate_state(SimulationState())
    assert result.eta_abs is not None
    assert result.eta_abs <= 1.0
    assert result.C_r_W**2 + result.C_i_W**2 <= result.B_bg_W * result.S_W


def test_formal_failure_does_not_fallback_to_fast_control() -> None:
    observation = ObservationOperatorState(collection_na=1.05)
    with pytest.raises(FoundationError, match="formal M1 computational exit pupil"):
        simulate_state(SimulationState(observation=observation))
    control = simulate_state(
        SimulationState(
            observation=observation,
            physics_profile_id=FAST_CONTROL_PROFILE,
        )
    )
    assert control.fidelity_class == "SCALING_CONTROL_ONLY"


def test_qualification_report_and_implementation_are_exactly_bound() -> None:
    report_path = ROOT / "formal_m1_v3_dry_etch_qualification_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == (
        FORMAL_QUALIFICATION_REPORT_SHA256
    )
    payload_hash = report.pop("payload_sha256")
    assert canonical_sha256(report) == payload_hash
    implementation = ROOT / "src/nodi_foundation/_physics/formal_m1.py"
    normalized = implementation.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(normalized.encode("utf-8")).hexdigest() == (
        FORMAL_IMPLEMENTATION_SHA256
    )
