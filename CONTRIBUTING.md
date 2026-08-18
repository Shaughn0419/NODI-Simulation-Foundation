# Contributing

Contributions are welcome when they keep NODI Simulation Foundation a lean,
standalone, deterministic scientific product. Repository rules in `AGENTS.md`
remain binding for implementation and review.

## Submit one coherent change

- Keep the public surface within `src/nodi_foundation/api.py`; do not add a
  competing package, CLI, schema line, physics engine, or runtime dependency on
  another repository.
- Include only current code, focused tests, concise documentation, and necessary
  manifests. Do not commit caches, logs, checkpoints, temporary tables, or
  generated release data.
- Identify every external source, dataset, or copied fragment and its license.
  Do not submit material that you are not authorized to contribute.
- Preserve explicit failure for invalid or unqualified physics and the claim
  ceiling of every affected profile.

## Pull request contract

A pull request should state the outcome, affected public contract, scientific
boundary, and checks run. Run changed or impacted checks during development;
run full static checks, tests, and clean-install smoke for a material phase or
release boundary. Keep repairs targeted after the failure class is established.

## Contribution license

Unless explicitly marked `Not a Contribution`, an intentional submission for
inclusion in this repository is provided under the Apache License 2.0, including
its contributor copyright and patent terms. By submitting, you represent that
you have the right to provide the contribution under those terms. A separate
contributor license agreement is not required for ordinary contributions.
