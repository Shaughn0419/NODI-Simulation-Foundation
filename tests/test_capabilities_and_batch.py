from __future__ import annotations

from dataclasses import replace

from nodi_foundation import (
    ExecutionSpec,
    SimulationState,
    capabilities,
    simulate_batch,
)


def test_capability_catalogue_has_exact_candidate_universe() -> None:
    report = capabilities()
    assert report.feature_count == 27
    assert len({row["id"] for row in report.features}) == 27
    assert {row["implementation_status"] for row in report.features} == {
        "FORMAL_DIRECT",
        "FORMAL_WITH_LIMITS",
    }
    assert all(
        row["profile_status"]["FAST_SCALING_CONTROL_V1"] == "SCALING_CONTROL_ONLY"
        for row in report.features
    )
    assert len(report.catalogue_hash) == 64


def test_batch_order_parallel_and_cache(tmp_path) -> None:
    baseline = SimulationState()
    states = [
        baseline,
        replace(baseline, source=replace(baseline.source, normalization_power_W=0.5)),
        replace(baseline, source=replace(baseline.source, normalization_power_W=2.0)),
    ]
    spec = ExecutionSpec(workers=2, chunk_size=2, cache_dir=tmp_path / "cache")
    first = simulate_batch(states, execution=spec)
    assert first.state_count == 3
    assert first.cache_hits == 0
    assert [result.state_id for result in first.results] == [state.state_id for state in states]
    second = simulate_batch(states, execution=spec)
    assert second.cache_hits == 3
    assert [result.result_hash for result in second.results] == [
        result.result_hash for result in first.results
    ]


def test_batch_chunk_resume_is_identity_preserving(tmp_path) -> None:
    states = [SimulationState(), SimulationState()]
    spec = ExecutionSpec(workers=1, chunk_size=1, output_dir=tmp_path / "run")
    first = simulate_batch(states, execution=spec)
    second = simulate_batch(states, execution=spec)
    assert first.resumed_chunks == 0
    assert second.resumed_chunks == 2
    assert [result.result_hash for result in second.results] == [
        result.result_hash for result in first.results
    ]
