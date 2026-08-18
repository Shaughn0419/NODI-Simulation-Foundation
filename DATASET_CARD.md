# NODI Foundation V5 dataset card

## Scope and claim ceiling

V5 tables are deterministic outputs of
`FORMAL_FIELD_COUPLING_M1_V5_EXACT_SUPPORT`. They are first-order idealized
formal references with declared limits, not experimental truth, COMSOL/full
wave evidence, fabrication feasibility, calibrated detection, transport,
clogging, yield, or route-ranking authority.

Material indices are point values at each row wavelength. Particle index may
be complex; fill and wall indices are real. No material identity or dispersion
curve is inferred.

## Exact dry-etch support

For lateral coordinate `u` and depth `z` measured upward from the nominal
bottom, the physical side half-width is
`a(z) = b/2 + z cot(alpha)`. With
`R = particle_diameter/2 + effective_wall_exclusion`, the exact accessible
half-width is `h(z) = a(z) - R/sin(alpha)`. The accessible upper depth is
`H-R`; the lower depth is the larger of the bottom-wall offset `R` and the
intersection of the two eroded sidewalls. This naturally yields a rectangle,
trapezoid, or triangle. For `b=0`, the degenerate bottom is not treated as a
physical wall and the eroded support is a triangle.

Every released position satisfies all actual center-to-wall normal distances
`>= R`. Rows report geometric particle-surface clearance separately from the
remaining effective-exclusion margin. Geometric and optical diameter both
equal the declared homogeneous-sphere diameter; effective steric diameter is
`d+2t`.

## Primitive controls

| Group | Controls and API domains | Release treatment |
| --- | --- | --- |
| Geometry | width/depth 0.2-2.0 um; sidewall 70-90 deg | Coupled legal designs; explicit rectangular, near-apex, and exact-apex strata. |
| Particle | diameter 20-200 nm; real index 1.30-2.00; imaginary index 0-0.20 | Release real index 1.34-2.00; eight diameter levels up to each design's exact legal maximum. |
| Position | longitudinal -2 to 2 w0; lateral -1 to 1; depth 0.05-0.95 | Four balanced positions; lateral/depth fractions use exact eroded support. |
| Source | wavelength 400-900 nm; waist 0.5-2.0 um; power 0.25-4 W; two offsets -1.5 to 1.5 w0; full Poincare polarization | `w0 >= wavelength`; formal releases fix power at 1 W and sample offsets over -0.8 to 0.8. |
| Environment | fill index 1.30-1.40; wall index 1.40-1.55; exclusion 0-20 nm | Explicit `t=0` baseline every 16th reference plus 2-20 nm sensitivity sampling. Exclusion requires application-specific calibration. |
| Observation | NA 0.40-1.20; analyzer azimuth 0-pi; ellipticity -pi/4 to pi/4; pupil radii 0-0.75 and 0.85-1; sector center 0-2pi and width pi/6-2pi | Physical NA requires `NA < n_fill`; boundary designs include exact low/high NA, full pupil, annulus, and partial sectors. |

Periodic endpoints and polarization-degenerate coordinates are canonicalized
before state identity generation. API domains are sensitivity/model domains;
they do not assert that every Cartesian combination is fabricable.

## Output semantics

Each row contains 27 primitive controls and 50 derived descriptors. Important
V5 additions are exact accessible topology/area/depth span, exact physical
coordinates, wall-normal clearances, geometric/optical/steric diameters,
common-pupil transverse wavevector, and passive-analyzer trace.

`reference_design_id` identifies shared geometry/source/environment design.
`split_group_id` is the default leakage-safe train/evaluation grouping key and
equals that design identity. `reference_block_id` remains the sampled-field
cache identity and must not be used as the ML split key.

`B_bg_W`, `S_W`, and complex `C` are always retained when finite. Eta is null
only when a reference or particle field is below the normalization-aware
numerical floor; `coupling_defined` and `coupling_undefined_reason` distinguish
`LOW_REFERENCE_FIELD`, `LOW_PARTICLE_FIELD`, and their joint case. Missing eta
is not a zero coupling label.

## Release design

- Capability: 256 designs x 8 particles x 4 positions x 4 operators = 32,768
  states.
- Quickstart: 4,096 Capability rows without recomputation.
- Development: 4,096 designs x 128 = 524,288 states.
- Interventions: 16,384 legal pairs, divided between the selected primary and
  a different-mechanism replication feature.
- Evaluation: 1,024 independently seeded designs x 128 = 131,072 inputs, with
  4,096 anchors and separately held aligned labels.

Development and Evaluation must have zero shared state IDs and zero shared
split-group IDs. Input/label IDs and order must match. The `.sealed` suffix is
a content-addressed custody commitment, not encryption.

The scale remains unchanged from V4 because 4,096 independent designs already
provide wide, stage-stable coverage. V5 improves information content through
exact apex, zero-exclusion, joint high-NA/low-fill, and exact-fit strata rather
than inflating row count. Expansion should be justified by group-aware learning
curves, not by raw volume.

## Provenance and version policy

Formal releases bind the exact feature catalogue, implementation, numerical
profile, qualification matrix, frozen scaling-control regression, and
qualification-report hashes. Only current V5 products are retained locally;
V4 source and receipts remain available through Git history and tag `v4.0.0`.
