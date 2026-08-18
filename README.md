# NODI Simulation Foundation

Standalone simulation and immutable reference-data tooling for NODI research.
The released 1.0.0 software and data remain byte-for-byte immutable, but their
physics profile is now formally classified as `FAST_SCALING_CONTROL_V1`: a
software, pipeline, and scaling control that is not eligible as Paper 2 final
truth. The product-correction mainline is implementing
`FORMAL_FIELD_COUPLING_M1_V2` for the 2.0.0 release. Neither line has a runtime
dependency on Paper 1, Paper 2, the legacy simulator, COMSOL, or an external
checkout.

The machine-readable correction and exact immutable v1 bindings are in
[v1_control_reclassification.json](v1_control_reclassification.json). The v1
profile never serves as an automatic fallback for the formal profile.

## Install and quickstart

Python 3.12 is required.

```text
python -m pip install nodi_foundation-2.0.0-py3-none-any.whl
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
print(result.physics_profile_id, result.fidelity_class, result.claim_ceiling)
```

`SimulationState()` selects `FORMAL_FIELD_COUPLING_M1_V2`. The old scaling
control runs only when `physics_profile_id="FAST_SCALING_CONTROL_V1"` is set
explicitly. A formal-domain or numerical failure is returned as an error; it
never switches profiles.

## Stable API

Only these six functions form the public compatibility contract:

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

`SimulationState` is an immutable nested model with an explicit physics profile
and SI-unit names for
geometry, particle, position, source, environment, and observation operator.
Invalid coupled states are rejected rather than clipped. `StateResult` exposes
`B_bg_W`, `S_W`, `C_r_W`, `C_i_W`, `Y_0_W`, complex-overlap metadata,
fidelity and claim ceilings, factorized block IDs, numerical-receipt IDs,
versions, and canonical identities. Full field details
are defined by [state_schema.json](schemas/state_schema.json) and intervention
rows by [pair_schema.json](schemas/pair_schema.json).

Stable error codes remain `E_DOMAIN_INVALID`, `E_SCHEMA_INCOMPATIBLE`,
`E_NUMERICAL_NONFINITE`, `E_RESOURCE_LIMIT`, and `E_RELEASE_INVALID`.

## Formal field-coupling profile

The v2 engine independently evaluates an absolutely power-normalized Gaussian
source, finite-length trapezoid replacement-phase reference field, analytic
local empty-channel excitation, complex homogeneous-sphere Mie amplitudes,
vector angular pupil, and one common positive operator for `B`, `S`, and `C`.
Reference, particle, position, and operator identities are separately hashed so
nested production can reuse real intermediate blocks. Its declared ceiling is
first-order M1 with explicit omissions; it is not full Maxwell, COMSOL,
experimental, event-time, or detector-readout authority.

R1 engine implementation, the single R2 qualification/pilot, and the single R3
formal capability sprint are complete. The 384-state panel passed with declared
limits, and the 4,096-state nested pilot selected one worker and chunk size
1,024. The binding report SHA-256 is
`1b2059100a3d18260ca3e4c65f9ee9a72095e062063910a3a3651bd92f1b94f3`.
The fresh 32,768-state sprint retained all 26 primitives under its predeclared
rule and froze `particle_longitudinal` as the primary exposure and
`pupil_inner_radius` as the different-mechanism replication exposure. R4
reference products are produced only from this formal v2 identity.

## Frozen v1 control products

The sole v1 capability sprint retained all 26 declared primitives and 20
derived descriptors. Its `channel_width` and `particle_depth` selections are
frozen control-route results only. They do not select v2 features, authorize
Paper 2 intake, or establish that all 26 variables have formal-field support.

| Product | Rows | Release ID |
| --- | ---: | --- |
| NODI-QUICKSTART-V1 | 4,096 | `a1b20622a0bd23079569135692c3f2f9e733a62a537cecb3faac3a310dcbfb8c` |
| NODI-ATLAS-DEV-V1 | 524,288 | `3c483f971d21241f39ce5e941a7e4e375f8a952fd3f560dc6bd8fd1b73333cbb` |
| Development interventions | 16,384 | `e3c620e49d60af6f62201ca67e6a2934eb639b2d988b42d490a59232080a2c01` |
| NODI-ATLAS-EVAL-INPUTS-V1 | 65,536 | `2a1e513b1ff022d93e508d1a9d0bfa94782374ba14cc2ce706d3bc8f78fc2eff` |
| NODI-ATLAS-EVAL-LABELS-V1.sealed | 65,536 | `94930a90743425fdb6f729aacd2cad519012bf18cac1cc8cee99346bbe09c7e2` |

The exact immutable v1 receipts are in
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
workers and less than 210,000,000,000 committed bytes. The historical v1 N3
pilot measured the control kernel at about 15,876 states/s with one worker.
The formal v2 worker choice is set only by its R2 nested pilot. Raw logs,
checkpoints, rebuildable fragments, and large state tables are not committed.

## Scientific boundary and correction state

The frozen v1 canonical point is retained as a single-point implementation
regression. It is not domain validation. All v1 parameter extensions and data
products are `SCALING_CONTROL_ONLY`, with claim ceiling
`SOFTWARE_PIPELINE_AND_SCALING_CONTROL_ONLY`; they are not Paper 2 final truth,
full-wave, experimental, calibrated-detection, fabrication, yield, mobility,
or COMSOL evidence. Dataset size and retained feature count are infrastructure
properties, not independent scientific claims.

Formal qualification, the nested performance pilot, and the new capability
sprint are complete. Fresh v2 reference releases remain the final data gate.
The event-time/readout chain is outside this correction route.

Copyright and reuse terms are in [LICENSE](LICENSE); citation metadata is in
[CITATION.cff](CITATION.cff).
