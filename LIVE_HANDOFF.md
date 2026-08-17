# NODI Simulation Foundation live handoff

- Product target: `v1.0.0`
- Active phase: `N2_PRODUCT_SURFACE`
- Completed phase: `N1_PHYSICS_CORE`
- Current batch: `N2_API_BATCH_RELEASE_SURFACE`
- Foundation base commit: `8c319dcc9d1f6b36fd0af70bf61646385c885220`
- Physics specification source: Paper 1 analytical M1 at
  `bb27a3ac882344e4ef26663102cd6c0a6882b675`
- Optional utility reference: legacy NODI Simulator at
  `96c514d3908ed1bcdd84d342cadf5be1e8a9dd0b`
- Migration mode: `REIMPLEMENT_FROM_SPECIFICATION_NO_RUNTIME_IMPORT`
- Maximum aggregate workers: `24`
- Committed-memory ceiling: `<210000000000 bytes`

## Current next dependency

Complete the six-entry public API, capability catalogue, schemas, CLI, deterministic
batch/chunk/resume engine, immutable release validation, and wheel smoke.

## Claim ceiling

The frozen Paper 1 baseline has implementation parity under the analytical M1
contract. Parameter extensions remain `SUPPORTED_WITH_LIMITS`; parity does not
establish full-domain, full-wave, experimental, fabrication, or release authority.
