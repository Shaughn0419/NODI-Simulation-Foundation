# NODI Simulation Foundation

NODI Simulation Foundation 5.0.0 is a standalone deterministic simulator and
content-addressed reference-data producer for an idealized dry-etched glass
nanochannel. The current profile is
`FORMAL_FIELD_COUPLING_M1_V5_EXACT_SUPPORT`; it has no runtime dependency on
Paper 1, Paper 2, COMSOL, or another repository.

V5 is a breaking scientific-contract release. It replaces the V4 horizontal
particle-fit approximation with exact wall-normal erosion, puts reference and
particle fields on one fill-medium pupil, normalizes the analyzer as a passive
rank-one projector, and supplies explicit low-field and split-group semantics.

## Geometry contract

- `width_m` is top width `W`, `depth_m` is vertical depth `H`, and
  `sidewall_angle_deg` is measured from the substrate plane.
- `b = W - 2 H / tan(alpha)` is the bottom width. `b = 0` is the legal closed
  apex; a materially negative value is rejected and is never clipped.
- The particle-center domain is the exact cross-section eroded normally from
  every physical wall by `R = diameter/2 + effective_wall_exclusion`.
- `depth_fraction` maps over the exact eroded depth span, then
  `lateral_fraction` maps over the exact eroded cross-section at that depth.
- Principal API bounds are width/depth 0.2-2.0 um, angle 70-90 degrees,
  particle diameter 20-200 nm, and vacuum wavelength 400-900 nm. They form a
  coupled legal domain, not an unrestricted fabricability claim.

## Optical convention

The receiver is the fill-medium side of the idealized system. At normalized
pupil radius `rho`, both formal fields use
`q = k_fill sin(theta_fill) = k0 NA rho`; integration weights are fill-medium
solid angle. The reference uses an analytic longitudinal Gaussian transform
and piecewise lateral Gauss integration at the trapezoid path-slope changes.
The analyzer is a passive ideal projector with eigenvalues 0 and 1.

This remains a first-order formal M1 model. Fresnel/Snell interfaces, full
Maxwell boundaries, multiple scattering, roughness, corner rounding, material
dispersion lookup, detector noise/readout, transport, clogging, yield, and
fabrication-process prediction are outside its authority.

## Install and use

Python 3.12 is required.

```text
python -m pip install nodi_foundation-5.0.0-py3-none-any.whl
nodi-foundation info
nodi-foundation capabilities
nodi-foundation simulate examples/state.yaml --output result.json
nodi-foundation dataset build examples/dataset.yaml --output custom-release/
nodi-foundation release validate custom-release/
```

```python
from nodi_foundation import SimulationState, simulate_state

result = simulate_state(SimulationState())
print(result.B_bg_W, result.S_W, result.C_r_W, result.C_i_W)
print(result.coupling_defined, result.coupling_undefined_reason)
print(result.reference_design_id, result.split_group_id)
```

The stable facade contains `simulate_state`, `simulate_batch`, `build_dataset`,
`build_intervention_pairs`, `derive_observation`, and `validate_release`.
The complete Python and CLI contract is documented in [`API.md`](API.md);
`src/nodi_foundation/api.py` is the sole authoritative export list.
`FAST_SCALING_CONTROL_V1` remains an explicitly selected software regression
control and is never an automatic fallback.

## Qualification and releases

The single qualification artifact is
[`formal_m1_v5_qualification_report.json`](formal_m1_v5_qualification_report.json).
It covers one consolidated invariant panel, 384 coupled-domain convergence
states, and a 4,096-state performance pilot. Production uses an 80x160
Gauss-Legendre pupil and order-96 piecewise lateral quadrature.

Formal products are rebuilt with:

```text
python tools/qualify_formal_m1_v5.py
python tools/build_reference_releases_v5.py --phase all --workers 4
```

Large reproducible tables stay ignored under `releases/nodi-v5`; the tracked
`v5_release_manifest.json` is their compact receipt. Only V5 remains in the
active working tree. V4 is recoverable from Git tag `v4.0.0`, not duplicated
beside the current product.

## License and contributions

Copyright 2026 Shaughn0419. Original code, documentation, and project-produced
datasets are licensed under the [Apache License 2.0](LICENSE). Contributions follow
[`CONTRIBUTING.md`](CONTRIBUTING.md) and are submitted under the same license.
Third-party dependencies and referenced upstream materials remain under their
own terms and are not relicensed by this repository.
