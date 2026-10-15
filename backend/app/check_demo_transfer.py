import json
from datetime import timedelta
from decimal import Decimal

from app.core.database import engine
from app.services.transfer_recommendation import (
    recommend_warehouse_transfer,
)


def main() -> None:
    result = recommend_warehouse_transfer(
        sku="FAN-MOTOR-45W",
        plant_code="LK-HOM-PLANT",
        warehouse_code="LK-WAT-WH",
        lead_time=timedelta(hours=6),
        fixed_transport_cost=Decimal("18000.00"),
        currency="LKR",
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()