"""Authenticated local mock execution worker. No Gemini or real ERP calls."""
import argparse
import getpass
import time
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.core.approval_auth import authenticate_token
from app.core.config import settings
from app.core.database import engine
from app.services.approval_resume import process_next


def checked_actor(token):
    actor = authenticate_token(token, settings.approval_principals_json.get_secret_value(),
                               now=datetime.now(timezone.utc))
    if actor.role != "PROCUREMENT_MANAGER":
        raise PermissionError("Procurement manager permission required.")
    return actor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    token = getpass.getpass("Procurement manager application token (hidden): ")
    consecutive_failures = 0
    print("MOCK resume worker: pending approved jobs will be processed.", flush=True)
    try:
        while True:
            try:
                # Recheck expiry before every transaction. Config changes require restart.
                actor = checked_actor(token)
            except (HTTPException, PermissionError):
                print("Worker stopped: invalid, expired, or unauthorized credential.", flush=True)
                raise SystemExit(1) from None
            try:
                outcome = process_next(actor)
            except SQLAlchemyError:
                consecutive_failures += 1
                print("Database transaction rolled back; no job acknowledged.", flush=True)
                if args.once or consecutive_failures >= 5:
                    raise SystemExit(1) from None
                time.sleep(min(2 ** consecutive_failures, 30))
                continue
            except Exception:
                print("Worker stopped after an unexpected failure; transaction rolled back. Investigate before restarting.", flush=True)
                raise SystemExit(1) from None
            consecutive_failures = 0
            if outcome:
                print(f"Proposal {outcome['proposal_id']}: {outcome['status']}", flush=True)
            if args.once:
                if outcome is None:
                    print("No pending job available.", flush=True)
                break
            if outcome is None:
                time.sleep(2)
    except KeyboardInterrupt:
        print("Worker stopped.", flush=True)
    finally:
        token = ""
        engine.dispose()


if __name__ == "__main__":
    main()
