from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import database_url
from app.models import (
    InventoryBalance,
    Location,
    Product,
    ProductionDemand,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
    ShipmentLine,
    Supplier,
    SupplierOffer,
)
from app.services.impact_assessment import (
    ImpactTargetNotFound,
    _assess,
)


AS_OF = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def test_engine():
    # Explicitly use a separate database.
    test_url = database_url.set(database="opsflow_test")

    if test_url.database != "opsflow_test":
        raise RuntimeError("Integration tests require opsflow_test.")

    engine = create_engine(
        test_url,
        isolation_level="REPEATABLE READ",
        connect_args={"connect_timeout": 5},
    )

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()

        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
        ) as db_session:
            try:
                yield db_session
            finally:
                db_session.close()
                transaction.rollback()


def seed_pool(
    session,
    *,
    observed_at=AS_OF,
    include_balance=True,
):
    suffix = uuid4().hex[:12]

    product = Product(
        sku=f"TEST-MOTOR-{suffix}",
        name="Integration Test Motor",
        unit_of_measure="UNIT",
        is_active=True,
    )
    plant = Location(
        code=f"TEST-PLANT-{suffix}",
        name="Integration Test Plant",
        type="PLANT",
    )

    session.add_all([product, plant])
    session.flush()

    if include_balance:
        session.add(
            InventoryBalance(
                product_id=product.id,
                location_id=plant.id,
                on_hand_qty=Decimal("120"),
                reserved_qty=Decimal("20"),
                observed_at=observed_at,
                source_system="TEST_WMS",
                source_version="1",
            )
        )

    first = ProductionDemand(
        source_system="TEST_ERP",
        source_ref=f"TEST-DEMAND-A-{suffix}",
        plant_id=plant.id,
        product_id=product.id,
        required_qty=Decimal("80"),
        fulfilled_qty=Decimal("0"),
        required_at=AS_OF + timedelta(hours=2),
        status="OPEN",
    )

    second = ProductionDemand(
        source_system="TEST_ERP",
        source_ref=f"TEST-DEMAND-B-{suffix}",
        plant_id=plant.id,
        product_id=product.id,
        required_qty=Decimal("70"),
        fulfilled_qty=Decimal("0"),
        required_at=AS_OF + timedelta(hours=3),
        status="OPEN",
    )

    session.add_all([first, second])
    session.flush()

    return product, plant, first, second


def assess(session, product, plant):
    return _assess(
        session=session,
        sku=product.sku,
        plant_code=plant.code,
        as_of=AS_OF,
    )


def test_fresh_stock_is_shared_without_double_allocation(session):
    product, plant, first, second = seed_pool(session)

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    assert result["issues"] == []

    allocations = result["allocations"]
    assert len(allocations) == 2

    assert allocations[0]["demand_id"] == str(first.id)
    assert Decimal(allocations[0]["stock_allocated_qty"]) == Decimal("80")
    assert Decimal(allocations[0]["shortage_qty"]) == Decimal("0")

    assert allocations[1]["demand_id"] == str(second.id)
    assert Decimal(allocations[1]["stock_allocated_qty"]) == Decimal("20")
    assert Decimal(allocations[1]["shortage_qty"]) == Decimal("50")

    total_allocated = sum(
        Decimal(item["stock_allocated_qty"])
        for item in allocations
    )
    assert total_allocated == Decimal("100")

    # Assessment must not modify the persisted inventory.
    session.expire_all()
    balance = session.query(InventoryBalance).filter_by(
        product_id=product.id,
        location_id=plant.id,
    ).one()

    assert balance.on_hand_qty == Decimal("120")
    assert balance.reserved_qty == Decimal("20")


def test_stale_inventory_blocks_allocation(session):
    product, plant, _, _ = seed_pool(
        session,
        observed_at=AS_OF - timedelta(minutes=31),
    )

    result = assess(session, product, plant)

    assert result["status"] == "INCOMPLETE"
    assert result["allocations"] == []
    assert "INVENTORY_STALE" in {
        issue["code"] for issue in result["issues"]
    }


def test_missing_inventory_is_not_treated_as_zero(session):
    product, plant, _, _ = seed_pool(
        session,
        include_balance=False,
    )

    result = assess(session, product, plant)

    assert result["status"] == "INCOMPLETE"
    assert result["allocations"] == []
    assert "MISSING_INVENTORY" in {
        issue["code"] for issue in result["issues"]
    }


def test_past_deadline_blocks_deadline_coverage_assessment(session):
    product, plant, first, _ = seed_pool(session)

    first.required_at = AS_OF - timedelta(minutes=1)
    session.flush()

    result = assess(session, product, plant)

    assert result["status"] == "INCOMPLETE"
    assert result["allocations"] == []
    assert "DEMAND_DEADLINE_PASSED" in {
        issue["code"] for issue in result["issues"]
    }


def test_closed_demands_are_excluded(session):
    product, plant, first, second = seed_pool(session)

    first.status = "FULFILLED"
    first.fulfilled_qty = first.required_qty
    second.status = "CANCELLED"
    session.flush()

    result = assess(session, product, plant)

    assert result["status"] == "NO_OPEN_DEMANDS"
    assert result["allocations"] == []


def test_unknown_product_raises_not_found(session):
    with pytest.raises(ImpactTargetNotFound, match="Product not found"):
        _assess(
            session=session,
            sku=f"MISSING-{uuid4().hex}",
            plant_code="MISSING-PLANT",
            as_of=AS_OF,
        )
def seed_inbound(
    session,
    *,
    product,
    plant,
    quantity="60",
    eta_hours=1,
    observed_at=AS_OF,
    status="IN_TRANSIT",
    po_status="CONFIRMED",
    po_destination=None,
):
    suffix = uuid4().hex[:12]

    supplier = Supplier(
        code=f"TEST-SUP-{suffix}",
        name="Integration Test Supplier",
        approval_status="APPROVED",
    )
    session.add(supplier)
    session.flush()

    purchase_order = PurchaseOrder(
        source_system="TEST_ERP",
        external_id=f"TEST-PO-{suffix}",
        supplier_id=supplier.id,
        destination_id=(
            po_destination.id
            if po_destination is not None
            else plant.id
        ),
        status=po_status,
        currency="LKR",
        expected_at=AS_OF + timedelta(hours=eta_hours),
    )
    session.add(purchase_order)
    session.flush()

    order_line = PurchaseOrderLine(
        purchase_order_id=purchase_order.id,
        line_number=1,
        product_id=product.id,
        quantity=Decimal(quantity),
        unit_price=Decimal("2100.0000"),
    )
    session.add(order_line)
    session.flush()

    shipment = Shipment(
        source_system="TEST_CARRIER",
        external_id=f"TEST-SHP-{suffix}",
        destination_id=plant.id,
        status=status,
        original_eta=AS_OF + timedelta(hours=eta_hours),
        current_eta=AS_OF + timedelta(hours=eta_hours),
        observed_at=observed_at,
    )
    session.add(shipment)
    session.flush()

    shipment_line = ShipmentLine(
        shipment_id=shipment.id,
        purchase_order_line_id=order_line.id,
        quantity=Decimal(quantity),
    )
    session.add(shipment_line)
    session.flush()

    return shipment, shipment_line


def test_multiple_inbound_shipments_cover_remaining_shortage(session):
    product, plant, _, _ = seed_pool(session)

    seed_inbound(
        session,
        product=product,
        plant=plant,
        quantity="30",
    )
    seed_inbound(
        session,
        product=product,
        plant=plant,
        quantity="30",
    )

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    first, second = result["allocations"]

    assert Decimal(first["stock_allocated_qty"]) == Decimal("80")
    assert Decimal(first["inbound_allocated_qty"]) == Decimal("0")

    assert Decimal(second["stock_allocated_qty"]) == Decimal("20")
    assert Decimal(second["inbound_allocated_qty"]) == Decimal("50")
    assert Decimal(second["shortage_qty"]) == Decimal("0")

    # Each shipment has 30 units, so covering 50 requires both.
    assert len(second["inbound_allocations"]) == 2
    assert sorted(
        Decimal(item["quantity"])
        for item in second["inbound_allocations"]
    ) == [Decimal("20"), Decimal("30")]


def test_shared_inbound_is_not_allocated_twice(session):
    product, plant, _, _ = seed_pool(session)

    balance = session.query(InventoryBalance).filter_by(
        product_id=product.id,
        location_id=plant.id,
    ).one()

    balance.reserved_qty = Decimal("0")
    balance.on_hand_qty = Decimal("0")
    session.flush()

    _, line = seed_inbound(
        session,
        product=product,
        plant=plant,
        quantity="100",
    )

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    first, second = result["allocations"]

    assert Decimal(first["inbound_allocated_qty"]) == Decimal("80")
    assert Decimal(second["inbound_allocated_qty"]) == Decimal("20")
    assert Decimal(second["shortage_qty"]) == Decimal("50")

    total_from_line = sum(
        Decimal(item["quantity"])
        for allocation in result["allocations"]
        for item in allocation["inbound_allocations"]
        if item["shipment_line_id"] == str(line.id)
    )
    assert total_from_line == Decimal("100")


def test_late_inbound_does_not_cover_deadlines(session):
    product, plant, _, _ = seed_pool(session)

    seed_inbound(
        session,
        product=product,
        plant=plant,
        quantity="100",
        eta_hours=4,
    )

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    assert all(
        Decimal(item["inbound_allocated_qty"]) == Decimal("0")
        for item in result["allocations"]
    )
    assert Decimal(
        result["allocations"][1]["shortage_qty"]
    ) == Decimal("50")


@pytest.mark.parametrize("status", ["DELIVERED", "CANCELLED"])
def test_inactive_inbound_is_excluded_from_database_query(session, status):
    product, plant, _, _ = seed_pool(session)

    seed_inbound(
        session,
        product=product,
        plant=plant,
        status=status,
    )

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    assert Decimal(
        result["allocations"][1]["inbound_allocated_qty"]
    ) == Decimal("0")


@pytest.mark.parametrize(
    "case, expected_code",
    [
        ("stale", "SHIPMENT_STALE"),
        ("past_eta", "SHIPMENT_ETA_PASSED"),
        ("closed_po", "INACTIVE_PURCHASE_ORDER"),
    ],
)
def test_invalid_inbound_evidence_blocks_assessment(
    session,
    case,
    expected_code,
):
    product, plant, _, _ = seed_pool(session)

    options = {}

    if case == "stale":
        options["observed_at"] = AS_OF - timedelta(minutes=31)
    elif case == "past_eta":
        options["eta_hours"] = -1
    elif case == "closed_po":
        options["po_status"] = "CANCELLED"

    seed_inbound(
        session,
        product=product,
        plant=plant,
        **options,
    )

    result = assess(session, product, plant)

    assert result["status"] == "INCOMPLETE"
    assert result["allocations"] == []
    assert expected_code in {
        issue["code"] for issue in result["issues"]
    }


def test_purchase_order_destination_mismatch_blocks_assessment(session):
    product, plant, _, _ = seed_pool(session)

    other_plant = Location(
        code=f"OTHER-{uuid4().hex[:12]}",
        name="Other Test Plant",
        type="PLANT",
    )
    session.add(other_plant)
    session.flush()

    seed_inbound(
        session,
        product=product,
        plant=plant,
        po_destination=other_plant,
    )

    result = assess(session, product, plant)

    assert result["status"] == "INCOMPLETE"
    assert result["allocations"] == []
    assert "DESTINATION_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }

@pytest.mark.parametrize("different_field", ["product", "plant"])
def test_unrelated_shipments_do_not_enter_supply_pool(
    session,
    different_field,
):
    product, plant, _, _ = seed_pool(session)
    other_product, other_plant, _, _ = seed_pool(session)

    seed_inbound(
        session,
        product=(
            other_product
            if different_field == "product"
            else product
        ),
        plant=(
            other_plant
            if different_field == "plant"
            else plant
        ),
    )

    result = assess(session, product, plant)

    assert result["status"] == "ASSESSED"
    assert Decimal(
        result["allocations"][1]["inbound_allocated_qty"]
    ) == Decimal("0")
    assert Decimal(
        result["allocations"][1]["shortage_qty"]
    ) == Decimal("50")

@pytest.fixture
def transfer_scenario(test_engine):
    from sqlalchemy import delete

    created = {}
    try:
        with Session(test_engine) as setup:
            with setup.begin():
                product, plant, first, second = seed_pool(setup)
                warehouse = Location(
                    code=f"TEST-WH-{uuid4().hex[:12]}",
                    name="Test Transfer Warehouse",
                    type="WAREHOUSE",
                )
                setup.add(warehouse)
                setup.flush()
                warehouse_balance = InventoryBalance(
                    product_id=product.id,
                    location_id=warehouse.id,
                    on_hand_qty=Decimal("100"),
                    reserved_qty=Decimal("20"),
                    observed_at=AS_OF,
                    source_system="TEST_WMS",
                    source_version="1",
                )
                setup.add(warehouse_balance)
                setup.flush()
                created.update({
                    "product_id": product.id,
                    "plant_id": plant.id,
                    "warehouse_id": warehouse.id,
                    "warehouse_balance_id": warehouse_balance.id,
                    "demand_ids": [first.id, second.id],
                    "sku": product.sku,
                    "plant_code": plant.code,
                    "warehouse_code": warehouse.code,
                })
        yield created
    finally:
        if created:
            with Session(test_engine) as cleanup:
                with cleanup.begin():
                    cleanup.execute(
                        delete(ProductionDemand).where(
                            ProductionDemand.id.in_(created["demand_ids"])
                        )
                    )
                    cleanup.execute(
                        delete(InventoryBalance).where(
                            InventoryBalance.product_id == created["product_id"],
                            InventoryBalance.location_id.in_([
                                created["plant_id"], created["warehouse_id"],
                            ]),
                        )
                    )
                    cleanup.execute(
                        delete(Product).where(Product.id == created["product_id"])
                    )
                    cleanup.execute(
                        delete(Location).where(Location.id.in_([
                            created["plant_id"], created["warehouse_id"],
                        ]))
                    )


@pytest.fixture
def purchase_scenario(test_engine, transfer_scenario):
    from sqlalchemy import delete

    scenario = dict(transfer_scenario)
    created = {}

    try:
        with Session(test_engine) as setup:
            with setup.begin():
                supplier = Supplier(
                    code=f"TEST-BUY-{uuid4().hex[:12]}",
                    name="Test Purchase Supplier",
                    approval_status="APPROVED",
                )
                setup.add(supplier)
                setup.flush()

                offer = SupplierOffer(
                    supplier_id=supplier.id,
                    product_id=scenario["product_id"],
                    unit_price=Decimal("2100.0000"),
                    currency="LKR",
                    available_qty=Decimal("100"),
                    lead_time_hours=1,
                    observed_at=AS_OF,
                    valid_until=AS_OF + timedelta(hours=24),
                )
                setup.add(offer)
                setup.flush()

                created.update({
                    "supplier_id": supplier.id,
                    "offer_id": offer.id,
                })

        scenario.update(created)
        yield scenario

    finally:
        if created:
            with Session(test_engine) as cleanup:
                with cleanup.begin():
                    cleanup.execute(
                        delete(SupplierOffer).where(
                            SupplierOffer.id == created["offer_id"]
                        )
                    )
                    cleanup.execute(
                        delete(Supplier).where(
                            Supplier.id == created["supplier_id"]
                        )
                    )


@pytest.mark.parametrize(
    "case, expected_status, expected_reason",
    [
        ("fresh", "FULL_COVERAGE", None),
        ("limited", "PARTIAL_COVERAGE", None),
        ("stale", "BLOCKED", "OFFER_STALE"),
        ("expired", "BLOCKED", "OFFER_EXPIRED"),
        ("suspended", "BLOCKED", "SUPPLIER_NOT_APPROVED"),
        ("currency", "BLOCKED", "CURRENCY_MISMATCH"),
        ("late", "NO_FEASIBLE_PURCHASE", None),
    ],
)
def test_purchase_recommendation_with_database(
    test_engine,
    purchase_scenario,
    monkeypatch,
    case,
    expected_status,
    expected_reason,
):
    from unittest.mock import patch

    from app.services import purchase_recommendation as service

    scenario = purchase_scenario

    with Session(test_engine) as setup:
        with setup.begin():
            offer = setup.get(SupplierOffer, scenario["offer_id"])
            supplier = setup.get(Supplier, scenario["supplier_id"])

            if case == "limited":
                offer.available_qty = Decimal("20")
            elif case == "stale":
                offer.observed_at = AS_OF - timedelta(minutes=31)
            elif case == "expired":
                offer.observed_at = AS_OF - timedelta(minutes=5)
                offer.valid_until = AS_OF
            elif case == "suspended":
                supplier.approval_status = "SUSPENDED"
            elif case == "currency":
                offer.currency = "USD"
            elif case == "late":
                offer.lead_time_hours = 4

    monkeypatch.setattr(service, "engine", test_engine)

    with patch.object(service, "datetime", wraps=datetime) as clock:
        clock.now.return_value = AS_OF

        result = service.recommend_supplier_purchases(
            sku=scenario["sku"],
            plant_code=scenario["plant_code"],
            freight_cost=Decimal("12000.00"),
            currency="LKR",
        )

    assert result["execution_status"] == "NOT_EXECUTED"
    assert len(result["options"]) == 1

    option = result["options"][0]
    assert option["offer_id"] == str(scenario["offer_id"])
    assert option["status"] == expected_status

    if expected_reason is not None:
        assert result["status"] == "NO_ELIGIBLE_OPTIONS"
        assert expected_reason in option["reasons"]
        assert option["plan"] is None

    elif case == "late":
        assert result["status"] == "NO_ELIGIBLE_OPTIONS"
        assert Decimal(option["plan"]["purchase_qty"]) == Decimal("0")
        assert Decimal(option["plan"]["total_cost"]) == Decimal("0")

    else:
        assert result["status"] == "OPTIONS_AVAILABLE"

        plan = option["plan"]
        expected_qty = Decimal("20") if case == "limited" else Decimal("50")

        assert Decimal(plan["purchase_qty"]) == expected_qty
        assert Decimal(plan["items_cost"]) == expected_qty * Decimal("2100")
        assert Decimal(plan["freight_cost"]) == Decimal("12000")
        assert Decimal(plan["total_cost"]) == (
            expected_qty * Decimal("2100") + Decimal("12000")
        )

        remaining = sum(
            Decimal(item["remaining_shortage_qty"])
            for item in plan["allocations"]
        )
        assert remaining == Decimal("50") - expected_qty

    # Generating a recommendation must not consume supplier inventory.
    with Session(test_engine) as verification:
        offer = verification.get(
            SupplierOffer,
            scenario["offer_id"],
        )
        expected_available = (
            Decimal("20") if case == "limited" else Decimal("100")
        )
        assert offer.available_qty == expected_available


def test_purchase_recommendation_reports_no_offers(
    test_engine,
    transfer_scenario,
    monkeypatch,
):
    from unittest.mock import patch

    from app.services import purchase_recommendation as service

    monkeypatch.setattr(service, "engine", test_engine)

    with patch.object(service, "datetime", wraps=datetime) as clock:
        clock.now.return_value = AS_OF

        result = service.recommend_supplier_purchases(
            sku=transfer_scenario["sku"],
            plant_code=transfer_scenario["plant_code"],
            freight_cost=Decimal("12000.00"),
            currency="LKR",
        )

    assert result["status"] == "NO_OFFERS"
    assert result["options"] == []
    assert result["execution_status"] == "NOT_EXECUTED"

@pytest.mark.parametrize(
    "case, expected_status, expected_transfer, expected_remaining",
    [
        ("fresh", "FULL_COVERAGE", "50", "0"),
        ("limited", "PARTIAL_COVERAGE", "20", "30"),
        ("stale", "INCOMPLETE", None, None),
        ("late", "NO_FEASIBLE_TRANSFER", "0", "50"),
    ],
)
def test_transfer_recommendation_with_database(
    test_engine,
    transfer_scenario,
    monkeypatch,
    case,
    expected_status,
    expected_transfer,
    expected_remaining,
):
    from unittest.mock import patch

    from app.services import transfer_recommendation as service

    scenario = transfer_scenario

    if case in ("limited", "stale"):
        with Session(test_engine) as setup:
            with setup.begin():
                balance = setup.get(
                    InventoryBalance,
                    scenario["warehouse_balance_id"],
                )

                if case == "limited":
                    # 40 on hand - 20 reserved = 20 transferable.
                    balance.on_hand_qty = Decimal("40")
                else:
                    balance.observed_at = (
                        AS_OF - timedelta(minutes=31)
                    )

    # Ensure the public service uses only opsflow_test.
    monkeypatch.setattr(service, "engine", test_engine)

    # Fixed clock keeps all test observations and deadlines deterministic.
    with patch.object(service, "datetime", wraps=datetime) as clock:
        clock.now.return_value = AS_OF

        result = service.recommend_warehouse_transfer(
            sku=scenario["sku"],
            plant_code=scenario["plant_code"],
            warehouse_code=scenario["warehouse_code"],
            lead_time=timedelta(
                hours=4 if case == "late" else 1
            ),
            fixed_transport_cost=Decimal("18000.00"),
            currency="LKR",
        )

    assert result["status"] == expected_status
    assert result["execution_status"] == "NOT_EXECUTED"

    if case == "stale":
        assert result["plan"] is None
        assert "WAREHOUSE_STALE" in {
            issue["code"] for issue in result["issues"]
        }
    else:
        plan = result["plan"]

        assert Decimal(plan["transfer_qty"]) == Decimal(
            expected_transfer
        )
        assert Decimal(plan["remaining_shortage_qty"]) == Decimal(
            expected_remaining
        )

        expected_cost = (
            Decimal("0")
            if case == "late"
            else Decimal("18000.00")
        )
        assert Decimal(plan["transport_cost"]) == expected_cost

    # Recommendations must not modify warehouse stock or reservations.
    with Session(test_engine) as verification:
        balance = verification.get(
            InventoryBalance,
            scenario["warehouse_balance_id"],
        )

        expected_on_hand = (
            Decimal("40") if case == "limited" else Decimal("100")
        )
        assert balance.on_hand_qty == expected_on_hand
        assert balance.reserved_qty == Decimal("20")