"""Build the current v5 exact-support formal reference-data products."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
import warnings
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from scipy.stats import qmc

from nodi_foundation import (
    EnvironmentState,
    ExecutionSpec,
    GeometryState,
    ObservationOperatorState,
    ParticleState,
    PositionState,
    SimulationState,
    SourceState,
    StateResult,
    capabilities,
    simulate_batch,
    simulate_state,
    validate_release,
)
from nodi_foundation.datasets import result_row, state_with_value
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import canonical_json, canonical_sha256, dry_etch_bottom_width
from nodi_foundation.profiles import (
    FORMAL_IMPLEMENTATION_SHA256,
    FORMAL_NUMERICAL_PROFILE_SHA256,
    FORMAL_CONTROL_REGRESSION_SHA256,
    FORMAL_PROFILE,
    FORMAL_QUALIFICATION_MATRIX_SHA256,
    FORMAL_QUALIFICATION_REPORT_SHA256,
)
from nodi_foundation.releases import write_release_manifest
from nodi_foundation.resources import (
    COMMITTED_MEMORY_EMERGENCY_STOP_BYTES,
    COMMITTED_MEMORY_LIMIT_BYTES,
    COMMITTED_MEMORY_SOFT_STOP_BYTES,
    FULL_RUN_LAUNCH_HEADROOM_BYTES,
    assert_resource_budget,
    system_committed_memory_bytes,
)

RELEASE_ROOT = ROOT / "releases/nodi-v5"
RECEIPT_PATH = ROOT / "v5_release_manifest.json"
CAPABILITY_REFERENCE_BLOCKS = 256
CAPABILITY_STATE_COUNT = 32_768
QUICKSTART_STATE_COUNT = 4_096
DEVELOPMENT_REFERENCE_BLOCKS = 4_096
DEVELOPMENT_STATE_COUNT = 524_288
DEVELOPMENT_PAIR_COUNT = 16_384
EVALUATION_REFERENCE_BLOCKS = 1_024
EVALUATION_STATE_COUNT = 131_072
EVALUATION_ANCHOR_COUNT = 4_096
REFERENCE_CHUNK = 8
DEVELOPMENT_SEED = 2026081921
EVALUATION_SEED = 2026081922
PAIR_CHUNK = 512
WHEEL_NAME = "nodi_foundation-5.0.0-py3-none-any.whl"
DEFAULT_BOUNDARY_POLICY = "UNPOLARIZED_BOUNDARY_V1"
EVALUATION_BOUNDARY_POLICY = "PARTIALLY_POLARIZED_BOUNDARY_V1"

PARALLELISM_SELECTION = {
    "selected_workers": 4,
    "selection_rule": "USER_SELECTED_CURRENT_RELEASE_EXECUTION_CONTRACT",
    "selection_date": "2026-08-18",
    "purpose": "BOUNDED_REPRODUCIBLE_FORMAL_RELEASE_RECOMPUTATION",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

MECHANISM_GROUPS = {
    "CHANNEL_REFERENCE_GEOMETRY": (
        "channel_width",
        "channel_depth",
        "sidewall_angle",
    ),
    "PARTICLE_OPTICAL_STRENGTH": (
        "particle_diameter",
        "particle_n_real",
        "particle_n_imag",
    ),
    "PARTICLE_POSITION_OVERLAP": (
        "particle_longitudinal_over_w0",
        "particle_lateral",
        "particle_depth",
    ),
    "SOURCE_ILLUMINATION_STATE": (
        "wavelength",
        "beam_waist",
        "normalization_power",
        "beam_offset_longitudinal_over_w0",
        "beam_offset_lateral_over_w0",
        "source_polarization_azimuth",
        "source_ellipticity",
        "degree_of_polarization",
    ),
    "MEDIUM_WALL_CONTRAST": (
        "fill_refractive_index",
        "wall_refractive_index",
        "effective_wall_exclusion",
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
            float(
                row.get(
                    "reference_release_domain",
                    row.get("formal_domain", row["domain"]),
                )[0]
            ),
            float(
                row.get(
                    "reference_release_domain",
                    row.get("formal_domain", row["domain"]),
                )[1]
            ),
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


def _stabilize_result_table_schema(table: pa.Table) -> pa.Table:
    name = "coupling_undefined_reason"
    index = table.schema.get_field_index(name)
    if index < 0:
        return table
    field = table.schema.field(index)
    if pa.types.is_string(field.type):
        return table
    if not pa.types.is_null(field.type):
        raise RuntimeError(f"unexpected {name} type: {field.type}")
    values = pa.array(table.column(index).to_pylist(), type=pa.string())
    return table.set_column(index, pa.field(name, pa.string(), nullable=True), values)


def _formal_metadata() -> dict[str, Any]:
    return {
        "profile": FORMAL_PROFILE,
        "feature_catalogue_hash": capabilities().catalogue_hash,
        "qualification_report_sha256": FORMAL_QUALIFICATION_REPORT_SHA256,
        "physics_implementation_sha256": FORMAL_IMPLEMENTATION_SHA256,
        "numerical_profile_sha256": FORMAL_NUMERICAL_PROFILE_SHA256,
        "qualification_matrix_sha256": FORMAL_QUALIFICATION_MATRIX_SHA256,
        "scaling_control_regression_sha256": FORMAL_CONTROL_REGRESSION_SHA256,
        "formal_reference_label_eligible": True,
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


def _boundary_reference_blocks(
    seed: int,
    boundary_policy: str = DEFAULT_BOUNDARY_POLICY,
) -> tuple[SimulationState, ...]:
    if boundary_policy not in {
        DEFAULT_BOUNDARY_POLICY,
        EVALUATION_BOUNDARY_POLICY,
    }:
        raise ValueError(f"unsupported boundary policy: {boundary_policy}")
    rows: list[tuple[float, float, float, float, float, float]] = [
        (2.0e-7, 2.0e-7, 90.0, 4.0e-7, 9.0e-7, 0.0),
        (2.0e-6, 2.0e-6, 90.0, 9.0e-7, 1.8e-6, 2.0e-8),
        (4.0e-7, 2.0e-6, 90.0, 6.0e-7, 1.2e-6, 0.0),
        (2.0e-6, 2.0e-7, 90.0, 5.0e-7, 9.0e-7, 2.0e-8),
    ]
    for index, angle in enumerate((70.0, 72.5, 75.0, 77.5, 80.0, 82.5, 85.0, 87.0)):
        depth = 2.0e-6
        rows.append(
            (
                2.0 * depth / math.tan(math.radians(angle)),
                depth,
                angle,
                4.0e-7 + index * (5.0e-7 / 7.0),
                9.0e-7 + index * (9.0e-7 / 7.0),
                (0.0, 2.0e-9, 1.0e-8, 2.0e-8)[index % 4],
            )
        )
    for index, angle in enumerate((70.0, 75.0, 80.0, 85.0)):
        depth = 1.5e-6
        bottom_width = 2.0e-8
        rows.append(
            (
                bottom_width + 2.0 * depth / math.tan(math.radians(angle)),
                depth,
                angle,
                5.0e-7 + index * 1.0e-7,
                1.0e-6 + index * 2.0e-7,
                (0.0, 5.0e-9, 1.0e-8, 2.0e-8)[index],
            )
        )
    states = []
    for index, (width, depth, angle, wavelength, waist, exclusion) in enumerate(rows):
        phase_fraction = ((seed % 10_007) + 101 * index) % 10_007 / 10_007
        degree_of_polarization = (
            0.0
            if boundary_policy == DEFAULT_BOUNDARY_POLICY
            else 0.05 * (index + 1)
        )
        states.append(
            SimulationState(
                geometry=GeometryState(width, depth, angle),
                particle=ParticleState(2.0e-8, 1.34, 0.0),
                source=SourceState(
                    wavelength_m=wavelength,
                    waist_m=waist,
                    normalization_power_W=1.0,
                    polarization_azimuth_rad=phase_fraction * math.pi,
                    degree_of_polarization=degree_of_polarization,
                ),
                environment=EnvironmentState(
                    min(1.40, 1.30 + 0.10 * index / (len(rows) - 1)),
                    min(1.55, 1.42 + 0.13 * index / (len(rows) - 1)),
                    exclusion,
                ),
            )
        )
    return tuple(states)


def _reference_blocks(
    count: int,
    seed: int,
    *,
    boundary_policy: str = DEFAULT_BOUNDARY_POLICY,
) -> tuple[SimulationState, ...]:
    sampler = qmc.Sobol(d=13, scramble=True, seed=seed)
    accepted = list(_boundary_reference_blocks(seed, boundary_policy)[:count])
    identifiers = {state.state_id for state in accepted}
    while len(accepted) < count:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            values = sampler.random(max(256, count - len(accepted)))
        for row in values:
            width = 2.0e-7 + float(row[0]) * 1.8e-6
            depth = 2.0e-7 + float(row[1]) * 1.8e-6
            angle = 70.0 + float(row[2]) * 20.0
            wavelength = 4.0e-7 + float(row[3]) * 5.0e-7
            minimum_waist = max(5.0e-7, wavelength)
            waist = minimum_waist + float(row[4]) * (2.0e-6 - minimum_waist)
            fill = 1.30 + float(row[10]) * 0.09
            wall = 1.41 + float(row[11]) * 0.13
            exclusion = (
                0.0
                if len(accepted) % 16 == 0
                else 2.0e-9 + float(row[12]) * 1.8e-8
            )
            try:
                state = SimulationState(
                    geometry=GeometryState(width, depth, angle),
                    particle=ParticleState(2.0e-8, 1.34, 0.0),
                    source=SourceState(
                        wavelength_m=wavelength,
                        waist_m=waist,
                        normalization_power_W=1.0,
                        beam_offset_longitudinal_over_w0=float(row[5]) * 1.6 - 0.8,
                        beam_offset_lateral_over_w0=float(row[6]) * 1.6 - 0.8,
                        polarization_azimuth_rad=float(row[7]) * math.pi,
                        ellipticity_rad=(float(row[8]) - 0.5) * math.pi / 2.0,
                        degree_of_polarization=float(row[9]),
                    ),
                    environment=EnvironmentState(fill, wall, exclusion),
                )
                _particle_blocks(state, len(accepted))
            except FoundationError:
                continue
            if state.state_id in identifiers:
                continue
            accepted.append(state)
            identifiers.add(state.state_id)
            if len(accepted) == count:
                break
    return tuple(accepted)


def _particle_blocks(
    reference: SimulationState,
    reference_index: int,
) -> tuple[ParticleState, ...]:
    real_levels = np.linspace(1.34, 2.00, 8)
    imaginary_levels = (0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20)

    def legal(diameter: float) -> bool:
        particle = ParticleState(diameter, 1.60, 0.05)
        try:
            for position in _position_blocks(reference_index):
                replace_state(reference, particle, position, ObservationOperatorState())
        except FoundationError:
            return False
        return True

    lower = 2.0e-8
    upper = 2.0e-7
    if not legal(lower):
        raise FoundationError("E_DOMAIN_INVALID", "reference cannot hold the minimum particle")
    if not legal(upper):
        for _ in range(52):
            middle = 0.5 * (lower + upper)
            if legal(middle):
                lower = middle
            else:
                upper = middle
        upper = lower
    diameters = np.linspace(2.0e-8, upper, 8)
    real_shift = reference_index % 8
    imaginary_shift = (reference_index // 8) % 8
    return tuple(
        ParticleState(
            float(diameter),
            float(real_levels[(index + real_shift) % 8]),
            imaginary_levels[(3 * index + imaginary_shift) % 8],
        )
        for index, diameter in enumerate(diameters)
    )


def _position_blocks(reference_index: int) -> tuple[PositionState, ...]:
    longitudinal = (-1.5, -0.5, 0.5, 1.5)
    lateral = (-0.75, -0.25, 0.25, 0.75)
    depth = (0.15, 0.35, 0.65, 0.85)
    lateral_shift = reference_index % 4
    depth_shift = (reference_index // 4) % 4
    return tuple(
        PositionState(
            longitudinal[index],
            lateral[(index + lateral_shift) % 4],
            depth[(3 * index + depth_shift) % 4],
        )
        for index in range(4)
    )


def _radical_inverse(index: int, base: int) -> float:
    value = 0.0
    scale = 1.0 / base
    while index:
        index, digit = divmod(index, base)
        value += digit * scale
        scale /= base
    return value


def _operator_blocks(reference_index: int) -> tuple[ObservationOperatorState, ...]:
    if reference_index < 16:
        analyzer_azimuth = math.pi * (reference_index + 1) / 17.0
        analyzer_ellipticity = math.pi * (reference_index - 7.5) / 40.0
        sector_center = 2.0 * math.pi * (reference_index + 0.5) / 16.0
        return (
            ObservationOperatorState(
                collection_na=0.40,
                analyzer_azimuth_rad=analyzer_azimuth,
            ),
            ObservationOperatorState(
                collection_na=1.20,
                analyzer_azimuth_rad=analyzer_azimuth,
            ),
            ObservationOperatorState(
                pupil_inner_radius=0.75,
                pupil_outer_radius=0.85,
                analyzer_azimuth_rad=analyzer_azimuth,
                analyzer_ellipticity_rad=analyzer_ellipticity,
                detector_sector_center_rad=sector_center,
                detector_sector_width_rad=math.pi / 6.0,
            ),
            ObservationOperatorState(
                collection_na=1.20,
                analyzer_azimuth_rad=analyzer_azimuth,
                analyzer_ellipticity_rad=math.pi / 8.0,
                detector_sector_center_rad=3.0 * math.pi / 4.0,
                detector_sector_width_rad=math.pi / 2.0,
            ),
        )
    primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61)
    unit = tuple(_radical_inverse(reference_index + 1, base) for base in primes)
    grids: list[dict[str, float]] = []
    for grid_index in range(2):
        offset = 5 * grid_index
        outer = 0.85 + 0.15 * unit[offset + 2]
        inner = min(0.75, outer - 0.1) * unit[offset + 1]
        grids.append(
            {
                "collection_na": 0.40 + 0.80 * unit[offset],
                "pupil_inner_radius": inner,
                "pupil_outer_radius": outer,
                "detector_sector_center_rad": 2.0 * math.pi * unit[offset + 3],
                "detector_sector_width_rad": (
                    math.pi / 6.0 + (2.0 * math.pi - math.pi / 6.0) * unit[offset + 4]
                ),
            }
        )
    operators = []
    for index in range(4):
        analyzer_offset = 10 + 2 * index
        operators.append(
            ObservationOperatorState(
                **grids[index // 2],
                analyzer_azimuth_rad=math.pi * unit[analyzer_offset],
                analyzer_ellipticity_rad=(unit[analyzer_offset + 1] - 0.5) * math.pi / 2.0,
            )
        )
    return tuple(operators)


@cache
def _design_balance_receipt(reference_count: int) -> dict[str, Any]:
    reference = SimulationState()
    optical_pairs: dict[int, set[tuple[float, float]]] = defaultdict(set)
    for reference_index in range(min(reference_count, 64)):
        for rank, particle in enumerate(_particle_blocks(reference, reference_index)):
            optical_pairs[rank].add(
                (particle.refractive_index_real, particle.refractive_index_imag)
            )
    position_pairs: dict[int, set[tuple[float, float]]] = defaultdict(set)
    for reference_index in range(min(reference_count, 16)):
        for rank, position in enumerate(_position_blocks(reference_index)):
            position_pairs[rank].add((position.lateral_fraction, position.depth_fraction))
    operator_identities: dict[int, set[str]] = defaultdict(set)
    for reference_index in range(min(reference_count, 64)):
        for rank, operator in enumerate(_operator_blocks(reference_index)):
            operator_identities[rank].add(
                canonical_sha256(
                    {
                        "collection_na": operator.collection_na,
                        "analyzer_azimuth_rad": operator.analyzer_azimuth_rad,
                        "analyzer_ellipticity_rad": operator.analyzer_ellipticity_rad,
                        "pupil_inner_radius": operator.pupil_inner_radius,
                        "pupil_outer_radius": operator.pupil_outer_radius,
                        "detector_sector_center_rad": operator.detector_sector_center_rad,
                        "detector_sector_width_rad": operator.detector_sector_width_rad,
                    }
                )
            )
    minimum_optical_pairs = min(map(len, optical_pairs.values()))
    minimum_position_pairs = min(map(len, position_pairs.values()))
    minimum_operator_identities = min(map(len, operator_identities.values()))
    if minimum_optical_pairs < min(reference_count, 64):
        raise RuntimeError("particle optical assignments remain rank-confounded")
    if minimum_position_pairs < min(reference_count, 16):
        raise RuntimeError("position assignments remain rank-confounded")
    if minimum_operator_identities < min(reference_count, 64):
        raise RuntimeError("operator assignments remain fixed across reference blocks")
    return {
        "particle_optical_pairs_per_diameter_rank": minimum_optical_pairs,
        "lateral_depth_pairs_per_longitudinal_rank": minimum_position_pairs,
        "operator_identities_per_operator_rank": minimum_operator_identities,
        "status": "PASS_BALANCED_ROTATIONS_REMOVE_FIXED_ONE_TO_ONE_BINDINGS",
    }


def _reference_design_matrix(references: tuple[SimulationState, ...]) -> np.ndarray:
    rows = []
    for state in references:
        source = state.source
        minimum_waist = max(5.0e-7, source.wavelength_m)
        rows.append(
            (
                (state.geometry.width_m - 2.0e-7) / 1.8e-6,
                (state.geometry.depth_m - 2.0e-7) / 1.8e-6,
                (state.geometry.sidewall_angle_deg - 70.0) / 20.0,
                (source.wavelength_m - 4.0e-7) / 5.0e-7,
                (source.waist_m - minimum_waist) / (2.0e-6 - minimum_waist),
                (source.beam_offset_longitudinal_over_w0 + 0.8) / 1.6,
                (source.beam_offset_lateral_over_w0 + 0.8) / 1.6,
                source.polarization_azimuth_rad / math.pi,
                source.ellipticity_rad / (math.pi / 2.0) + 0.5,
                source.degree_of_polarization,
                (state.environment.fill_refractive_index - 1.30) / 0.09,
                (state.environment.wall_refractive_index - 1.41) / 0.13,
                state.environment.effective_wall_exclusion_m / 2.0e-8,
            )
        )
    return np.asarray(rows, dtype=np.float64)


def _reference_coverage_receipt(
    references: tuple[SimulationState, ...],
) -> dict[str, Any]:
    matrix = _reference_design_matrix(references)
    stage_counts = tuple(
        count for count in (256, 512, 1024, 2048, 4096) if count <= len(references)
    )
    stages = {
        str(count): {
            "maximum_absolute_mean_offset_from_half": float(
                np.max(np.abs(np.mean(matrix[:count], axis=0) - 0.5))
            ),
            "minimum_normalized_span": float(
                np.min(np.ptp(matrix[:count], axis=0))
            ),
        }
        for count in stage_counts
    }
    maximum_successive_mean_shift = 0.0
    for lower, upper in zip(stage_counts, stage_counts[1:], strict=False):
        maximum_successive_mean_shift = max(
            maximum_successive_mean_shift,
            float(
                np.max(
                    np.abs(
                        np.mean(matrix[:lower], axis=0)
                        - np.mean(matrix[:upper], axis=0)
                    )
                )
            ),
        )
    unique_count = len({state.state_id for state in references})
    final_span = float(np.min(np.ptp(matrix, axis=0)))
    passed = (
        unique_count == len(references)
        and final_span >= 0.95
        and maximum_successive_mean_shift <= 0.05
    )
    if not passed:
        raise RuntimeError("reference design failed uniqueness or coverage stability")
    return {
        "reference_state_count": len(references),
        "unique_reference_state_count": unique_count,
        "normalized_dimension_count": int(matrix.shape[1]),
        "minimum_final_normalized_span": final_span,
        "maximum_successive_mean_shift": maximum_successive_mean_shift,
        "stage_summaries": stages,
        "status": "PASS_UNIQUE_WIDE_AND_STAGE_STABLE_REFERENCE_DESIGN",
    }


def _nested_states(reference_count: int, seed: int) -> Iterator[SimulationState]:
    for reference_index, reference in enumerate(_reference_blocks(reference_count, seed)):
        for particle in _particle_blocks(reference, reference_index):
            for position in _position_blocks(reference_index):
                for operator in _operator_blocks(reference_index):
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
    return replace(reference, particle=particle, position=position, observation=operator)


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


def _states_for_references(
    indexed_references: tuple[tuple[int, SimulationState], ...],
) -> tuple[SimulationState, ...]:
    states = tuple(
        replace_state(reference, particle, position, operator)
        for reference_index, reference in indexed_references
        for particle in _particle_blocks(reference, reference_index)
        for position in _position_blocks(reference_index)
        for operator in _operator_blocks(reference_index)
    )
    if len({state.state_id for state in states}) != len(states):
        raise RuntimeError("nested design produced duplicate state identities")
    return states


def _write_nested_fragment(
    path_text: str,
    indexed_references: tuple[tuple[int, SimulationState], ...],
) -> tuple[str, int]:
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    states = _states_for_references(indexed_references)
    rows = [result_row(simulate_state(state)) for state in states]
    table = _stabilize_result_table_schema(pa.Table.from_pylist(rows))
    _write_table(Path(path_text), table)
    return path_text, len(rows)


def _consolidate(paths: list[Path], target: Path) -> None:
    handle, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(handle)
    writer: pq.ParquetWriter | None = None
    try:
        for path in paths:
            table = _stabilize_result_table_schema(pq.read_table(path))
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
    workers: int,
    boundary_policy: str = DEFAULT_BOUNDARY_POLICY,
) -> dict[str, Any]:
    state_count = reference_count * 8 * 4 * 4
    if _valid_release(directory, release_name, state_count):
        manifest = _read_manifest(directory)
        observed_policy = manifest["metadata"]["nested_design"].get(
            "boundary_reference_policy", DEFAULT_BOUNDARY_POLICY
        )
        if observed_policy == boundary_policy:
            return manifest
    assert_resource_budget(
        workers,
        worker_reserve_bytes=512 * 1024 * 1024,
        launch_headroom_bytes=FULL_RUN_LAUNCH_HEADROOM_BYTES,
    )
    references = _reference_blocks(
        reference_count,
        seed,
        boundary_policy=boundary_policy,
    )
    balance_receipt = _design_balance_receipt(reference_count)
    coverage_receipt = _reference_coverage_receipt(references)
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".work"
    work.mkdir(parents=True, exist_ok=True)
    fragments: list[Path] = []
    started = time.monotonic()
    peak_commit = system_committed_memory_bytes()
    missing: list[tuple[int, Path, tuple[tuple[int, SimulationState], ...]]] = []
    for offset in range(0, reference_count, REFERENCE_CHUNK):
        indexed = tuple(
            (index, references[index])
            for index in range(offset, min(offset + REFERENCE_CHUNK, reference_count))
        )
        states = _states_for_references(indexed)
        fragment = work / f"part-{offset // REFERENCE_CHUNK:05d}.parquet"
        fragments.append(fragment)
        if not _fragment_matches(fragment, states):
            missing.append((offset, fragment, indexed))

    completed_references = reference_count - sum(len(item[2]) for item in missing)

    def record_completion(offset: int, indexed_count: int) -> None:
        nonlocal completed_references, peak_commit
        completed_references += indexed_count
        committed = system_committed_memory_bytes()
        if committed is not None and (peak_commit is None or committed > peak_commit):
            peak_commit = committed
        print(
            canonical_json(
                {
                    "event": "nested_chunk",
                    "release": release_name,
                    "reference_block_offset": offset,
                    "reference_blocks_complete": completed_references,
                    "reference_blocks_total": reference_count,
                }
            ),
            flush=True,
        )

    if workers == 1:
        for offset, fragment, indexed in missing:
            _write_nested_fragment(str(fragment), indexed)
            record_completion(offset, len(indexed))
    elif missing:
        environment_names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        previous_environment = {name: os.environ.get(name) for name in environment_names}
        for name in environment_names:
            os.environ[name] = "1"
        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                pending: dict[Future[tuple[str, int]], tuple[int, int]] = {}
                cursor = 0

                def submit_available() -> None:
                    nonlocal cursor
                    while cursor < len(missing) and len(pending) < workers:
                        offset, fragment, indexed = missing[cursor]
                        cursor += 1
                        future = executor.submit(_write_nested_fragment, str(fragment), indexed)
                        pending[future] = (offset, len(indexed))

                submit_available()
                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        offset, indexed_count = pending.pop(future)
                        future.result()
                        record_completion(offset, indexed_count)
                    committed = system_committed_memory_bytes()
                    if (
                        committed is not None
                        and committed >= COMMITTED_MEMORY_EMERGENCY_STOP_BYTES
                    ):
                        for future in pending:
                            future.cancel()
                        raise RuntimeError("emergency committed-memory stop reached")
                    if committed is not None and committed >= COMMITTED_MEMORY_SOFT_STOP_BYTES:
                        if cursor < len(missing):
                            for future in pending:
                                future.cancel()
                            raise RuntimeError(
                                "soft committed-memory stop reached before completion"
                            )
                    else:
                        submit_available()
        finally:
            for name, value in previous_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    _consolidate(fragments, directory / "data.parquet")
    shutil.rmtree(work)
    elapsed = time.monotonic() - started
    metadata = {
        **_formal_metadata(),
        "release_name": release_name,
        "state_count": state_count,
        "seed": seed,
        "nested_design": {
            **(
                {"boundary_reference_policy": boundary_policy}
                if boundary_policy != DEFAULT_BOUNDARY_POLICY
                else {}
            ),
            "reference_blocks": reference_count,
            "reference_design_groups": reference_count,
            "reference_sobol_dimension_count": 13,
            "exact_closed_apex_reference_designs": sum(
                dry_etch_bottom_width(
                    state.geometry.width_m,
                    state.geometry.depth_m,
                    state.geometry.sidewall_angle_deg,
                )
                == 0.0
                for state in references
            ),
            "zero_wall_exclusion_reference_designs": sum(
                state.environment.effective_wall_exclusion_m == 0.0
                for state in references
            ),
            "wall_exclusion_sampling_policy": (
                "EXPLICIT_ZERO_STRATUM_EVERY_16TH_REFERENCE_PLUS_2_TO_20_NM_SOBOL"
            ),
            "normalization_power_W": 1.0,
            "normalization_power_policy": (
                "FIXED_UNIT_REFERENCE_TO_AVOID_EXACT_LINEAR_DUPLICATION"
            ),
            "particle_assignments": 8,
            "particle_assignment_rule": (
                "EIGHT_DIAMETER_LEVELS_TO_LOCAL_LEGAL_MAX_WITH_INDEPENDENT_BALANCED_"
                "REAL_AND_IMAGINARY_INDEX_PERMUTATIONS_ACROSS_REFERENCE_BLOCKS"
            ),
            "positions": 4,
            "position_assignment_rule": (
                "FOUR_BALANCED_LONGITUDINAL_LATERAL_DEPTH_PERMUTATIONS_"
                "ROTATED_ACROSS_REFERENCE_BLOCKS"
            ),
            "operators": 4,
            "operator_assignment_rule": (
                "TWO_LOW_DISCREPANCY_PUPIL_GEOMETRIES_CROSSED_WITH_FOUR_"
                "LOW_DISCREPANCY_ANALYZERS_PER_REFERENCE_BLOCK"
            ),
            "balance_receipt": balance_receipt,
            "coverage_receipt": coverage_receipt,
        },
        "selected_workers": workers,
        "chunk_size_states": REFERENCE_CHUNK * 8 * 4 * 4,
        "elapsed_seconds": elapsed,
        "peak_observed_system_committed_memory_bytes": peak_commit,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
        "parallelism_selection": PARALLELISM_SELECTION,
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
    workers: int,
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
    assert_resource_budget(
        workers,
        worker_reserve_bytes=512 * 1024 * 1024,
        launch_headroom_bytes=FULL_RUN_LAUNCH_HEADROOM_BYTES,
    )
    pair_states = tuple(
        state
        for _feature, low, high in pair_records
        for state in (low, high)
    )
    batch = simulate_batch(
        pair_states,
        execution=ExecutionSpec(
            workers=workers,
            chunk_size=len(pair_states),
            worker_reserve_bytes=512 * 1024 * 1024,
        ),
    )
    pair_results = list(zip(batch.results[::2], batch.results[1::2], strict=True))
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
        feature_row = next(row for row in _feature_rows() if row["id"] == feature)
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
                "formal_status": feature_row["formal_status"],
                "intervention_selection_eligible": feature_row.get(
                    "intervention_selection_eligible", True
                ),
                "legal_pair_count": len(values),
                "median_normalized_effect": median,
                "q90_normalized_effect": q90,
                "robust_exposure_fraction_span": fraction_span,
                "retained": keep,
                "retention_rule": "Q90_NORMALIZED_COMPLEX_OUTPUT_EFFECT_GT_1E-6",
            }
        )
    qualified = [
        row
        for row in rows
        if row["retained"] and row["intervention_selection_eligible"]
    ]
    if len(qualified) < 2:
        raise RuntimeError("formal capability sprint retained fewer than two features")
    primary = max(qualified, key=lambda row: row["median_normalized_effect"])
    replication = max(
        (row for row in qualified if row["mechanism_group"] != primary["mechanism_group"]),
        key=lambda row: row["median_normalized_effect"],
    )
    return rows, retained, str(primary["feature"]), str(replication["feature"])


def _build_capability_freeze(
    capability: dict[str, Any],
    seed: int,
    workers: int,
) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V5"
    release_name = "NODI-QUALIFICATION-PROFILE-V5"
    if _valid_release(directory, release_name, CAPABILITY_STATE_COUNT):
        return _read_manifest(directory)
    states = tuple(_nested_states(CAPABILITY_REFERENCE_BLOCKS, seed))
    rows, retained, primary, replication = _capability_effects(states, workers)
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
        "selected_workers": workers,
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


def run_sprint(seed: int, workers: int) -> dict[str, Any]:
    capability_dir = RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V5"
    capability = _build_nested_release(
        capability_dir,
        release_name="NODI-CAPABILITY-SPRINT-V5",
        reference_count=CAPABILITY_REFERENCE_BLOCKS,
        seed=seed,
        workers=workers,
    )
    qualification = _build_capability_freeze(capability, seed, workers)
    receipt = {
        "manifest_schema_version": 2,
        "phase": "R6_V5_FORMAL_CAPABILITY_FREEZE",
        "status": "PASS",
        "profile": FORMAL_PROFILE,
        "release_root": "releases/nodi-v5",
        "maximum_workers": 24,
        "selected_workers": workers,
        "parallelism_selection": PARALLELISM_SELECTION,
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
                RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V5", qualification
            ),
        },
        "formal_reference_data_state": "BLOCKED_UNTIL_V5_RELEASES_COMPLETE",
    }
    _atomic_json(RECEIPT_PATH, receipt)
    return receipt


def _build_quickstart(capability: dict[str, Any]) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-QUICKSTART-V5"
    release_name = "NODI-QUICKSTART-V5"
    if _valid_release(directory, release_name, QUICKSTART_STATE_COUNT):
        return _read_manifest(directory)
    source = pq.read_table(RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V5" / "data.parquet")
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
                "longitudinal_over_w0": row["position.longitudinal_over_w0"],
                "lateral_fraction": row["position.lateral_fraction"],
                "depth_fraction": row["position.depth_fraction"],
            },
            "source": {
                "wavelength_m": row["source.wavelength_m"],
                "waist_m": row["source.waist_m"],
                "normalization_power_W": row["source.normalization_power_W"],
                "beam_offset_longitudinal_over_w0": row[
                    "source.beam_offset_longitudinal_over_w0"
                ],
                "beam_offset_lateral_over_w0": row[
                    "source.beam_offset_lateral_over_w0"
                ],
                "polarization_azimuth_rad": row["source.polarization_azimuth_rad"],
                "ellipticity_rad": row["source.ellipticity_rad"],
                "degree_of_polarization": row["source.degree_of_polarization"],
            },
            "environment": {
                "fill_refractive_index": row["environment.fill_refractive_index"],
                "wall_refractive_index": row["environment.wall_refractive_index"],
                "effective_wall_exclusion_m": row[
                    "environment.effective_wall_exclusion_m"
                ],
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
        "anchor_reference_design_id": anchor.reference_design_id,
        "anchor_split_group_id": anchor.split_group_id,
        "feature": feature,
        "low_value": low_value,
        "high_value": high_value,
        "low_state_id": low_state.state_id,
        "high_state_id": high_state.state_id,
        "low_split_group_id": low_state.split_group_id,
        "high_split_group_id": high_state.split_group_id,
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
    fallback_records: dict[
        str,
        list[tuple[str, SimulationState, SimulationState, SimulationState, float, float]],
    ] = {feature: [] for feature in features}
    counts = {feature: 0 for feature in features}
    parquet = pq.ParquetFile(development_directory / "data.parquet")
    global_index = 0
    for batch in parquet.iter_batches(batch_size=8_192, columns=input_columns):
        for row in batch.to_pylist():
            remainder = global_index % 64
            global_index += 1
            if remainder >= 2 * len(features):
                continue
            feature = features[remainder % len(features)]
            is_primary_slot = remainder < len(features)
            if is_primary_slot and counts[feature] >= DEVELOPMENT_PAIR_COUNT // len(
                features
            ):
                continue
            if not is_primary_slot and len(fallback_records[feature]) >= 64:
                continue
            anchor = _state_from_flat_row(row)
            pair = _legal_pair(anchor, feature, _feature_ranges()[feature])
            if pair is None:
                continue
            low, high = pair
            record = (
                feature,
                anchor,
                low,
                high,
                _feature_value(low, feature),
                _feature_value(high, feature),
            )
            if is_primary_slot:
                records.append(record)
                counts[feature] += 1
            else:
                fallback_records[feature].append(record)
    target = DEVELOPMENT_PAIR_COUNT // len(features)
    for feature in features:
        missing = target - counts[feature]
        records.extend(fallback_records[feature][:missing])
        counts[feature] += min(missing, len(fallback_records[feature]))
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


def _write_pair_fragment(
    path_text: str,
    records: list[
        tuple[str, SimulationState, SimulationState, SimulationState, float, float]
    ],
) -> tuple[str, int]:
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    results = [(simulate_state(record[2]), simulate_state(record[3])) for record in records]
    rows = [
        _pair_row(*record, result[0], result[1])
        for record, result in zip(records, results, strict=True)
    ]
    _write_table(Path(path_text), pa.Table.from_pylist(rows))
    return path_text, len(rows)


def _build_interventions(
    development: dict[str, Any],
    qualification: dict[str, Any],
    workers: int,
) -> dict[str, Any]:
    directory = RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V5"
    release_name = "NODI-ATLAS-DEV-INTERVENTIONS-V5"
    if _valid_release(directory, release_name, DEVELOPMENT_PAIR_COUNT):
        return _read_manifest(directory)
    features = (
        str(qualification["metadata"]["primary_exposure_family"]),
        str(qualification["metadata"]["replication_exposure_family"]),
    )
    records = _intervention_records(RELEASE_ROOT / "NODI-ATLAS-DEV-V5", features)
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".work"
    work.mkdir(parents=True, exist_ok=True)
    fragments: list[Path] = []
    missing: list[
        tuple[
            int,
            Path,
            list[
                tuple[
                    str,
                    SimulationState,
                    SimulationState,
                    SimulationState,
                    float,
                    float,
                ]
            ],
        ]
    ] = []
    for offset in range(0, len(records), PAIR_CHUNK):
        chunk = records[offset : offset + PAIR_CHUNK]
        fragment = work / f"part-{offset // PAIR_CHUNK:05d}.parquet"
        fragments.append(fragment)
        if not _pair_fragment_matches(fragment, chunk):
            missing.append((offset, fragment, chunk))

    completed_pairs = len(records) - sum(len(item[2]) for item in missing)

    def record_completion(offset: int, pair_count: int) -> None:
        nonlocal completed_pairs
        completed_pairs += pair_count
        print(
            canonical_json(
                {
                    "event": "intervention_chunk",
                    "pair_offset": offset,
                    "pairs_complete": completed_pairs,
                    "pairs_total": len(records),
                }
            ),
            flush=True,
        )

    assert_resource_budget(
        workers,
        worker_reserve_bytes=512 * 1024 * 1024,
        launch_headroom_bytes=FULL_RUN_LAUNCH_HEADROOM_BYTES,
    )
    if workers == 1:
        for offset, fragment, chunk in missing:
            _write_pair_fragment(str(fragment), chunk)
            record_completion(offset, len(chunk))
    elif missing:
        environment_names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        previous_environment = {name: os.environ.get(name) for name in environment_names}
        for name in environment_names:
            os.environ[name] = "1"
        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_jobs = {
                    executor.submit(_write_pair_fragment, str(fragment), chunk): (
                        offset,
                        len(chunk),
                    )
                    for offset, fragment, chunk in missing
                }
                for future in future_jobs:
                    offset, pair_count = future_jobs[future]
                    future.result()
                    record_completion(offset, pair_count)
                    committed = system_committed_memory_bytes()
                    if (
                        committed is not None
                        and committed >= COMMITTED_MEMORY_EMERGENCY_STOP_BYTES
                    ):
                        for pending in future_jobs:
                            pending.cancel()
                        raise RuntimeError("emergency committed-memory stop reached")
        finally:
            for name, value in previous_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
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
            "anchor_selection": (
                "EVERY_64TH_DEVELOPMENT_ROW_OFFSETS_0_AND_1_"
                "WITH_SAME_CYCLE_OFFSETS_2_AND_3_AS_LEGALITY_FALLBACK"
            ),
            "selection": "FROZEN_PRIMARY_AND_DIFFERENT_MECHANISM_REPLICATION",
            "selected_workers": workers,
        },
    )
    report = validate_release(directory)
    if not report.valid:
        raise RuntimeError(f"intervention release validation failed: {report.errors}")
    return manifest


def _build_evaluation_releases(
    development: dict[str, Any],
    workers: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_directory = RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V5"
    label_directory = RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V5.sealed"
    input_name = "NODI-ATLAS-EVAL-INPUTS-V5"
    label_name = "NODI-ATLAS-EVAL-LABELS-V5.sealed"
    if _valid_release(
        input_directory, input_name, EVALUATION_STATE_COUNT
    ) and _valid_release(label_directory, label_name, EVALUATION_STATE_COUNT):
        return _read_manifest(input_directory), _read_manifest(label_directory)
    transition = RELEASE_ROOT / ".evaluation-full-v5"
    full_manifest = _build_nested_release(
        transition,
        release_name="NODI-EVALUATION-FULL-V5-TRANSITION",
        reference_count=EVALUATION_REFERENCE_BLOCKS,
        seed=EVALUATION_SEED,
        workers=workers,
        boundary_policy=EVALUATION_BOUNDARY_POLICY,
    )
    full = pq.read_table(transition / "data.parquet")
    identifiers = full["state_id"].to_pylist()
    development_identity = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-DEV-V5" / "data.parquet",
        columns=["state_id", "split_group_id"],
    )
    development_ids = set(development_identity["state_id"].to_pylist())
    if development_ids.intersection(identifiers):
        raise RuntimeError("Development and Evaluation state identities overlap")
    development_groups = set(development_identity["split_group_id"].to_pylist())
    evaluation_groups = set(full["split_group_id"].to_pylist())
    if development_groups.intersection(evaluation_groups):
        raise RuntimeError("Development and Evaluation split groups overlap")
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
            "reference_design_id",
            "split_group_id",
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
            "combined_total_W",
            "eta_real",
            "eta_imag",
            "eta_abs",
            "C_phase_rad",
            "coupling_defined",
            "coupling_undefined_reason",
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
            "boundary_reference_policy": EVALUATION_BOUNDARY_POLICY,
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
            "boundary_reference_policy": EVALUATION_BOUNDARY_POLICY,
            "development_release_id": development["release_id"],
            "label_commitment_release_id": label_manifest["release_id"],
            "label_delivery_state": "SEALED_NOT_DELIVERED",
            "development_evaluation_shared_state_count": 0,
            "development_evaluation_shared_split_group_count": 0,
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
            RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V5" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    quickstart_ids = set(
        pq.read_table(
            RELEASE_ROOT / "NODI-QUICKSTART-V5" / "data.parquet",
            columns=["state_id"],
        )["state_id"].to_pylist()
    )
    development = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-DEV-V5" / "data.parquet",
        columns=["state_id", "reference_design_id", "split_group_id"],
    )
    development_ids = set(development["state_id"].to_pylist())
    development_groups = set(development["split_group_id"].to_pylist())
    evaluation = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V5" / "inputs.parquet",
        columns=[
            "state_id",
            "reference_design_id",
            "split_group_id",
            "is_intervention_anchor",
        ],
    )
    evaluation_ids = evaluation["state_id"].to_pylist()
    evaluation_groups = set(evaluation["split_group_id"].to_pylist())
    label_ids = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V5.sealed" / "labels.parquet.sealed",
        columns=["state_id"],
    )["state_id"].to_pylist()
    pairs = pq.read_table(
        RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V5" / "pairs.parquet",
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
        "development_unique_split_group_count": len(development_groups),
        "evaluation_unique_split_group_count": len(evaluation_groups),
        "development_evaluation_shared_split_group_count": len(
            development_groups.intersection(evaluation_groups)
        ),
        "reference_design_and_split_group_columns_match": bool(
            pc.all(
                pc.equal(
                    development["reference_design_id"],
                    development["split_group_id"],
                )
            ).as_py()
            and pc.all(
                pc.equal(
                    evaluation["reference_design_id"],
                    evaluation["split_group_id"],
                )
            ).as_py()
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
        "superseded_data_or_feature_selection_imported": False,
    }
    expected_features = {
        feature: DEVELOPMENT_PAIR_COUNT // len(features) for feature in features
    }
    if not (
        acceptance["quickstart_is_capability_subset_without_recompute"]
        and acceptance["development_unique_state_count"] == DEVELOPMENT_STATE_COUNT
        and acceptance["evaluation_unique_state_count"] == EVALUATION_STATE_COUNT
        and acceptance["development_evaluation_shared_state_count"] == 0
        and acceptance["development_unique_split_group_count"]
        == DEVELOPMENT_REFERENCE_BLOCKS
        and acceptance["evaluation_unique_split_group_count"]
        == EVALUATION_REFERENCE_BLOCKS
        and acceptance["development_evaluation_shared_split_group_count"] == 0
        and acceptance["reference_design_and_split_group_columns_match"]
        and acceptance["evaluation_input_label_identity_and_order_match"]
        and acceptance["evaluation_intervention_anchor_count"] == EVALUATION_ANCHOR_COUNT
        and acceptance["development_intervention_unique_pair_count"]
        == DEVELOPMENT_PAIR_COUNT
        and feature_counts == expected_features
    ):
        raise RuntimeError(f"v5 cross-release acceptance failed: {acceptance}")
    return acceptance


def run_all(seed: int, workers: int) -> dict[str, Any]:
    capability_directory = RELEASE_ROOT / "NODI-CAPABILITY-SPRINT-V5"
    capability = _build_nested_release(
        capability_directory,
        release_name="NODI-CAPABILITY-SPRINT-V5",
        reference_count=CAPABILITY_REFERENCE_BLOCKS,
        seed=seed,
        workers=workers,
    )
    qualification = _build_capability_freeze(capability, seed, workers)
    quickstart = _build_quickstart(capability)
    development_directory = RELEASE_ROOT / "NODI-ATLAS-DEV-V5"
    development = _build_nested_release(
        development_directory,
        release_name="NODI-ATLAS-DEV-V5",
        reference_count=DEVELOPMENT_REFERENCE_BLOCKS,
        seed=DEVELOPMENT_SEED,
        workers=workers,
    )
    interventions = _build_interventions(development, qualification, workers)
    evaluation_inputs, evaluation_labels = _build_evaluation_releases(development, workers)
    directories = {
        "capability_sprint": capability_directory,
        "qualification_profile": RELEASE_ROOT / "NODI-QUALIFICATION-PROFILE-V5",
        "quickstart": RELEASE_ROOT / "NODI-QUICKSTART-V5",
        "development_atlas": development_directory,
        "development_interventions": (
            RELEASE_ROOT / "NODI-ATLAS-DEV-INTERVENTIONS-V5"
        ),
        "evaluation_inputs": RELEASE_ROOT / "NODI-ATLAS-EVAL-INPUTS-V5",
        "evaluation_labels": RELEASE_ROOT / "NODI-ATLAS-EVAL-LABELS-V5.sealed",
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
        raise RuntimeError("one or more v5 releases failed final validation")
    selected_features = (
        str(qualification["metadata"]["primary_exposure_family"]),
        str(qualification["metadata"]["replication_exposure_family"]),
    )
    acceptance = _final_acceptance(selected_features)
    wheel_path = ROOT / "dist" / WHEEL_NAME
    if not wheel_path.is_file():
        raise RuntimeError(f"missing current software wheel: {wheel_path}")
    receipt = {
        "manifest_schema_version": 2,
        "product": "NODI Simulation Foundation",
        "version": "5.0.0",
        "release_date": "2026-08-18",
        "phase": "R6_V5_EXACT_SUPPORT_FORMAL_REFERENCE_RELEASES",
        "status": "PASS",
        "profile": FORMAL_PROFILE,
        "release_root": "releases/nodi-v5",
        "maximum_workers": 24,
        "selected_workers": workers,
        "parallelism_selection": PARALLELISM_SELECTION,
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
        "development_size_state": "V5_INFORMATION_BEARING_524288_STATE_ATLAS",
        "label_delivery_state": "SEALED_NOT_DELIVERED",
        "formal_reference_data_state": (
            "ELIGIBLE_REFERENCE_LABELS_WITH_DECLARED_LIMITS_NOT_EXPERIMENTAL_TRUTH"
        ),
        "source_archive": {
            "mode": "GIT_ANNOTATED_TAG",
            "tag": "v5.0.0",
            "repository": "https://github.com/Shaughn0419/NODI-Simulation-Foundation",
        },
        "software_delivery": {
            "wheel": WHEEL_NAME,
            "wheel_sha256": _sha256(wheel_path),
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
    parser.add_argument("--seed", type=int, default=2026081902)
    parser.add_argument("--workers", type=int, choices=range(1, 25), default=4)
    args = parser.parse_args()
    receipt = (
        run_sprint(args.seed, args.workers)
        if args.phase == "sprint"
        else run_all(args.seed, args.workers)
    )
    print(canonical_json({"status": receipt["status"], "phase": receipt["phase"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
