# Chronos Cloud — Architecture Specification

> **Status:** Draft / design (Milestone 8). This is a specification, not shipped
> code. It describes the commercial, multi-tenant Hosted DBaaS that wraps the
> open-source chronos-mem engine.

## 1. Goal & scope

chronos-mem (OSS) is a single-tenant PostgreSQL engine a developer runs
themselves. **Chronos Cloud** turns it into a managed, multi-tenant service:
a developer signs up, gets a connection string, and writes/queries agent memory
without provisioning Postgres, managing pgvector, or tuning for the sub-5ms
target.

Three things must be true for this to be sellable:

1. **Frictionless connect** — one URI, no infra. (§3)
2. **Hard tenant isolation** — one customer can never read another's agent data,
   even on shared hardware. (§4)
3. **Safe by default** — encrypted at rest, credentials never leaked, and a
   tenant cannot run up an unbounded bill. (§5–§7)

Non-goals for this doc: pricing, the web console UX, and the OSS-vs-Cloud feature
split. Those are tracked separately.

## 2. High-level topology

```
   Agent / SDK
       │  rdb://<token>@gateway.chronos.cloud/<tenant>
       ▼
┌─────────────────────────────────────────────────────────┐
│                  Chronos Cloud Gateway                    │
│  (stateless, horizontally scaled behind a load balancer)  │
│                                                           │
│   ┌──────────┐  ┌──────────────┐  ┌────────────────────┐ │
│   │  AuthN/  │  │  Tenant      │  │  Spend Guardrail   │ │
│   │  AuthZ   │─▶│  Router      │─▶│  (token metering)  │ │
│   └──────────┘  └──────────────┘  └─────────┬──────────┘ │
└───────────────────────────────────────────────┼──────────┘
                                                 │ pooled, per-tenant role
                                                 ▼
┌─────────────────────────────────────────────────────────┐
│         PostgreSQL cluster(s) — pgvector enabled          │
│   Row-Level Security keyed on tenant_id (shared schema)   │
│   + KMS-backed encryption at rest                         │
└─────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
                       Control plane: signup, key issuance,
                       billing rollups, KMS, audit log
```

The **gateway** is the only component that speaks the public protocol. It is
stateless (all state lives in Postgres, the control plane, or KMS), so it scales
out horizontally and any node can serve any tenant.

## 3. Connection model — the `rdb://` scheme

Tenants never receive raw Postgres credentials. They receive a **Chronos URI**:

```
rdb://<api_token>@<region>.gateway.chronos.cloud[:443]/<tenant_slug>
```

- `rdb://` — "remote database"; signals the SDK to use the Chronos transport
  (TLS-wrapped Postgres wire protocol) rather than a direct `postgresql://`
  socket. The SDK keeps the same `ChronosClient` API; only the DSN parser and
  transport differ.
- `<api_token>` — an opaque, revocable token (see §6). Carries identity; **not**
  a Postgres password.
- `<region>.gateway...` — region-pinned endpoint for data residency + latency.
- `<tenant_slug>` — human-readable tenant id; the authoritative tenant UUID is
  resolved server-side from the token, never trusted from the URI alone.

**Wire path:** SDK → TLS 1.3 → gateway. The gateway terminates TLS, authenticates
the token, resolves the tenant, then proxies to Postgres over an internal,
mutually-authenticated channel using a **per-tenant database role** (never a
superuser, never a shared app role). The Postgres credentials live only inside
the gateway's trust boundary.

Backward compatibility: the OSS SDK already accepts a DSN or `CHRONOS_DSN`. The
Cloud SDK adds an `rdb://` parser; everything above `_fetch`/`_cursor` is
unchanged, so tracking/causality/intervention calls work identically.

## 4. Multi-tenant isolation

### 4.1 Options considered

| Model | Isolation | Density / cost | Ops complexity | Verdict |
|-------|-----------|----------------|----------------|---------|
| **A. Shared schema + `tenant_id` + RLS** | Logical (enforced by Postgres RLS) | Highest density | Low | **Default** |
| **B. Schema-per-tenant** | Stronger (namespace) | Medium | Migrations fan out per schema | Mid-tier / "Pro" |
| **C. Database/cluster-per-tenant** | Physical | Lowest density | High | Enterprise / "Dedicated" |

We **default to (A)** for density and operational simplicity, with (C) available
as a premium "Dedicated" tier for customers with compliance needs. (B) is an
optional middle tier.

### 4.2 Shared-schema isolation rules (Model A)

Every pillar table gains a non-null `tenant_id UUID` column (FK to a
control-plane `tenants` table), and **Row-Level Security** enforces it:

```sql
-- one-time, per table (memories, plans, actions, outcomes, interventions)
ALTER TABLE plans ADD COLUMN tenant_id UUID NOT NULL;
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans FORCE ROW LEVEL SECURITY;   -- applies even to table owner

CREATE POLICY tenant_isolation ON plans
    USING      (tenant_id = current_setting('chronos.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('chronos.tenant_id')::uuid);
```

The gateway sets the tenant context **per connection checkout**, inside the same
transaction as the query, using a `SET LOCAL` so it cannot leak across pooled
reuse:

```sql
SET LOCAL chronos.tenant_id = '<resolved-tenant-uuid>';
```

Key rules:

1. **`tenant_id` is server-assigned**, derived from the authenticated token —
   never accepted from the client payload. The SDK doesn't even send it.
2. **`FORCE ROW LEVEL SECURITY`** so the policy binds even for the connecting
   role; the per-tenant role additionally has no `BYPASSRLS`.
3. **Composite indexes lead with `tenant_id`** (e.g. `(tenant_id, parent_plan_id)`,
   `(tenant_id, error_type, succeeded)`) so the recursive-CTE traversals and
   `get_best_intervention` stay sub-5ms *within* a tenant's slice and never scan
   across tenants.
4. **The recursive CTEs are unchanged** — RLS transparently constrains the
   anchor and every recursion step to the active tenant.
5. **`SET LOCAL` (not `SET`)** guarantees the tenant binding is scoped to the
   transaction and reset on commit/rollback, so a returned pooled connection
   carries no residual tenant context.

### 4.3 Pooling under multi-tenancy

The OSS single-connection-per-op model (`_cursor`) maps cleanly: the gateway
maintains **per-tenant pools** (or a shared pool with mandatory `SET LOCAL`
on checkout). A connection is never handed to tenant B without first re-binding
`chronos.tenant_id` inside a fresh transaction. Idle per-tenant pools scale to
zero to control connection count on the shared cluster (PgBouncer in
transaction-pooling mode sits between gateway and Postgres).

## 5. Encryption at rest

Three layers, defense-in-depth:

1. **Volume/cluster level** — storage encrypted with a cloud KMS-managed key
   (e.g. cloud-provider TDE / encrypted EBS-equivalent). Covers full-disk theft.
2. **Per-tenant data key (envelope encryption)** — each tenant has a data
   encryption key (DEK) wrapped by a KMS master key. Sensitive JSONB columns
   (`actions.payload`, `outcomes.result`, `interventions.details`) that may hold
   credentials or PII are encrypted with the tenant DEK before write (app-side,
   in the gateway) so even a DBA with cluster access cannot read raw tenant
   payloads.
3. **`memories.embedding`** stays unencrypted to preserve pgvector HNSW
   similarity search; only the source `content` is encryptable. (Trade-off noted:
   embeddings can leak coarse semantics — flagged as an open question in §9.)

Key rotation: DEKs rotate without re-encrypting the cluster (rewrap the DEK under
a new KMS key version); tenant-payload re-encryption is a background job.

## 6. Credentialing & secret handling

- **API tokens** are opaque, prefixed (`chronos_pat_…`), and stored only as a
  salted hash in the control plane — the plaintext is shown once at issuance.
- **Scopes**: tokens carry a scope (`read`, `write`, `admin`) and an optional
  TTL; the gateway enforces scope before proxying (e.g. a `read` token can call
  `query_causality`/`get_best_intervention` but not `log_*`).
- **Per-tenant Postgres roles** are provisioned by the control plane, credentials
  stored in the gateway's secret manager (KMS/Vault), rotated on a schedule, and
  never exposed to tenants or logged.
- **Remote model-provider credentials** (if Chronos ever calls embedding APIs on
  the tenant's behalf): stored as tenant-scoped secrets, injected at call time,
  never persisted in the pillar tables, and redacted from audit logs.
- **Audit log**: every auth decision, token issuance/revocation, and admin action
  is written to an append-only control-plane log.

## 7. Spend-limit guardrails (real-time)

Agents can loop; a runaway agent must not produce a runaway bill. The gateway
meters and enforces in the request path:

- **Metered units**: write ops, trace/query ops, rows scanned, embedding tokens
  (if Chronos generates embeddings), and storage bytes.
- **Real-time counter**: per-tenant rolling usage held in a fast store (Redis)
  and incremented on each gateway request; periodically reconciled against
  authoritative Postgres rollups.
- **Enforcement tiers** per tenant: **soft limit** → warn (header + webhook);
  **hard limit** → the gateway returns a typed `429 SpendLimitExceeded` *before*
  touching Postgres, so the limit also protects the shared cluster.
- **Rate limiting** (token-bucket per tenant) is a separate, always-on guardrail
  protecting cluster QPS independent of the monthly spend cap.
- The SDK surfaces these as a distinct exception so an agent can back off or
  escalate (and, fittingly, `log_intervention` the throttle).

## 8. Rollout phases

1. **P1 — Single shared cluster, Model A.** RLS isolation, `rdb://` gateway,
   token auth, KMS volume encryption, basic rate limiting.
2. **P2 — Spend guardrails + per-tenant DEK encryption** for sensitive JSONB.
3. **P3 — Tiering:** schema-per-tenant (Pro) and dedicated cluster (Enterprise),
   region pinning for data residency.
4. **P4 — Self-serve console**, usage dashboards, billing integration.

## 9. Open questions / risks

- **Embedding confidentiality** — encrypting `memories.embedding` breaks HNSW
  search. Options: encrypted-but-unsearchable tier, or per-tenant pgvector index
  partitions. Needs a decision.
- **`current_setting` performance** — verify `SET LOCAL` + RLS predicate overhead
  stays within the sub-5ms budget at the recursive-CTE level (benchmark required).
- **Noisy-neighbor** — one tenant's storm (cf. the M7 stress test) degrading
  shared-cluster latency; mitigated by rate limits + connection caps, but
  needs load validation per cluster sizing.
- **Connection scaling** — thousands of tenants × pools exceeds Postgres
  `max_connections`; PgBouncer transaction pooling is assumed but must be
  validated against the `SET LOCAL` tenant-binding requirement.

## 10. Relationship to the OSS engine

Chronos Cloud is a **wrapper, not a fork**. The five-pillar schema, the recursive
causal CTEs, `get_best_intervention`, and the SDK surface are identical; Cloud
adds `tenant_id` + RLS, the `rdb://` transport, and the gateway's auth / metering /
encryption. Anything a tenant can do on Cloud, they can do on a local
`docker compose up` — which keeps the OSS project honest and the Cloud value
clearly about *operations*, not lock-in.
