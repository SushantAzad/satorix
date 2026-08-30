# Satorix platform architecture

Satorix is being built as a governed operational data platform inspired by
Palantir Foundry. It is not a Foundry clone and should not claim enterprise
capabilities until they are implemented and verified.

## Platform contract

```
Sources -> raw, versioned datasets -> transforms -> governed clean datasets
        -> Ontology objects and links -> applications and agents
        -> permissioned Actions -> audited writeback / notifications
```

The Ontology is the primary interface for users and agents. Raw tables remain
part of the data plane; applications must not mutate them directly.

## Current layers

- **Data plane (Layers 1–2):** connectors, Parquet/MinIO storage, sync state,
  transforms, data-quality checks, and lineage records.
- **Ontology (Layer 3):** object types, link types, interfaces, materialized
  objects, event timeline, and registered Actions.
- **Intelligence (Layers 4–5):** graph analytics, deterministic analytics,
  retrieval, provider abstraction, and agent tooling.
- **Experience (Layer 6):** BFF, dashboards, authentication, WebSockets, and
  operational views.

## Non-negotiable invariants

1. A dataset version is immutable after publication.
2. Every derived value retains source dataset/version and transform lineage.
3. Every object write is an Ontology Action, never an ad-hoc database update.
4. An Action must be authenticated, authorized, validated, and audit logged.
5. Applications must visibly identify demo or degraded data; they must not
   silently present it as live.
6. Tenant, marking, row, and column controls are evaluated before object reads
   or writes.
7. Agents use the same object, function, and Action permissions as people.

## Delivery sequence

### Foundation (current)

- Reproducible Python 3.11 runtime and pinned dependencies.
- Secure environment configuration and no tracked secrets.
- Buildable dashboards and an executable local Compose stack.
- Authenticated Layer 3 Action boundary and immutable audit records.

### Data and Ontology

- Dataset transaction/version API backed by Parquet now and Iceberg when the
  table engine is introduced.
- Typed object/link registry, interfaces, data-source mappings, and automatic
  materialization from clean datasets.
- Object-set query API and generated TypeScript/Python SDKs.

### Operational applications and AIP

- Explicit Action approval workflows, writeback adapters, and automations.
- Retrieval grounded in object-level permissions and citations.
- Prompt/tool evaluation suites, traces, model budgets, and human approval
  gates for consequential actions.

### Deployment and governance

- CI gates for builds, tests, migrations, SAST, secret scanning, and image
  scanning.
- Environment promotion with signed artifacts, health checks, rollbacks, and
  observability.
- SSO/MFA, tenant isolation, classifications/markings, retention, and exportable
  audit trails.

## Current exclusions

Iceberg, Spark/Flink execution, OIDC, row/column policy enforcement, generated
SDKs, approval queues, and autonomous production agents are planned work—not
current capabilities.
