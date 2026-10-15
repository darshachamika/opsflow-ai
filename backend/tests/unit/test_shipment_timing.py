from datetime import datetime, timedelta, timezone

import pytest

from app.services.impact import assess_shipment_timing


@pytest.mark.parametrize(
    "eta_hours, expected_on_time, expected_late_hours",
    [
        (4, True, 0),
        (8, True, 0),
        (72, False, 64),
    ],
)
def test_shipment_timing(
    eta_hours,
    expected_on_time,
    expected_late_hours,
):
    start = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

    result = assess_shipment_timing(
        current_eta=start + timedelta(hours=eta_hours),
        required_at=start + timedelta(hours=8),
    )

    assert result.arrives_by_deadline is expected_on_time
    assert result.lateness == timedelta(hours=expected_late_hours)


def test_compares_different_timezones_correctly():
    sri_lanka = timezone(timedelta(hours=5, minutes=30))

    result = assess_shipment_timing(
        current_eta=datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc),
        required_at=datetime(2026, 10, 15, 22, 30, tzinfo=sri_lanka),
    )

    assert result.arrives_by_deadline is True
    assert result.lateness == timedelta(0)


@pytest.mark.parametrize("field", ["current_eta", "required_at"])
def test_rejects_datetime_without_timezone(field):
    inputs = {
        "current_eta": datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc),
        "required_at": datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc),
    }
    inputs[field] = inputs[field].replace(tzinfo=None)

    with pytest.raises(ValueError):
        assess_shipment_timing(**inputs)