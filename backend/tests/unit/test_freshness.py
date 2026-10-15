from datetime import datetime, timedelta, timezone

import pytest

from app.services.freshness import assess_freshness


AS_OF = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "age_seconds, expected_fresh, expected_reason",
    [
        (0, True, "FRESH"),
        (600, True, "FRESH"),
        (1800, True, "FRESH"),
        (1801, False, "STALE"),
        (-30, True, "FRESH"),
        (-60, True, "FRESH"),
        (-61, False, "FUTURE_TIMESTAMP"),
    ],
)
def test_freshness_boundaries(
    age_seconds,
    expected_fresh,
    expected_reason,
):
    result = assess_freshness(
        observed_at=AS_OF - timedelta(seconds=age_seconds),
        as_of=AS_OF,
    )

    assert result.is_fresh is expected_fresh
    assert result.reason == expected_reason
    assert result.age == timedelta(seconds=age_seconds)


def test_custom_max_age():
    result = assess_freshness(
        observed_at=AS_OF - timedelta(minutes=45),
        as_of=AS_OF,
        max_age=timedelta(hours=1),
    )

    assert result.is_fresh is True


def test_different_timezones_represent_same_instant():
    sri_lanka = timezone(timedelta(hours=5, minutes=30))

    result = assess_freshness(
        observed_at=AS_OF.astimezone(sri_lanka),
        as_of=AS_OF,
    )

    assert result.is_fresh is True
    assert result.age == timedelta(0)


@pytest.mark.parametrize("field", ["observed_at", "as_of"])
def test_naive_timestamp_is_rejected(field):
    arguments = {
        "observed_at": AS_OF,
        "as_of": AS_OF,
    }
    arguments[field] = AS_OF.replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone"):
        assess_freshness(**arguments)


@pytest.mark.parametrize("field", ["max_age", "future_tolerance"])
def test_negative_policy_duration_is_rejected(field):
    arguments = {
        "observed_at": AS_OF,
        "as_of": AS_OF,
        field: timedelta(seconds=-1),
    }

    with pytest.raises(ValueError, match="negative"):
        assess_freshness(**arguments)