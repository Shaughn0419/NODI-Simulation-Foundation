# NODI Simulation Foundation live handoff

- Product/version: `NODI Simulation Foundation 5.0.0`
- Profile: `FORMAL_FIELD_COUPLING_M1_V5_EXACT_SUPPORT`
- Engine/schema/feature: `5.0.0 / 5.0 / 5.0`
- Source state: `V5_QUALIFIED_RELEASE_BUILD_PENDING`
- Qualification: `PASS_WITH_LIMITS`, 384/384 convergence cases and consolidated invariants passed
- Qualification artifact: `formal_m1_v5_qualification_report.json`
- Production quadrature: pupil `80 x 160`, piecewise lateral order `96`
- Selected release workers: `4`
- Committed-memory contract: soft stop 206 GB, emergency 208 GB, absolute below 210 GB
- Planned active release root: `releases/nodi-v5`
- Planned compact receipt: `v5_release_manifest.json`
- Data-version policy: `V5_ONLY_AFTER_ACCEPTANCE`; V4 remains in Git history/tag only

V5 corrects four breaking semantics together: exact wall-normal particle-center
support, one fill-side transverse pupil coordinate, passive analyzer
normalization, and explicit low-field/split-group fields. The release scale is
kept at 524,288 Development states while boundary and zero-exclusion coverage
is strengthened.

The next material action is the 4-worker full V5 rebuild, cross-release
acceptance, atomic retirement of the ignored local V4 tree, and Git/GitHub
closeout. No V5 formal labels are current until that acceptance completes.
