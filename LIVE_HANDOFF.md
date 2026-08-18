# NODI Simulation Foundation live handoff

- Released product version: `v1.0.0` (immutable)
- Target product version: `v2.0.0`
- Current state: `R1_FORMAL_ENGINE_COMPLETE_R2_ACTIVE`
- Current batch: `R2_QUALIFICATION_PANEL_AND_NESTED_PILOT`
- Physics specification source: Paper 1 analytical M1 at
  `bb27a3ac882344e4ef26663102cd6c0a6882b675`
- Foundation physics base: `ea01b875d031c18541bf740c3db0a21868d2e318`
- Migration mode: `REIMPLEMENT_FROM_SPECIFICATION_NO_RUNTIME_IMPORT`
- Released engine/schema/feature identity: `1.0.0 / 1.0 / 1.0`
- Target engine/schema/feature identity: `2.0.0 / 2.0 / 2.0`
- Maximum aggregate workers: `24`
- Historical v1 control production workers: `1`
- Formal v2 production workers: `PENDING_R2_PILOT`
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
- Paper 2 final intake: `HOLD_FOR_FORMAL_FIELD_COUPLING_M1_V2`

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
