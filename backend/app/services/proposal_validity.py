"""Conservative expiry; approval and execution still require fresh evaluation."""
from datetime import datetime, timedelta
from decimal import Decimal


def proposal_expiry(*, assessed_at, evidence, plan, lead_time, offer_id=None):
    limits = [assessed_at + timedelta(minutes=5)]
    for record in evidence["inventory_balances"] + evidence["shipments"]:
        limits.append(datetime.fromisoformat(record["observed_at"]) + timedelta(minutes=30))
    # An active shipment with a passed ETA needs a new observation/receipt.
    for record in evidence["shipments"]:
        limits.append(datetime.fromisoformat(record["current_eta"]))
    if offer_id is not None:
        offer = next(row for row in evidence["supplier_offers"] if row["id"] == str(offer_id))
        limits.extend((
            datetime.fromisoformat(offer["valid_until"]),
            datetime.fromisoformat(offer["observed_at"]) + timedelta(minutes=30),
        ))
    deadlines = {row["id"]: datetime.fromisoformat(row["required_at"])
                 for row in evidence["production_demands"]}
    for allocation in plan["allocations"]:
        if Decimal(allocation["allocated_qty"]) > 0:
            limits.append(deadlines[allocation["demand_id"]] - lead_time)
    expires_at = min(limits)
    if expires_at <= assessed_at:
        raise ValueError("Proposal has no remaining approval window. Evaluate another option.")
    return expires_at
