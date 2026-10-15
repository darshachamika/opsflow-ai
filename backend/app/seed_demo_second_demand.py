from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import ProductionDemand


NAMESPACE = UUID("97ce2500-17fa-45dc-adf7-21655f72db46")


def seed_second_demand() -> None:
    with Session(engine) as session:
        with session.begin():
            original = session.scalar(
                select(ProductionDemand).where(
                    ProductionDemand.source_system == "DEMO_ERP",
                    ProductionDemand.source_ref == "DEMAND-DEMO-LK-001",
                )
            )

            if original is None:
                raise RuntimeError("Run the original demo seed first.")

            existing = session.scalar(
                select(ProductionDemand).where(
                    ProductionDemand.source_system == "DEMO_ERP",
                    ProductionDemand.source_ref == "DEMAND-DEMO-LK-002",
                )
            )

            if existing is not None:
                print("Second demo demand already exists.")
                return

            session.add(
                ProductionDemand(
                    id=uuid5(NAMESPACE, "second-demand"),
                    source_system="DEMO_ERP",
                    source_ref="DEMAND-DEMO-LK-002",
                    plant_id=original.plant_id,
                    product_id=original.product_id,
                    required_qty=Decimal("200"),
                    fulfilled_qty=Decimal("0"),
                    required_at=original.required_at + timedelta(hours=1),
                    status="OPEN",
                )
            )

        print("Created DEMAND-DEMO-LK-002: 200 units.")
        print("Deadline: one hour after the first demand.")


if __name__ == "__main__":
    try:
        seed_second_demand()
    finally:
        engine.dispose()