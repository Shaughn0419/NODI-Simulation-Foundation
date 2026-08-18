# NODI Simulation Foundation

NODI Simulation Foundation 3.0.0 is the current standalone simulation and
content-addressed reference-data product. Its default profile is
`FORMAL_FIELD_COUPLING_M1_V3_DRY_ETCH`. It has no runtime dependency on Paper 1,
Paper 2, COMSOL, the legacy simulator, or another checkout.

Only v3 data and manifests belong in the current product tree. Superseded
software is recoverable from Git tags and GitHub releases, not duplicated in
the active branch or local release root.

## Dry-etch geometry contract

The geometry represents an idealized dry-etched glass nanochannel:

- `width_m` is the top width `W`.
- `depth_m` is the vertical depth `H`.
- `sidewall_angle_deg` is the sidewall angle `alpha` measured from the substrate
  plane.
- Bottom width is `b = W - 2 H / tan(alpha)`; at 90 degrees, `b = W`.
- `b = 0` is a legal closed-apex terminus.
- A materially negative `b` is rejected. Only relative floating-point roundoff
  at the zero boundary is canonicalized to zero; geometry is never clipped.

The formal input bounds are width 0.2-2.0 um, depth 0.2-2.0 um, angle 70-90
degrees, particle diameter 20-200 nm, and wavelength 400-900 nm. These are a
coupled domain, not an unrestricted Cartesian product. A state must also have
nonnegative bottom width, particle diameter smaller than channel depth and the
particle's local channel width, and beam waist at least one wavelength.
Refractive indices supplied in a state are interpreted at that state's
wavelength; the package does not silently invent material dispersion.

## Install and quickstart

Python 3.12 is required.

```text
python -m pip install nodi_foundation-3.0.0-py3-none-any.whl
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

`FAST_SCALING_CONTROL_V1` remains callable only as an explicitly selected
software/scaling control. A formal-domain or numerical failure never falls back
to it.

## Stable API

The public compatibility contract contains six functions:

- `simulate_state(state_spec) -> StateResult`
- `simulate_batch(states, execution=...) -> BatchResult`
- `build_dataset(dataset_spec) -> DatasetRelease`
- `build_intervention_pairs(pair_spec) -> PairRelease`
- `derive_observation(result, theta=...) -> float`
- `validate_release(path) -> ValidationReport`

Inputs and outputs are immutable, SI-unit models with canonical SHA-256
identities. Release validation checks paths, sizes, content hashes, exact formal
qualification bindings, and row-profile consistency. Schemas are in
[`schemas/state_schema.json`](schemas/state_schema.json) and
[`schemas/pair_schema.json`](schemas/pair_schema.json).

## Physics and qualification boundary

The formal engine evaluates an absolutely power-normalized Gaussian source,
finite idealized trapezoid reference field, homogeneous-sphere complex Mie
amplitudes, local position field, vector angular pupil, and common-field
`B/S/C` coupling. It is a first-order M1 reference with declared limits, not
full Maxwell, COMSOL, experimental, fabrication-process, roughness, calibrated
detector, event-time, mobility, clogging, yield, or unrestricted physical-truth
authority.

The single v3 qualification report is
[`formal_m1_v3_dry_etch_qualification_report.json`](formal_m1_v3_dry_etch_qualification_report.json),
SHA-256 `adc804dc447a6688dcd2943e3e43fe5c3aea71b8fdf40f9c64caabcfd225e20a`.
All 384 coupled-domain cases passed, including eight exact closed-apex cases.
Maximum reference refinement from order 96 to 128 was 0.0746%; maximum pupil
refinement from 24x48 to 32x64 was 5.97%, and the strict 32x64 to 40x80 check was
0.483%. Production therefore uses a 32x64 pupil and order-96 reference
quadrature. The 4,096-state performance pilot passed with one worker and a
1,024-state chunk.

## Current v3 reference products

| Product | Rows | Release ID |
| --- | ---: | --- |
| NODI-CAPABILITY-SPRINT-V3 | 32,768 | `dd96fb6cd3e15feb05ec35c227b1246e0f344b0b414efc7106fad7dbd69b666e` |
| NODI-QUICKSTART-V3 | 4,096 | `0b1de1a1c90164b24d4fab6818eb9cc4cc3c126635467e6891762be4d4701729` |
| NODI-ATLAS-DEV-V3 | 524,288 | `2cda382d4ab489f193b696444077c918bf49dcd55fecce224f653f501e9735da` |
| Development interventions | 16,384 | `c207f5a5b8ccf730fd72452d1491cdb68c8493e3e7f1400095ec23f11eb36396` |
| NODI-ATLAS-EVAL-INPUTS-V3 | 65,536 | `1154959dfe2c0fadb6c8996dd424c5d8f4a6d72380ddd1ec3c404c13c1898c73` |
| NODI-ATLAS-EVAL-LABELS-V3.sealed | 65,536 | `caccd9819838cfb75af40817f4f7188fd252c95d6607876191684cd68e57c3b8` |

The capability sprint retained all 26 primitive variables under the declared
effect rule. `particle_longitudinal` is the frozen primary exposure and
`particle_diameter` is the different-mechanism replication exposure. Quickstart
is a no-recompute subset. Development and Evaluation share zero state IDs;
Evaluation inputs and sealed labels have identical ID order. The label artifact
remains owner-custody `SEALED_NOT_DELIVERED`.

Exact primary-file hashes and acceptance results are in
[`v3_release_manifest.json`](v3_release_manifest.json). Large tables are kept
outside Git under the ignored `releases/nodi-v3` root.

## Reproduction and resources

```text
python tools/qualify_formal_m1_v3_dry_etch.py
python tools/build_reference_releases_v3.py --phase all
```

Production is deterministic, chunked, recoverable, limited to at most 24
workers, and must remain below 210,000,000,000 bytes of system committed memory.
The measured nested pilot selected one worker because its in-process
content-addressed cache avoids replicated work. Raw logs, fragments,
checkpoints, build products, and obsolete data versions are not committed.

See [`DATASET_CARD.md`](DATASET_CARD.md) for dataset use and limitations and
[`LIVE_HANDOFF.md`](LIVE_HANDOFF.md) for the current operational receipt.
