from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class FreshnessResult:
    is_fresh: bool
    age: timedelta
    reason: str


def assess_freshness(
    *,
    observed_at: datetime,
    as_of: datetime,
    max_age: timedelta = timedelta(minutes=30),
    future_tolerance: timedelta = timedelta(minutes=1),
) -> FreshnessResult:
    for name, value in (
        ("observed_at", observed_at),
        ("as_of", as_of),
    ):
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime.")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone.")

    for name, value in (
        ("max_age", max_age),
        ("future_tolerance", future_tolerance),
    ):
        if not isinstance(value, timedelta):
            raise TypeError(f"{name} must be a timedelta.")

        if value < timedelta(0):
            raise ValueError(f"{name} cannot be negative.")

    age = (
        as_of.astimezone(timezone.utc)
        - observed_at.astimezone(timezone.utc)
    )

    if age < -future_tolerance:
        return FreshnessResult(
            is_fresh=False,
            age=age,
            reason="FUTURE_TIMESTAMP",
        )

    if age > max_age:
        return FreshnessResult(
            is_fresh=False,
            age=age,
            reason="STALE",
        )

    return FreshnessResult(
        is_fresh=True,
        age=age,
        reason="FRESH",
    )