# NODI Simulation Foundation

NODI Simulation Foundation 4.0.0 is a standalone, deterministic simulator and
content-addressed reference-data product for an idealized dry-etched glass
nanochannel. The current physics profile is
`FORMAL_FIELD_COUPLING_M1_V4_DRY_ETCH`. Runtime operation does not depend on
Paper 1, Paper 2, COMSOL, or another repository.

The active branch contains only the v4 contract, producer, qualification
receipt, and compact release manifest. Large reproducible tables are ignored
under `releases/nodi-v4`; superseded products remain recoverable from Git tags
and GitHub releases instead of being duplicated in the working tree.

## Geometry and input contract

- `width_m` is top width `W`, `depth_m` is vertical depth `H`, and
  `sidewall_angle_deg` is the sidewall angle `alpha` measured from the
  substrate plane.
- Bottom width is `b = W - 2 H / tan(alpha)`; at 90 degrees, `b = W`.
- `b = 0` is the legal closed-apex dry-etch terminus. A materially negative
  value is rejected, never clipped. Only numerical roundoff at zero is
  canonicalized.
- Current principal bounds are width 0.2-2.0 um, depth 0.2-2.0 um, angle
  70-90 degrees, particle diameter 20-200 nm, and wavelength 400-900 nm.

These bounds define a coupled domain, not an unrestricted Cartesian product.
The effective particle diameter, including the declared one-sided wall
exclusion layer, must be strictly smaller than the depth and local channel
width. Beam waist must be at least one wavelength. A supplied complex
refractive index is interpreted at that state's wavelength; the package does
not invent a dispersion curve.

## Install and quickstart

Python 3.12 is required.

```text
python -m pip install nodi_foundation-4.0.0-py3-none-any.whl
nodi-foundation info
nodi-foundation capabilities
nodi-foundation simulate examples/state.yaml --output result.json
nodi-foundation dataset build examples/dataset.yaml --output custom-release/
nodi-foundation release validate custom-release/
```

```python
from nodi_foundation import SimulationState, derive_observation, simulate_state

result = simulate_state(SimulationState())
print(result.S_W, result.C_r_W, result.C_i_W)
print(derive_observation(result, theta=0.0))
print(result.physics_profile_id, result.fidelity_class, result.claim_ceiling)
```

`FAST_SCALING_CONTROL_V1` is callable only when explicitly selected for
software regression or scaling checks. A formal-domain or numerical failure
never falls back to it.

## Stable API and data model

The public compatibility contract contains six functions:

- `simulate_state(state_spec) -> StateResult`
- `simulate_batch(states, execution=...) -> BatchResult`
- `build_dataset(dataset_spec) -> DatasetRelease`
- `build_intervention_pairs(pair_spec) -> PairRelease`
- `derive_observation(result, theta=...) -> float`
- `validate_release(path) -> ValidationReport`

Inputs and outputs are immutable SI-unit models with canonical SHA-256
identities. The v4 catalogue contains 27 primitive features and each reference
row contains 36 derived physical descriptors. Periodic and polarization
equivalences are canonicalized before identity generation. Collection NA is
treated physically through `NA / n_fill`, and `collection_na < n_fill` is
required.

Release validation checks safe paths, row counts, file sizes and hashes,
profile identity, qualification bindings, uniqueness, and cross-release
alignment. Schemas are in [`schemas/state_schema.json`](schemas/state_schema.json)
and [`schemas/pair_schema.json`](schemas/pair_schema.json).

## Physics and qualification boundary

The formal engine evaluates an absolutely power-normalized Gaussian source,
finite idealized trapezoid reference field, homogeneous-sphere complex Mie
amplitudes, local position field, vector angular pupil, and common-field
`B/S/C` coupling. It is a first-order M1 reference with declared limits. It is
not full Maxwell, COMSOL, experimental, fabrication-process, roughness,
calibrated detector, event-time, mobility, clogging, yield, or unrestricted
physical-truth authority.

The single current qualification receipt is
[`formal_m1_v4_dry_etch_qualification_report.json`](formal_m1_v4_dry_etch_qualification_report.json),
SHA-256 `f6eda106983dcd72ac96290bd44f6dc644d4f8bbb8590f9a9248c8de715936e5`.
It was produced on Python 3.12.10 with NumPy 2.5.2, SciPy 1.18.0, and PyArrow
25.0.1. All 384 coupled-domain cases passed, including eight exact closed-apex
cases. Maximum reference refinement from order 96 to 128 was 0.453%; maximum
pupil refinement from 64x128 to 80x160 was 1.47%; the strict 80x160 to 96x192
change was 0.804%. Production therefore uses an 80x160 pupil and order-96
reference quadrature.

## Current reference products

| Product | Information-bearing scale |
| --- | ---: |
| Capability sprint | 32,768 states |
| Quickstart | 4,096 states |
| Development atlas | 524,288 states from 4,096 independent reference blocks |
| Development interventions | 16,384 one-axis pairs |
| Evaluation inputs | 131,072 states from 1,024 independent reference blocks |
| Evaluation labels | 131,072 aligned, sealed labels |

The development design covers 13 continuous reference dimensions and then
crosses independent particle, position, and observation strata. Exact linear
power normalization is fixed at 1 W in formal releases so rescaled duplicate
states do not inflate the dataset. Development and evaluation have disjoint
state identities; input and sealed-label rows are exactly aligned. Exact
release IDs, primary-file hashes, design-balance receipts, and acceptance
results are in [`v4_release_manifest.json`](v4_release_manifest.json).

## Reproduction and resources

```text
python tools/qualify_formal_m1_v4_dry_etch.py
python tools/build_reference_releases_v4.py --phase all --workers 4
```

The current release execution contract is four worker processes with numerical
library threads pinned to one per process. The producer is deterministic,
chunked, resumable, and bounded by a 206 GB submission stop, a 208 GB emergency
stop, a strict committed-memory ceiling below 210 GB, and 30 GB launch
headroom. Rebuildable fragments, raw logs, caches, and obsolete release
versions are not committed.

See [`DATASET_CARD.md`](DATASET_CARD.md) for feature semantics, literature
support, intended use, and limitations, and [`LIVE_HANDOFF.md`](LIVE_HANDOFF.md)
for the current operational receipt.
