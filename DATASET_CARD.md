# NODI Foundation v3 dataset card

## Summary

The current releases are deterministic outputs of NODI Simulation Foundation
3.0.0 using `FORMAL_FIELD_COUPLING_M1_V3_DRY_ETCH`. They are eligible as
first-order formal-M1 reference data only within the declared idealized
dry-etch limits. They are not full-wave, COMSOL, experimental, fabrication,
mobility, clogging, yield, calibrated-detection, event-time, or unrestricted
physical truth.

## Domain and geometry

Nominal bounds are width 0.2-2.0 um, depth 0.2-2.0 um, sidewall angle 70-90
degrees, particle diameter 20-200 nm, and wavelength 400-900 nm. Width is the
top width and the angle is measured from the substrate plane. The ideal bottom
width is `W - 2 H / tan(alpha)`. Zero is a legal closed apex; negative values
are rejected rather than clipped.

The valid data domain is coupled: particles must fit the depth and their local
channel width, and the beam waist must be at least the wavelength. Each
refractive index is interpreted at the row's wavelength. No automatic material
dispersion database, corner rounding, surface roughness, or etch-process model
is supplied.

## Provenance and qualification

- Engine/schema/feature versions: `3.0.0 / 3.0 / 3.0`.
- Physics profile: `FORMAL_FIELD_COUPLING_M1_V3_DRY_ETCH`.
- Sampling: deterministic scrambled Sobol reference blocks with invalid coupled
  states rejected.
- Qualification report SHA-256:
  `adc804dc447a6688dcd2943e3e43fe5c3aea71b8fdf40f9c64caabcfd225e20a`.
- Feature catalogue SHA-256:
  `782deded565d28ee70a1250b87f13c526089f2ff38dd8abd47d6512ab9a67f17`.
- Outputs: `B_bg_W`, `S_W`, `C_r_W`, `C_i_W`, `Y_0_W`, overlap metadata,
  factorized block IDs, numerical receipts, applicability, and canonical IDs.
- Derived descriptors: 23, including bottom width, bottom-width fraction, and
  dry-etch depth utilization.

The 384-state qualification panel passed and includes eight exact apex cases.
Production uses a 32x64 vector pupil and order-96 reference quadrature, checked
against 40x80 and order 128.

## Composition

- Capability sprint: 32,768 states.
- Quickstart: 4,096 rows selected from the capability sprint without recompute.
- Development: 524,288 unique states.
- Development interventions: 16,384 pairs, split equally between
  `particle_longitudinal` and `particle_diameter`.
- Evaluation: 65,536 unique inputs with 2,048 intervention anchors.
- Evaluation labels: a separately held, exactly aligned 65,536-row commitment.

The full content IDs, file hashes, sizes, formal bindings, and acceptance
results are in [`v3_release_manifest.json`](v3_release_manifest.json).

## Split and leakage controls

- Development and Evaluation have zero shared state IDs.
- Evaluation inputs and labels have identical state IDs in identical order.
- Labels are content-addressed in an owner-custody `.sealed` release; sealing is
  controlled separation and commitment, not encryption.
- Labels remain `SEALED_NOT_DELIVERED` until the applicable prediction freeze.
- Release validation rejects mixed profiles, stale qualification hashes, unsafe
  paths, size drift, and content drift.

## Intended and prohibited uses

Appropriate uses are formal-M1 reference modelling, API/CLI integration,
deterministic regression, bounded feature studies, and downstream experiments
whose claims stay below the profile ceiling. Do not treat the data as evidence
for fabrication feasibility, experimental performance, full-wave agreement,
calibrated detection, mobility, clogging, yield, or real-device ranking.

Only v3 is retained in the active release root. Earlier products are not mixed
with current data and are recoverable only from their immutable Git tags or
GitHub releases. Code and data reuse are governed by `LICENSE`; cite the
software and the exact release ID consumed.
