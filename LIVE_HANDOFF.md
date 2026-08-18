# NODI Simulation Foundation live handoff

- Current product version: `3.0.0`
- Current state: `V3_DRY_ETCH_RELEASE_READY`
- Physics profile: `FORMAL_FIELD_COUPLING_M1_V3_DRY_ETCH`
- Engine/schema/feature: `3.0.0 / 3.0 / 3.0`
- Release root: `releases/nodi-v3`
- Release manifest: `v3_release_manifest.json`
- Release manifest SHA-256:
  `8476b866bde8b3c3762656d81eb5a26265e2750dbaf9b6fab08d6616cc78bfab`
- Qualification report SHA-256:
  `adc804dc447a6688dcd2943e3e43fe5c3aea71b8fdf40f9c64caabcfd225e20a`
- Qualification: `PASS_WITH_LIMITS`, 384/384 states, eight exact apex cases
- Production pupil/reference order: `32x64 / 96`
- Selected workers/chunk: `1 / 1024`
- Maximum permitted workers: `24`
- Committed-memory ceiling: `<210000000000 bytes`
- Capability sprint: `PASS`, all 26 primitives retained
- Primary/replication: `particle_longitudinal / particle_diameter`
- Development: `524288` unique states
- Development interventions: `16384` unique pairs
- Evaluation: `65536` unique states, zero Development overlap
- Evaluation input/label alignment: `PASS`
- Sealed-label delivery: `SEALED_NOT_DELIVERED`
- Current-branch data-version policy: `V3_ONLY`

## Binding geometry decision

`width_m` is top width, `depth_m` is vertical depth, and sidewall angle is
measured from the substrate plane. Bottom width is
`W - 2 H / tan(alpha)`. Zero bottom width is the legal dry-etch closed-apex
terminus. A negative value is never retained or clipped; only floating-point
roundoff at zero is normalized.

The nominal five ranges form a coupled domain. Particle fit, local width,
depth, nonnegative bottom width, and beam-waist/wavelength constraints remain
binding. State refractive indices apply at the state wavelength.

## Current product state

The formal engine, one qualification report, one nested performance pilot, one
capability sprint, and the complete v3 reference release set are finished. All
seven releases validate against the exact v3 implementation, numerical
profile, feature catalogue, qualification matrix, and parity-panel hashes.

Large current tables remain outside Git in `releases/nodi-v3`. Superseded local
v1/v2 release directories, manifests, and producers were removed to prevent
mixed-version search and consumption. Historical recovery uses immutable Git
tags/GitHub releases only.

The data are first-order idealized dry-etch M1 references with declared limits.
They do not establish full-wave, COMSOL, experimental, etch-process,
fabrication, detector-readout, mobility, clogging, yield, or unrestricted
physical authority.
