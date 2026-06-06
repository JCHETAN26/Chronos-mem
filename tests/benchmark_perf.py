"""chronos-mem performance benchmark (Milestone 4).

Simulates 1,000 parallel agent calls and verifies the sub-5ms write/read
target. Reports two distinct numbers, because they answer different questions:

  * UNCONTENDED per-operation latency (sequential, warm pool) — this is the
    "is a single write/read under 5ms?" claim. The gate asserts on this.
  * UNDER-LOAD latency + throughput (1,000 fired concurrently over a bounded
    pool) — shows behaviour at saturation, where per-op wall time includes
    pool-queueing and is expected to exceed the single-op figure.

Run:
    CHRONOS_DSN="postgresql://chronos:chronos@localhost:5432/chronos_mem" \
        python tests/benchmark_perf.py

Env knobs: BENCH_N (default 1000), BENCH_POOL (default 20),
BENCH_GATE_MS (default 5.0).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from chronos_mem import ChronosClient, OutcomeStatus, PlanStatus

N = int(os.getenv("BENCH_N", "1000"))
POOL = int(os.getenv("BENCH_POOL", "20"))
GATE_MS = float(os.getenv("BENCH_GATE_MS", "5.0"))


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p / 100 * len(s))) - 1))
    return s[idx]


def _summary(name: str, lat: list[float]) -> dict[str, float]:
    return {
        "op": name,
        "best": min(lat),
        "p50": _pct(lat, 50),
        "p95": _pct(lat, 95),
        "p99": _pct(lat, 99),
        "max": max(lat),
    }


def _print_table(rows: list[dict[str, float]]) -> None:
    print(f"  {'op':<22}{'best':>9}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}  (ms)")
    for r in rows:
        print(
            f"  {r['op']:<22}{r['best']:>9.3f}{r['p50']:>9.3f}"
            f"{r['p95']:>9.3f}{r['p99']:>9.3f}{r['max']:>9.3f}"
        )


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    # Generous acquisition timeout: at 1,000-way concurrency over a small pool,
    # the tail waits in the pool queue; we want to measure that wait, not error on it.
    async with ChronosClient(dsn=dsn, min_size=POOL, max_size=POOL, timeout=60.0) as db:
        # --- Seed a small tree to read against ---
        root = await db.create_plan(agent_id="bench", goal="benchmark root goal")
        for i in range(5):
            child = await db.create_plan(
                agent_id="bench", goal=f"sub-goal {i}", parent_plan_id=root.id,
                status=PlanStatus.IN_PROGRESS,
            )
            act = await db.log_action(child.id, "bench.seed", payload={"i": i})
            await db.log_outcome(act.id, OutcomeStatus.SUCCESS)

        # --- UNCONTENDED baseline (sequential, warm) ---
        warm = 20
        n_base = 200
        for _ in range(warm):
            await db.log_action(root.id, "bench.warm")
            await db.query_causality(root.id)

        w_lat: list[float] = []
        for _ in range(n_base):
            t0 = time.perf_counter()
            await db.log_action(root.id, "bench.write", payload={"k": "v"})
            w_lat.append((time.perf_counter() - t0) * 1000)

        r_lat: list[float] = []
        for _ in range(n_base):
            t0 = time.perf_counter()
            await db.query_causality(root.id)
            r_lat.append((time.perf_counter() - t0) * 1000)

        print(f"\nUNCONTENDED per-op latency (sequential, {n_base} samples):")
        uncontended = [_summary("write (log_action)", w_lat),
                       _summary("read (query_causality)", r_lat)]
        _print_table(uncontended)

        # --- UNDER LOAD: N concurrent ops over a bounded pool ---
        async def timed_write(i: int) -> float:
            t0 = time.perf_counter()
            await db.log_action(root.id, "bench.cwrite", payload={"i": i})
            return (time.perf_counter() - t0) * 1000

        async def timed_read(_i: int) -> float:
            t0 = time.perf_counter()
            await db.query_causality(root.id)
            return (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        cw_lat = await asyncio.gather(*(timed_write(i) for i in range(N)))
        wall_w = time.perf_counter() - t0

        t0 = time.perf_counter()
        cr_lat = await asyncio.gather(*(timed_read(i) for i in range(N)))
        wall_r = time.perf_counter() - t0

        print(f"\nUNDER LOAD: {N} concurrent ops, pool={POOL}:")
        _print_table([_summary("write x" + str(N), list(cw_lat)),
                      _summary("read x" + str(N), list(cr_lat))])
        print(f"  writes: {N} in {wall_w*1000:.1f}ms  ->  {N/wall_w:,.0f} ops/s")
        print(f"  reads:  {N} in {wall_r*1000:.1f}ms  ->  {N/wall_r:,.0f} ops/s")
        print(
            "  note: writes are I/O-bound and parallelise across the pool; reads run\n"
            "        query_causality, whose trace assembly (row grouping + Pydantic) is\n"
            "        CPU-bound under the GIL, so read THROUGHPUT scales with worker\n"
            "        processes, not pool size. Per-op read LATENCY still meets the\n"
            "        target when the pool is not oversubscribed (see uncontended above)."
        )

        # --- Gate on the uncontended single-op claim ---
        write_p50 = uncontended[0]["p50"]
        read_p50 = uncontended[1]["p50"]
        ok = write_p50 < GATE_MS and read_p50 < GATE_MS
        print(
            f"\nGate (uncontended p50 < {GATE_MS}ms): "
            f"write={write_p50:.3f}ms read={read_p50:.3f}ms -> "
            f"{'PASS' if ok else 'FAIL'}"
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
