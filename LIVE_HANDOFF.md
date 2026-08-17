# NODI Simulation Foundation live handoff

- Product version: `v1.0.0`
- Terminal state: `N1_N2_N3_N4_COMPLETE`
- Current batch: `V1_RELEASE_CLOSEOUT`
- Physics specification source: Paper 1 analytical M1 at
  `bb27a3ac882344e4ef26663102cd6c0a6882b675`
- Foundation physics base: `ea01b875d031c18541bf740c3db0a21868d2e318`
- Migration mode: `REIMPLEMENT_FROM_SPECIFICATION_NO_RUNTIME_IMPORT`
- Engine/schema/feature identity: `1.0.0 / 1.0 / 1.0`
- Maximum aggregate workers: `24`
- Formal production workers selected by pilot: `1`
- Committed-memory ceiling: `<210000000000 bytes`
- External-consumer smoke: `PASS`
- Reference-release validation: `PASS`
- Sealed-label delivery state: `SEALED_NOT_DELIVERED`
- Source archive: annotated Git tag `v1.0.0`

## Frozen v1 decisions

The sole 32,768-state capability sprint retained 26 primitives and 20 derived
descriptors. The primary exposure family is `channel_width`; the replication
family is `particle_depth` from a different mechanism group. No second feature
campaign or Development doubling is authorized for v1.

Quickstart has 4,096 rows, Development has 524,288 states and 16,384
intervention pairs, and fresh Evaluation has 65,536 inputs with 2,048 marked
anchors plus a separate owner-custody label commitment. Exact content IDs are
in `n3_release_manifest.json`; the software/wheel receipt and acceptance state
are in `release_manifest.json`.

## Claim ceiling

The frozen canonical point has analytical M1 implementation parity. Parameter
extensions remain `SUPPORTED_WITH_LIMITS`; neither parity nor the synthetic
reference releases establish full-domain, full-wave, experimental, material,
fabrication, mobility, yield, calibrated-detection, or scientific authority.

Post-v1 work is SemVer maintenance only unless the owner explicitly authorizes
a new product phase. Large datasets, sealed labels, build products, raw logs,
checkpoints, and rebuildable fragments remain outside Git.
