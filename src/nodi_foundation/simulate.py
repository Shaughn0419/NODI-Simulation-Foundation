"""Single-state simulation and algebraic observations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ._physics import evaluate_profile
from .models import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    SCHEMA_VERSION,
    SimulationState,
    StateResult,
    canonical_sha256,
)
from .profiles import (
    FAST_CLAIM_CEILING,
    FAST_CONTROL_PROFILE,
    FAST_FIDELITY,
    FORMAL_CLAIM_CEILING,
    FORMAL_FIDELITY,
)


def simulate_state(state_spec: SimulationState | Mapping[str, Any]) -> StateResult:
    """Validate and simulate one state with its explicit physics profile."""

    state = (
        state_spec
        if isinstance(state_spec, SimulationState)
        else SimulationState.from_mapping(state_spec)
    )
    primitive = evaluate_profile(state)
    is_control = state.physics_profile_id == FAST_CONTROL_PROFILE
    y_0 = primitive.S_W + 2.0 * primitive.C_r_W
    payload: dict[str, Any] = {
        "state_id": state.state_id,
        "inputs": state.to_payload(),
        "physics_profile_id": state.physics_profile_id,
        "fidelity_class": FAST_FIDELITY if is_control else FORMAL_FIDELITY,
        "claim_ceiling": FAST_CLAIM_CEILING if is_control else FORMAL_CLAIM_CEILING,
        "reference_design_id": state.reference_design_id,
        "split_group_id": state.split_group_id,
        "reference_block_id": primitive.reference_block_id,
        "particle_block_id": primitive.particle_block_id,
        "position_block_id": primitive.position_block_id,
        "operator_block_id": primitive.operator_block_id,
        "numerical_receipt_ids": primitive.numerical_receipt_ids,
        "B_bg_W": primitive.B_bg_W,
        "S_W": primitive.S_W,
        "C_r_W": primitive.C_r_W,
        "C_i_W": primitive.C_i_W,
        "Y_0_W": y_0,
        "combined_total_W": primitive.B_bg_W + y_0,
        "eta_real": primitive.eta_real,
        "eta_imag": primitive.eta_imag,
        "eta_abs": primitive.eta_abs,
        "C_phase_rad": primitive.C_phase_rad,
        "coupling_defined": primitive.coupling_defined,
        "coupling_undefined_reason": primitive.coupling_undefined_reason,
        "numerical_status": "SCALING_CONTROL_FINITE" if is_control else "FORMAL_FIELD_FINITE",
        "uncertainty": {
            "numerical": (
                "CLOSED_FORM_DOUBLE_PRECISION_CONTROL"
                if is_control
                else "DECLARED_QUADRATURE_AND_MIE_CONVERGENCE"
            ),
            "model_discrepancy": (
                "NOT_SCIENTIFICALLY_QUALIFIED_CONTROL_ONLY"
                if is_control
                else "FIRST_ORDER_M1_OMISSIONS_DECLARED"
            ),
        },
        "applicability_profile_id": state.physics_profile_id,
        "operator_qualification_status": primitive.operator_qualification_status,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "feature_version": FEATURE_VERSION,
        "config_hash": primitive.config_hash,
    }
    return StateResult(**payload, result_hash=canonical_sha256(payload))


def derive_observation(result: StateResult, *, theta: float) -> float:
    """Derive ``Y_theta = S + 2 Cr cos(theta) + 2 Ci sin(theta)``."""

    if isinstance(theta, bool) or not isinstance(theta, (int, float)) or not math.isfinite(theta):
        raise ValueError("theta must be finite")
    return result.S_W + 2.0 * result.C_r_W * math.cos(theta) + 2.0 * result.C_i_W * math.sin(theta)
