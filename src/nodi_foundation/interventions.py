"""One-axis intervention pair releases."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from .batch import ExecutionSpec, simulate_batch
from .capabilities import capabilities
from .datasets import state_with_value
from .errors import E_DOMAIN_INVALID, FoundationError
from .models import SimulationState, canonical_sha256
from .profiles import (
    FORMAL_IMPLEMENTATION_SHA256,
    FORMAL_NUMERICAL_PROFILE_SHA256,
    FORMAL_PARITY_PANEL_SHA256,
    FORMAL_PROFILE,
    FORMAL_QUALIFICATION_MATRIX_SHA256,
    FORMAL_QUALIFICATION_REPORT_SHA256,
)
from .releases import PairRelease, write_release_manifest


@dataclass(frozen=True, slots=True)
class PairSpec:
    output_dir: Path
    anchor_states: tuple[SimulationState, ...]
    feature: str
    low_value: float
    high_value: float
    release_name: str = "NODI-PAIRS-CUSTOM-V3"
    execution: ExecutionSpec = ExecutionSpec()
    feature_catalogue_hash: str | None = None
    qualification_report_hash: str | None = None

    def __post_init__(self) -> None:
        profiles = {state.physics_profile_id for state in self.anchor_states}
        if len(profiles) > 1:
            raise FoundationError(E_DOMAIN_INVALID, "pair anchors cannot mix physics profiles")
        if profiles == {FORMAL_PROFILE}:
            if self.feature_catalogue_hash != capabilities().catalogue_hash:
                raise FoundationError(
                    E_DOMAIN_INVALID, "formal pairs must bind the current feature catalogue hash"
                )
            if self.qualification_report_hash != FORMAL_QUALIFICATION_REPORT_SHA256:
                raise FoundationError(
                    E_DOMAIN_INVALID, "formal pairs must bind the qualified report SHA-256"
                )


def build_intervention_pairs(pair_spec: PairSpec) -> PairRelease:
    states: list[SimulationState] = []
    pairs: list[tuple[SimulationState, SimulationState, SimulationState]] = []
    for anchor in pair_spec.anchor_states:
        low = state_with_value(anchor, pair_spec.feature, pair_spec.low_value)
        high = state_with_value(anchor, pair_spec.feature, pair_spec.high_value)
        states.extend((low, high))
        pairs.append((anchor, low, high))
    batch = simulate_batch(states, execution=pair_spec.execution)
    rows = []
    for index, (anchor, low, high) in enumerate(pairs):
        low_result = batch.results[2 * index]
        high_result = batch.results[2 * index + 1]
        pair_id = canonical_sha256(
            {
                "anchor_state_id": anchor.state_id,
                "feature": pair_spec.feature,
                "low_state_id": low.state_id,
                "high_state_id": high.state_id,
            }
        )
        rows.append(
            {
                "pair_id": pair_id,
                "physics_profile_id": low_result.physics_profile_id,
                "anchor_state_id": anchor.state_id,
                "feature": pair_spec.feature,
                "low_value": pair_spec.low_value,
                "high_value": pair_spec.high_value,
                "low_state_id": low.state_id,
                "high_state_id": high.state_id,
                "low_S_W": low_result.S_W,
                "high_S_W": high_result.S_W,
                "delta_S_W": high_result.S_W - low_result.S_W,
                "low_C_r_W": low_result.C_r_W,
                "high_C_r_W": high_result.C_r_W,
                "delta_C_r_W": high_result.C_r_W - low_result.C_r_W,
                "low_C_i_W": low_result.C_i_W,
                "high_C_i_W": high_result.C_i_W,
                "delta_C_i_W": high_result.C_i_W - low_result.C_i_W,
                "low_Y_0_W": low_result.Y_0_W,
                "high_Y_0_W": high_result.Y_0_W,
                "delta_Y_0_W": high_result.Y_0_W - low_result.Y_0_W,
            }
        )
    pair_spec.output_dir.mkdir(parents=True, exist_ok=True)
    target = pair_spec.output_dir / "pairs.parquet"
    handle, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(handle)
    try:
        pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    metadata = {
        "release_name": pair_spec.release_name,
        "pair_count": len(rows),
        "feature": pair_spec.feature,
        "low_value": pair_spec.low_value,
        "high_value": pair_spec.high_value,
        "profile": (
            pair_spec.anchor_states[0].physics_profile_id
            if pair_spec.anchor_states
            else None
        ),
        "feature_catalogue_hash": pair_spec.feature_catalogue_hash,
        "qualification_report_sha256": pair_spec.qualification_report_hash,
        "physics_implementation_sha256": (
            FORMAL_IMPLEMENTATION_SHA256
            if pair_spec.anchor_states
            and pair_spec.anchor_states[0].physics_profile_id == FORMAL_PROFILE
            else None
        ),
        "numerical_profile_sha256": (
            FORMAL_NUMERICAL_PROFILE_SHA256
            if pair_spec.anchor_states
            and pair_spec.anchor_states[0].physics_profile_id == FORMAL_PROFILE
            else None
        ),
        "qualification_matrix_sha256": (
            FORMAL_QUALIFICATION_MATRIX_SHA256
            if pair_spec.anchor_states
            and pair_spec.anchor_states[0].physics_profile_id == FORMAL_PROFILE
            else None
        ),
        "parity_panel_sha256": (
            FORMAL_PARITY_PANEL_SHA256
            if pair_spec.anchor_states
            and pair_spec.anchor_states[0].physics_profile_id == FORMAL_PROFILE
            else None
        ),
        "paper2_final_truth_eligible": bool(
            pair_spec.anchor_states
            and pair_spec.anchor_states[0].physics_profile_id == FORMAL_PROFILE
        ),
    }
    manifest = write_release_manifest(
        pair_spec.output_dir,
        release_type="NODI_PAIR_RELEASE",
        primary_files=("pairs.parquet",),
        metadata=metadata,
    )
    return PairRelease(
        path=pair_spec.output_dir,
        release_id=str(manifest["release_id"]),
        pair_count=len(rows),
        manifest=manifest,
    )
