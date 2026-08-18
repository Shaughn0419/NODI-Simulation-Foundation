# NODI Simulation Foundation live handoff

- Released product version: `v1.0.0` (immutable)
- Target product version: `v2.0.0`
- Current state: `R4_PASS_V2_RELEASE_ACTIVE`
- Current batch: `V2_PRODUCT_RELEASE`
- Physics specification source: Paper 1 analytical M1 at
  `bb27a3ac882344e4ef26663102cd6c0a6882b675`
- Foundation physics base: `ea01b875d031c18541bf740c3db0a21868d2e318`
- Migration mode: `REIMPLEMENT_FROM_SPECIFICATION_NO_RUNTIME_IMPORT`
- Released engine/schema/feature identity: `1.0.0 / 1.0 / 1.0`
- Target engine/schema/feature identity: `2.0.0 / 2.0 / 2.0`
- Maximum aggregate workers: `24`
- Historical v1 control production workers: `1`
- Formal v2 production workers: `1`
- Formal v2 chunk size: `1024`
- Qualification report SHA-256: `1b2059100a3d18260ca3e4c65f9ee9a72095e062063910a3a3651bd92f1b94f3`
- Committed-memory ceiling: `<210000000000 bytes`
- External-consumer smoke: `PASS`
- Reference-release validation: `PASS`
- Sealed-label delivery state: `SEALED_NOT_DELIVERED`
- Source archive: annotated Git tag `v1.0.0`
- v1 current profile ID: `FAST_SCALING_CONTROL_V1`
- v1 scientific role: `SOFTWARE_AND_PIPELINE_CONTROL`
- v1 Paper 2 final eligibility: `false`
- v2 default profile ID: `FORMAL_FIELD_COUPLING_M1_V2`
- v2 release root: `releases/nodi-v2`
- Paper 2 final intake: `ELIGIBLE_FORMAL_M1_REFERENCE_WITH_DECLARED_LIMITS`

## Immutable v1 and binding correction

The sole 32,768-state capability sprint retained 26 primitives and 20 derived
descriptors. The primary exposure family is `channel_width`; the replication
family is `particle_depth` from a different mechanism group. No second feature
campaign or Development doubling is authorized for v1.

Those selections and every v1 release are retained only as software, pipeline,
and scaling controls. Existing tags, Parquet files, sealed labels, release IDs,
and manifests are not overwritten or resealed. The binding additive correction
is `v1_control_reclassification.json`. It prohibits v1 data, labels, and
exposure-family import into the Paper 2 final identity and prohibits automatic
fallback from the formal v2 profile.

Quickstart has 4,096 rows, Development has 524,288 states and 16,384
intervention pairs, and fresh Evaluation has 65,536 inputs with 2,048 marked
anchors plus a separate owner-custody label commitment. Exact content IDs are
in `n3_release_manifest.json`; the software/wheel receipt and acceptance state
are in `release_manifest.json`.

## Current route and claim ceiling

The v1 canonical point is a single-point implementation regression only.
Parameter extensions and releases have fidelity `SCALING_CONTROL_ONLY` and
claim ceiling `SOFTWARE_PIPELINE_AND_SCALING_CONTROL_ONLY`; they establish no
full-domain, full-wave, experimental, material, fabrication, mobility, yield,
calibrated-detection, or scientific authority.

The owner-authorized correction route is: formal field-coupling engine, one
compact qualification report, one 4,096-state nested performance pilot, one
formal 32,768-state capability sprint, then fresh v2 Quickstart/Development/
Evaluation products. Formal requests fail closed; there is no fast-profile
fallback. COMSOL and the event-time/readout chain are not required by this
route. Large datasets, build products, raw logs, checkpoints, and rebuildable
fragments remain outside Git.

R1 now provides the standalone finite trapezoid reference, absolute Gaussian
power normalization, complex homogeneous Mie amplitudes, analytic local field,
vector pupil/operator, common-field `B/S/C` coupling, stable factor block IDs,
and numerical receipt IDs. The default canonical state is within 0.1% of the
frozen reference `B`, reproduces `S` at numerical precision, and is within 5%
for both complex `C` components. These are implementation observations pending
the single R2 qualification report, not a release promotion.

R2 disposition is `PASS_WITH_LIMITS`: 384/384 predeclared panel cases passed,
maximum middle-to-final complex-field refinement was 2.93%, and all direct
parity plus extension invariants passed. The 4,096-state profiled cold pilot
took 3.88 s and the warm operator-summary replay 0.203 s; reference and Mie each
had 64 misses/960 hits, position-field had 1,024 misses/3,072 hits, and observed
system committed-memory peak was about 47.0 GB.

R3 is complete. Its fresh 32,768-state formal sprint retained all 26 declared
primitive features under the predeclared q90 complex-output-effect rule. The
independently selected primary exposure is `particle_longitudinal`; the
different-mechanism replication exposure is `pupil_inner_radius`. The sprint
release ID is `29f5eab0578bec02e0727d43741e7413bef6141c66c6a856c6932e3565cb73bf`
and the qualification-profile release ID is
`64f069373f8987e20018c0ded115af83e1564fd915f40c40881780cf03f44c20`.
Both validate against the exact R2 binding. R4 may now produce the fresh v2
Quickstart, Development, intervention, Evaluation-input, and sealed-label
products; Paper 2 intake remains held until that release set is complete.

R4 is complete. Quickstart contains 4,096 rows copied without recomputation from
the capability sprint. Development contains 524,288 unique formal states and
16,384 unique intervention pairs split evenly across the frozen primary and
replication exposures. Evaluation contains 65,536 fresh unique inputs, 2,048
marked anchors, and an exactly aligned owner-custody label commitment; it shares
zero state IDs with Development. All seven v2 releases validate, all temporary
work directories were removed, and the complete external release root is about
112.7 MB. The exact release IDs and file hashes are in
`v2_release_manifest.json`.

The data are now eligible as formal first-order M1 reference products under the
declared limitations. This is not full-wave, COMSOL, experimental, fabrication,
mobility, event-time, detector-readout, yield, or unrestricted physical-truth
authority. Sealed Evaluation labels remain `SEALED_NOT_DELIVERED`.
