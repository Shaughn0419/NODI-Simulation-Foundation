"""Single-state simulation and algebraic observations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ._physics import evaluate_m1
from .models import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    SCHEMA_VERSION,
    SimulationState,
    StateResult,
    canonical_sha256,
)


def simulate_state(state_spec: SimulationState | Mapping[str, Any]) -> StateResult:
    """Validate and simulate one state with the Foundation analytical M1 engine."""

    state = (
        state_spec
        if isinstance(state_spec, SimulationState)
        else SimulationState.from_mapping(state_spec)
    )
    primitive = evaluate_m1(state)
    y_0 = primitive.S_W + 2.0 * primitive.C_r_W
    payload: dict[str, Any] = {
        "state_id": state.state_id,
        "inputs": state.to_payload(),
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
        "numerical_status": "ANALYTICAL_FINITE",
        "uncertainty": {
            "numerical": "CLOSED_FORM_DOUBLE_PRECISION",
            "model_discrepancy": "UNAVAILABLE_ANALYTICAL_M1_ONLY",
        },
        "applicability_profile_id": "M1_ANALYTICAL_SYNTHETIC_V1",
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
