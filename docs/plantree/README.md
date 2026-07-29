# Project Plan Tree

This directory is the durable planning entrypoint for the application demo.
Implementation and medical-safety truth remain in code, governed YAML, tests,
and accepted quality artifacts.

## Authority order

1. `AGENTS.md` safety and governance boundaries.
2. Runtime code, schemas, migrations, and governed configuration.
3. Accepted tests and quality-gate artifacts.
4. Active plan state under `plans/`.
5. Historical project documents.

## Baseline

- [Baseline](baseline/README.md)
- [Module map](baseline/module-map.md)
- [Runtime flows](baseline/runtime-flows.md)
- [Storage and state](baseline/storage-and-state.md)
- [Test and release gates](baseline/test-and-release-gates.md)
- [Risk hotspots](baseline/risk-hotspots.md)

## Active plans

| Plan | Status | Current phase | Last landed | Next target |
| --- | --- | --- | --- | --- |
| [Admin V1 productionization](plans/admin-v1-productionization/README.md) | In Progress | Runtime bootstrap | Admin V1 pushed at `39d75cd` | Migrate the admin DB and establish credentials |

## Ideas

- [Inbox](ideas/inbox.md)
