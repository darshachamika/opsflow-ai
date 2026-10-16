from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Location, Product
from app.services.incidents import create_or_get_incident


def main() -> None:
    with Session(engine) as session:
        with session.begin():
            product = session.scalar(
                select(Product).where(
                    Product.sku == "FAN-MOTOR-45W"
                )
            )
            plant = session.scalar(
                select(Location).where(
                    Location.code == "LK-HOM-PLANT"
                )
            )

            if product is None or plant is None:
                raise RuntimeError("Original demo product or plant is missing.")

            arguments = {
                "session": session,
                "source_system": "DEMO_TRIAGE",
                "source_ref": "INCIDENT-DEMO-LK-001",
                "title": "Fan motor supply disruption at Homagama",
                "description": (
                    "Fictional demo incident for evaluating recovery options."
                ),
                "product_id": product.id,
                "plant_id": plant.id,
                # Stable original event time makes repeated runs idempotent.
                "detected_at": datetime(
                    2026, 10, 15, 9, 40,
                    tzinfo=timezone.utc,
                ),
            }

            first, first_created = create_or_get_incident(**arguments)
            second, second_created = create_or_get_incident(**arguments)

            incident_id = first.id
            same_id = first.id == second.id
            status = first.status

            if not same_id or second_created:
                raise RuntimeError("Incident replay did not behave correctly.")

        print("=== DEMO INCIDENT ===")
        print(f"Incident ID: {incident_id}")
        print(f"First call created: {first_created}")
        print(f"Second call created: {second_created}")
        print(f"Same incident ID: {same_id}")
        print(f"Status: {status}")
        print("Transaction committed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()