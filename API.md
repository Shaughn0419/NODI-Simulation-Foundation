# Public interface contract

This contract applies to NODI Simulation Foundation 5.0.0. The package root is
the supported import path. `src/nodi_foundation/api.py` is the sole authoritative
export list; `src/nodi_foundation/__init__.py` only re-exports that list.

## Python operations

| Operation | Signature | Result |
| --- | --- | --- |
| Single state | `simulate_state(state_spec)` | `StateResult` |
| Ordered batch | `simulate_batch(states, *, execution=None)` | `BatchResult` |
| Dataset release | `build_dataset(dataset_spec)` | `DatasetRelease` |
| Intervention pairs | `build_intervention_pairs(pair_spec)` | `PairRelease` |
| Analyzer observation | `derive_observation(result, *, theta)` | `float` in watts |
| Release validation | `validate_release(path)` | `ValidationReport` |

`state_spec` may be a `SimulationState` or a mapping accepted by
`SimulationState.from_mapping`. Batch inputs preserve input order. `theta` is a
finite angle in radians. `validate_release` reports content or identity failures
through `ValidationReport.valid` and `ValidationReport.errors` rather than
promoting an invalid release.

The facade also exposes immutable input models (`GeometryState`, `ParticleState`,
`PositionState`, `SourceState`, `EnvironmentState`,
`ObservationOperatorState`, and `SimulationState`), execution and release types,
and the read-only `capabilities()` metadata query. `capabilities()` describes
supported features; it is not a seventh simulation or production operation.

## Errors

Invalid or unsupported computations fail explicitly with `FoundationError`,
which carries a machine-readable `code`. The stable code namespace is:

- `E_DOMAIN_INVALID`
- `E_FEATURE_UNSUPPORTED`
- `E_OPERATOR_UNQUALIFIED`
- `E_NUMERICAL_NONFINITE`
- `E_RELEASE_HASH_MISMATCH`
- `E_SCHEMA_INCOMPATIBLE`
- `E_RESOURCE_LIMIT`

No public operation clips an invalid state, substitutes an unresolved effect
with zero, or silently falls back to another physics profile.

## Command line

```text
nodi-foundation info
nodi-foundation capabilities
nodi-foundation simulate STATE --output RESULT
nodi-foundation batch STATES_JSONL --output RUN_DIR [execution options]
nodi-foundation dataset build SPEC --output RELEASE_DIR
nodi-foundation pairs build SPEC --output RELEASE_DIR [execution options]
nodi-foundation release validate RELEASE_DIR
```

Execution options are `--workers`, `--chunk-size`, `--cache-dir`, and
`--no-resume`. Release validation exits with code 0 when valid and 2 when
invalid. `STATE` and `SPEC` accept YAML or JSON; `STATES_JSONL` contains one
state mapping per non-empty line. Other failures are explicit command failures.

## Serialized contracts

- State input: [`schemas/state_schema.json`](schemas/state_schema.json)
- Pair rows: [`schemas/pair_schema.json`](schemas/pair_schema.json)
- Minimal state example: [`examples/state.yaml`](examples/state.yaml)
- Dataset-build example: [`examples/dataset.yaml`](examples/dataset.yaml)

Generated datasets and pair tables are immutable content-addressed releases.
Their `manifest.json` binds file paths, byte sizes, SHA-256 digests, engine,
schema, feature, profile, and qualification identity. The `_physics` package and
all unlisted symbols are internal and have no compatibility guarantee.
