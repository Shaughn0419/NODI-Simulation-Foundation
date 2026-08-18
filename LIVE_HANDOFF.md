# NODI Simulation Foundation live handoff

- Product/version: `NODI Simulation Foundation 5.0.0`
- Profile: `FORMAL_FIELD_COUPLING_M1_V5_EXACT_SUPPORT`
- Engine/schema/feature: `5.0.0 / 5.0 / 5.0`
- Source state: `V5_FORMAL_RELEASES_ACCEPTED`
- Qualification: `PASS_WITH_LIMITS`, 384/384 convergence cases and consolidated invariants passed
- Qualification artifact: `formal_m1_v5_qualification_report.json`
- Production quadrature: pupil `80 x 160`, piecewise lateral order `96`
- Selected release workers: `4`
- Committed-memory contract: soft stop 206 GB, emergency 208 GB, absolute below 210 GB
- Observed Development peak committed: `170609590272` bytes
- Active release root: `releases/nodi-v5`
- Compact receipt: `v5_release_manifest.json`, SHA-256 `8f14c82d9c94cdbf2cacacda1f8001603a631a4fb40e65821aa5e68eae0381d2`
- Data-version policy: `V5_ONLY`; V4 remains recoverable from Git history/tag only

V5 corrects four breaking semantics together: exact wall-normal particle-center
support, one fill-side transverse pupil coordinate, passive analyzer
normalization, and explicit low-field/split-group fields. The release scale is
kept at 524,288 Development states while boundary and zero-exclusion coverage
is strengthened.

The accepted products contain 32,768 capability states, 4,096 quickstart
states, 524,288 Development states, 16,384 Development intervention pairs,
131,072 evaluation inputs, and 131,072 order-matched sealed labels. Development
and evaluation share neither state IDs nor split-group IDs. All seven release
manifests and primary-file hashes pass independent readback; the transient
evaluation build and local V4 release trees are absent. The source archive is
the annotated Git tag `v5.0.0`.
