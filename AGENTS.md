# NODI Simulation Foundation repository rules

These rules apply to the entire repository. Live user authorization outranks a
roadmap or generated status file. The Foundation is a standalone product: it may
read frozen upstream sources during a declared migration/parity task, but it may
never import another repository at runtime.

## Product identity and scientific boundary

- Maintain one installable package, one CLI, one public facade, one error-code
  namespace, and one schema-version line.
- The only stable Python entries are `simulate_state`, `simulate_batch`,
  `build_dataset`, `build_intervention_pairs`, `derive_observation`, and
  `validate_release`. Everything under `_physics` is internal.
- Keep Paper 1/2 version names, XAI metrics/models, publication gates, COMSOL
  orchestration, dashboards, web servers, and plugin systems out of the v1 core.
- Unsupported or unqualified physics must fail explicitly. Never clip invalid
  states, fill unresolved effects with zero, or promote synthetic controls into
  material, fabrication, experimental, or scientific authority.
- Source migration is one-time and rewrite-from-specification unless explicit
  copy authorization is recorded. Bind every source use in `source_map.json` and
  establish parity before removing the upstream comparison harness.

## Lean repository and artifact budget

- Keep only current code, focused tests, schemas, profiles, necessary examples,
  concise user documentation, current handoff state, and release manifests.
  Git history is the history; superseded routes and process reports do not stay
  in the current tree.
- Do not track raw logs, caches, checkpoints, temporary CSVs, debug images,
  duplicated exports, large datasets, or sealed labels. Put large products in a
  content-addressed external release and track only its manifest when needed.
- A normal implementation batch may add at most one human-readable report, one
  manifest/status JSON, and one necessary primary result artifact. Code,
  schemas, and focused tests do not count toward this budget.
- Maintain one roadmap, one `LIVE_HANDOFF.md`, and one current-state source.
  Reference canonical files by path and hash instead of copying their contents.
- Remove migration-only shims in the same coherent batch; do not accumulate
  `old`, `new`, `v2`, `final`, and `fixed` implementations.

## Outcome-first validation

- Use N1-N4 as the four material phase exits. Do not create per-feature,
  per-field, or per-file gates.
- During implementation run changed/impacted checks. Run full static checks,
  full tests, and clean-install smoke only at material phase boundaries, before
  a large production launch, or for a formal release.
- Perform at most one full independent review of a candidate. After repair, use
  targeted verification; stop expanding cases once the failure class and the
  minimum corrective condition are proven.
- A professional batch should end with usable code, a primary artifact, an
  executed computation, an accepted receipt, or one precise external blocker.
  Readiness-only audit packets are not deliverables.
- Build the minimum safe producer and harden defects exposed by the real
  candidate. Do not add speculative abstractions, empty future modules, or
  multiple competing engines.

## Compute resources

- Aggregate workers across Foundation processes must not exceed 24. System
  committed memory must remain below `210000000000` bytes.
- Prefer bounded parallel execution for independent states or chunks when a
  measured pilot shows useful speedup and safe memory. Do not parallelize small
  work only to consume all workers.
- Prevent nested oversubscription: process workers default to one BLAS/OpenMP
  thread unless a bounded benchmark proves another setting faster and safe.
- Large production must be deterministic, chunked, recoverable, and identity
  preserving. Resume may not change seeds, state IDs, output ordering, or hashes.
- Measure representative per-worker peak memory and throughput once before N3
  production, then select worker count and chunk size from that evidence.

## Git closeout

- Before tracked writes, fetch and compare local HEAD, upstream, and remote.
  Never force-push, overwrite unknown work, or stage unrelated paths.
- Stage explicit paths only, validate the coherent batch, commit intentionally,
  push promptly, and verify local HEAD equals the remote SHA readback.
- Update `LIVE_HANDOFF.md` only for a material source-lock, phase, gate, runtime,
  or terminal-result change; do not commit unchanged monitoring state.

