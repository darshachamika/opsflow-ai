import json

from app.core.database import engine
from app.services.impact_assessment import assess_product_impact


def main() -> None:
    result = assess_product_impact(
        sku="FAN-MOTOR-45W",
        plant_code="LK-HOM-PLANT",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()