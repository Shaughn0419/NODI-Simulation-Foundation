# NODI Simulation Foundation

Standalone analytical simulation and immutable dataset tooling for NODI research.

The v1 product provides a stable Python API and CLI for single-state simulation,
deterministic batches, one-axis intervention pairs, custom datasets, and
content-addressed release validation. It has no runtime dependency on Paper 1,
Paper 2, the legacy NODI Simulator, or COMSOL.

## Product contract

```python
simulate_state(state_spec)
simulate_batch(states, execution=...)
build_dataset(dataset_spec)
build_intervention_pairs(pair_spec)
derive_observation(result, theta=...)
validate_release(path)
```

All physical inputs use explicit SI-unit field names. Candidate feature support
is reported by capability status; unsupported or unqualified features are never
silently clipped, defaulted, or filled with zero.

## Current status

N1 Physics Core and N2 Product Surface are complete. The exact source lineage
and rewrite-only migration policy are recorded in `source_map.json`; current
execution state is summarized in `LIVE_HANDOFF.md`.

## Install and quickstart

```text
python -m pip install nodi_foundation-*.whl
nodi-foundation info
nodi-foundation capabilities
nodi-foundation simulate examples/state.yaml --output result.json
nodi-foundation dataset build examples/dataset.yaml --output release/
nodi-foundation release validate release/
```

Python callers can construct `SimulationState()` and call `simulate_state`, or
pass validated mappings directly. Batch results preserve input order; cache and
resume never change state or result identities.

## Scope boundaries

- analytical M1 is the default engine;
- COMSOL/M2 may only provide optional, release-bound qualification metadata;
- Paper-specific XAI metrics, labels, gates, and model policy are downstream;
- large state tables and sealed labels live in immutable releases, not Git.
