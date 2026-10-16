"""One local transfer demo: fresh incident -> proposal -> approval -> mock -> retry."""
import getpass
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

BASE = "http://127.0.0.1:8000/api/v1"


def main():
    token = getpass.getpass("Manager bearer token (hidden): ").strip()
    if not token:
        raise SystemExit("Token is required.")
    def call(path, body=None, key=None):
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method="POST" if body is not None else "GET")
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            print(f"Request failed: {path} | HTTP {exc.code}")
            print(exc.read().decode())
            raise SystemExit(1) from None
    _, actor = call("/auth/me")
    if actor["role"] != "PROCUREMENT_MANAGER":
        raise SystemExit("A procurement manager token is required.")
    reference = f"MOCK-EXEC-{uuid4().hex[:16]}"
    _, incident = call("/incidents", {
        "source_system": "DEMO_EXECUTION", "source_ref": reference,
        "title": "Homagama motor recovery execution demo", "description": "Local mock only",
        "product_id": "4a6e7125-6030-56c0-ba1e-aa63215655e8",
        "plant_id": "7725ae12-9ff2-5cfe-8e2b-0ce4ce88bf77",
        "detected_at": datetime.now(timezone.utc).isoformat(),
    })
    _, proposal = call(f'/incidents/{incident["id"]}/proposals/transfer', {
        "warehouse_code": "LK-WAT-WH", "lead_time_hours": 6,
        "fixed_transport_cost": "18000", "currency": "LKR",
    }, reference + "-proposal")
    proposal_id = proposal["id"]
    print(f"Proposal ID: {proposal_id}")
    call(f"/proposals/{proposal_id}/decision", {
        "decision": "APPROVED", "reason": "Manager-authorized local mock execution demonstration.",
    }, reference + "-decision")
    status, result = call(f"/proposals/{proposal_id}/execute-mock", {})
    print(f"First execution HTTP {status}")
    print(json.dumps(result, indent=2))
    replay_status, replay = call(f"/proposals/{proposal_id}/execute-mock", {})
    if status != 201 or replay_status != 200 or replay["id"] != result["id"]:
        raise SystemExit("Unexpected retry behavior. Inspect the responses.")
    print("Retry HTTP 200: same execution ID; no second mock order.")
    print("Stock is reserved. No physical delivery/receipt was recorded.")


if __name__ == "__main__":
    main()
