from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from nodi_foundation import (
    EnvironmentState,
    GeometryState,
    ParticleState,
    SimulationState,
    derive_observation,
    simulate_state,
)
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import dry_etch_bottom_width
from nodi_foundation.profiles import FAST_CONTROL_PROFILE, FORMAL_PROFILE


def test_formal_baseline_is_independently_recomputed_within_declared_tolerance() -> None:
    result = simulate_state(SimulationState())
    assert result.B_bg_W == pytest.approx(0.20297283613317754, rel=5.0e-2)
    assert result.S_W == pytest.approx(3.1501989107668475e-7, rel=5.0e-2)
    assert result.C_r_W == pytest.approx(-0.00011614407102063403, rel=5.0e-2)
    assert result.C_i_W == pytest.approx(7.370152211533342e-5, rel=5.0e-2)
    assert result.Y_0_W == pytest.approx(result.S_W + 2.0 * result.C_r_W)
    assert result.combined_total_W == pytest.approx(result.B_bg_W + result.Y_0_W)
    assert result.physics_profile_id == FORMAL_PROFILE
    assert result.operator_qualification_status == "FORMAL_WITH_LIMITS"
    assert len(result.numerical_receipt_ids) == 2


def test_fast_control_preserves_v1_numbers_only_when_explicitly_selected() -> None:
    result = simulate_state(SimulationState(physics_profile_id=FAST_CONTROL_PROFILE))
    assert result.B_bg_W == pytest.approx(0.20297283613317754, rel=2.0e-15)
    assert result.S_W == pytest.approx(3.1501989107668475e-7, rel=2.0e-15)
    assert result.fidelity_class == "SCALING_CONTROL_ONLY"


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


def test_partial_detector_sector_is_bound_to_operator_identity() -> None:
    baseline = SimulationState()
    partial = replace(
        baseline,
        observation=replace(
            baseline.observation,
            detector_sector_width_rad=math.pi,
            detector_sector_center_rad=0.0,
        ),
    )
    shifted = replace(
        partial,
        observation=replace(partial.observation, detector_sector_center_rad=math.pi / 2.0),
    )
    first = simulate_state(partial)
    second = simulate_state(shifted)
    assert second.B_bg_W == pytest.approx(first.B_bg_W, rel=1.0e-14)
    assert second.S_W == pytest.approx(first.S_W, rel=1.0e-14)
    assert second.operator_block_id != first.operator_block_id
    assert second.result_hash != first.result_hash


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


def test_dry_etch_zero_bottom_is_terminal_and_negative_bottom_is_rejected() -> None:
    width = 1.0e-6
    angle = 70.0
    apex_depth = 0.5 * width * math.tan(math.radians(angle))
    apex = SimulationState(geometry=GeometryState(width, apex_depth, angle))
    assert dry_etch_bottom_width(width, apex_depth, angle) == 0.0
    assert simulate_state(apex).numerical_status == "FORMAL_FIELD_FINITE"

    with pytest.raises(FoundationError, match="negative bottom width"):
        SimulationState(
            geometry=GeometryState(width, apex_depth * (1.0 + 1.0e-8), angle)
        )


def test_profile_specific_ranges_and_coupled_particle_fit_fail_closed() -> None:
    expanded = SimulationState(
        geometry=GeometryState(2.0e-6, 2.0e-6, 70.0),
        particle=ParticleState(diameter_m=2.0e-7),
        source=replace(SimulationState().source, wavelength_m=9.0e-7),
    )
    assert expanded.physics_profile_id == FORMAL_PROFILE
    with pytest.raises(FoundationError, match="depth_m must be"):
        replace(expanded, physics_profile_id=FAST_CONTROL_PROFILE)
    with pytest.raises(FoundationError, match="particle does not fit channel depth"):
        SimulationState(
            geometry=GeometryState(2.0e-7, 2.0e-7, 90.0),
            particle=ParticleState(diameter_m=2.0e-7),
        )
