"""Add isolated fictional supply scenarios; never overwrite existing evidence."""
import argparse
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models import Product, Location, InventoryBalance, ProductionDemand, Supplier, SupplierOffer, PurchaseOrder, PurchaseOrderLine, Shipment, ShipmentLine
from app.models.incident import Incident

NAMESPACE = UUID('e8bfbbec-9527-4135-9726-3d4f159df7ae')
# city, product, demand, plant stock, inbound, ETA hours, warehouse stock, stale
SCENARIOS = [
 ('Homagama', 'Fan motor 60W', 600, 100, 200, 5, 500, False),
 ('Katunayake', 'Control circuit board', 400, 50, 150, 30, 100, False),
 ('Biyagama', 'Food packaging carton', 1200, 1300, 200, 5, 600, False),
 ('Horana', 'Water pump assembly', 350, 100, 250, 5, 450, False),
 ('Kandy', 'Temperature sensor', 500, 60, 100, 26, 500, True),
 ('Galle', 'Industrial cable roll', 300, 80, 70, 5, 250, False),
 ('Kurunegala', 'Machine bearing kit', 700, 150, 200, 32, 200, False),
 ('Ratmalana', 'Power adapter unit', 800, 200, 250, 5, 500, False),
]

def seed(batch: str, assess: bool) -> None:
    now = datetime.now(timezone.utc)
    targets = []
    created = 0
    def ident(key): return uuid5(NAMESPACE, f'{batch}:{key}')
    with Session(engine) as session, session.begin():
        for i, (city, name, demand, stock, inbound, eta, whstock, stale) in enumerate(SCENARIOS, 1):
            prefix = f'DASH-{batch}-{i:02}'
            iid = ident(f'{i}:incident')
            warehouse_code = f'{prefix}-WH'
            targets.append((iid, warehouse_code))
            if session.get(Incident, iid):
                continue
            observed = now - timedelta(hours=3) if stale else now
            product = Product(id=ident(f'{i}:product'), sku=f'{prefix}-SKU', name=f'{name} (Fictional demo)', unit_of_measure='UNIT', is_active=True)
            plant = Location(id=ident(f'{i}:plant'), code=f'{prefix}-PLANT', name=f'{city} Plant (Demo {batch})', type='PLANT')
            warehouse = Location(id=ident(f'{i}:warehouse'), code=warehouse_code, name=f'{city} Reserve Warehouse (Demo {batch})', type='WAREHOUSE')
            supplier = Supplier(id=ident(f'{i}:supplier'), code=f'{prefix}-SUP', name=f'{city} Components (Fictional)', approval_status='APPROVED')
            session.add_all([product, plant, warehouse, supplier]); session.flush()
            for label, loc, qty in [('plant', plant, stock), ('warehouse', warehouse, whstock)]:
                session.add(InventoryBalance(id=ident(f'{i}:stock:{label}'), product_id=product.id, location_id=loc.id, on_hand_qty=Decimal(qty), reserved_qty=Decimal(0), observed_at=observed, source_system='FICTIONAL_DASHBOARD', source_version=batch))
            session.add(ProductionDemand(id=ident(f'{i}:demand'), source_system='FICTIONAL_DASHBOARD', source_ref=f'{prefix}-DEMAND', plant_id=plant.id, product_id=product.id, required_qty=Decimal(demand), fulfilled_qty=Decimal(0), required_at=now+timedelta(hours=12), status='OPEN'))
            session.add(SupplierOffer(id=ident(f'{i}:offer'), supplier_id=supplier.id, product_id=product.id, unit_price=Decimal(500+i*250), currency='LKR', available_qty=Decimal(1000), lead_time_hours=7, observed_at=observed, valid_until=now+timedelta(hours=24)))
            po = PurchaseOrder(id=ident(f'{i}:po'), source_system='FICTIONAL_DASHBOARD', external_id=f'{prefix}-PO', supplier_id=supplier.id, destination_id=plant.id, status='CONFIRMED', currency='LKR', expected_at=now+timedelta(hours=5))
            shipment = Shipment(id=ident(f'{i}:shipment'), source_system='FICTIONAL_DASHBOARD', external_id=f'{prefix}-SHP', destination_id=plant.id, status='DELAYED' if eta>12 else 'IN_TRANSIT', original_eta=now+timedelta(hours=5), current_eta=now+timedelta(hours=eta), observed_at=observed)
            session.add_all([po, shipment]); session.flush()
            line = PurchaseOrderLine(id=ident(f'{i}:po-line'), purchase_order_id=po.id, line_number=1, product_id=product.id, quantity=Decimal(inbound), unit_price=Decimal(500+i*250))
            session.add(line); session.flush()
            session.add(ShipmentLine(id=ident(f'{i}:shipment-line'), shipment_id=shipment.id, purchase_order_line_id=line.id, quantity=Decimal(inbound)))
            session.add(Incident(id=iid, source_system='FICTIONAL_DASHBOARD', source_ref=f'{prefix}-INC', title=f'[DEMO] {city}: {name} supply review', description=f'Fictional interview scenario. Batch {batch}. Required {demand} units; plant stock {stock}; inbound {inbound}. Source warehouse: {warehouse_code}. No real company or order.', product_id=product.id, plant_id=plant.id, status='OPEN', detected_at=now))
            created += 1
    print(f'Created {created} fictional scenarios. Existing scenarios and reservations unchanged.', flush=True)
    if assess:
        from app.schemas.orchestration import OrchestrationRequest
        from app.services.workflows import create_run
        for iid, warehouse_code in targets:
            result, fresh = create_run(iid, OrchestrationRequest(warehouse_code=warehouse_code, transfer_lead_time_hours=6, transport_cost=Decimal('18000'), purchase_freight_cost=Decimal('12000'), currency='LKR'), 'demo.dashboard.seed', f'dashboard:{batch}:{iid}')
            print(f'{warehouse_code}: run {result["status"]} ({"created" if fresh else "existing"})', flush=True)
    print('No approvals or executions were created. Use the UI to review and act.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', default='v1', help='A new batch creates separate product/plant scenarios; existing batches are never reset.')
    parser.add_argument('--assess', action='store_true', help='Run actual planning services; configured optional AI provider may be called.')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9-]{1,16}', args.batch):
        parser.error('batch must contain 1–16 letters, numbers or hyphens')
    try:
        seed(args.batch, args.assess)
    finally:
        engine.dispose()
