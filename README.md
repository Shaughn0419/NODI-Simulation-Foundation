# NODI Simulation Foundation

Standalone analytical simulation and immutable reference-data tooling for NODI
research. Version 1.0.0 owns its analytical M1 implementation, public state
model, batch runner, feature catalogue, and release format. It has no runtime
dependency on Paper 1, Paper 2, the legacy simulator, COMSOL, or an external
checkout.

## Install and quickstart

Python 3.12 is required.

```text
python -m pip install nodi_foundation-1.0.0-py3-none-any.whl
nodi-foundation info
nodi-foundation capabilities
nodi-foundation simulate examples/state.yaml --output result.json
nodi-foundation dataset build examples/dataset.yaml --output custom-release/
nodi-foundation release validate custom-release/
```

The minimal Python path is:

```python
from nodi_foundation import SimulationState, derive_observation, simulate_state

result = simulate_state(SimulationState())
print(result.S_W, result.C_r_W, result.C_i_W)
print(derive_observation(result, theta=0.0))
print(result.applicability_profile_id, result.operator_qualification_status)
```

## Stable API

Only these six functions form the v1 compatibility contract:

- `simulate_state(state_spec) -> StateResult` validates and evaluates one state.
- `simulate_batch(states, execution=...) -> BatchResult` preserves input order
  and supports bounded workers, cache, and chunk resume.
- `build_dataset(dataset_spec) -> DatasetRelease` performs deterministic Sobol
  or seeded-random sampling and writes a content-addressed Parquet release.
- `build_intervention_pairs(pair_spec) -> PairRelease` changes one primitive at
  a time and records paired differences in `S`, `C_r`, `C_i`, and `Y_0`.
- `derive_observation(result, theta=...) -> float` evaluates
  `S + 2 C_r cos(theta) + 2 C_i sin(theta)` without another simulation.
- `validate_release(path) -> ValidationReport` checks manifest identity, file
  sizes, hashes, and safe relative paths.

`SimulationState` is an immutable nested model with explicit SI-unit names for
geometry, particle, position, source, environment, and observation operator.
Invalid coupled states are rejected rather than clipped. `StateResult` exposes
`B_bg_W`, `S_W`, `C_r_W`, `C_i_W`, `Y_0_W`, complex-overlap metadata,
applicability status, versions, and canonical identities. Full field details
are defined by [state_schema.json](schemas/state_schema.json) and intervention
rows by [pair_schema.json](schemas/pair_schema.json).

Stable error codes are `E_DOMAIN_INVALID`, `E_SCHEMA_INCOMPATIBLE`,
`E_NUMERICAL_NONFINITE`, `E_RESOURCE_LIMIT`, and `E_RELEASE_INVALID`.

## Frozen v1 capability and data products

The sole capability sprint retained all 26 declared primitives and 20 derived
descriptors. It selected `channel_width` as the primary exposure family and
`particle_depth` as the different-mechanism replication family. This selection
is frozen; v1 permits neither a second feature campaign nor Development
doubling.

| Product | Rows | Release ID |
| --- | ---: | --- |
| NODI-QUICKSTART-V1 | 4,096 | `a1b20622a0bd23079569135692c3f2f9e733a62a537cecb3faac3a310dcbfb8c` |
| NODI-ATLAS-DEV-V1 | 524,288 | `3c483f971d21241f39ce5e941a7e4e375f8a952fd3f560dc6bd8fd1b73333cbb` |
| Development interventions | 16,384 | `e3c620e49d60af6f62201ca67e6a2934eb639b2d988b42d490a59232080a2c01` |
| NODI-ATLAS-EVAL-INPUTS-V1 | 65,536 | `2a1e513b1ff022d93e508d1a9d0bfa94782374ba14cc2ce706d3bc8f78fc2eff` |
| NODI-ATLAS-EVAL-LABELS-V1.sealed | 65,536 | `94930a90743425fdb6f729aacd2cad519012bf18cac1cc8cee99346bbe09c7e2` |

The exact current receipts are in
[n3_release_manifest.json](n3_release_manifest.json); large tables and sealed
labels remain outside Git under the ignored content-addressed release root.
Quickstart is a deterministic subset of the capability release and performs no
additional physics calculation. Evaluation inputs are fresh and disjoint from
Development. Their labels are held as a separate owner-custody commitment and
are not a downstream-delivery artifact.

See [DATASET_CARD.md](DATASET_CARD.md) for provenance, fields, intended use,
limitations, and access policy.

## Reproducibility and resource policy

```text
python tools/build_reference_releases.py
```

Production is deterministic, chunked, recoverable, and capped at 24 aggregate
workers and less than 210,000,000,000 committed bytes. The N3 pilot measured
the closed-form kernel at about 15,876 states/s with one worker; multiprocessing
was slower, so the formal releases correctly used one worker. Raw logs,
checkpoints, rebuildable fragments, and large state tables are not committed.

## Scientific boundary

The frozen canonical point has implementation parity with the declared Paper 1
analytical M1 product. Parameter extensions are analytical synthetic controls
with `SUPPORTED_WITH_LIMITS` qualification. They are not full-wave,
experimental, calibrated-detection, fabrication, yield, mobility, or COMSOL
evidence. Dataset size and retained feature count are infrastructure properties,
not independent scientific claims.

Copyright and reuse terms are in [LICENSE](LICENSE); citation metadata is in
[CITATION.cff](CITATION.cff).
