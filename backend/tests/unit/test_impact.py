from decimal import Decimal

import pytest

from app.services.impact import calculate_shortage


@pytest.mark.parametrize(
    "required, fulfilled, on_hand, reserved, remaining, available, shortage",
    [
        ("500", "0", "120", "0", "500", "120", "380"),
        ("500", "0", "600", "0", "500", "600", "0"),
        ("500", "0", "500", "0", "500", "500", "0"),
        ("500", "200", "120", "0", "300", "120", "180"),
        ("500", "0", "400", "20", "500", "380", "120"),
        ("500", "500", "0", "0", "0", "0", "0"),
        ("10.500", "0", "4.250", "0", "10.500", "4.250", "6.250"),
    ],
)
def test_calculate_shortage(
    required,
    fulfilled,
    on_hand,
    reserved,
    remaining,
    available,
    shortage,
):
    result = calculate_shortage(
        required_qty=Decimal(required),
        fulfilled_qty=Decimal(fulfilled),
        on_hand_qty=Decimal(on_hand),
        reserved_qty=Decimal(reserved),
    )

    assert result.remaining_demand == Decimal(remaining)
    assert result.available_stock == Decimal(available)
    assert result.shortage_qty == Decimal(shortage)


@pytest.mark.parametrize(
    "field, value",
    [
        ("required_qty", Decimal("0")),
        ("required_qty", Decimal("-1")),
        ("fulfilled_qty", Decimal("-1")),
        ("fulfilled_qty", Decimal("501")),
        ("on_hand_qty", Decimal("-1")),
        ("reserved_qty", Decimal("-1")),
        ("reserved_qty", Decimal("121")),
        ("on_hand_qty", Decimal("NaN")),
        ("on_hand_qty", Decimal("Infinity")),
    ],
)
def test_rejects_invalid_quantities(field, value):
    inputs = {
        "required_qty": Decimal("500"),
        "fulfilled_qty": Decimal("0"),
        "on_hand_qty": Decimal("120"),
        "reserved_qty": Decimal("0"),
    }
    inputs[field] = value

    with pytest.raises(ValueError):
        calculate_shortage(**inputs)


def test_rejects_float_input():
    with pytest.raises(TypeError):
        calculate_shortage(
            required_qty=500.0,
            fulfilled_qty=Decimal("0"),
            on_hand_qty=Decimal("120"),
            reserved_qty=Decimal("0"),
        )