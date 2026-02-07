"""German tax calculation engine.

This module contains pure Python implementations of German tax calculations.
No framework dependencies (FastAPI, Jinja2, etc.) allowed here.

Modules:
    einkommensteuer: Income tax (§ 32a EStG)
    umsatzsteuer: VAT/Sales tax (§ 12, 13b, 19 UStG)
    deadlines: Tax filing deadlines and payment schedules
    health_insurance: Health insurance deductions (§ 10 EStG)

All calculations use Decimal for precision. No float arithmetic.
"""

from src.core.tax.deadlines import DeadlineCalculator
from src.core.tax.einkommensteuer import EinkommensteuerCalculator
from src.core.tax.health_insurance import HealthInsuranceCalculator
from src.core.tax.umsatzsteuer import UmsatzsteuerCalculator

__all__ = [
    "EinkommensteuerCalculator",
    "UmsatzsteuerCalculator",
    "DeadlineCalculator",
    "HealthInsuranceCalculator",
]
