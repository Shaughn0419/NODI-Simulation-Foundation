# NODI Simulation Foundation live handoff

- Current product version: `4.0.0`
- Current state: `V4_CORRECTED_FORMAL_REFERENCE_RELEASES_PASS`
- Physics profile: `FORMAL_FIELD_COUPLING_M1_V4_DRY_ETCH`
- Engine/schema/feature: `4.0.0 / 4.0 / 4.0`
- Release root: `releases/nodi-v4`
- Release manifest: `v4_release_manifest.json`
- Release manifest SHA-256:
  `abe500496799b6ecf15a80e202a1a753a5bd2c7639d511dcae5d05cbaefbc1e7`
- Qualification report SHA-256:
  `f6eda106983dcd72ac96290bd44f6dc644d4f8bbb8590f9a9248c8de715936e5`
- Qualification: `PASS_WITH_LIMITS`, 384/384 states, eight exact apex cases
- Production pupil/reference order: `80x160 / 96`
- Current release workers: `4`
- Observed development-run peak committed memory: `179162140672 bytes`
- Submission/emergency/absolute memory gates:
  `206000000000 / 208000000000 / <210000000000 bytes`
- Primitive/derived feature count: `27 / 36`
- Primary/replication exposure:
  `particle_lateral / beam_offset_longitudinal_over_w0`
- Sealed-label delivery: `SEALED_NOT_DELIVERED`
- Current-branch data-version policy: `V4_ONLY`

## Current release identities

| Product | Rows or pairs | Release ID |
| --- | ---: | --- |
| Capability sprint | 32,768 states | `ae6911e7a0801933f6777573bdec220a1923f548182a79e7281fd7cfea50faa0` |
| Qualification profile | 27 feature rows | `d9c3605d8a0c9b5f525c5d0b430f6a580a6b5a37206b693e8ef87f0e263c5548` |
| Quickstart | 4,096 states | `9b08689e066e209c31f47e37adb593a912459a038dafdbc76a3bde7856e95e61` |
| Development atlas | 524,288 states | `d18ea65b607bb8eceb54b3e7b8980390777b29eed9ff6412ebb680bcaeb24f9b` |
| Development interventions | 16,384 pairs | `5194e791aa33a30e675e8cbf05dd74a41b0fc75fb84b39a2882183a66b00367d` |
| Evaluation inputs | 131,072 states | `f03e0e5336d7949add07142a9866f9a845034d10f02df9ee41eab642a0e8d8fa` |
| Evaluation labels | 131,072 sealed rows | `ecfb8a8262622ec328574255bbf8102d88a90311836deeedfcaba93ff134d039` |

## Binding geometry and feature decisions

`width_m` is top width, `depth_m` is vertical depth, and the sidewall angle is
measured from the substrate plane. Bottom width is
`W - 2 H / tan(alpha)`. Zero is the legal closed-apex dry-etch terminus; a
materially negative value is rejected and never clipped.

The current principal ranges are width/depth 0.2-2.0 um, sidewall angle 70-90
degrees, particle diameter 20-200 nm, and wavelength 400-900 nm. They form a
coupled legal domain. Particle fit uses geometric radius plus one declared
one-sided effective wall-exclusion layer. Collection NA is interpreted through
the fill medium, periodic states are canonicalized, and formal releases fix
normalization power at 1 W to avoid exact linear duplicates.

## Acceptance and custody

The development atlas contains 4,096 unique 13-dimensional reference blocks,
with a minimum final normalized span of 0.99925. Particle optical, position,
and observation assignments pass balanced-rotation checks. Development has
524,288 unique state IDs; Evaluation has 131,072 unique state IDs and zero
Development overlap. Evaluation inputs and sealed labels have identical state
ID order, and exactly 4,096 Evaluation rows are marked as intervention anchors.

An initial evaluation candidate correctly failed closed because 512
unpolarized boundary states overlapped Development after polarization
canonicalization. The current evaluation boundary policy uses distinct partial
polarization levels and passed the zero-overlap gate. The failed transition
artifact was replaced and removed; only the accepted v4 products remain.

These data are first-order idealized dry-etch M1 references with declared
limits. They do not establish full-wave, COMSOL, experimental, etch-process,
fabrication, detector-readout, mobility, clogging, yield, or unrestricted
physical authority.
