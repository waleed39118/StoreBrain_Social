"""Patient/insurer cost split.

Model (configurable per plan): flat copay first, then remaining deductible,
then coinsurance on the rest; patient share capped by remaining out-of-pocket
max. VAT, if any, is applied to the patient share only when ``vat_rate`` > 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, Field

from atheer.calculations._num import Number, dec, round_to


class CoverageTerms(BaseModel):
    copay: Decimal = Field(default=Decimal(0), ge=0)
    deductible_remaining: Decimal = Field(default=Decimal(0), ge=0)
    coinsurance_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)
    out_of_pocket_remaining: Decimal | None = Field(default=None, ge=0)
    vat_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)


class CostBreakdown(BaseModel):
    total_charges: Decimal
    copay: Decimal
    deductible: Decimal
    coinsurance: Decimal
    oop_cap_applied: bool
    vat: Decimal
    patient_pays: Decimal
    insurer_pays: Decimal


def patient_cost(charges: Sequence[Number] | Number, terms: CoverageTerms | None = None) -> CostBreakdown:
    terms = terms or CoverageTerms(coinsurance_rate=Decimal(1))  # self-pay by default
    items = charges if isinstance(charges, Sequence) and not isinstance(charges, str) else [charges]
    amounts = [dec(c, "charge") for c in items]
    if any(a < 0 for a in amounts):
        raise ValueError("charges must be non-negative")
    total = sum(amounts, Decimal(0))

    copay = min(terms.copay, total)
    remaining = total - copay
    deductible = min(terms.deductible_remaining, remaining)
    coinsurance = (remaining - deductible) * terms.coinsurance_rate
    share = copay + deductible + coinsurance

    capped = terms.out_of_pocket_remaining is not None and share > terms.out_of_pocket_remaining
    if capped:
        share = terms.out_of_pocket_remaining  # type: ignore[assignment]

    share = round_to(share)
    vat = round_to(share * terms.vat_rate)
    return CostBreakdown(
        total_charges=round_to(total),
        copay=round_to(copay),
        deductible=round_to(deductible),
        coinsurance=round_to(coinsurance),
        oop_cap_applied=capped,
        vat=vat,
        patient_pays=share + vat,
        insurer_pays=round_to(total) - share,
    )
