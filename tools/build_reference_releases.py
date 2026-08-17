"""Build the single N3 capability sprint and v1 reference releases.

Large artifacts are written below the ignored ``releases/`` directory.  The
only repository receipt is the compact aggregate JSON requested with
``--receipt``.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import tempfile
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from nodi_foundation.batch import ExecutionSpec, simulate_batch
from nodi_foundation.capabilities import capabilities
from nodi_foundation.datasets import DatasetSpec, build_dataset, sample_states
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    SimulationState,
    StateResult,
    canonical_json,
    canonical_sha256,
)
from nodi_foundation.releases import validate_release, write_release_manifest
from nodi_foundation.resources import COMMITTED_MEMORY_LIMIT_BYTES, system_committed_memory_bytes

ROOT = Path(__file__).resolve().parents[1]
PILOT_STATE_COUNT = 8192
CAPABILITY_STATE_COUNT = 32_768
QUICKSTART_STATE_COUNT = 4096
DEVELOPMENT_STATE_COUNT = 524_288
DEVELOPMENT_PAIR_COUNT = 16_384
EVALUATION_STATE_COUNT = 65_536
EVALUATION_ANCHOR_COUNT = 2048
PRODUCTION_CHUNK_SIZE = 65_536

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

DERIVED_DESCRIPTORS = (
    "W_over_lambda",
    "H_over_lambda",
    "dp_over_lambda",
    "H_over_W",
    "W_over_w0",
    "H_over_w0",
    "mie_size_parameter",
    "relative_particle_index_abs",
    "relative_particle_index_phase_rad",
    "longitudinal_over_w0",
    "steric_ratio",
    "wall_fill_contrast",
    "normalized_collection_na",
    "pupil_area_fraction",
    "source_stokes_q",
    "source_stokes_u",
    "source_stokes_v",
    "analyzer_stokes_q",
    "analyzer_stokes_u",
    "analyzer_stokes_v",
)


@cache
def _feature_records() -> tuple[dict[str, Any], ...]:
    return capabilities().features


@cache
def _feature_ranges() -> dict[str, tuple[float, float]]:
    return {
        str(row["id"]): (float(row["domain"][0]), float(row["domain"][1]))
        for row in _feature_records()
    }


@cache
def _feature_paths() -> dict[str, str]:
    return {str(row["id"]): str(row["path"]) for row in _feature_records()}


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


def _read_manifest(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def _valid_release(directory: Path, release_name: str, count: int) -> bool:
    report = validate_release(directory)
    if not report.valid:
        return False
    manifest = _read_manifest(directory)
    metadata = manifest.get("metadata", {})
    observed_count = metadata.get("state_count", metadata.get("pair_count"))
    return (
        metadata.get("release_name") == release_name
        and observed_count == count
        and manifest.get("engine_version") == ENGINE_VERSION
        and manifest.get("feature_version") == FEATURE_VERSION
    )


def _dataset_spec(
    directory: Path,
    *,
    state_count: int,
    seed: int,
    release_name: str,
    workers: int,
) -> DatasetSpec:
    return DatasetSpec(
        output_dir=directory,
        state_count=state_count,
        feature_ranges=_feature_ranges(),
        sampling_method="sobol",
        seed=seed,
        release_name=release_name,
        execution=ExecutionSpec(
            workers=workers,
            chunk_size=min(PRODUCTION_CHUNK_SIZE, state_count),
            resume=True,
        ),
    )


def _ensure_dataset(spec: DatasetSpec) -> dict[str, Any]:
    if not _valid_release(spec.output_dir, spec.release_name, spec.state_count):
        print(canonical_json({"event": "build_dataset", "release": spec.release_name}))
        build_dataset(spec)
    report = validate_release(spec.output_dir)
    if not report.valid:
        raise RuntimeError(f"invalid release {spec.output_dir}: {report.errors}")
    return _read_manifest(spec.output_dir)


def _measure_peak(function: Callable[[], Any]) -> tuple[Any, float, int | None]:
    stop = threading.Event()
    initial = system_committed_memory_bytes()
    peak = [initial]

    def monitor() -> None:
        while not stop.wait(0.05):
            value = system_committed_memory_bytes()
            if value is not None and (peak[0] is None or value > peak[0]):
                peak[0] = value

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        result = function()
    finally:
        elapsed = time.monotonic() - started
        stop.set()
        thread.join()
    return result, elapsed, peak[0]


def _run_pilot(output_root: Path) -> dict[str, Any]:
    state_file = output_root / ".production_state.json"
    if state_file.is_file():
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        if payload.get("pilot_state_count") == PILOT_STATE_COUNT:
            return payload
    prior_qualification = output_root / "NODI-QUALIFICATION-PROFILE-V1" / "manifest.json"
    if prior_qualification.is_file():
        prior_manifest = json.loads(prior_qualification.read_text(encoding="utf-8"))
        prior_pilot = prior_manifest.get("metadata", {}).get("throughput_report")
        if (
            isinstance(prior_pilot, dict)
            and prior_pilot.get("pilot_state_count") == PILOT_STATE_COUNT
        ):
            _atomic_json(state_file, prior_pilot)
            return prior_pilot
    pilot_spec = _dataset_spec(
        output_root / ".pilot-unused",
        state_count=PILOT_STATE_COUNT,
        seed=2026081801,
        release_name="NODI-N3-THROUGHPUT-PILOT",
        workers=1,
    )
    states = sample_states(pilot_spec)
    rows: list[dict[str, Any]] = []
    maximum_workers = min(os.cpu_count() or 1, 24)
    candidates = sorted({1, min(4, maximum_workers), min(12, maximum_workers), maximum_workers})
    for workers in candidates:
        batch, elapsed, peak = _measure_peak(
            lambda workers=workers: simulate_batch(
                states,
                execution=ExecutionSpec(
                    workers=workers,
                    chunk_size=len(states),
                    resume=False,
                ),
            )
        )
        row = {
            "workers": workers,
            "state_count": len(states),
            "elapsed_seconds": elapsed,
            "states_per_second": len(states) / elapsed,
            "peak_committed_memory_bytes": peak,
            "result_identity": canonical_sha256([result.result_hash for result in batch.results]),
        }
        rows.append(row)
        print(canonical_json({"event": "throughput_pilot", **row}))
    if len({row["result_identity"] for row in rows}) != 1:
        raise RuntimeError("worker-count pilot changed deterministic result identity")
    baseline = rows[0]["states_per_second"]
    fastest = max(rows, key=lambda row: row["states_per_second"])
    selected = int(fastest["workers"]) if fastest["states_per_second"] >= 1.10 * baseline else 1
    payload = {
        "pilot_state_count": PILOT_STATE_COUNT,
        "candidate_runs": rows,
        "selected_workers": selected,
        "selection_rule": "FASTEST_IF_AT_LEAST_1.10X_SINGLE_ELSE_SINGLE",
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
    }
    _atomic_json(state_file, payload)
    return payload


def _state_with_feature(state: SimulationState, feature: str, value: float) -> SimulationState:
    payload = copy.deepcopy(state.to_payload())
    group, field = _feature_paths()[feature].split(".", 1)
    payload[group][field] = float(value)
    return SimulationState.from_mapping(payload)


def _legal_pair(
    state: SimulationState,
    feature: str,
    bounds: tuple[float, float],
) -> tuple[SimulationState, SimulationState, float, float] | None:
    group, field = _feature_paths()[feature].split(".", 1)
    current = float(state.to_payload()[group][field])
    lower, upper = bounds
    target_low = lower + 0.20 * (upper - lower)
    target_high = lower + 0.70 * (upper - lower)
    for scale in (1.0, 0.5, 0.25, 0.125, 0.0625):
        low_value = current + scale * (target_low - current)
        high_value = current + scale * (target_high - current)
        if math.isclose(low_value, high_value, rel_tol=0.0, abs_tol=1.0e-30):
            continue
        try:
            low = _state_with_feature(state, feature, low_value)
            high = _state_with_feature(state, feature, high_value)
        except FoundationError:
            continue
        return low, high, low_value, high_value
    return None


def _effect_summary(
    capability_states: tuple[SimulationState, ...], workers: int
) -> tuple[list[dict[str, Any]], list[str], str, str]:
    ranges = _feature_ranges()
    groups = _feature_groups()
    records = {str(row["id"]): row for row in _feature_records()}
    pair_specs: list[tuple[str, float, float]] = []
    pair_states: list[SimulationState] = []
    for feature_index, feature in enumerate(sorted(ranges)):
        accepted = 0
        cursor = 0
        while accepted < 64 and cursor < len(capability_states):
            index = (feature_index * 977 + cursor * 509) % len(capability_states)
            pair = _legal_pair(capability_states[index], feature, ranges[feature])
            cursor += 1
            if pair is None:
                continue
            low, high, low_value, high_value = pair
            pair_specs.append((feature, low_value, high_value))
            pair_states.extend((low, high))
            accepted += 1
        if accepted < 48:
            raise RuntimeError(f"insufficient legal one-axis pairs for {feature}: {accepted}")
    batch = simulate_batch(
        pair_states,
        execution=ExecutionSpec(
            workers=workers,
            chunk_size=len(pair_states),
            resume=False,
        ),
    )
    by_feature: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for index, (feature, _, _) in enumerate(pair_specs):
        low = batch.results[2 * index]
        high = batch.results[2 * index + 1]
        delta_s = high.S_W - low.S_W
        delta_cr = high.C_r_W - low.C_r_W
        delta_ci = high.C_i_W - low.C_i_W
        denominator = math.sqrt(delta_s**2 + (2.0 * delta_cr) ** 2 + (2.0 * delta_ci) ** 2)
        exposure = 0.0 if denominator == 0.0 else abs(delta_s) / denominator
        scale = abs(low.S_W) + abs(high.S_W) + abs(low.C_r_W) + abs(high.C_r_W)
        normalized_effect = (
            abs(delta_s) + abs(delta_cr) + abs(delta_ci)
        ) / max(scale, 1.0e-300)
        by_feature[feature].append((exposure, normalized_effect))
    rows: list[dict[str, Any]] = []
    retained: list[str] = []
    for feature in sorted(ranges):
        effects = by_feature[feature]
        logs = np.log(np.maximum([value[0] for value in effects], 1.0e-15))
        robust_span = float(np.quantile(logs, 0.95) - np.quantile(logs, 0.05))
        maximum_effect = max(value[1] for value in effects)
        role = str(records[feature]["role"])
        is_retained = maximum_effect > 1.0e-12 or role == "EXACT_SCALING_CONTROL"
        if is_retained:
            retained.append(feature)
        rows.append(
            {
                "record_type": "FEATURE_EFFECT",
                "feature": feature,
                "mechanism_group": groups[feature],
                "role": role,
                "legal_pair_count": len(effects),
                "robust_log_exposure_span": robust_span,
                "maximum_normalized_effect": maximum_effect,
                "retained": is_retained,
                "qualification_status": "QUALIFIED_ONE_AXIS" if is_retained else "NOT_RETAINED",
            }
        )
    qualified = [row for row in rows if row["retained"]]
    primary_row = max(qualified, key=lambda row: row["robust_log_exposure_span"])
    replication_row = max(
        (row for row in qualified if row["mechanism_group"] != primary_row["mechanism_group"]),
        key=lambda row: row["robust_log_exposure_span"],
    )
    return rows, retained, str(primary_row["feature"]), str(replication_row["feature"])


def _build_qualification(
    directory: Path,
    capability_directory: Path,
    capability_states: tuple[SimulationState, ...],
    pilot: dict[str, Any],
) -> dict[str, Any]:
    release_name = "NODI-QUALIFICATION-PROFILE-V1"
    if _valid_release(directory, release_name, CAPABILITY_STATE_COUNT):
        return _read_manifest(directory)
    prior_manifest_path = directory / "manifest.json"
    qualification_path = directory / "qualification.parquet"
    if prior_manifest_path.is_file() and qualification_path.is_file():
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        prior_metadata = dict(prior_manifest.get("metadata", {}))
        if (
            prior_metadata.get("release_name") == release_name
            and prior_metadata.get("feature_campaign_state") == "FROZEN_NO_SECOND_CAMPAIGN"
            and prior_metadata.get("retained_feature_count") == 26
        ):
            parity_path = ROOT / "canonical_parity_report.json"
            prior_metadata.update(
                {
                    "capability_release_id": _read_manifest(capability_directory)["release_id"],
                    "selected_workers": int(pilot["selected_workers"]),
                    "throughput_report": pilot,
                    "baseline_parity_report_sha256": canonical_sha256(
                        json.loads(parity_path.read_text(encoding="utf-8"))
                    ),
                }
            )
            manifest = write_release_manifest(
                directory,
                release_type="NODI_QUALIFICATION_PROFILE_RELEASE",
                primary_files=("qualification.parquet",),
                metadata=prior_metadata,
            )
            if not validate_release(directory).valid:
                raise RuntimeError("rebound qualification release failed validation")
            return manifest
    workers = int(pilot["selected_workers"])
    feature_rows, retained, primary, replication = _effect_summary(capability_states, workers)
    capability_table = pq.read_table(
        capability_directory / "data.parquet", columns=["operator_qualification_status"]
    )
    operator_counts = Counter(capability_table["operator_qualification_status"].to_pylist())
    rows = feature_rows + [
        {
            "record_type": "OPERATOR_QUALIFICATION",
            "qualification_status": str(status),
            "state_count": int(count),
        }
        for status, count in sorted(operator_counts.items())
    ]
    rows.extend(
        {
            "record_type": "THROUGHPUT",
            "workers": int(run["workers"]),
            "state_count": int(run["state_count"]),
            "elapsed_seconds": float(run["elapsed_seconds"]),
            "states_per_second": float(run["states_per_second"]),
            "peak_committed_memory_bytes": run["peak_committed_memory_bytes"],
        }
        for run in pilot["candidate_runs"]
    )
    directory.mkdir(parents=True, exist_ok=True)
    _write_table(directory / "qualification.parquet", pa.Table.from_pylist(rows))
    parity_path = ROOT / "canonical_parity_report.json"
    parity_hash = canonical_sha256(json.loads(parity_path.read_text(encoding="utf-8")))
    metadata = {
        "release_name": release_name,
        "state_count": CAPABILITY_STATE_COUNT,
        "capability_release_id": _read_manifest(capability_directory)["release_id"],
        "candidate_feature_count": len(_feature_records()),
        "retained_feature_count": len(retained),
        "retained_features": retained,
        "derived_descriptors": list(DERIVED_DESCRIPTORS),
        "mechanism_groups": {key: list(value) for key, value in MECHANISM_GROUPS.items()},
        "qualified_exposure_families": retained,
        "primary_exposure_family": primary,
        "replication_exposure_family": replication,
        "exposure_selection_rule": "LARGEST_ROBUST_LOG_SPAN_WITH_DIFFERENT_GROUP_REPLICATION",
        "selected_workers": workers,
        "throughput_report": pilot,
        "baseline_parity_report_sha256": parity_hash,
        "downstream_power_preview": "NOT_IN_FOUNDATION_SCOPE",
        "feature_campaign_state": "FROZEN_NO_SECOND_CAMPAIGN",
        "development_size_state": "FROZEN_NO_DOUBLING",
        "claim_ceiling": "ANALYTICAL_M1_SYNTHETIC_CONTROLS_WITH_DECLARED_LIMITS",
    }
    manifest = write_release_manifest(
        directory,
        release_type="NODI_QUALIFICATION_PROFILE_RELEASE",
        primary_files=("qualification.parquet",),
        metadata=metadata,
    )
    if not validate_release(directory).valid:
        raise RuntimeError("qualification release failed validation")
    return manifest


def _build_quickstart(directory: Path, capability_directory: Path) -> dict[str, Any]:
    release_name = "NODI-QUICKSTART-V1"
    if _valid_release(directory, release_name, QUICKSTART_STATE_COUNT):
        return _read_manifest(directory)
    source = pq.read_table(capability_directory / "data.parquet")
    subset = source.sort_by([("state_id", "ascending")]).slice(0, QUICKSTART_STATE_COUNT)
    directory.mkdir(parents=True, exist_ok=True)
    _write_table(directory / "data.parquet", subset)
    manifest = write_release_manifest(
        directory,
        release_type="NODI_DATASET_RELEASE",
        primary_files=("data.parquet",),
        metadata={
            "release_name": release_name,
            "state_count": QUICKSTART_STATE_COUNT,
            "source_release_id": _read_manifest(capability_directory)["release_id"],
            "selection": "LEXICOGRAPHIC_STATE_ID_FIRST_4096_NO_RECOMPUTE",
        },
    )
    return manifest


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
        "pair_id": canonical_sha256(
            {
                "anchor_state_id": anchor.state_id,
                "feature": feature,
                "low_state_id": low_state.state_id,
                "high_state_id": high_state.state_id,
            }
        ),
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


def _build_intervention_atlas(
    directory: Path,
    development_spec: DatasetSpec,
    qualification: dict[str, Any],
    workers: int,
) -> dict[str, Any]:
    release_name = "NODI-ATLAS-DEV-INTERVENTIONS-V1"
    if _valid_release(directory, release_name, DEVELOPMENT_PAIR_COUNT):
        return _read_manifest(directory)
    metadata = qualification["metadata"]
    features = (
        str(metadata["primary_exposure_family"]),
        str(metadata["replication_exposure_family"]),
    )
    prior_manifest_path = directory / "manifest.json"
    pairs_path = directory / "pairs.parquet"
    if prior_manifest_path.is_file() and pairs_path.is_file():
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        prior_metadata = dict(prior_manifest.get("metadata", {}))
        if (
            prior_metadata.get("release_name") == release_name
            and prior_metadata.get("pair_count") == DEVELOPMENT_PAIR_COUNT
            and tuple(prior_metadata.get("features", ())) == features
        ):
            return write_release_manifest(
                directory,
                release_type="NODI_INTERVENTION_ATLAS_RELEASE",
                primary_files=("pairs.parquet",),
                metadata=prior_metadata,
            )
    ranges = _feature_ranges()
    states = sample_states(development_spec)
    pair_records: list[
        tuple[str, SimulationState, SimulationState, SimulationState, float, float]
    ] = []
    target_per_feature = DEVELOPMENT_PAIR_COUNT // len(features)
    for feature_index, feature in enumerate(features):
        cursor = feature_index
        accepted = 0
        while accepted < target_per_feature:
            if cursor >= len(states):
                raise RuntimeError(f"insufficient development anchors for {feature}")
            anchor = states[cursor]
            cursor += len(features)
            pair = _legal_pair(anchor, feature, ranges[feature])
            if pair is None:
                continue
            low, high, low_value, high_value = pair
            pair_records.append((feature, anchor, low, high, low_value, high_value))
            accepted += 1
    pair_states = [state for record in pair_records for state in (record[2], record[3])]
    batch = simulate_batch(
        pair_states,
        execution=ExecutionSpec(
            workers=workers,
            chunk_size=len(pair_states),
            resume=False,
        ),
    )
    rows = [
        _pair_row(*record, batch.results[2 * index], batch.results[2 * index + 1])
        for index, record in enumerate(pair_records)
    ]
    directory.mkdir(parents=True, exist_ok=True)
    _write_table(directory / "pairs.parquet", pa.Table.from_pylist(rows))
    manifest = write_release_manifest(
        directory,
        release_type="NODI_INTERVENTION_ATLAS_RELEASE",
        primary_files=("pairs.parquet",),
        metadata={
            "release_name": release_name,
            "pair_count": DEVELOPMENT_PAIR_COUNT,
            "source_release_name": development_spec.release_name,
            "features": list(features),
            "pairs_per_feature": target_per_feature,
            "selection": "FROZEN_PRIMARY_AND_DIFFERENT_MECHANISM_REPLICATION",
        },
    )
    return manifest


def _build_evaluation_releases(
    output_root: Path,
    evaluation_spec: DatasetSpec,
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_dir = output_root / "NODI-ATLAS-EVAL-INPUTS-V1"
    label_dir = output_root / "NODI-ATLAS-EVAL-LABELS-V1.sealed"
    input_name = "NODI-ATLAS-EVAL-INPUTS-V1"
    label_name = "NODI-ATLAS-EVAL-LABELS-V1.sealed"
    if _valid_release(input_dir, input_name, EVALUATION_STATE_COUNT) and _valid_release(
        label_dir, label_name, EVALUATION_STATE_COUNT
    ):
        return _read_manifest(input_dir), _read_manifest(label_dir)
    transition_dir = output_root / ".evaluation-full"
    transition_spec = DatasetSpec(
        output_dir=transition_dir,
        state_count=evaluation_spec.state_count,
        feature_ranges=evaluation_spec.feature_ranges,
        sampling_method=evaluation_spec.sampling_method,
        seed=evaluation_spec.seed,
        release_name="NODI-EVALUATION-FULL-TRANSITION",
        execution=evaluation_spec.execution,
    )
    _ensure_dataset(transition_spec)
    full = pq.read_table(transition_dir / "data.parquet")
    identifiers = full["state_id"].to_pylist()
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
    label_columns = [
        "state_id",
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
    label_table = full.select(label_columns)
    label_dir.mkdir(parents=True, exist_ok=True)
    _write_table(label_dir / "labels.parquet.sealed", label_table)
    label_manifest = write_release_manifest(
        label_dir,
        release_type="NODI_SEALED_LABEL_RELEASE",
        primary_files=("labels.parquet.sealed",),
        metadata={
            "release_name": label_name,
            "state_count": EVALUATION_STATE_COUNT,
            "seed": evaluation_spec.seed,
            "access_state": "SEALED_OWNER_ONLY",
            "delivery_state": "NOT_RELEASED_TO_DOWNSTREAM",
            "sealing_method": "CONTENT_ADDRESSED_SEPARATE_OWNER_CUSTODY",
        },
    )
    input_dir.mkdir(parents=True, exist_ok=True)
    _write_table(input_dir / "inputs.parquet", input_table)
    input_manifest = write_release_manifest(
        input_dir,
        release_type="NODI_EVALUATION_INPUT_RELEASE",
        primary_files=("inputs.parquet",),
        metadata={
            "release_name": input_name,
            "state_count": EVALUATION_STATE_COUNT,
            "intervention_anchor_count": EVALUATION_ANCHOR_COUNT,
            "seed": evaluation_spec.seed,
            "label_commitment_release_id": label_manifest["release_id"],
            "label_delivery_state": "SEALED_NOT_DELIVERED",
        },
    )
    shutil.rmtree(transition_dir)
    return input_manifest, label_manifest


def _release_receipt(directory: Path, manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    return {
        "path": directory.relative_to(ROOT).as_posix(),
        "release_id": manifest["release_id"],
        "release_type": manifest["release_type"],
        "primary_files": manifest["files"],
        "manifest_sha256": canonical_sha256(manifest),
        "valid": validate_release(directory).valid,
        "external_release_root": root.relative_to(ROOT).as_posix(),
    }


def build_all(output_root: Path, receipt_path: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    pilot = _run_pilot(output_root)
    workers = int(pilot["selected_workers"])
    capability_spec = _dataset_spec(
        output_root / "NODI-CAPABILITY-SPRINT-V1",
        state_count=CAPABILITY_STATE_COUNT,
        seed=2026081802,
        release_name="NODI-CAPABILITY-SPRINT-V1",
        workers=workers,
    )
    capability = _ensure_dataset(capability_spec)
    capability_states = sample_states(capability_spec)
    qualification = _build_qualification(
        output_root / "NODI-QUALIFICATION-PROFILE-V1",
        capability_spec.output_dir,
        capability_states,
        pilot,
    )
    quickstart_dir = output_root / "NODI-QUICKSTART-V1"
    quickstart = _build_quickstart(quickstart_dir, capability_spec.output_dir)
    development_spec = _dataset_spec(
        output_root / "NODI-ATLAS-DEV-V1",
        state_count=DEVELOPMENT_STATE_COUNT,
        seed=2026081803,
        release_name="NODI-ATLAS-DEV-V1",
        workers=workers,
    )
    development = _ensure_dataset(development_spec)
    intervention_dir = output_root / "NODI-ATLAS-DEV-INTERVENTIONS-V1"
    interventions = _build_intervention_atlas(
        intervention_dir,
        development_spec,
        qualification,
        workers,
    )
    evaluation_spec = _dataset_spec(
        output_root / ".evaluation-unused",
        state_count=EVALUATION_STATE_COUNT,
        seed=2026081804,
        release_name="NODI-ATLAS-EVAL-INPUTS-V1",
        workers=workers,
    )
    evaluation_inputs, evaluation_labels = _build_evaluation_releases(
        output_root,
        evaluation_spec,
    )
    directories = {
        "capability_sprint": capability_spec.output_dir,
        "qualification_profile": output_root / "NODI-QUALIFICATION-PROFILE-V1",
        "quickstart": quickstart_dir,
        "development_atlas": development_spec.output_dir,
        "development_interventions": intervention_dir,
        "evaluation_inputs": output_root / "NODI-ATLAS-EVAL-INPUTS-V1",
        "evaluation_labels": output_root / "NODI-ATLAS-EVAL-LABELS-V1.sealed",
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
    receipts = {
        name: _release_receipt(directories[name], manifest, output_root)
        for name, manifest in manifests.items()
    }
    if not all(row["valid"] for row in receipts.values()):
        raise RuntimeError("one or more N3 releases failed final validation")
    payload = {
        "manifest_schema_version": 1,
        "phase": "N3_REFERENCE_DATA_PRODUCTS",
        "status": "PASS",
        "release_root": output_root.relative_to(ROOT).as_posix(),
        "selected_workers": workers,
        "maximum_workers": 24,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
        "capability_sprint_state_count": CAPABILITY_STATE_COUNT,
        "quickstart_state_count": QUICKSTART_STATE_COUNT,
        "development_state_count": DEVELOPMENT_STATE_COUNT,
        "development_intervention_pair_count": DEVELOPMENT_PAIR_COUNT,
        "evaluation_state_count": EVALUATION_STATE_COUNT,
        "evaluation_intervention_anchor_count": EVALUATION_ANCHOR_COUNT,
        "feature_campaign_state": "FROZEN_NO_SECOND_CAMPAIGN",
        "development_size_state": "FROZEN_NO_DOUBLING",
        "label_delivery_state": "SEALED_NOT_DELIVERED",
        "releases": receipts,
    }
    _atomic_json(receipt_path, payload)
    state_path = output_root / ".production_state.json"
    if state_path.exists():
        state_path.unlink()
    print(canonical_json({"event": "n3_complete", "receipt": str(receipt_path)}))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "releases" / "nodi-v1")
    parser.add_argument("--receipt", type=Path, default=ROOT / "n3_release_manifest.json")
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    if args.pilot_only:
        print(canonical_json(_run_pilot(args.output.resolve())))
        return 0
    build_all(args.output.resolve(), args.receipt.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
