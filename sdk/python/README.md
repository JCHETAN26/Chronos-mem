# chronos-mem (Python SDK)

Async, typed client for the chronos-mem agent memory engine.

```python
import asyncio
from chronos_mem import ChronosClient

async def main():
    async with ChronosClient(dsn="postgresql://chronos:chronos@localhost:5432/chronos_mem") as db:
        plan = await db.create_plan(agent_id="agent-1", goal="Book a vacation to Tokyo")

        action = await db.log_action(
            plan_id=plan.id,
            tool_name="flights.search",
            payload={"from": "SFO", "to": "HND"},
        )

        await db.log_outcome(
            action_id=action.id,
            status="success",
            result={"cheapest_usd": 812},
        )

asyncio.run(main())
```

## Install (dev)

```bash
pip install -e ".[dev]"
```

The DSN can also be supplied via the `CHRONOS_DSN` environment variable instead
of the `dsn=` argument.

## Design

- **`client.py`** — `ChronosClient` owns one async `psycopg_pool` connection pool;
  open once per process and share it across concurrent agent calls.
- **`tracking.py`** — `create_plan` / `log_action` / `log_outcome`, the three core
  write verbs, each a single `INSERT ... RETURNING *`.
- **`models.py`** — Pydantic v2 models (`Plan`, `Action`, `Outcome`, `Memory`)
  mirroring the SQL schema in `db/migrations/001_init_chronos_schema.sql`.
