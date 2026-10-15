import json
from decimal import Decimal

from app.core.database import engine
from app.services.purchase_recommendation import (
    recommend_supplier_purchases,
)


def main() -> None:
    result = recommend_supplier_purchases(
        sku="FAN-MOTOR-45W",
        plant_code="LK-HOM-PLANT",
        freight_cost=Decimal("12000.00"),
        currency="LKR",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()