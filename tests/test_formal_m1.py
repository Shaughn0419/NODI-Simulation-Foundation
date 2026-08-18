from __future__ import annotations

from dataclasses import replace

import pytest

from nodi_foundation import ObservationOperatorState, SimulationState, simulate_state
from nodi_foundation._physics.formal_m1 import evaluate_formal_m1
from nodi_foundation.errors import FoundationError
from nodi_foundation.profiles import FAST_CONTROL_PROFILE


def test_declared_pupil_refinement_converges() -> None:
    state = SimulationState()
    middle = evaluate_formal_m1(state, pupil_order=(12, 24))
    final = evaluate_formal_m1(state, pupil_order=(16, 32))
    for name in ("B_bg_W", "S_W", "C_r_W", "C_i_W"):
        expected = getattr(final, name)
        assert getattr(middle, name) == pytest.approx(expected, rel=2.0e-2, abs=1.0e-24)


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

