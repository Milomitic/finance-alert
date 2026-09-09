# Bandit triage — 2026-09-09

The static scan found no high-severity issues. `npm audit` and `pip-audit` report no known dependency vulnerabilities.

- `B310` in Prometheus/Nasdaq clients: URLs are constructed from fixed service configuration or fixed HTTPS provider endpoints. Runtime scheme and netloc validation was added before `urlopen`; `noqa: S310` documents that invariant.
- `B608` in maintenance scripts: table and column names come from module constants and internal SQLAlchemy reflection, never request input. Value data uses bind parameters where applicable. These are low-confidence static positives.
- `B110`/`B112`: best-effort health/maintenance paths intentionally continue after isolated failures; each occurrence is scoped to a non-critical path.
- `B105`, `B101`, `B311`: test/configuration constants or assertions in non-production maintenance paths; no credential or externally controlled secret was found.

The remaining action is a periodic review when maintenance scripts change.
