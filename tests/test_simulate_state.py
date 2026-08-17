from __future__ import annotations

import json
import math

import pytest

from nodi_foundation import (
    EnvironmentState,
    ParticleState,
    SimulationState,
    derive_observation,
    simulate_state,
)
from nodi_foundation.errors import FoundationError


def test_frozen_paper1_baseline_parity() -> None:
    result = simulate_state(SimulationState())
    assert result.B_bg_W == pytest.approx(0.20297283613317754, rel=2.0e-15)
    assert result.S_W == pytest.approx(3.1501989107668475e-7, rel=2.0e-15)
    assert result.C_r_W == pytest.approx(-0.00011614407102063403, rel=2.0e-15)
    assert result.C_i_W == pytest.approx(7.370152211533342e-5, rel=2.0e-15)
    assert result.eta_real == pytest.approx(-0.4593133792174526, rel=2.0e-15)
    assert result.eta_imag == pytest.approx(0.29146640787414346, rel=2.0e-15)
    assert result.Y_0_W == pytest.approx(result.S_W + 2.0 * result.C_r_W)
    assert result.combined_total_W == pytest.approx(result.B_bg_W + result.Y_0_W)
    assert result.operator_qualification_status == "QUALIFIED_CANONICAL_FULL_PUPIL"


def test_state_and_result_identities_are_canonical() -> None:
    state = SimulationState()
    result = simulate_state(state)
    assert SimulationState.from_mapping(state.to_payload()).state_id == state.state_id
    payload = json.loads(result.to_canonical_json())
    assert payload["state_id"] == state.state_id
    assert payload["result_hash"] == result.result_hash


def test_zero_particle_contrast_is_typed_low_field() -> None:
    state = SimulationState(
        particle=ParticleState(
            diameter_m=1.0e-7,
            refractive_index_real=1.33,
            refractive_index_imag=0.0,
        )
    )
    result = simulate_state(state)
    assert result.S_W == 0.0
    assert result.C_r_W == 0.0
    assert result.C_i_W == 0.0
    assert result.eta_real is result.eta_imag is result.eta_abs is None
    assert result.C_phase_rad is None


def test_observation_angle_is_algebraic() -> None:
    result = simulate_state(SimulationState())
    assert derive_observation(result, theta=0.0) == pytest.approx(result.Y_0_W)
    assert derive_observation(result, theta=math.pi / 2.0) == pytest.approx(
        result.S_W + 2.0 * result.C_i_W
    )


def test_invalid_geometry_and_na_fail_closed() -> None:
    with pytest.raises(FoundationError, match="E_DOMAIN_INVALID"):
        SimulationState(
            environment=EnvironmentState(fill_refractive_index=1.33, wall_refractive_index=1.40),
            observation=SimulationState().observation.__class__(collection_na=1.40),
        )
