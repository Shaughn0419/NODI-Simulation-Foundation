"""Deterministic custom dataset generation and release assembly."""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from scipy.stats import qmc  # type: ignore[import-untyped]

from .batch import ExecutionSpec, simulate_batch
from .capabilities import capabilities
from .errors import E_DOMAIN_INVALID, FoundationError
from .models import SimulationState, StateResult
from .releases import DatasetRelease, write_release_manifest


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    output_dir: Path
    state_count: int
    feature_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    fixed_values: dict[str, float] = field(default_factory=dict)
    sampling_method: str = "sobol"
    seed: int = 0
    profile: str = "M1_ANALYTICAL_SYNTHETIC_V1"
    release_name: str = "NODI-CUSTOM-V1"
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
    base = SimulationState().to_payload()
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
            "B_bg_W": result.B_bg_W,
            "S_W": result.S_W,
            "C_r_W": result.C_r_W,
            "C_i_W": result.C_i_W,
            "Y_0_W": result.Y_0_W,
            "eta_real": result.eta_real,
            "eta_imag": result.eta_imag,
            "eta_abs": result.eta_abs,
            "numerical_status": result.numerical_status,
            "operator_qualification_status": result.operator_qualification_status,
            "config_hash": result.config_hash,
            "result_hash": result.result_hash,
        }
    )
    return row


def _write_parquet_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    try:
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_dataset(dataset_spec: DatasetSpec) -> DatasetRelease:
    """Build one deterministic custom dataset and content-addressed release."""

    states = sample_states(dataset_spec)
    batch = simulate_batch(states, execution=dataset_spec.execution)
    dataset_spec.output_dir.mkdir(parents=True, exist_ok=True)
    data_path = dataset_spec.output_dir / "data.parquet"
    _write_parquet_atomic(data_path, [result_row(result) for result in batch.results])
    metadata = {
        "release_name": dataset_spec.release_name,
        "profile": dataset_spec.profile,
        "state_count": dataset_spec.state_count,
        "sampling_method": dataset_spec.sampling_method,
        "seed": dataset_spec.seed,
        "feature_ranges": {key: list(value) for key, value in dataset_spec.feature_ranges.items()},
        "fixed_values": dataset_spec.fixed_values,
        "worker_count": dataset_spec.execution.workers,
        "chunk_size": dataset_spec.execution.chunk_size,
        "cache_hits": batch.cache_hits,
        "resumed_chunks": batch.resumed_chunks,
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
        profile=str(value.get("profile", "M1_ANALYTICAL_SYNTHETIC_V1")),
        release_name=str(value.get("release_name", "NODI-CUSTOM-V1")),
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
