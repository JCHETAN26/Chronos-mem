# chronos-mem web dashboard

An interactive, dark-themed dashboard for tracing an agent's causal graph,
inspecting failures, and seeing the historically best fix per error.

- **`api/`** — a thin **FastAPI** JSON layer over the `chronos-mem` SDK.
- **`app/`** — a **React + Vite + TypeScript** frontend (Tailwind, React Flow
  graph, dagre layout).

```
┌──────────┐   /api/*   ┌──────────────┐   SDK    ┌─────────────┐
│ React UI │ ─────────▶ │ FastAPI (api)│ ───────▶ │ Postgres    │
│ (app)    │ ◀───────── │              │ ◀─────── │ + pgvector  │
└──────────┘   JSON     └──────────────┘          └─────────────┘
```

## Run it

**0. Postgres** (from the repo root):

```bash
docker compose -f db/docker-compose.yml up -d   # auto-applies migrations
export CHRONOS_DSN="postgresql://chronos:chronos@localhost:5432/chronos_mem"
```

**1. Backend** (from `web/api/`):

```bash
pip install -r requirements.txt
# for local dev against the in-repo SDK:  pip install -e ../../sdk/python
uvicorn main:app --reload --port 8000
```

**2. Frontend** (from `web/app/`):

```bash
npm install
npm run dev          # http://localhost:5173 (proxies /api → :8000)
```

**Seed demo data** (optional, so the dashboard has something to show):

```bash
python web/seed_demo.py     # with CHRONOS_DSN set
```

## API

| Endpoint | Returns |
|----------|---------|
| `GET /api/roots` | recent root plans (the run picker) |
| `GET /api/trace/{plan_id}` | full causal trace (nodes, actions, outcomes, metrics) |
| `GET /api/best-intervention?error_type=…` | historically best fix for an error |
| `GET /api/tools` | tool-brittleness stats |

## Build

```bash
cd web/app && npm run build      # type-checks + bundles to app/dist
```
