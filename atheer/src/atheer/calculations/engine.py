"""CalcEngine: one entry point for every calculation, plus the clinic formulary.

The formulary (dose limits per drug) is data owned by the clinic. It is loaded
from a JSON file and can be replaced at runtime by a signed content release
without restarting; the swap is a single reference assignment, so concurrent
readers always see a complete formulary.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Literal

from atheer.calculations import billing, dosage, operations
from atheer.calculations._num import Number

logger = logging.getLogger(__name__)


class UnknownDrugError(LookupError):
    pass


class CalcEngine:
    def __init__(self, rules: Iterable[dosage.DoseRule] = ()) -> None:
        self._formulary: Mapping[str, dosage.DoseRule] = {}
        self.replace_formulary(rules)

    # ------------------------------------------------------------- formulary

    def replace_formulary(self, rules: Iterable[dosage.DoseRule]) -> int:
        table = {_key(r.drug_name): r for r in rules}
        self._formulary = table  # atomic swap
        return len(table)

    def load_formulary(self, path: Path) -> int:
        """Load ``[{"drug_name": ..., "min_mg_per_kg": ..., ...}, ...]``. Invalid files leave the current formulary."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("formulary.json must contain a JSON list of dose rules")
        rules = [dosage.DoseRule.model_validate(item) for item in raw]  # validate everything before swapping
        count = self.replace_formulary(rules)
        logger.info("Formulary loaded: %d drugs from %s", count, path)
        return count

    @property
    def drugs(self) -> list[str]:
        return sorted(r.drug_name for r in self._formulary.values())

    def rule(self, drug_name: str) -> dosage.DoseRule:
        try:
            return self._formulary[_key(drug_name)]
        except KeyError:
            raise UnknownDrugError(f"'{drug_name}' is not in the clinic formulary.") from None

    # ------------------------------------------------------------- dosage

    def verify_dose(
        self, drug_name: str, prescribed_mg: Number, weight_kg: Number, doses_per_day: int = 1
    ) -> dosage.DoseVerification:
        return dosage.verify_dose(prescribed_mg, weight_kg, self.rule(drug_name), doses_per_day)

    def dose_range(self, drug_name: str, weight_kg: Number) -> tuple[Decimal, Decimal]:
        return dosage.weight_based_range(weight_kg, self.rule(drug_name))

    @staticmethod
    def bsa(height_cm: Number, weight_kg: Number):
        return dosage.bsa_mosteller(height_cm, weight_kg)

    @staticmethod
    def creatinine_clearance(age_years: int, weight_kg: Number, serum_creatinine_mg_dl: Number,
                             sex: Literal["male", "female"]):
        return dosage.creatinine_clearance_cg(age_years, weight_kg, serum_creatinine_mg_dl, sex)

    @staticmethod
    def volume_ml(dose_mg: Number, concentration_mg_per_ml: Number):
        return dosage.volume_ml(dose_mg, concentration_mg_per_ml)

    # ------------------------------------------------------------- billing / operations

    @staticmethod
    def patient_cost(charges: Sequence[Number] | Number, terms: billing.CoverageTerms | None = None):
        return billing.patient_cost(charges, terms)

    @staticmethod
    def wait_time(patients_ahead: int, recent_consult_minutes: Sequence[float], **kwargs) -> operations.WaitEstimate:
        return operations.estimate_wait(patients_ahead, recent_consult_minutes, **kwargs)

    @staticmethod
    def stock(on_hand: int, daily_usage: Sequence[int], lead_time_days: int, **kwargs) -> operations.StockAnalysis:
        return operations.analyze_stock(on_hand, daily_usage, lead_time_days, **kwargs)


def _key(name: str) -> str:
    return " ".join(name.casefold().split())
