"""Build the formal v2 capability freeze and reference-data products."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
import time
import warnings
from collections import defaultdict
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import qmc

from nodi_foundation import (
    EnvironmentState,
    GeometryState,
    ObservationOperatorState,
    ParticleState,
    PositionState,
    SimulationState,
    SourceState,
    StateResult,
    capabilities,
    simulate_state,
    validate_release,
)
from nodi_foundation.datasets import result_row, state_with_value
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import canonical_json, canonical_sha256
from nodi_foundation.profiles import (
    FORMAL_IMPLEMENTATION_SHA256,
    FORMAL_NUMERICAL_PROFILE_SHA256,
    FORMAL_PARITY_PANEL_SHA256,
    FORMAL_PROFILE,
    FORMAL_QUALIFICATION_MATRIX_SHA256,
    FORMAL_QUALIFICATION_REPORT_SHA256,
)
from nodi_foundation.releases import write_release_manifest
from nodi_foundation.resources import (
    COMMITTED_MEMORY_LIMIT_BYTES,
    assert_resource_budget,
    system_committed_memory_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "releases/nodi-v2"
RECEIPT_PATH = ROOT / "v2_release_manifest.json"
CAPABILITY_REFERENCE_BLOCKS = 256
CAPABILITY_STATE_COUNT = 32_768
QUICKSTART_STATE_COUNT = 4_096
DEVELOPMENT_REFERENCE_BLOCKS = 4_096
DEVELOPMENT_STATE_COUNT = 524_288
DEVELOPMENT_PAIR_COUNT = 16_384
EVALUATION_REFERENCE_BLOCKS = 512
EVALUATION_STATE_COUNT = 65_536
EVALUATION_ANCHOR_COUNT = 2_048
REFERENCE_CHUNK = 64
DEVELOPMENT_SEED = 2026081821
EVALUATION_SEED = 2026081822
PAIR_CHUNK = 2_048

MECHANISM_GROUPS = {
    "CHANNEL_REFERENCE_GEOMETRY": (
        "channel_width",
        "channel_depth",
        "sidewall_angle",
        "beam_offset_longitudinal",
        "beam_offset_lateral",
    ),
    "PARTICLE_OPTICAL_STRENGTH": (
        "particle_diameter",
        "particle_n_real",
        "particle_n_imag",
    ),
    "PARTICLE_POSITION_OVERLAP": (
        "particle_longitudinal",
        "particle_lateral",
        "particle_depth",
    ),
    "SOURCE_ILLUMINATION_STATE": (
        "wavelength",
        "beam_waist",
        "incident_power",
        "source_polarization_azimuth",
        "source_ellipticity",
        "degree_of_polarization",
    ),
    "MEDIUM_WALL_CONTRAST": (
        "fill_refractive_index",
        "wall_refractive_index",
    ),
    "DETECTOR_SELECTION": (
        "collection_na",
        "analyzer_azimuth",
        "analyzer_ellipticity",
        "pupil_inner_radius",
        "pupil_outer_radius",
        "detector_sector_center",
        "detector_sector_width",
    ),
}


@cache
def _feature_rows() -> tuple[dict[str, Any], ...]:
    return capabilities().features


@cache
def _feature_ranges() -> dict[str, tuple[float, float]]:
    return {
        str(row["id"]): (
            float(row.get("formal_domain", row["domain"])[0]),
            float(row.get("formal_domain", row["domain"])[1]),
        )
        for row in _feature_rows()
    }


@cache
def _feature_groups() -> dict[str, str]:
    return {
        feature: group
        for group, features in MECHANISM_GROUPS.items()
        for feature in features
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(payload) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_table(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    try:
        pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _formal_metadata() -> dict[str, Any]:
    return {
        "profile": FORMAL_PROFILE,
        "feature_catalogue_hash": capabilities().catalogue_hash,
        "qualification_report_sha256": FORMAL_QUALIFICATION_REPORT_SHA256,
        "physics_implementation_sha256": FORMAL_IMPLEMENTATION_SHA256,
        "numerical_profile_sha256": FORMAL_NUMERICAL_PROFILE_SHA256,
        "qualification_matrix_sha256": FORMAL_QUALIFICATION_MATRIX_SHA256,
        "parity_panel_sha256": FORMAL_PARITY_PANEL_SHA256,
        "paper2_final_truth_eligible": True,
    }


def _read_manifest(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def _valid_release(directory: Path, release_name: str, count: int) -> bool:
    report = validate_release(directory)
    if not report.valid:
        return False
    manifest = _read_manifest(directory)
    metadata = manifest.get("metadata", {})
    observed = metadata.get("state_count", metadata.get("pair_count"))
    return metadata.get("release_name") == release_name and observed == count


def _reference_blocks(count: int, seed: int) -> tuple[SimulationState, ...]:
    sampler = qmc.Sobol(d=13, scramble=True, seed=seed)
    accepted: list[SimulationState] = []
    while len(accepted) < count:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            values = sampler.random(max(256, count - len(accepted)))
        for row in values:
            width = 6.0e-7 + float(row[0]) * 1.2e-6
            depth = 2.5e-7 + float(row[1]) * 7.5e-7
            angle = 82.0 + float(row[2]) * 8.0
            wavelength = 4.5e-7 + float(row[3]) * 2.5e-7
            waist = 7.0e-7 + float(row[4]) * 1.1e-6
            power = 0.25 + float(row[5]) * 3.75
            fill = 1.30 + float(row[11]) * 0.09
            wall = 1.41 + float(row[12]) * 0.13
            bottom = width - 2.0 * depth / math.tan(math.radians(angle))
            if bottom <= 3.0e-7:
                continue
            try:
                state = SimulationState(
                    geometry=GeometryState(width, depth, angle),
                    source=SourceState(
                        wavelength_m=wavelength,
                        waist_m=waist,
                        incident_power_W=power,
                        beam_offset_longitudinal_m=(float(row[6]) * 1.6 - 0.8) * waist,
                        beam_offset_lateral_m=(float(row[7]) * 1.6 - 0.8) * waist,
                        polarization_azimuth_rad=float(row[8]) * math.pi,
                        ellipticity_rad=(float(row[9]) - 0.5) * math.pi / 2.0,
                        degree_of_polarization=float(row[10]),
                    ),
                    environment=EnvironmentState(fill, wall),
                )
            except FoundationError:
                continue
            accepted.append(state)
            if len(accepted) == count:
                break
    return tuple(accepted)


def _particle_blocks() -> tuple[ParticleState, ...]:
    return tuple(
        ParticleState(*row)
        for row in (
            (3.0e-8, 1.34, 0.00),
            (5.0e-8, 1.38, 0.00),
            (7.0e-8, 1.45, 0.01),
            (9.0e-8, 1.55, 0.00),
            (1.05e-7, 1.38, 0.02),
            (1.2e-7, 1.65, 0.05),
            (1.35e-7, 1.80, 0.10),
            (1.5e-7, 2.00, 0.20),
        )
    )


def _position_blocks() -> tuple[PositionState, ...]:
    return (
        PositionState(0.0, 0.0, 0.5),
        PositionState(3.5e-7, -0.6, 0.25),
        PositionState(-3.5e-7, 0.6, 0.75),
        PositionState(1.5e-7, 0.25, 0.9),
    )


def _operator_blocks() -> tuple[ObservationOperatorState, ...]:
    return (
        ObservationOperatorState(),
        ObservationOperatorState(analyzer_azimuth_rad=math.pi / 4.0),
        ObservationOperatorState(
            analyzer_azimuth_rad=math.pi / 2.0,
            pupil_inner_radius=0.2,
            pupil_outer_radius=0.9,
            detector_sector_width_rad=math.pi,
        ),
        ObservationOperatorState(
            collection_na=0.75,
            analyzer_azimuth_rad=math.pi / 3.0,
            analyzer_ellipticity_rad=math.pi / 8.0,
            detector_sector_center_rad=3.0 * math.pi / 4.0,
            detector_sector_width_rad=math.pi / 2.0,
        ),
    )


def _nested_states(reference_count: int, seed: int) -> Iterator[SimulationState]:
    for reference in _reference_blocks(reference_count, seed):
        for particle in _particle_blocks():
            for position in _position_blocks():
                for operator in _operator_blocks():
                    try:
                        yield replace_state(reference, particle, position, operator)
                    except FoundationError as exc:
                        raise RuntimeError("predeclared nested state is invalid") from exc


def replace_state(
    reference: SimulationState,
    particle: ParticleState,
    position: PositionState,
    operator: ObservationOperatorState,
) -> SimulationState:
    payload = reference.to_payload()
    payload["particle"] = {
        "diameter_m": particle.diameter_m,
        "refractive_index_real": particle.refractive_index_real,
        "refractive_index_imag": particle.refractive_index_imag,
    }
    payload["position"] = {
        "longitudinal_m": position.longitudinal_m,
        "lateral_fraction": position.lateral_fraction,
        "depth_fraction": position.depth_fraction,
    }
    payload["observation"] = {
        "collection_na": operator.collection_na,
        "analyzer_azimuth_rad": operator.analyzer_azimuth_rad,
        "analyzer_ellipticity_rad": operator.analyzer_ellipticity_rad,
        "pupil_inner_radius": operator.pupil_inner_radius,
        "pupil_outer_radius": operator.pupil_outer_radius,
        "detector_sector_center_rad": operator.detector_sector_center_rad,
        "detector_sector_width_rad": operator.detector_sector_width_rad,
    }
    return SimulationState.from_mapping(payload)


def _fragment_matches(path: Path, states: tuple[SimulationState, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        table = pq.read_table(path, columns=["state_id", "physics_profile_id"])
    except (OSError, pa.ArrowException):
        return False
    return table["state_id"].to_pylist() == [state.state_id for state in states] and set(
        table["physics_profile_id"].to_pylist()
    ) == {FORMAL_PROFILE}


def _consolidate(paths: list[Path], target: Path) -> None:
    handle, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(handle)
    writer: pq.ParquetWriter | None = None
    try:
        for path in paths:
            table = pq.read_table(path)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
        if writer is None:
            raise RuntimeError("cannot consolidate an empty nested release")
        writer.close()
        writer = None
        os.replace(temporary, target)
    finally:
        if writer is not None:
            writer.close()
        if os.path.exists(temporary):
            os.unlink(temporary)


def _build_nested_release(
    directory: Path,
    *,
    release_name: str,
    reference_count: int,
    seed: int,
) -> dict[str, Any]:
    state_count = reference_count * 8 * 4 * 4
    if _valid_release(directory, release_name, state_count):
        return _read_manifest(directory)
    assert_resource_budget(1)
    references = _reference_blocks(reference_count, seed)
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".work"
    work.mkdir(parents=True, exist_ok=True)
    fragments: list[Path] = []
    started = time.monotonic()
    peak_commit = system_committed_memory_bytes()
    for offset in range(0, reference_count, REFERENCE_CHUNK):
        states = tuple(
            replace_state(reference, particle, position, operator)
            for reference in references[offset : offset + REFERENCE_CHUNK]
            for particle in _particle_blocks()
            for position in _position_blocks()
            for operator in _operator_blocks()
        )
        fragment = work / f"part-{offset // REFERENCE_CHUNK:05d}.parquet"
        fragments.append(fragment)
        if not _fragment_matches(fragment, states):
            rows = [result_row(simulate_state(state)) for state in states]
            _write_table(fragment, pa.Table.from_pylist(rows))
        committed = system_committed_memory_bytes()
        if committed is not None and (peak_commit is None or committed > peak_commit):
            peak_commit = committed
        print(
            canonical_json(
                {
                    "event": "nested_chunk",
                    "release": release_name,
                    "reference_blocks_complete": min(offset + REFERENCE_CHUNK, reference_count),
                    "reference_blocks_total": reference_count,
                }
            ),
            flush=True,
        )
    _consolidate(fragments, directory / "data.parquet")
    shutil.rmtree(work)
    elapsed = time.monotonic() - started
    metadata = {
        **_formal_metadata(),
        "release_name": release_name,
        "state_count": state_count,
        "seed": seed,
        "nested_design": {
            "reference_blocks": reference_count,
            "particle_assignments": 8,
            "positions": 4,
            "operators": 4,
        },
        "selected_workers": 1,
        "chunk_size_states": REFERENCE_CHUNK * 8 * 4 * 4,
        "elapsed_seconds": elapsed,
        "peak_observed_system_committed_memory_bytes": peak_commit,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
    }
    manifest = write_release_manifest(
        directory,
        release_type="NODI_DATASET_RELEASE",
        primary_files=("data.parquet",),
        metadata=metadata,
    )
    report = validate_release(directory)
    if not report.valid:
        raise RuntimeError(f"nested release validation failed: {report.errors}")
    return manifest


def _legal_pair(
    state: SimulationState, feature: str, bounds: tuple[float, float]
) -> tuple[SimulationState, SimulationState] | None:
    lower, upper = bounds
    for fractions in ((0.2, 0.8), (0.3, 0.7), (0.4, 0.6)):
        try:
            return (
                state_with_value(state, feature, lower + fractions[0] * (upper - lower)),
                state_with_value(state, feature, lower + fractions[1] * (upper - lower)),
            )
        except FoundationError:
            continue
    return None


def _capability_effects(
    states: tuple[SimulationState, ...],
) -> tuple[list[dict[str, Any]], list[str], str, str]:
    ranges = _feature_ranges()
    groups = _feature_groups()
    pair_records: list[tuple[str, SimulationState, SimulationState]] = []
    for feature_index, feature in enumerate(sorted(ranges)):
        accepted = 0
        cursor = 0
        while accepted < 64 and cursor < len(states):
            anchor = states[(feature_index * 977 + cursor * 509) % len(states)]
            cursor += 1
            pair = _legal_pair(anchor, feature, ranges[feature])
            if pair is None:
                continue
            pair_records.append((feature, pair[0], pair[1]))
            accepted += 1
        if accepted != 64:
            raise RuntimeError(f"insufficient legal formal pairs for {feature}: {accepted}")
    pair_results = [
        (simulate_state(low), simulate_state(high)) for _feature, low, high in pair_records
    ]
    effects: dict[str, list[float]] = defaultdict(list)
    exposure_fractions: dict[str, list[float]] = defaultdict(list)
    for (feature, _low_state, _high_state), (low, high) in zip(
        pair_records, pair_results, strict=True
    ):
        delta = np.asarray(
            [high.S_W - low.S_W, 2.0 * (high.C_r_W - low.C_r_W), 2.0 * (high.C_i_W - low.C_i_W)]
        )
        low_vector = np.asarray([low.S_W, 2.0 * low.C_r_W, 2.0 * low.C_i_W])
        high_vector = np.asarray([high.S_W, 2.0 * high.C_r_W, 2.0 * high.C_i_W])
        norm = float(np.linalg.norm(delta))
        scale = max(float(np.linalg.norm(low_vector)), float(np.linalg.norm(high_vector)), 1.0e-24)
        effects[feature].append(norm / scale)
        exposure_fractions[feature].append(0.0 if norm == 0.0 else abs(float(delta[0])) / norm)
    rows = []
    retained = []
    for feature in sorted(ranges):
        values = np.asarray(effects[feature], dtype=np.float64)
        fractions = np.asarray(exposure_fractions[feature], dtype=np.float64)
        median = float(np.median(values))
        q90 = float(np.quantile(values, 0.9))
        fraction_span = float(np.quantile(fractions, 0.9) - np.quantile(fractions, 0.1))
        keep = q90 > 1.0e-6
        if keep:
            retained.append(feature)
        rows.append(
            {
                "feature": feature,
                "mechanism_group": groups[feature],
                "formal_status": next(
                    row["formal_status"] for row in _feature_rows() if row["id"] == feature
                ),
                "legal_pair_count": len(values),
                "median_normalized_effect": median,
                "q90_normalized_effect": q90,
                "robust_exposure_fraction_span": fraction_span,
                "retained": keep,
                "retention_rule": "Q90_NORMALIZED_COMPLEX_OUTPUT_EFFECT_GT_1E-6",
            }
        )
    qualified = [row for row in rows if row["retained"]]
    if len(qualified) < 2:
        raise RuntimeError("formal capability sprint retained fewer than two features")
    primary = max(qualified, key=lambda row: row["median_normalized_effect"])
    replication = max(
        (row for row in qualified if row["mechanism_group"] != primary["mechanism_group"]),
        key=lambda row: row["median_normalized_effect"],
    )
    return rows, retained, str(primary["feature"]), str(replication["feature"])


def _build_capability_freeze(capability: dict[str, Any], seed: int) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V2"
    release_name = "NODI-QUALIFICATION-PROFILE-V2"
    if _valid_release(directory, release_name, CAPABILITY_STATE_COUNT):
        return _read_manifest(directory)
    states = tuple(_nested_states(CAPABILITY_REFERENCE_BLOCKS, seed))
    rows, retained, primary, replication = _capability_effects(states)
    directory.mkdir(parents=True, exist_ok=True)
    _write_table(directory / "qualification.parquet", pa.Table.from_pylist(rows))
    metadata = {
        **_formal_metadata(),
        "release_name": release_name,
        "state_count": CAPABILITY_STATE_COUNT,
        "capability_release_id": capability["release_id"],
        "candidate_feature_count": len(rows),
        "retained_feature_count": len(retained),
        "retained_features": retained,
        "primary_exposure_family": primary,
        "replication_exposure_family": replication,
        "selection_rule": "MAX_MEDIAN_EFFECT_WITH_DIFFERENT_MECHANISM_REPLICATION",
        "feature_campaign_state": "FROZEN_SINGLE_FORMAL_SPRINT",
    }
    return write_release_manifest(
        directory,
        release_type="NODI_QUALIFICATION_PROFILE_RELEASE",
        primary_files=("qualification.parquet",),
        metadata=metadata,
    )


def _release_summary(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(directory.relative_to(ROOT)).replace("\\", "/"),
        "release_id": manifest["release_id"],
        "release_type": manifest["release_type"],
        "manifest_sha256": canonical_sha256(manifest),
        "primary_files": manifest["files"],
        "valid": validate_release(directory).valid,
    }


def run_sprint(seed: int) -> dict[str, Any]:
    capability_dir = RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V2"
    capability = _build_nested_release(
        capability_dir,
        release_name="NODI-CAPABILITY-SPRINT-V2",
        reference_count=CAPABILITY_REFERENCE_BLOCKS,
        seed=seed,
    )
    qualification = _build_capability_freeze(capability, seed)
    receipt = {
        "manifest_schema_version": 2,
        "phase": "R3_FORMAL_CAPABILITY_FREEZE",
        "status": "PASS",
        "profile": FORMAL_PROFILE,
        "release_root": "releases/nodi-v2",
        "maximum_workers": 24,
        "selected_workers": 1,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
        "qualification_report_sha256": FORMAL_QUALIFICATION_REPORT_SHA256,
        "feature_catalogue_hash": capabilities().catalogue_hash,
        "retained_features": qualification["metadata"]["retained_features"],
        "primary_exposure_family": qualification["metadata"]["primary_exposure_family"],
        "replication_exposure_family": qualification["metadata"][
            "replication_exposure_family"
        ],
        "releases": {
            "capability_sprint": _release_summary(capability_dir, capability),
            "qualification_profile": _release_summary(
                RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V2", qualification
            ),
        },
        "paper2_final_data_state": "BLOCKED_UNTIL_R4_RELEASES_COMPLETE",
    }
    _atomic_json(RECEIPT_PATH, receipt)
    return receipt


def _build_quickstart(capability: dict[str, Any]) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-QUICKSTART-V2"
    release_name = "NODI-QUICKSTART-V2"
    if _valid_release(directory, release_name, QUICKSTART_STATE_COUNT):
        return _read_manifest(directory)
    source = pq.read_table(RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V2" / "data.parquet")
    subset = source.sort_by([("state_id", "ascending")]).slice(0, QUICKSTART_STATE_COUNT)
    directory.mkdir(parents=True, exist_ok=True)
    _write_table(directory / "data.parquet", subset)
    manifest = write_release_manifest(
        directory,
        release_type="NODI_DATASET_RELEASE",
        primary_files=("data.parquet",),
        metadata={
            **_formal_metadata(),
            "release_name": release_name,
            "state_count": QUICKSTART_STATE_COUNT,
            "source_release_id": capability["release_id"],
            "selection": "LEXICOGRAPHIC_STATE_ID_FIRST_4096_NO_RECOMPUTE",
        },
    )
    report = validate_release(directory)
    if not report.valid:
        raise RuntimeError(f"quickstart release validation failed: {report.errors}")
    return manifest


def _state_from_flat_row(row: dict[str, Any]) -> SimulationState:
    return SimulationState.from_mapping(
        {
            "geometry": {
                "width_m": row["geometry.width_m"],
                "depth_m": row["geometry.depth_m"],
                "sidewall_angle_deg": row["geometry.sidewall_angle_deg"],
            },
            "particle": {
                "diameter_m": row["particle.diameter_m"],
                "refractive_index_real": row["particle.refractive_index_real"],
                "refractive_index_imag": row["particle.refractive_index_imag"],
            },
            "position": {
                "longitudinal_m": row["position.longitudinal_m"],
                "lateral_fraction": row["position.lateral_fraction"],
                "depth_fraction": row["position.depth_fraction"],
            },
            "source": {
                "wavelength_m": row["source.wavelength_m"],
                "waist_m": row["source.waist_m"],
                "incident_power_W": row["source.incident_power_W"],
                "beam_offset_longitudinal_m": row["source.beam_offset_longitudinal_m"],
                "beam_offset_lateral_m": row["source.beam_offset_lateral_m"],
                "polarization_azimuth_rad": row["source.polarization_azimuth_rad"],
                "ellipticity_rad": row["source.ellipticity_rad"],
                "degree_of_polarization": row["source.degree_of_polarization"],
            },
            "environment": {
                "fill_refractive_index": row["environment.fill_refractive_index"],
                "wall_refractive_index": row["environment.wall_refractive_index"],
            },
            "observation": {
                "collection_na": row["observation.collection_na"],
                "analyzer_azimuth_rad": row["observation.analyzer_azimuth_rad"],
                "analyzer_ellipticity_rad": row["observation.analyzer_ellipticity_rad"],
                "pupil_inner_radius": row["observation.pupil_inner_radius"],
                "pupil_outer_radius": row["observation.pupil_outer_radius"],
                "detector_sector_center_rad": row[
                    "observation.detector_sector_center_rad"
                ],
                "detector_sector_width_rad": row["observation.detector_sector_width_rad"],
            },
            "physics_profile_id": row["physics_profile_id"],
        }
    )


def _feature_value(state: SimulationState, feature: str) -> float:
    path = next(row["path"] for row in _feature_rows() if row["id"] == feature)
    group, field = str(path).split(".", 1)
    return float(state.to_payload()[group][field])


def _pair_id(
    feature: str,
    anchor: SimulationState,
    low_state: SimulationState,
    high_state: SimulationState,
) -> str:
    return canonical_sha256(
        {
            "anchor_state_id": anchor.state_id,
            "feature": feature,
            "low_state_id": low_state.state_id,
            "high_state_id": high_state.state_id,
        }
    )


def _pair_row(
    feature: str,
    anchor: SimulationState,
    low_state: SimulationState,
    high_state: SimulationState,
    low_value: float,
    high_value: float,
    low: StateResult,
    high: StateResult,
) -> dict[str, Any]:
    return {
        "pair_id": _pair_id(feature, anchor, low_state, high_state),
        "physics_profile_id": low.physics_profile_id,
        "anchor_state_id": anchor.state_id,
        "feature": feature,
        "low_value": low_value,
        "high_value": high_value,
        "low_state_id": low_state.state_id,
        "high_state_id": high_state.state_id,
        "low_S_W": low.S_W,
        "high_S_W": high.S_W,
        "delta_S_W": high.S_W - low.S_W,
        "low_C_r_W": low.C_r_W,
        "high_C_r_W": high.C_r_W,
        "delta_C_r_W": high.C_r_W - low.C_r_W,
        "low_C_i_W": low.C_i_W,
        "high_C_i_W": high.C_i_W,
        "delta_C_i_W": high.C_i_W - low.C_i_W,
        "low_Y_0_W": low.Y_0_W,
        "high_Y_0_W": high.Y_0_W,
        "delta_Y_0_W": high.Y_0_W - low.Y_0_W,
    }


def _intervention_records(
    development_directory: Path,
    features: tuple[str, str],
) -> list[
    tuple[str, SimulationState, SimulationState, SimulationState, float, float]
]:
    input_columns = [
        name
        for name in pq.read_schema(development_directory / "data.parquet").names
        if name.startswith(
            (
                "geometry.",
                "particle.",
                "position.",
                "source.",
                "environment.",
                "observation.",
            )
        )
        or name == "physics_profile_id"
    ]
    records: list[
        tuple[str, SimulationState, SimulationState, SimulationState, float, float]
    ] = []
    counts = {feature: 0 for feature in features}
    parquet = pq.ParquetFile(development_directory / "data.parquet")
    global_index = 0
    for batch in parquet.iter_batches(batch_size=8_192, columns=input_columns):
        for row in batch.to_pylist():
            remainder = global_index % 64
            global_index += 1
            if remainder >= len(features):
                continue
            feature = features[remainder]
            if counts[feature] >= DEVELOPMENT_PAIR_COUNT // len(features):
                continue
            anchor = _state_from_flat_row(row)
            pair = _legal_pair(anchor, feature, _feature_ranges()[feature])
            if pair is None:
                continue
            low, high = pair
            records.append(
                (
                    feature,
                    anchor,
                    low,
                    high,
                    _feature_value(low, feature),
                    _feature_value(high, feature),
                )
            )
            counts[feature] += 1
    target = DEVELOPMENT_PAIR_COUNT // len(features)
    if any(count != target for count in counts.values()):
        raise RuntimeError(f"insufficient predeclared intervention anchors: {counts}")
    return records


def _pair_fragment_matches(
    path: Path,
    records: list[
        tuple[str, SimulationState, SimulationState, SimulationState, float, float]
    ],
) -> bool:
    if not path.is_file():
        return False
    try:
        table = pq.read_table(path, columns=["pair_id", "physics_profile_id"])
    except (OSError, pa.ArrowException):
        return False
    expected = [_pair_id(record[0], record[1], record[2], record[3]) for record in records]
    return table["pair_id"].to_pylist() == expected and set(
        table["physics_profile_id"].to_pylist()
    ) == {FORMAL_PROFILE}


def _build_interventions(
    development: dict[str, Any],
    qualification: dict[str, Any],
) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V2"
    release_name = "NODI-ATLAS-DEV-INTERVENTIONS-V2"
    if _valid_release(directory, release_name, DEVELOPMENT_PAIR_COUNT):
        return _read_manifest(directory)
    features = (
        str(qualification["metadata"]["primary_exposure_family"]),
        str(qualification["metadata"]["replication_exposure_family"]),
    )
    records = _intervention_records(RELEASE_ROOT / "NODI-ATLAS-DEV-V2", features)
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".work"
    work.mkdir(parents=True, exist_ok=True)
    fragments: list[Path] = []
    for offset in range(0, len(records), PAIR_CHUNK):
        chunk = records[offset : offset + PAIR_CHUNK]
        fragment = work / f"part-{offset // PAIR_CHUNK:05d}.parquet"
        fragments.append(fragment)
        if not _pair_fragment_matches(fragment, chunk):
            results = [
                (simulate_state(record[2]), simulate_state(record[3])) for record in chunk
            ]
            rows = [
                _pair_row(*record, result[0], result[1])
                for record, result in zip(chunk, results, strict=True)
            ]
            _write_table(fragment, pa.Table.from_pylist(rows))
        print(
            canonical_json(
                {
                    "event": "intervention_chunk",
                    "pairs_complete": min(offset + PAIR_CHUNK, len(records)),
                    "pairs_total": len(records),
                }
            ),
            flush=True,
        )
    _consolidate(fragments, directory / "pairs.parquet")
    shutil.rmtree(work)
    manifest = write_release_manifest(
        directory,
        release_type="NODI_PAIR_RELEASE",
        primary_files=("pairs.parquet",),
        metadata={
            **_formal_metadata(),
            "release_name": release_name,
            "pair_count": DEVELOPMENT_PAIR_COUNT,
            "source_release_id": development["release_id"],
            "features": list(features),
            "pairs_per_feature": DEVELOPMENT_PAIR_COUNT // len(features),
            "anchor_selection": "EVERY_64TH_DEVELOPMENT_ROW_OFFSETS_0_AND_1",
            "selection": "FROZEN_PRIMARY_AND_DIFFERENT_MECHANISM_REPLICATION",
        },
    )
    report = validate_release(directory)
    if not report.valid:
        raise RuntimeError(f"intervention release validation failed: {report.errors}")
    return manifest


def _build_evaluation_releases(
    development: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_directory = RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V2"
    label_directory = RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V2.sealed"
    input_name = "NODI-ATLAS-EVAL-INPUTS-V2"
    label_name = "NODI-ATLAS-EVAL-LABELS-V2.sealed"
    if _valid_release(
        input_directory, input_name, EVALUATION_STATE_COUNT
    ) and _valid_release(label_directory, label_name, EVALUATION_STATE_COUNT):
        return _read_manifest(input_directory), _read_manifest(label_directory)
    transition = RELEASE_ROOT / ".evaluation-full-v2"
    full_manifest = _build_nested_release(
        transition,
        release_name="NODI-EVALUATION-FULL-V2-TRANSITION",
        reference_count=EVALUATION_REFERENCE_BLOCKS,
        seed=EVALUATION_SEED,
    )
    full = pq.read_table(transition / "data.parquet")
    identifiers = full["state_id"].to_pylist()
    development_ids = set(
        pq.read_table(
            RELEASE_ROOT / "NODI-ATLAS-DEV-V2" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    if development_ids.intersection(identifiers):
        raise RuntimeError("Development and Evaluation state identities overlap")
    anchor_ids = set(sorted(identifiers)[:EVALUATION_ANCHOR_COUNT])
    input_columns = [
        name
        for name in full.column_names
        if name.startswith(
            (
                "geometry.",
                "particle.",
                "position.",
                "source.",
                "environment.",
                "observation.",
                "derived.",
            )
        )
        or name
        in {
            "state_id",
            "physics_profile_id",
            "fidelity_class",
            "claim_ceiling",
            "reference_block_id",
            "particle_block_id",
            "position_block_id",
            "operator_block_id",
            "numerical_receipt_ids",
            "numerical_status",
            "applicability_profile_id",
            "operator_qualification_status",
            "engine_version",
            "schema_version",
            "feature_version",
            "config_hash",
        }
    ]
    input_table = full.select(input_columns).append_column(
        "is_intervention_anchor",
        pa.array([identifier in anchor_ids for identifier in identifiers], type=pa.bool_()),
    )
    label_table = full.select(
        [
            "state_id",
            "physics_profile_id",
            "B_bg_W",
            "S_W",
            "C_r_W",
            "C_i_W",
            "Y_0_W",
            "eta_real",
            "eta_imag",
            "eta_abs",
            "result_hash",
        ]
    )
    label_directory.mkdir(parents=True, exist_ok=True)
    _write_table(label_directory / "labels.parquet.sealed", label_table)
    label_manifest = write_release_manifest(
        label_directory,
        release_type="NODI_SEALED_LABEL_RELEASE",
        primary_files=("labels.parquet.sealed",),
        metadata={
            **_formal_metadata(),
            "release_name": label_name,
            "state_count": EVALUATION_STATE_COUNT,
            "seed": EVALUATION_SEED,
            "full_transition_release_id": full_manifest["release_id"],
            "access_state": "SEALED_OWNER_ONLY",
            "delivery_state": "NOT_RELEASED_TO_DOWNSTREAM",
            "sealing_method": "CONTENT_ADDRESSED_SEPARATE_OWNER_CUSTODY",
        },
    )
    input_directory.mkdir(parents=True, exist_ok=True)
    _write_table(input_directory / "inputs.parquet", input_table)
    input_manifest = write_release_manifest(
        input_directory,
        release_type="NODI_EVALUATION_INPUT_RELEASE",
        primary_files=("inputs.parquet",),
        metadata={
            **_formal_metadata(),
            "release_name": input_name,
            "state_count": EVALUATION_STATE_COUNT,
            "intervention_anchor_count": EVALUATION_ANCHOR_COUNT,
            "seed": EVALUATION_SEED,
            "development_release_id": development["release_id"],
            "label_commitment_release_id": label_manifest["release_id"],
            "label_delivery_state": "SEALED_NOT_DELIVERED",
            "development_evaluation_shared_state_count": 0,
        },
    )
    for directory in (label_directory, input_directory):
        report = validate_release(directory)
        if not report.valid:
            raise RuntimeError(f"evaluation release validation failed: {report.errors}")
    shutil.rmtree(transition)
    return input_manifest, label_manifest


def _final_acceptance(features: tuple[str, str]) -> dict[str, Any]:
    capability_ids = set(
        pq.read_table(
            RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V2" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    quickstart_ids = set(
        pq.read_table(
            RELEASE_ROOT / "NODI-QUICKSTART-V2" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    development_ids = set(
        pq.read_table(
            RELEASE_ROOT / "NODI-ATLAS-DEV-V2" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    evaluation = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V2" / "inputs.parquet",
        columns=["state_id", "is_intervention_anchor"],
    )
    evaluation_ids = evaluation["state_id"].to_pylist()
    label_ids = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V2.sealed" / "labels.parquet.sealed",
        columns=["state_id"],
    )["state_id"].to_pylist()
    pairs = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V2" / "pairs.parquet",
        columns=["pair_id", "feature"],
    )
    feature_counts = {
        feature: pairs["feature"].to_pylist().count(feature)
        for feature in sorted(set(pairs["feature"].to_pylist()))
    }
    acceptance = {
        "quickstart_is_capability_subset_without_recompute": (
            len(quickstart_ids) == QUICKSTART_STATE_COUNT
            and quickstart_ids <= capability_ids
        ),
        "development_unique_state_count": len(development_ids),
        "evaluation_unique_state_count": len(set(evaluation_ids)),
        "development_evaluation_shared_state_count": len(
            development_ids.intersection(evaluation_ids)
        ),
        "evaluation_input_label_identity_and_order_match": evaluation_ids == label_ids,
        "evaluation_intervention_anchor_count": sum(
            evaluation["is_intervention_anchor"].to_pylist()
        ),
        "development_intervention_unique_pair_count": len(
            set(pairs["pair_id"].to_pylist())
        ),
        "development_intervention_feature_counts": feature_counts,
        "all_release_profiles": [FORMAL_PROFILE],
        "v1_data_or_feature_selection_imported": False,
    }
    expected_features = {
        feature: DEVELOPMENT_PAIR_COUNT // len(features) for feature in features
    }
    if not (
        acceptance["quickstart_is_capability_subset_without_recompute"]
        and acceptance["development_unique_state_count"] == DEVELOPMENT_STATE_COUNT
        and acceptance["evaluation_unique_state_count"] == EVALUATION_STATE_COUNT
        and acceptance["development_evaluation_shared_state_count"] == 0
        and acceptance["evaluation_input_label_identity_and_order_match"]
        and acceptance["evaluation_intervention_anchor_count"] == EVALUATION_ANCHOR_COUNT
        and acceptance["development_intervention_unique_pair_count"]
        == DEVELOPMENT_PAIR_COUNT
        and feature_counts == expected_features
    ):
        raise RuntimeError(f"v2 cross-release acceptance failed: {acceptance}")
    return acceptance


def run_all(seed: int) -> dict[str, Any]:
    capability_directory = RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V2"
    capability = _build_nested_release(
        capability_directory,
        release_name="NODI-CAPABILITY-SPRINT-V2",
        reference_count=CAPABILITY_REFERENCE_BLOCKS,
        seed=seed,
    )
    qualification = _build_capability_freeze(capability, seed)
    quickstart = _build_quickstart(capability)
    development_directory = RELEASE_ROOT / "NODI-ATLAS-DEV-V2"
    development = _build_nested_release(
        development_directory,
        release_name="NODI-ATLAS-DEV-V2",
        reference_count=DEVELOPMENT_REFERENCE_BLOCKS,
        seed=DEVELOPMENT_SEED,
    )
    interventions = _build_interventions(development, qualification)
    evaluation_inputs, evaluation_labels = _build_evaluation_releases(development)
    directories = {
        "capability_sprint": capability_directory,
        "qualification_profile": RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V2",
        "quickstart": RELEASE_ROOT / "NODI-QUICKSTART-V2",
        "development_atlas": development_directory,
        "development_interventions": (
            RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V2"
        ),
        "evaluation_inputs": RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V2",
        "evaluation_labels": RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V2.sealed",
    }
    manifests = {
        "capability_sprint": capability,
        "qualification_profile": qualification,
        "quickstart": quickstart,
        "development_atlas": development,
        "development_interventions": interventions,
        "evaluation_inputs": evaluation_inputs,
        "evaluation_labels": evaluation_labels,
    }
    releases = {
        name: _release_summary(directories[name], manifest)
        for name, manifest in manifests.items()
    }
    if not all(release["valid"] for release in releases.values()):
        raise RuntimeError("one or more v2 releases failed final validation")
    selected_features = (
        str(qualification["metadata"]["primary_exposure_family"]),
        str(qualification["metadata"]["replication_exposure_family"]),
    )
    acceptance = _final_acceptance(selected_features)
    receipt = {
        "manifest_schema_version": 2,
        "product": "NODI Simulation Foundation",
        "version": "2.0.0",
        "release_date": "2026-08-18",
        "phase": "R4_FORMAL_REFERENCE_RELEASES",
        "status": "PASS",
        "profile": FORMAL_PROFILE,
        "release_root": "releases/nodi-v2",
        "maximum_workers": 24,
        "selected_workers": 1,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
        "qualification_report_sha256": FORMAL_QUALIFICATION_REPORT_SHA256,
        "feature_catalogue_hash": capabilities().catalogue_hash,
        "primary_exposure_family": qualification["metadata"][
            "primary_exposure_family"
        ],
        "replication_exposure_family": qualification["metadata"][
            "replication_exposure_family"
        ],
        "feature_campaign_state": "FROZEN_SINGLE_FORMAL_SPRINT",
        "development_size_state": "FROZEN_SINGLE_524288_STATE_ATLAS",
        "label_delivery_state": "SEALED_NOT_DELIVERED",
        "paper2_final_data_state": "ELIGIBLE_FORMAL_M1_REFERENCE_WITH_DECLARED_LIMITS",
        "source_archive": {
            "mode": "GIT_ANNOTATED_TAG",
            "tag": "v2.0.0",
            "repository": "https://github.com/Shaughn0419/NODI-Simulation-Foundation",
        },
        "software_delivery": {
            "wheel": "nodi_foundation-2.0.0-py3-none-any.whl",
            "wheel_sha256_location": "GITHUB_RELEASE_NOTES",
            "python_requires": ">=3.12,<3.13",
        },
        "acceptance": acceptance,
        "releases": releases,
    }
    _atomic_json(RECEIPT_PATH, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sprint", "all"), default="all")
    parser.add_argument("--seed", type=int, default=2026081802)
    args = parser.parse_args()
    receipt = run_sprint(args.seed) if args.phase == "sprint" else run_all(args.seed)
    print(canonical_json({"status": receipt["status"], "phase": receipt["phase"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
