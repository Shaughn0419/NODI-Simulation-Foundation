# NODI Foundation v1 reference datasets

## Summary

These releases contain deterministic synthetic outputs from NODI Simulation
Foundation 1.0.0 using the analytical M1 applicability profile. They support
software integration, controlled analytical studies, and fresh holdout
workflows. They do not contain experimental, COMSOL, fabrication, mobility,
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

## Capability freeze

One 32,768-state sprint retained all 26 primitives after legal one-axis effect
checks. `channel_width` is the primary exposure family and `particle_depth` is
the replication family from a different predeclared mechanism group. The
selection does not use downstream model errors. No second feature campaign or
Development-size doubling is permitted for v1.

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

Appropriate uses include API/CLI integration, deterministic examples,
analytical sensitivity work within the declared domains, and testing immutable
data-release consumers. Do not treat these data as experimental truth,
full-wave validation, material calibration, clinical evidence, fabrication
feasibility, production yield, or authority to rank real devices.

## Access, license, and citation

Large data files are intentionally not stored in Git. Access is controlled by
the Foundation owner; the sealed label artifact has a stricter owner-only
delivery state. Code and data reuse are governed by `LICENSE`. Cite the
software using `CITATION.cff` and include the exact dataset release ID used.
