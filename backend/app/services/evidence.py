"""Capture planning inputs inside the evaluator's REPEATABLE READ transaction."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance, Location, Product, ProductionDemand,
    PurchaseOrder, PurchaseOrderLine, Shipment, ShipmentLine,
    Supplier, SupplierOffer,
)


def _json_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported evidence value: {type(value).__name__}")


def _record_snapshot(record) -> dict:
    return {
        column.key: _json_value(getattr(record, column.key))
        for column in inspect(type(record)).column_attrs
    }


def capture_recovery_evidence(
    *, session: Session, sku: str, plant_code: str,
    assessed_at: datetime, warehouse_code: str | None = None,
) -> dict:
    product = session.scalar(select(Product).where(Product.sku == sku))
    plant = session.scalar(select(Location).where(
        Location.code == plant_code, Location.type == "PLANT"
    ))
    if product is None or plant is None:
        raise ValueError("Evidence scope no longer exists.")
    warehouse = None
    location_ids = [plant.id]
    if warehouse_code is not None:
        warehouse = session.scalar(select(Location).where(
            Location.code == warehouse_code, Location.type == "WAREHOUSE"
        ))
        if warehouse is None:
            raise ValueError("Evidence warehouse no longer exists.")
        location_ids.append(warehouse.id)
    balances = session.scalars(select(InventoryBalance).where(
        InventoryBalance.product_id == product.id,
        InventoryBalance.location_id.in_(location_ids),
    ).order_by(InventoryBalance.id)).all()
    demands = session.scalars(select(ProductionDemand).where(
        ProductionDemand.product_id == product.id,
        ProductionDemand.plant_id == plant.id,
        ProductionDemand.status.in_(("OPEN", "PARTIALLY_FULFILLED")),
    ).order_by(ProductionDemand.required_at, ProductionDemand.id)).all()
    rows = session.execute(
        select(ShipmentLine, Shipment, PurchaseOrderLine, PurchaseOrder)
        .join(Shipment, ShipmentLine.shipment_id == Shipment.id)
        .join(PurchaseOrderLine, ShipmentLine.purchase_order_line_id == PurchaseOrderLine.id)
        .join(PurchaseOrder, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .where(
            PurchaseOrderLine.product_id == product.id,
            Shipment.destination_id == plant.id,
            Shipment.status.in_(("PLANNED", "IN_TRANSIT", "DELAYED")),
        ).order_by(Shipment.current_eta, Shipment.id, ShipmentLine.id)
    ).all()
    groups = [{}, {}, {}, {}]
    for row in rows:
        for group, record in zip(groups, row):
            group[str(record.id)] = _record_snapshot(record)
    evidence = {
        "schema_version": 2,
        "snapshot_kind": "RECOVERY_INPUT_RECORDS",
        "assessed_at": _json_value(assessed_at),
        "scope": {"product_id": str(product.id), "plant_id": str(plant.id)},
        "product": _record_snapshot(product),
        "plant": _record_snapshot(plant),
        "inventory_balances": [_record_snapshot(row) for row in balances],
        "production_demands": [_record_snapshot(row) for row in demands],
        "requires_revalidation": True,
    }
    for name, group in zip(
        ("shipment_lines", "shipments", "purchase_order_lines", "purchase_orders"), groups
    ):
        evidence[name] = list(group.values())
    if warehouse is not None:
        evidence["warehouse"] = _record_snapshot(warehouse)
        evidence["scope"]["warehouse_id"] = str(warehouse.id)
    else:
        offers = session.execute(
            select(SupplierOffer, Supplier)
            .join(Supplier, SupplierOffer.supplier_id == Supplier.id)
            .where(SupplierOffer.product_id == product.id)
            .order_by(Supplier.code, SupplierOffer.id)
        ).all()
        evidence["supplier_offers"] = [_record_snapshot(offer) for offer, _ in offers]
        suppliers = {str(supplier.id): _record_snapshot(supplier) for _, supplier in offers}
        evidence["suppliers"] = list(suppliers.values())
    return evidence


def capture_transfer_evidence(
    *, session: Session, product_id: UUID, plant_id: UUID,
    warehouse_id: UUID, assessed_at: datetime,
) -> dict:
    """Compatibility entry point for existing callers."""
    product = session.get(Product, product_id)
    plant = session.get(Location, plant_id)
    warehouse = session.get(Location, warehouse_id)
    if product is None or plant is None or warehouse is None:
        raise ValueError("Evidence scope not found.")
    return capture_recovery_evidence(
        session=session, sku=product.sku, plant_code=plant.code,
        warehouse_code=warehouse.code, assessed_at=assessed_at,
    )
