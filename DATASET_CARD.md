# NODI Foundation v4 dataset card

## Scope

The current products are deterministic outputs of NODI Simulation Foundation
4.0.0 using `FORMAL_FIELD_COUPLING_M1_V4_DRY_ETCH`. They are first-order,
idealized dry-etch reference labels with declared limits. They are not COMSOL,
full-wave, experimental, fabrication, mobility, clogging, yield, calibrated
detection, event-time, or unrestricted physical truth.

Geometry uses top width `W`, vertical depth `H`, and sidewall angle `alpha`
measured from the substrate plane. The bottom width is
`b = W - 2 H / tan(alpha)`. `b = 0` is the legal closed-apex dry-etch terminus;
a materially negative value is rejected, never clipped.

Particle fit uses a separate one-sided effective wall-exclusion layer `t`:
`d + 2t` must be strictly smaller than the channel depth and the local width.
The layer is subtracted once per wall. The particle's geometric surface
clearance is still reported separately.

## Primitive-feature decisions

API domains are sensitivity domains, not claims that every Cartesian
combination is fabricable or experimentally safe. Reference domains describe
the formal v4 release design.

| Feature | API domain | v4 reference design | Decision and limit |
| --- | --- | --- | --- |
| `channel_width` | 0.2-2.0 um | full coupled range | Top width; broad nano/micro transition range. Geometry with negative bottom width is excluded. |
| `channel_depth` | 0.2-2.0 um | full coupled range | Vertical etch depth; coupled to width and angle, not sampled as an unrestricted box. |
| `sidewall_angle` | 70-90 deg | full coupled range, exact apex cases | Measured from substrate. Lower angles consume more width; 90 deg is vertical. |
| `beam_offset_longitudinal_over_w0` | -1.5 to 1.5 | Sobol -0.8 to 0.8 | Dimensionless waist ratio prevents a hidden dependence on the selected waist. |
| `beam_offset_lateral_over_w0` | -1.5 to 1.5 | Sobol -0.8 to 0.8 | Same convention as the longitudinal offset. It is not a fabricated channel displacement. |
| `particle_diameter` | 20-200 nm | 8 levels from 20 nm to each reference's legal maximum | One homogeneous-sphere diameter serves geometric and optical M1 roles. No hydrodynamic or deformability claim is implied. |
| `particle_n_real` | 1.34-2.00 | 8 balanced levels rotated against diameter | Point value at the row wavelength; no automatic material identity or dispersion. |
| `particle_n_imag` | 0-0.20 | 8 balanced absorption levels rotated independently | Broad absorption sensitivity range, not a prior over real particle materials. |
| `particle_longitudinal_over_w0` | -2 to 2 | -1.5, -0.5, 0.5, 1.5 with rotated position pairing | Dimensionless optical coordinate; avoids a second hidden length scale. |
| `particle_lateral` | -1 to 1 | -0.75, -0.25, 0.25, 0.75 with rotations | Fraction of the legal center support after particle radius and wall exclusion. |
| `particle_depth` | 0.05-0.95 | 0.15, 0.35, 0.65, 0.85 with rotations | Fraction of the legal vertical center support; exact wall contact is excluded. |
| `wavelength` | 400-900 nm | full Sobol range | Vacuum wavelength. Material indices must be supplied for that wavelength. |
| `beam_waist` | 0.5-2.0 um | conditional Sobol range from `max(0.5 um, wavelength)` to 2.0 um | Formal M1 requires `w0 >= wavelength`; values are waist radii. |
| `normalization_power` | 0.25-4 W | fixed at 1 W | Exact linear reference normalization only. It is excluded from intervention selection and is not laser exposure or dose. |
| `source_polarization_azimuth` | 0 to pi rad | low-discrepancy | Periodic with pi; the duplicated endpoint is canonicalized to zero. |
| `source_ellipticity` | -pi/4 to pi/4 rad | low-discrepancy | Circular endpoints make azimuth non-identifiable, so azimuth is canonicalized there. |
| `degree_of_polarization` | 0-1 | low-discrepancy | At zero, azimuth and ellipticity are canonicalized because they carry no state information. |
| `fill_refractive_index` | 1.30-1.40 | Sobol 1.30-1.39 | Point value at the row wavelength, suitable for aqueous-medium sensitivity; no material database. |
| `wall_refractive_index` | 1.40-1.55 | Sobol 1.41-1.54 | Point value for glass-like wall sensitivity; Fresnel/refraction physics remains omitted. |
| `effective_wall_exclusion` | 0-20 nm | Sobol 2-20 nm, with 0 and 20 nm qualification boundaries | One-sided effective surface layer. The nonzero release range is a sensitivity prior and requires system-specific calibration. |
| `collection_na` | 0.40-1.20 | low-discrepancy plus exact 0.40/1.20 boundaries | Physical NA. The pupil uses `sin(theta_max) = NA / n_fill`; NA above one is legal when below the fill index. |
| `analyzer_azimuth` | 0 to pi rad | low-discrepancy | Periodic with pi; circular analyzer states canonicalize azimuth. |
| `analyzer_ellipticity` | -pi/4 to pi/4 rad | low-discrepancy | Ideal analyzer state, not a calibrated detector transfer function. |
| `pupil_inner_radius` | 0-0.75 | low-discrepancy | Radius normalized to the selected physical-NA pupil. |
| `pupil_outer_radius` | 0.85-1.00 | low-discrepancy | Must exceed the inner radius by at least 0.10. |
| `detector_sector_center` | 0 to 2pi rad | low-discrepancy | Periodic with 2pi; full-pupil sectors canonicalize the center to zero. |
| `detector_sector_width` | pi/6 to 2pi rad | low-discrepancy | Ideal angular support. A full 2pi sector is allowed. |

The catalogue contains 27 primitive controls. Rows also contain 36 derived
descriptors, including bottom and local widths, physical positions and beam
offsets, geometric and effective confinement, actual particle-surface
clearances, `NA/n_fill`, selected pupil area, Stokes coordinates, Mie size
parameter, and peak Gaussian normalization irradiance.

The physical-NA convention follows the pinned
[NODI Simulator pupil specification](https://github.com/Shaughn0419/NODI_Simulator/blob/96c514d3908ed1bcdd84d342cadf5be1e8a9dd0b/docs/realism_v2/physics_spec.md).
Top-width/angle geometry follows the pinned
[COMSOL sidewall authority](https://github.com/Shaughn0419/Comsol_MicroNanoFullChip_Simulation/blob/74cfa70ab9b7f00a5eaf05a9ee191c8ee670db31/roadmap/NODI_V4_8_SIDEWALL_GEOMETRY_AUTHORITY_V1_20260716.json),
except that this project's user-authorized dry-etch contract makes the exact
zero-bottom apex legal. The one-sided, single-subtraction exclusion convention
matches the pinned
[COMSOL formula source](https://github.com/Shaughn0419/Comsol_MicroNanoFullChip_Simulation/blob/74cfa70ab9b7f00a5eaf05a9ee191c8ee670db31/p0_model_package/src/physics_formulas.py).

The 2-20 nm release exclusion is deliberately a sensitivity bracket, not a
universal silica-water constant. Published work reports nanometre-scale
near-wall effects and chemistry-dependent electrostatic depletion, including an
estimated 6.8 nm Debye length for one low-ionic-strength fused-silica system
([Analytical Chemistry](https://pubs.acs.org/doi/abs/10.1021/acs.analchem.5b00485),
[Electrophoresis](https://pubmed.ncbi.nlm.nih.gov/18232026/)). Each application
therefore needs its own surface/ionic-strength calibration.

## Effective release design

- Capability: 256 reference blocks x 8 particles x 4 positions x 4 operators
  = 32,768 states.
- Quickstart: 4,096 rows selected from Capability without recomputation.
- Development: 4,096 independent reference blocks x 8 x 4 x 4 = 524,288
  states.
- Development interventions: 16,384 legal one-axis pairs, split equally across
  the selected primary and different-mechanism replication features.
- Evaluation: 1,024 independently seeded reference blocks x 8 x 4 x 4 =
  131,072 inputs, with 4,096 intervention anchors and separately held aligned
  labels.

Each reference block supplies 13 nontrivial geometry/source/environment
coordinates. Normalization power is fixed. Particle real and imaginary indices
are independently rotated against diameter over complete 64-reference cycles;
lateral and depth positions rotate against longitudinal position over complete
16-reference cycles. Two low-discrepancy pupil geometries and four analyzers
vary across reference blocks. The release manifest records uniqueness, range
span, staged mean stability, and rotation-diversity receipts.

## Split, provenance, and use

Development and Evaluation must share zero state IDs. Evaluation inputs and
labels must have identical IDs in identical order. The `.sealed` label artifact
is a content commitment under separate owner custody, not encryption. Every
formal release binds the exact feature catalogue, implementation, numerical
profile, qualification matrix, scaling-control regression, and qualification
report hashes.

Appropriate uses are formal-M1 reference modelling, deterministic regression,
bounded feature studies, and downstream methods whose claims remain below the
profile ceiling. Do not use these data as evidence for fabrication feasibility,
experimental performance, full-wave agreement, real-device ranking, mobility,
clogging, or yield. Only v4 remains in the active release root; older products
are recoverable from Git history or immutable releases, not mixed locally.
