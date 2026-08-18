"""Deterministic custom dataset generation and release assembly."""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import tempfile
import warnings
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import qmc  # type: ignore[import-untyped]

from .batch import ExecutionSpec, simulate_batch
from .capabilities import capabilities
from .errors import E_DOMAIN_INVALID, FoundationError
from .models import ENGINE_VERSION, FEATURE_VERSION, SimulationState, StateResult
from .profiles import (
    FORMAL_IMPLEMENTATION_SHA256,
    FORMAL_NUMERICAL_PROFILE_SHA256,
    FORMAL_PARITY_PANEL_SHA256,
    FORMAL_PROFILE,
    FORMAL_QUALIFICATION_MATRIX_SHA256,
    FORMAL_QUALIFICATION_REPORT_SHA256,
    SUPPORTED_PROFILES,
)
from .releases import DatasetRelease, write_release_manifest


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    output_dir: Path
    state_count: int
    feature_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    fixed_values: dict[str, float] = field(default_factory=dict)
    sampling_method: str = "sobol"
    seed: int = 0
    profile: str = FORMAL_PROFILE
    feature_catalogue_hash: str | None = None
    qualification_report_hash: str | None = None
    release_name: str = "NODI-CUSTOM-V2"
    execution: ExecutionSpec = ExecutionSpec()

    def __post_init__(self) -> None:
        if isinstance(self.state_count, bool) or not isinstance(self.state_count, int):
            raise FoundationError(E_DOMAIN_INVALID, "state_count must be an integer")
        if self.state_count < 1:
            raise FoundationError(E_DOMAIN_INVALID, "state_count must be positive")
        if self.sampling_method not in {"sobol", "random"}:
            raise FoundationError(E_DOMAIN_INVALID, "sampling_method must be sobol or random")
        if set(self.feature_ranges) & set(self.fixed_values):
            raise FoundationError(E_DOMAIN_INVALID, "a feature cannot be fixed and ranged")
        if self.profile not in SUPPORTED_PROFILES:
            raise FoundationError(E_DOMAIN_INVALID, f"unsupported physics profile {self.profile!r}")


def _feature_paths() -> dict[str, str]:
    report = capabilities()
    return {str(row["id"]): str(row["path"]) for row in report.features}


def _set_path(payload: dict[str, Any], dotted: str, value: float) -> None:
    group, field_name = dotted.split(".", 1)
    group_payload = payload.get(group)
    if not isinstance(group_payload, dict) or field_name not in group_payload:
        raise FoundationError(E_DOMAIN_INVALID, f"unknown feature path {dotted}")
    group_payload[field_name] = float(value)


def state_with_value(state: SimulationState, feature: str, value: float) -> SimulationState:
    paths = _feature_paths()
    if feature not in paths:
        raise FoundationError(E_DOMAIN_INVALID, f"unknown feature {feature}")
    payload = copy.deepcopy(state.to_payload())
    _set_path(payload, paths[feature], value)
    return SimulationState.from_mapping(payload)


def sample_states(spec: DatasetSpec) -> tuple[SimulationState, ...]:
    paths = _feature_paths()
    unknown = (set(spec.feature_ranges) | set(spec.fixed_values)) - set(paths)
    if unknown:
        raise FoundationError(E_DOMAIN_INVALID, f"unknown features: {sorted(unknown)}")
    for name, bounds in spec.feature_ranges.items():
        if len(bounds) != 2 or not math.isfinite(bounds[0]) or not math.isfinite(bounds[1]):
            raise FoundationError(E_DOMAIN_INVALID, f"invalid range for {name}")
        if bounds[0] > bounds[1]:
            raise FoundationError(E_DOMAIN_INVALID, f"reversed range for {name}")
    base = SimulationState(physics_profile_id=spec.profile).to_payload()
    for name, value in spec.fixed_values.items():
        _set_path(base, paths[name], value)
    names = tuple(sorted(spec.feature_ranges))
    if not names:
        state = SimulationState.from_mapping(base)
        return tuple(state for _ in range(spec.state_count))
    dimension = len(names)
    rng = np.random.default_rng(spec.seed)
    sobol = qmc.Sobol(d=dimension, scramble=True, seed=spec.seed)
    accepted: list[SimulationState] = []
    attempted = 0
    maximum_attempts = max(4096, 64 * spec.state_count)
    while len(accepted) < spec.state_count and attempted < maximum_attempts:
        draw_count = min(max(256, spec.state_count - len(accepted)), maximum_attempts - attempted)
        if spec.sampling_method == "sobol":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                unit = sobol.random(draw_count)
        else:
            unit = rng.random((draw_count, dimension))
        attempted += draw_count
        for row in unit:
            payload = copy.deepcopy(base)
            for index, name in enumerate(names):
                lower, upper = spec.feature_ranges[name]
                _set_path(payload, paths[name], lower + float(row[index]) * (upper - lower))
            try:
                accepted.append(SimulationState.from_mapping(payload))
            except FoundationError:
                continue
            if len(accepted) == spec.state_count:
                break
    if len(accepted) != spec.state_count:
        raise FoundationError(
            E_DOMAIN_INVALID,
            f"only {len(accepted)} valid states after {attempted} deterministic attempts",
        )
    return tuple(accepted)


def _flatten(prefix: str, value: dict[str, Any], output: dict[str, Any]) -> None:
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            _flatten(name, item, output)
        else:
            output[name] = item


def result_row(result: StateResult) -> dict[str, Any]:
    row: dict[str, Any] = {}
    _flatten("", result.inputs, row)
    row.update(
        {
            "state_id": result.state_id,
            "physics_profile_id": result.physics_profile_id,
            "fidelity_class": result.fidelity_class,
            "claim_ceiling": result.claim_ceiling,
            "reference_block_id": result.reference_block_id,
            "particle_block_id": result.particle_block_id,
            "position_block_id": result.position_block_id,
            "operator_block_id": result.operator_block_id,
            "numerical_receipt_ids": list(result.numerical_receipt_ids),
            "B_bg_W": result.B_bg_W,
            "S_W": result.S_W,
            "C_r_W": result.C_r_W,
            "C_i_W": result.C_i_W,
            "Y_0_W": result.Y_0_W,
            "eta_real": result.eta_real,
            "eta_imag": result.eta_imag,
            "eta_abs": result.eta_abs,
            "numerical_status": result.numerical_status,
            "applicability_profile_id": result.applicability_profile_id,
            "operator_qualification_status": result.operator_qualification_status,
            "engine_version": result.engine_version,
            "schema_version": result.schema_version,
            "feature_version": result.feature_version,
            "config_hash": result.config_hash,
            "result_hash": result.result_hash,
        }
    )
    row.update(_derived_descriptors(result.inputs))
    return row


def _derived_descriptors(inputs: dict[str, Any]) -> dict[str, float]:
    geometry = inputs["geometry"]
    particle = inputs["particle"]
    position = inputs["position"]
    source = inputs["source"]
    environment = inputs["environment"]
    operator = inputs["observation"]
    wavelength = float(source["wavelength_m"])
    waist = float(source["waist_m"])
    width = float(geometry["width_m"])
    depth = float(geometry["depth_m"])
    diameter = float(particle["diameter_m"])
    fill_index = float(environment["fill_refractive_index"])
    relative_index = complex(
        float(particle["refractive_index_real"]),
        float(particle["refractive_index_imag"]),
    ) / fill_index
    source_azimuth = float(source["polarization_azimuth_rad"])
    source_ellipticity = float(source["ellipticity_rad"])
    source_dop = float(source["degree_of_polarization"])
    analyzer_azimuth = float(operator["analyzer_azimuth_rad"])
    analyzer_ellipticity = float(operator["analyzer_ellipticity_rad"])
    return {
        "derived.W_over_lambda": width / wavelength,
        "derived.H_over_lambda": depth / wavelength,
        "derived.dp_over_lambda": diameter / wavelength,
        "derived.H_over_W": depth / width,
        "derived.W_over_w0": width / waist,
        "derived.H_over_w0": depth / waist,
        "derived.mie_size_parameter": math.pi * diameter * fill_index / wavelength,
        "derived.relative_particle_index_abs": abs(relative_index),
        "derived.relative_particle_index_phase_rad": math.atan2(
            relative_index.imag, relative_index.real
        ),
        "derived.longitudinal_over_w0": float(position["longitudinal_m"]) / waist,
        "derived.steric_ratio": diameter / min(width, depth),
        "derived.wall_fill_contrast": float(environment["wall_refractive_index"]) - fill_index,
        "derived.normalized_collection_na": float(operator["collection_na"]) / fill_index,
        "derived.pupil_area_fraction": float(operator["pupil_outer_radius"]) ** 2
        - float(operator["pupil_inner_radius"]) ** 2,
        "derived.source_stokes_q": source_dop
        * math.cos(2.0 * source_ellipticity)
        * math.cos(2.0 * source_azimuth),
        "derived.source_stokes_u": source_dop
        * math.cos(2.0 * source_ellipticity)
        * math.sin(2.0 * source_azimuth),
        "derived.source_stokes_v": source_dop * math.sin(2.0 * source_ellipticity),
        "derived.analyzer_stokes_q": math.cos(2.0 * analyzer_ellipticity)
        * math.cos(2.0 * analyzer_azimuth),
        "derived.analyzer_stokes_u": math.cos(2.0 * analyzer_ellipticity)
        * math.sin(2.0 * analyzer_azimuth),
        "derived.analyzer_stokes_v": math.sin(2.0 * analyzer_ellipticity),
    }


def _write_parquet_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    try:
        table = pa.Table.from_pylist(rows)
        pq.write_table(  # type: ignore[no-untyped-call]
            table, temporary, compression="zstd", use_dictionary=True
        )
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _fragment_matches(path: Path, states: tuple[SimulationState, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        table = pq.read_table(  # type: ignore[no-untyped-call]
            path,
            columns=["state_id", "engine_version", "feature_version"],
        )
        identifiers = table["state_id"].to_pylist()
    except (OSError, pa.ArrowException):
        return False
    return bool(
        identifiers == [state.state_id for state in states]
        and set(table["engine_version"].to_pylist()) == {ENGINE_VERSION}
        and set(table["feature_version"].to_pylist()) == {FEATURE_VERSION}
    )


def _consolidate_fragments(paths: list[Path], target: Path) -> None:
    handle, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(handle)
    writer: pq.ParquetWriter | None = None
    try:
        for path in paths:
            table = pq.read_table(path)  # type: ignore[no-untyped-call]
            if writer is None:
                writer = pq.ParquetWriter(  # type: ignore[no-untyped-call]
                    temporary,
                    table.schema,
                    compression="zstd",
                    use_dictionary=True,
                )
            writer.write_table(table)  # type: ignore[no-untyped-call]
        if writer is None:
            raise RuntimeError("cannot consolidate an empty dataset")
        writer.close()  # type: ignore[no-untyped-call]
        writer = None
        os.replace(temporary, target)
    finally:
        if writer is not None:
            writer.close()  # type: ignore[no-untyped-call]
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_dataset(dataset_spec: DatasetSpec) -> DatasetRelease:
    """Build one deterministic custom dataset and content-addressed release."""

    report = capabilities()
    if dataset_spec.profile == FORMAL_PROFILE:
        if dataset_spec.feature_catalogue_hash != report.catalogue_hash:
            raise FoundationError(
                E_DOMAIN_INVALID, "formal dataset must bind the current feature catalogue hash"
            )
        qualification = dataset_spec.qualification_report_hash
        if qualification != FORMAL_QUALIFICATION_REPORT_SHA256:
            raise FoundationError(
                E_DOMAIN_INVALID, "formal dataset must bind the qualified report SHA-256"
            )
    states = sample_states(dataset_spec)
    dataset_spec.output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = dataset_spec.output_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)
    fragments: list[Path] = []
    chunk_size = dataset_spec.execution.chunk_size
    for offset in range(0, len(states), chunk_size):
        chunk = states[offset : offset + chunk_size]
        fragment = work_dir / f"part-{offset // chunk_size:08d}.parquet"
        fragments.append(fragment)
        if dataset_spec.execution.resume and _fragment_matches(fragment, chunk):
            continue
        execution = replace(
            dataset_spec.execution,
            chunk_size=len(chunk),
            output_dir=None,
        )
        batch = simulate_batch(chunk, execution=execution)
        _write_parquet_atomic(fragment, [result_row(result) for result in batch.results])
    data_path = dataset_spec.output_dir / "data.parquet"
    _consolidate_fragments(fragments, data_path)
    shutil.rmtree(work_dir)
    metadata = {
        "release_name": dataset_spec.release_name,
        "profile": dataset_spec.profile,
        "feature_catalogue_hash": dataset_spec.feature_catalogue_hash,
        "qualification_report_sha256": dataset_spec.qualification_report_hash,
        "physics_implementation_sha256": (
            FORMAL_IMPLEMENTATION_SHA256 if dataset_spec.profile == FORMAL_PROFILE else None
        ),
        "numerical_profile_sha256": (
            FORMAL_NUMERICAL_PROFILE_SHA256 if dataset_spec.profile == FORMAL_PROFILE else None
        ),
        "qualification_matrix_sha256": (
            FORMAL_QUALIFICATION_MATRIX_SHA256 if dataset_spec.profile == FORMAL_PROFILE else None
        ),
        "parity_panel_sha256": (
            FORMAL_PARITY_PANEL_SHA256 if dataset_spec.profile == FORMAL_PROFILE else None
        ),
        "paper2_final_truth_eligible": dataset_spec.profile == FORMAL_PROFILE,
        "state_count": dataset_spec.state_count,
        "sampling_method": dataset_spec.sampling_method,
        "seed": dataset_spec.seed,
        "feature_ranges": {key: list(value) for key, value in dataset_spec.feature_ranges.items()},
        "fixed_values": dataset_spec.fixed_values,
    }
    manifest = write_release_manifest(
        dataset_spec.output_dir,
        release_type="NODI_DATASET_RELEASE",
        primary_files=("data.parquet",),
        metadata=metadata,
    )
    return DatasetRelease(
        path=dataset_spec.output_dir,
        release_id=str(manifest["release_id"]),
        state_count=dataset_spec.state_count,
        manifest=manifest,
    )


def dataset_spec_from_mapping(value: dict[str, Any], *, output_dir: Path) -> DatasetSpec:
    execution_raw = dict(value.get("execution", {}))
    execution = ExecutionSpec(
        workers=int(execution_raw.get("workers", 1)),
        chunk_size=int(execution_raw.get("chunk_size", 1024)),
        cache_dir=(
            None
            if execution_raw.get("cache_dir") is None
            else Path(str(execution_raw["cache_dir"]))
        ),
        output_dir=(
            None
            if execution_raw.get("output_dir") is None
            else Path(str(execution_raw["output_dir"]))
        ),
        resume=bool(execution_raw.get("resume", True)),
    )
    return DatasetSpec(
        output_dir=output_dir,
        state_count=int(value["state_count"]),
        feature_ranges={
            str(key): (float(bounds[0]), float(bounds[1]))
            for key, bounds in dict(value.get("feature_ranges", {})).items()
        },
        fixed_values={
            str(key): float(item) for key, item in dict(value.get("fixed_values", {})).items()
        },
        sampling_method=str(value.get("sampling_method", "sobol")),
        seed=int(value.get("seed", 0)),
        profile=str(value.get("profile", FORMAL_PROFILE)),
        feature_catalogue_hash=(
            None
            if value.get("feature_catalogue_hash") is None
            else str(value["feature_catalogue_hash"])
        ),
        qualification_report_hash=(
            None
            if value.get("qualification_report_hash") is None
            else str(value["qualification_report_hash"])
        ),
        release_name=str(value.get("release_name", "NODI-CUSTOM-V2")),
        execution=execution,
    )


def dataset_spec_payload(spec: DatasetSpec) -> dict[str, Any]:
    payload = asdict(spec)
    payload["output_dir"] = str(spec.output_dir)
    payload["execution"]["cache_dir"] = (
        None if spec.execution.cache_dir is None else str(spec.execution.cache_dir)
    )
    payload["execution"]["output_dir"] = (
        None if spec.execution.output_dir is None else str(spec.execution.output_dir)
    )
    return cast(dict[str, Any], json.loads(json.dumps(payload)))
