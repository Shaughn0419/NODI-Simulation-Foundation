"""Deterministic bounded batch execution with cache and chunk resume."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from .models import ENGINE_VERSION, SimulationState, StateResult
from .resources import ResourceSnapshot, assert_resource_budget, default_worker_count
from .simulate import simulate_state


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    workers: int = default_worker_count()
    chunk_size: int = 1024
    cache_dir: Path | None = None
    output_dir: Path | None = None
    resume: bool = True
    worker_reserve_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if (
            not isinstance(self.chunk_size, int)
            or isinstance(self.chunk_size, bool)
            or self.chunk_size < 1
        ):
            raise ValueError("chunk_size must be a positive integer")


@dataclass(frozen=True, slots=True)
class BatchResult:
    results: tuple[StateResult, ...]
    state_count: int
    cache_hits: int
    resumed_chunks: int
    elapsed_seconds: float
    resource_snapshot: ResourceSnapshot


def _coerce_state(value: SimulationState | Mapping[str, Any]) -> SimulationState:
    return value if isinstance(value, SimulationState) else SimulationState.from_mapping(value)


def _simulate_worker(state: SimulationState) -> StateResult:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    return simulate_state(state)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _cache_path(cache_dir: Path, state: SimulationState) -> Path:
    return cache_dir / ENGINE_VERSION / f"{state.state_id}.json"


def _load_result(path: Path, expected_state_id: str) -> StateResult | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = StateResult(**payload)
        if result.state_id != expected_state_id:
            return None
        result.to_payload()
        return result
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _run_chunk(states: Sequence[SimulationState], workers: int) -> list[StateResult]:
    if workers == 1 or len(states) <= 1:
        return [simulate_state(state) for state in states]
    with ProcessPoolExecutor(max_workers=min(workers, len(states))) as executor:
        return list(
            executor.map(_simulate_worker, states, chunksize=max(1, len(states) // workers))
        )


def simulate_batch(
    states: Iterable[SimulationState | Mapping[str, Any]],
    *,
    execution: ExecutionSpec | None = None,
) -> BatchResult:
    """Simulate states in stable input order with optional cache and chunk resume."""

    started = monotonic()
    spec = execution or ExecutionSpec()
    resource = assert_resource_budget(
        spec.workers,
        worker_reserve_bytes=spec.worker_reserve_bytes,
    )
    canonical_states = tuple(_coerce_state(state) for state in states)
    results: list[StateResult] = []
    cache_hits = 0
    resumed_chunks = 0
    for offset in range(0, len(canonical_states), spec.chunk_size):
        chunk = canonical_states[offset : offset + spec.chunk_size]
        chunk_index = offset // spec.chunk_size
        chunk_path = (
            None if spec.output_dir is None else spec.output_dir / f"chunk-{chunk_index:08d}.jsonl"
        )
        if spec.resume and chunk_path is not None and chunk_path.is_file():
            loaded = [
                StateResult(**json.loads(line))
                for line in chunk_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            if len(loaded) == len(chunk) and all(
                result.state_id == state.state_id and result.to_payload()
                for result, state in zip(loaded, chunk, strict=True)
            ):
                results.extend(loaded)
                resumed_chunks += 1
                continue

        chunk_results: list[StateResult | None] = [None] * len(chunk)
        missing: list[SimulationState] = []
        missing_indexes: list[int] = []
        for index, state in enumerate(chunk):
            cached = (
                None
                if spec.cache_dir is None
                else _load_result(_cache_path(spec.cache_dir, state), state.state_id)
            )
            if cached is None:
                missing.append(state)
                missing_indexes.append(index)
            else:
                chunk_results[index] = cached
                cache_hits += 1
        computed = _run_chunk(missing, spec.workers)
        for index, result in zip(missing_indexes, computed, strict=True):
            chunk_results[index] = result
            if spec.cache_dir is not None:
                _atomic_write(
                    _cache_path(spec.cache_dir, chunk[index]), result.to_canonical_json() + "\n"
                )
        complete = [result for result in chunk_results if result is not None]
        if len(complete) != len(chunk):
            raise RuntimeError("internal batch result cardinality mismatch")
        if chunk_path is not None:
            _atomic_write(
                chunk_path, "".join(result.to_canonical_json() + "\n" for result in complete)
            )
        results.extend(complete)
    return BatchResult(
        results=tuple(results),
        state_count=len(results),
        cache_hits=cache_hits,
        resumed_chunks=resumed_chunks,
        elapsed_seconds=monotonic() - started,
        resource_snapshot=resource,
    )
