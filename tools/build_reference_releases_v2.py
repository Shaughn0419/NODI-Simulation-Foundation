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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sprint",), default="sprint")
    parser.add_argument("--seed", type=int, default=2026081802)
    args = parser.parse_args()
    receipt = run_sprint(args.seed)
    print(canonical_json({"status": receipt["status"], "phase": receipt["phase"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
