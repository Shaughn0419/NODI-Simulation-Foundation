# NODI Foundation reference datasets

## Summary

These immutable releases contain deterministic outputs from NODI Simulation
Foundation 1.0.0. Their embedded historical profile identifier is
`M1_ANALYTICAL_SYNTHETIC_V1`; the binding current classification is
`FAST_SCALING_CONTROL_V1`, with fidelity `SCALING_CONTROL_ONLY`, scientific role
`SOFTWARE_AND_PIPELINE_CONTROL`, and `paper2_final_truth_eligible=false`.
They support software integration and control-route regression. They do not
contain Paper 2 final truth, experimental, COMSOL, fabrication, mobility,
clogging, yield, or calibrated detector evidence.

## Provenance and composition

- Physics lineage: the canonical Paper 1 analytical M1 specification at commit
  `bb27a3ac882344e4ef26663102cd6c0a6882b675`, reimplemented without source
  copying or runtime imports.
- Engine/schema/feature versions: `1.0.0 / 1.0 / 1.0`.
- Sampling: deterministic scrambled Sobol states with explicit fixed seeds;
  invalid coupled states are rejected, never clipped.
- Primitive universe: 26 SI-unit state fields.
- Derived descriptors: 20 dimensionless geometry, optical, position, pupil,
  and Stokes descriptors; they are not independent degrees of freedom.
- Outputs: `B_bg_W`, `S_W`, `C_r_W`, `C_i_W`, `Y_0_W`, overlap metadata,
  applicability/qualification fields, and canonical state/result identities.

The v1 products are a 4,096-row Quickstart subset, a 524,288-row Development
atlas, 16,384 Development intervention pairs, 65,536 fresh Evaluation inputs
with 2,048 marked anchors, and a separately held 65,536-row label commitment.
Exact release IDs, byte hashes, sizes, and local paths are recorded in
`n3_release_manifest.json`.

The original manifests and tables are not rewritten. The owner correction is
an additive, content-bound overlay in `v1_control_reclassification.json`; it
binds the v1 tag, commit, manifest hashes, and every release ID.

## Capability freeze

One 32,768-state sprint retained all 26 primitives after legal one-axis effect
checks. `channel_width` is the primary exposure family and `particle_depth` is
the replication family from a different predeclared mechanism group. The
selection does not use downstream model errors. No second feature campaign or
Development-size doubling is permitted for v1. The selected families are v1
controls only and must not be imported into the v2 formal identity or used to
select Paper 2 final features.

## Splits and leakage controls

- Quickstart is selected by lexicographic `state_id` from the capability
  release and adds no new calculation.
- Development and Evaluation use different fixed seeds and have zero shared
  state IDs.
- Evaluation input and label state IDs are identical and in the same order.
- Labels are content-addressed in a separate `.sealed` owner-custody release;
  sealing denotes controlled separation and commitment, not encryption.
- The label release is not delivered to downstream analysis before the
  applicable prediction freeze.

## Validation

Every release has a canonical manifest containing its release ID, logical
metadata, primary-file size, and SHA-256. `validate_release(path)` detects
manifest, size, path, or content drift. The v1 acceptance checks confirm all
row counts, Development/Evaluation disjointness, Quickstart subset identity,
input/label alignment, intervention allocation, and `1.0.0 / 1.0` identities.

## Intended and prohibited uses

Appropriate uses include API/CLI integration, deterministic examples, scaling
controls, and testing immutable data-release consumers. Do not import the v1
Development, Evaluation, sealed labels, interventions, or selected exposure
families as Paper 2 final data. Do not treat these data as scientific truth,
formal-field domain validation, experimental truth, full-wave validation,
material calibration, clinical evidence, fabrication feasibility, production
yield, or authority to rank real devices.

## Access, license, and citation

Large data files are intentionally not stored in Git. Access is controlled by
the Foundation owner; the sealed label artifact has a stricter owner-only
delivery state. Code and data reuse are governed by `LICENSE`. Cite the
software using `CITATION.cff` and include the exact dataset release ID used.

## v2 formal release boundary

`FORMAL_FIELD_COUPLING_M1_V2` passed its single 384-state qualification panel
and 4,096-state nested performance pilot with disposition `PASS_WITH_LIMITS`.
The binding report is `formal_m1_v2_qualification_report.json`, file SHA-256
`1b2059100a3d18260ca3e4c65f9ee9a72095e062063910a3a3651bd92f1b94f3`.
Formal releases must bind that exact report, physics implementation, feature
catalogue, qualification matrix, and parity panel; release validation rejects
missing/mixed profile rows. The fresh 32,768-state formal sprint independently
retained all 26 primitives and froze `particle_longitudinal` as primary and
`pupil_inner_radius` as the different-mechanism replication exposure. Its
release IDs and exact file hashes are recorded in `v2_release_manifest.json`;
v1 feature selections were not imported.

## v2 composition and split controls

The v2 release set contains a 32,768-state capability sprint, a 4,096-row
no-recompute Quickstart subset, 524,288 unique Development states, 16,384
Development intervention pairs, 65,536 fresh Evaluation inputs with 2,048
marked anchors, and a separately held 65,536-row label commitment. The
intervention allocation is fixed at 8,192 pairs for `particle_longitudinal` and
8,192 for `pupil_inner_radius`.

Every scientific row has profile `FORMAL_FIELD_COUPLING_M1_V2` and binds the
exact R2 qualification report plus the physics, numerical-profile, capability,
qualification-matrix, and parity-panel hashes. Quickstart state IDs are a subset
of the capability sprint; Development and Evaluation each contain no duplicate
state IDs and share zero IDs; Evaluation inputs and labels are identical in ID
and order. `validate_release` checks content hashes, formal binding, and row
profile for every delivered table. Exact release IDs and file SHA-256 values are
in `v2_release_manifest.json`.

The v2 products are eligible formal first-order M1 references with declared
limits. They do not establish full-wave, COMSOL, experimental, material,
fabrication, mobility, clogging, yield, calibrated-detection, event-time, or
unrestricted physical-truth claims. The sealed labels remain owner-only and are
not delivered before the applicable prediction freeze.
