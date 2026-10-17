"""Run separately from Uvicorn: python -m app.workflow_worker."""
import argparse
import time
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import engine
from app.services.workflow_queue import process_one


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one eligible job and exit.")
    args = parser.parse_args()
    worker_id = f"worker-{uuid4().hex}"
    print(f"Planning worker started: {worker_id}", flush=True)
    try:
        while True:
            try:
                worked = process_one(worker_id)
            except SQLAlchemyError:
                print("Database unavailable; unacknowledged jobs remain recoverable after lease expiry.", flush=True)
                if args.once:
                    raise SystemExit(1) from None
                time.sleep(5)
                continue
            if args.once:
                print("Job handled." if worked else "No job claimed.", flush=True)
                break
            if not worked:
                time.sleep(2)
    except KeyboardInterrupt:
        print("Worker stopped; unfinished leases will expire.", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
