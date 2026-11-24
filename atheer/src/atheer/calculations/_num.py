"""Exact-decimal helpers. Floats are converted via ``str`` to avoid binary artefacts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Number = int | float | str | Decimal

CENT = Decimal("0.01")


def dec(value: Number, name: str = "value") -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric, not bool")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is not a valid number: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def in_range(value: Decimal, low: Decimal, high: Decimal, name: str) -> Decimal:
    if not (low <= value <= high):
        raise ValueError(f"{name}={value} is outside the plausible range [{low}, {high}]")
    return value


def round_to(value: Decimal, quantum: Decimal = CENT) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)
