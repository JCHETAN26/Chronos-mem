# chronos-mem

**PostgreSQL for autonomous AI agents.** A structured memory and causal-debugging
engine that gives an agent a brain it can query — so it can explain its own
failures and self-correct in real time.

---

## The problem

Autonomous agents break a goal into plans, take actions, call tools, and observe
outcomes. Today that execution history gets dumped into spreadsheets or flat SQL
tables built for humans. It's a mess: you can't ask *"which decision upstream
caused this failure?"* or *"how did we fix this kind of error last time?"*

chronos-mem models an agent's run as what it actually is — a **causal graph over
time** — and makes it queryable in **under 5 milliseconds**.

## The five pillars

The schema is a hybrid JSONB-relational design split into five highly-indexed
pillars, so structured queries stay fast while raw tool payloads stay flexible:

| Pillar | What it stores |
|--------|----------------|
| **memories** | Long-term episodic facts / preferences (pgvector + text) |
| **plans** | Hierarchical goal DAG — sub-goals link to parents (`parent_plan_id`) |
| **actions** | Raw tool executions; inputs/params/payloads as JSONB |
| **outcomes** | Causal success/failure verdict for each action |
| **interventions** | Post-failure decisions (retry / escalate / pivot / …) and whether they worked |

The payoff is a closed loop: **explain the failure** (walk the causal graph
backward from a broken outcome) *and* **recommend the fix** (rank the
interventions that resolved this class of error before).

## Architecture

```
        ┌──────────────────────────────────────────────────────────┐
        │                     Autonomous agent                       │
        └──────────────────────────────┬─────────────────────────────┘
                                        │  create_plan / log_action
                                        │  log_outcome / log_intervention
                                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │              chronos-mem SDK  (async, psycopg3)            │
        │                                                            │
        │  WRITE                READ / DEBUG                         │
        │  ─────                ───────────                          │
        │  create_plan          query_causality(plan_id)  ── trace   │
        │  log_action           get_best_intervention()   ── fix     │
        │  log_outcome          tool_brittleness()         ── stats  │
        │  log_intervention                                          │
        └──────────────────────────────┬─────────────────────────────┘
                                        │  bounded async connection pool
                                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │           PostgreSQL 16 + pgvector  (sub-5ms)              │
        │                                                            │
        │   memories ── plans ──< actions ──1:1── outcomes           │
        │   (vector)   (DAG, self-ref)    (JSONB)        │           │
        │                                                ▼           │
        │                                          interventions     │
        │                                   view: tool_brittleness    │
        └──────────────────────────────┬─────────────────────────────┘
                                        │
                                        ▼
                          Streamlit debug dashboard
                       (goal DAG · failed nodes in red · suggested fix)
```

## Quickstart

**1. Bring up Postgres + pgvector:**

```bash
docker compose -f db/docker-compose.yml up -d
# the schema in db/migrations/ is applied automatically on first init
```

**2. Install the SDK:**

```bash
pip install -e sdk/python
export CHRONOS_DSN="postgresql://chronos:chronos@localhost:5432/chronos_mem"
```

**3. Track an agent's run:**

```python
import asyncio
from chronos_mem import ChronosClient, OutcomeStatus, InterventionStrategy

async def main():
    async with ChronosClient() as db:                       # reads CHRONOS_DSN
        plan = await db.create_plan(agent_id="a1", goal="Book a trip to Tokyo")
        sub  = await db.create_plan(agent_id="a1", goal="Buy the flight",
                                    parent_plan_id=plan.id)

        action  = await db.log_action(plan_id=sub.id, tool_name="payments.charge",
                                      payload={"usd": 812})
        outcome = await db.log_outcome(action_id=action.id,
                                       status=OutcomeStatus.FAILURE,
                                       error="payment_declined")

        # Record what we did about it (and whether it worked)...
        await db.log_intervention(outcome_id=outcome.id, agent_id="a1",
                                  error_type="payment_declined",
                                  strategy=InterventionStrategy.RETRY, succeeded=True)

        # ...so next time the agent can ask how this was fixed before:
        best = await db.get_best_intervention("payment_declined")
        print(best)            # -> RETRY (worked Nx)

        # And trace the whole causal graph under a goal:
        trace = await db.query_causality(plan.id)
        print(trace.failed_actions)

asyncio.run(main())
```

## Debug dashboard

A one-page visual tracer renders the goal DAG, highlights failed nodes in **red**,
and suggests the best past intervention for each failure:

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

## Repository layout

```
db/
  docker-compose.yml                  Postgres 16 + pgvector, SSD-tuned
  migrations/001_init_chronos_schema.sql   the five-pillar schema
  queries/                            canonical recursive-CTE + intervention SQL
sdk/python/chronos_mem/
  client.py                           async psycopg3 connection pool
  tracking.py                         create_plan / log_action / log_outcome / log_intervention
  causality.py                        query_causality (recursive CTE, both directions)
  interventions.py                    get_best_intervention (self-correction)
  models.py                           Pydantic v2 models mirroring the schema
dashboard/                            Streamlit causal tracer
tests/benchmark_perf.py               1,000-parallel-call performance benchmark
```

## Performance

Every tracking, traversal, and causal query targets **sub-5ms** execution. The
causal-trace CTEs are index-backed in both directions; per-operation latency
(uncontended) and server-side query execution both sit comfortably under the
target. Writes parallelise across the connection pool; high-volume read
throughput scales horizontally (the trace-assembly step is CPU-bound per
process). See `tests/benchmark_perf.py`.

## Status

Built in four milestones (see `build-plan.txt`):

1. **Postgres engine** — pgvector + the five-pillar schema
2. **Async Python SDK** — pooled client + tracking verbs
3. **Causal tracing & intervention engine** — `query_causality` + `get_best_intervention`
4. **Debug dashboard & benchmarks**

## Install from PyPI

```bash
pip install chronos-mem
```

## License

[Apache License 2.0](LICENSE).
