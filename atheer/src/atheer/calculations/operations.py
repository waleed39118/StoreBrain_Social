"""Operational estimates: waiting time and medical-supply stock levels."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from pydantic import BaseModel

MIN_SAMPLES = 5


class WaitEstimate(BaseModel):
    expected_minutes: int
    optimistic_minutes: int
    pessimistic_minutes: int
    sample_size: int


def estimate_wait(
    patients_ahead: int,
    recent_consult_minutes: Sequence[float],
    *,
    doctors_on_duty: int = 1,
    current_elapsed_minutes: float = 0.0,
    fallback_minutes: float = 15.0,
) -> WaitEstimate:
    """Assumes every on-duty doctor is busy; patients ahead are served in parallel rounds.

    wait ≈ remaining(current consult) + (patients_ahead // doctors) × typical consult.
    Median is used (robust to outliers); p25/p80 give the range.
    """
    if patients_ahead < 0 or doctors_on_duty < 1:
        raise ValueError("patients_ahead must be >= 0 and doctors_on_duty >= 1")
    samples = [m for m in recent_consult_minutes if m > 0]
    if len(samples) >= MIN_SAMPLES:
        q = statistics.quantiles(samples, n=20)  # 5% steps: q[4]=p25, q[15]=p80
        low, mid, high = q[4], statistics.median(samples), q[15]
    else:
        low, mid, high = fallback_minutes * 0.75, fallback_minutes, fallback_minutes * 1.5

    rounds = patients_ahead // doctors_on_duty

    def total(per: float) -> int:
        return max(0, math.ceil(max(0.0, per - current_elapsed_minutes) + rounds * per))

    return WaitEstimate(
        expected_minutes=total(mid),
        optimistic_minutes=total(low),
        pessimistic_minutes=total(high),
        sample_size=len(samples),
    )


class StockAnalysis(BaseModel):
    average_daily_usage: float
    safety_stock: int
    reorder_point: int
    days_of_cover: float | None
    should_reorder: bool
    suggested_order_qty: int


def analyze_stock(
    on_hand: int,
    daily_usage: Sequence[int],
    lead_time_days: int,
    *,
    on_order: int = 0,
    service_level: float = 0.95,
    review_period_days: int = 7,
) -> StockAnalysis:
    """Reorder-point model: ROP = d̄·L + z·σ·√L; order up to d̄·(L+R) + z·σ·√(L+R)."""
    if on_hand < 0 or on_order < 0 or lead_time_days < 0 or review_period_days < 1:
        raise ValueError("quantities and periods must be non-negative (review period >= 1)")
    if not 0.5 <= service_level < 1:
        raise ValueError("service_level must be in [0.5, 1)")
    if not daily_usage:
        raise ValueError("daily_usage history is required")

    avg = statistics.fmean(daily_usage)
    sigma = statistics.stdev(daily_usage) if len(daily_usage) > 1 else 0.0
    z = statistics.NormalDist().inv_cdf(service_level)

    safety = z * sigma * math.sqrt(lead_time_days)
    rop = avg * lead_time_days + safety
    horizon = lead_time_days + review_period_days
    order_up_to = avg * horizon + z * sigma * math.sqrt(horizon)

    position = on_hand + on_order
    reorder = position <= rop
    return StockAnalysis(
        average_daily_usage=round(avg, 2),
        safety_stock=math.ceil(safety),
        reorder_point=math.ceil(rop),
        days_of_cover=round(on_hand / avg, 1) if avg > 0 else None,
        should_reorder=reorder,
        suggested_order_qty=max(0, math.ceil(order_up_to - position)) if reorder else 0,
    )
