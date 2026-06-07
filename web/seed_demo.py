"""Seed a realistic multi-agent scenario so the dashboard has something to show.

A travel agent planning a Japan trip: a goal DAG with real failures, logged
interventions (so 'suggested fix' populates), and varied tool brittleness.
"""

import asyncio
import os

from chronos_mem import ChronosClient, InterventionStrategy, OutcomeStatus, PlanStatus


async def main() -> None:
    async with ChronosClient() as db:
        agent = "travel-agent"

        # ---- Root goal -------------------------------------------------------
        root = await db.create_plan(agent_id=agent, goal="Plan a 2-week trip to Japan")

        # ---- Branch 1: flights (contains a deep failure that got fixed) ------
        flights = await db.create_plan(agent_id=agent, goal="Book flights",
                                       parent_plan_id=root.id, status=PlanStatus.IN_PROGRESS)
        search = await db.log_action(flights.id, "flights.search",
                                     payload={"from": "SFO", "to": "HND"})
        await db.log_outcome(search.id, OutcomeStatus.SUCCESS, result={"options": 14})

        purchase = await db.create_plan(agent_id=agent, goal="Purchase the flight",
                                        parent_plan_id=flights.id, status=PlanStatus.FAILED)
        charge = await db.log_action(purchase.id, "payments.charge", payload={"usd": 1840})
        charge_outcome = await db.log_outcome(charge.id, OutcomeStatus.FAILURE,
                                              error="payment_declined")
        # The agent retried and it worked -> get_best_intervention will suggest RETRY.
        await db.log_intervention(outcome_id=charge_outcome.id, agent_id=agent,
                                  error_type="payment_declined",
                                  strategy=InterventionStrategy.RETRY, succeeded=True)

        # ---- Branch 2: hotels (clean success) --------------------------------
        hotels = await db.create_plan(agent_id=agent, goal="Book hotels",
                                      parent_plan_id=root.id, status=PlanStatus.COMPLETED)
        hs = await db.log_action(hotels.id, "hotels.search", payload={"city": "Tokyo"})
        await db.log_outcome(hs.id, OutcomeStatus.SUCCESS)
        hb = await db.log_action(hotels.id, "hotels.book", payload={"nights": 6})
        await db.log_outcome(hb.id, OutcomeStatus.SUCCESS)

        # ---- Branch 3: itinerary (a flaky tool) ------------------------------
        itin = await db.create_plan(agent_id=agent, goal="Plan daily itinerary",
                                    parent_plan_id=root.id, status=PlanStatus.IN_PROGRESS)
        route = await db.log_action(itin.id, "maps.route", payload={"stops": 9})
        await db.log_outcome(route.id, OutcomeStatus.SUCCESS)
        wx = await db.log_action(itin.id, "weather.forecast", payload={"days": 14})
        wx_outcome = await db.log_outcome(wx.id, OutcomeStatus.FAILURE, error="rate_limited")
        # Two interventions for rate_limited: escalate failed, retry succeeded.
        await db.log_intervention(outcome_id=wx_outcome.id, agent_id=agent,
                                  error_type="rate_limited",
                                  strategy=InterventionStrategy.ESCALATE, succeeded=False)
        wx2 = await db.log_action(itin.id, "weather.forecast", payload={"days": 14, "retry": 1})
        wx2_outcome = await db.log_outcome(wx2.id, OutcomeStatus.FAILURE, error="rate_limited")
        await db.log_intervention(outcome_id=wx2_outcome.id, agent_id=agent,
                                  error_type="rate_limited",
                                  strategy=InterventionStrategy.RETRY, succeeded=True)

        # ---- A second, smaller root so the picker has variety ---------------
        root2 = await db.create_plan(agent_id="ops-agent", goal="Nightly data sync")
        sync = await db.log_action(root2.id, "db.replicate", payload={"shard": 3})
        await db.log_outcome(sync.id, OutcomeStatus.SUCCESS)

        print("Seeded. Root plan ids:")
        print(f"  travel-agent : {root.id}")
        print(f"  ops-agent    : {root2.id}")


if __name__ == "__main__":
    asyncio.run(main())
