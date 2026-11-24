from __future__ import annotations

from decimal import Decimal

import pytest

from atheer.calculations import (
    CoverageTerms,
    DoseRule,
    DoseStatus,
    analyze_stock,
    bsa_mosteller,
    creatinine_clearance_cg,
    estimate_wait,
    patient_cost,
    verify_dose,
    volume_ml,
)

# Illustrative rule only. Real limits must come from the clinic's formulary.
RULE = DoseRule(
    drug_name="TestDrug",
    min_mg_per_kg=Decimal(10),
    max_mg_per_kg=Decimal(15),
    max_single_dose_mg=Decimal(1000),
    max_daily_dose_mg=Decimal(4000),
)


@pytest.mark.parametrize(
    ("dose", "weight", "per_day", "status"),
    [
        (250, 20, 1, DoseStatus.WITHIN_RANGE),
        (150, 20, 1, DoseStatus.BELOW_RANGE),
        (400, 20, 1, DoseStatus.ABOVE_RANGE),
        (1200, 100, 1, DoseStatus.EXCEEDS_SINGLE_MAX),
        (1000, 100, 5, DoseStatus.EXCEEDS_DAILY_MAX),
    ],
)
def test_verify_dose(dose, weight, per_day, status):
    result = verify_dose(dose, weight, RULE, doses_per_day=per_day)
    assert result.status is status
    assert result.requires_clinician_review is True
    assert bool(result.findings) is (status is not DoseStatus.WITHIN_RANGE)


def test_dose_range_capped_by_single_max():
    assert verify_dose(1000, 100, RULE).recommended_max_mg == Decimal("1000.00")


def test_dose_input_validation():
    with pytest.raises(ValueError):
        verify_dose(100, 0, RULE)
    with pytest.raises(ValueError):
        verify_dose(-5, 20, RULE)
    with pytest.raises(ValueError):
        DoseRule(drug_name="x", min_mg_per_kg=Decimal(5), max_mg_per_kg=Decimal(1))


def test_clinical_formulas():
    assert bsa_mosteller(180, 80) == Decimal("2.00")
    assert creatinine_clearance_cg(60, 72, 1, "male") == Decimal("80.0")
    assert creatinine_clearance_cg(60, 72, 1, "female") == Decimal("68.0")
    with pytest.raises(ValueError):
        creatinine_clearance_cg(10, 30, 0.5, "male")  # paediatric: formula not validated
    assert volume_ml(250, 50) == Decimal("5.00")


def test_billing_copay_deductible_coinsurance():
    terms = CoverageTerms(
        copay=Decimal(20), deductible_remaining=Decimal(100), coinsurance_rate=Decimal("0.2")
    )
    r = patient_cost([300, "200.00"], terms)
    # 500 total: 20 copay, 100 deductible, 20% of 380 = 76 → 196
    assert (r.copay, r.deductible, r.coinsurance, r.patient_pays, r.insurer_pays) == (
        Decimal("20.00"), Decimal("100.00"), Decimal("76.00"), Decimal("196.00"), Decimal("304.00")
    )


def test_billing_oop_cap_vat_and_self_pay():
    capped = patient_cost(1000, CoverageTerms(coinsurance_rate=Decimal("0.5"), out_of_pocket_remaining=Decimal(100)))
    assert capped.oop_cap_applied and capped.patient_pays == Decimal("100.00")
    vat = patient_cost(100, CoverageTerms(coinsurance_rate=Decimal(1), vat_rate=Decimal("0.15")))
    assert vat.vat == Decimal("15.00") and vat.patient_pays == Decimal("115.00")
    assert patient_cost(0.1 + 0.2).total_charges == Decimal("0.30")


def test_wait_estimate():
    est = estimate_wait(4, [10, 12, 8, 10, 14, 9], doctors_on_duty=2, current_elapsed_minutes=4)
    assert est.expected_minutes == 26  # (10 - 4) + 2 rounds × 10
    assert est.optimistic_minutes <= est.expected_minutes <= est.pessimistic_minutes
    assert estimate_wait(0, []).expected_minutes == 15  # fallback


def test_stock_analysis():
    usage = [10, 12, 8, 11, 9, 10, 10]
    low = analyze_stock(40, usage, lead_time_days=5)
    assert low.should_reorder and low.reorder_point >= 50 and low.suggested_order_qty > 0
    ok = analyze_stock(500, usage, lead_time_days=5)
    assert not ok.should_reorder and ok.days_of_cover == 50.0
