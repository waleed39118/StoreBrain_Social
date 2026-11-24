"""Dose *verification* helpers.

SAFETY: Atheer ships no drug data. Dose limits come from the clinic's approved
formulary (``DoseRule``). Every result carries ``requires_clinician_review=True``:
these functions flag discrepancies for a clinician; they never prescribe.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from atheer.calculations._num import Number, dec, in_range, round_to

WEIGHT_KG = (Decimal("0.3"), Decimal("500"))
HEIGHT_CM = (Decimal("20"), Decimal("280"))


class DoseRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_name: str
    min_mg_per_kg: Decimal
    max_mg_per_kg: Decimal
    max_single_dose_mg: Decimal | None = None
    max_daily_dose_mg: Decimal | None = None

    @model_validator(mode="after")
    def _check(self) -> DoseRule:
        if self.min_mg_per_kg < 0 or self.min_mg_per_kg > self.max_mg_per_kg:
            raise ValueError("Require 0 <= min_mg_per_kg <= max_mg_per_kg")
        return self


class DoseStatus(str, enum.Enum):
    WITHIN_RANGE = "within_range"
    BELOW_RANGE = "below_range"
    ABOVE_RANGE = "above_range"
    EXCEEDS_SINGLE_MAX = "exceeds_single_max"
    EXCEEDS_DAILY_MAX = "exceeds_daily_max"


class DoseVerification(BaseModel):
    drug_name: str
    status: DoseStatus
    prescribed_mg: Decimal
    recommended_min_mg: Decimal
    recommended_max_mg: Decimal
    daily_total_mg: Decimal
    findings: list[str]
    requires_clinician_review: Literal[True] = True


def weight_based_range(weight_kg: Number, rule: DoseRule) -> tuple[Decimal, Decimal]:
    w = in_range(dec(weight_kg, "weight_kg"), *WEIGHT_KG, "weight_kg")
    low, high = w * rule.min_mg_per_kg, w * rule.max_mg_per_kg
    if rule.max_single_dose_mg is not None:
        low, high = min(low, rule.max_single_dose_mg), min(high, rule.max_single_dose_mg)
    return round_to(low), round_to(high)


def verify_dose(prescribed_mg: Number, weight_kg: Number, rule: DoseRule, doses_per_day: int = 1) -> DoseVerification:
    if doses_per_day < 1 or doses_per_day > 24:
        raise ValueError("doses_per_day must be between 1 and 24")
    dose = dec(prescribed_mg, "prescribed_mg")
    if dose <= 0:
        raise ValueError("prescribed_mg must be positive")
    low, high = weight_based_range(weight_kg, rule)
    daily = dose * doses_per_day

    # Ordered by severity; the first matching status wins, all findings are reported.
    checks: list[tuple[bool, DoseStatus, str]] = [
        (
            rule.max_daily_dose_mg is not None and daily > rule.max_daily_dose_mg,
            DoseStatus.EXCEEDS_DAILY_MAX,
            f"Daily total {daily} mg exceeds formulary max {rule.max_daily_dose_mg} mg.",
        ),
        (
            rule.max_single_dose_mg is not None and dose > rule.max_single_dose_mg,
            DoseStatus.EXCEEDS_SINGLE_MAX,
            f"Single dose {dose} mg exceeds formulary max {rule.max_single_dose_mg} mg.",
        ),
        (dose > high, DoseStatus.ABOVE_RANGE, f"Dose above weight-based range ({low}–{high} mg)."),
        (dose < low, DoseStatus.BELOW_RANGE, f"Dose below weight-based range ({low}–{high} mg)."),
    ]
    hits = [(status, msg) for cond, status, msg in checks if cond]
    return DoseVerification(
        drug_name=rule.drug_name,
        status=hits[0][0] if hits else DoseStatus.WITHIN_RANGE,
        prescribed_mg=dose,
        recommended_min_mg=low,
        recommended_max_mg=high,
        daily_total_mg=daily,
        findings=[msg for _, msg in hits],
    )


def bsa_mosteller(height_cm: Number, weight_kg: Number) -> Decimal:
    """Body surface area (m²) = sqrt(height_cm × weight_kg / 3600)."""
    h = in_range(dec(height_cm, "height_cm"), *HEIGHT_CM, "height_cm")
    w = in_range(dec(weight_kg, "weight_kg"), *WEIGHT_KG, "weight_kg")
    return round_to((h * w / Decimal(3600)).sqrt())


def creatinine_clearance_cg(
    age_years: int, weight_kg: Number, serum_creatinine_mg_dl: Number, sex: Literal["male", "female"]
) -> Decimal:
    """Cockcroft–Gault CrCl (mL/min). Validated for adults only, so age < 18 is rejected."""
    if not 18 <= age_years <= 120:
        raise ValueError("Cockcroft–Gault is only validated for adults (18–120 years)")
    w = in_range(dec(weight_kg, "weight_kg"), *WEIGHT_KG, "weight_kg")
    scr = in_range(dec(serum_creatinine_mg_dl, "serum_creatinine"), Decimal("0.1"), Decimal("20"), "serum_creatinine")
    crcl = (Decimal(140 - age_years) * w) / (Decimal(72) * scr)
    if sex == "female":
        crcl *= Decimal("0.85")
    return round_to(crcl, Decimal("0.1"))


def volume_ml(dose_mg: Number, concentration_mg_per_ml: Number) -> Decimal:
    conc = dec(concentration_mg_per_ml, "concentration_mg_per_ml")
    if conc <= 0:
        raise ValueError("concentration must be positive")
    return round_to(dec(dose_mg, "dose_mg") / conc)
