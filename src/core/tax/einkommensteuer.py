"""German Income Tax Calculator (Einkommensteuer) per § 32a EStG.

Implements the progressive tax formula for German income tax.
All monetary values use Decimal for precision.

Tax Zones (2026):
    Zone 0: 0 - 12,348 EUR           → 0%
    Zone 1: 12,349 - 17,443 EUR      → 14% - 24% (progressive)
    Zone 2: 17,444 - 68,480 EUR      → 24% - 42% (progressive)
    Zone 3: 68,481 - 277,825 EUR     → 42% (flat)
    Zone 4: > 277,826 EUR            → 45% (Reichensteuer)

The formulas in Zone 1 and 2 are defined by law and use specific
mathematical progressions to ensure smooth transitions between zones.
"""

from decimal import ROUND_DOWN, Decimal

from src.core.models import (
    EinkommensteuerResult,
    TaxYearConfig,
    get_tax_config,
)


class EinkommensteuerCalculator:
    """Calculator for German income tax (§ 32a EStG).

    Usage:
        calc = EinkommensteuerCalculator(2026)
        result = calc.calculate(Decimal("50000"))
        print(f"Tax: {result.einkommensteuer} EUR")
        print(f"Effective rate: {result.effective_rate}%")
    """

    def __init__(self, year: int):
        """Initialize calculator with tax year configuration.

        Args:
            year: Tax year (must be in TAX_CONFIGS)

        Raises:
            ValueError: If year is not supported
        """
        self.config: TaxYearConfig = get_tax_config(year)
        self.year = year

    def calculate(self, zu_versteuerndes_einkommen: Decimal) -> EinkommensteuerResult:
        """Calculate income tax for given taxable income.

        Implements § 32a Abs. 1 EStG formula with all zones.

        Args:
            zu_versteuerndes_einkommen: Taxable income (after deductions)

        Returns:
            EinkommensteuerResult with tax breakdown
        """
        zve = zu_versteuerndes_einkommen.quantize(Decimal("1"), rounding=ROUND_DOWN)

        zve = max(zve, Decimal("0"))

        # Calculate base income tax
        einkommensteuer = self._calculate_tax(zve)

        # Calculate Solidaritätszuschlag
        soli = self._calculate_soli(einkommensteuer)

        # Calculate total and rates
        total_tax = einkommensteuer + soli
        effective_rate = (
            (total_tax / zve * 100).quantize(Decimal("0.01"))
            if zve > 0 else Decimal("0")
        )
        marginal_rate = self._get_marginal_rate(zve)

        return EinkommensteuerResult(
            year=self.year,
            zu_versteuerndes_einkommen=zve,
            einkommensteuer=einkommensteuer,
            solidaritaetszuschlag=soli,
            total_tax=total_tax,
            effective_rate=effective_rate,
            marginal_rate=marginal_rate,
        )

    def _calculate_tax(self, zve: Decimal) -> Decimal:
        """Apply § 32a EStG tax formula.

        The law defines specific formulas for each zone using helper
        variables y and z to calculate the progressive portion.

        Args:
            zve: zu versteuerndes Einkommen (taxable income)

        Returns:
            Income tax amount (Einkommensteuer)
        """
        cfg = self.config

        # Zone 0: Grundfreibetrag (0%)
        # § 32a Abs. 1 Nr. 1 EStG
        if zve <= cfg.grundfreibetrag:
            return Decimal("0")

        # Zone 1: First progressive zone (14% → 24%)
        # § 32a Abs. 1 Nr. 2 EStG
        # Formula: (979.18 * y + 1400) * y
        # where y = (zvE - Grundfreibetrag) / 10000
        if zve <= cfg.zone1_end:
            y = (zve - cfg.grundfreibetrag) / Decimal("10000")
            tax = (Decimal("979.18") * y + Decimal("1400")) * y
            return tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

        # Zone 2: Second progressive zone (24% → 42%)
        # § 32a Abs. 1 Nr. 3 EStG
        # Formula: (206.43 * z + 2397) * z + zone1_tax
        # where z = (zvE - zone1_end) / 10000
        if zve <= cfg.zone2_end:
            # First calculate Zone 1 tax (at zone1_end)
            y = (cfg.zone1_end - cfg.grundfreibetrag) / Decimal("10000")
            zone1_tax = (Decimal("979.18") * y + Decimal("1400")) * y

            # Then add Zone 2 progressive
            z = (zve - cfg.zone1_end) / Decimal("10000")
            zone2_tax = (Decimal("206.43") * z + Decimal("2397")) * z

            tax = zone1_tax + zone2_tax
            return tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

        # Zone 3: 42% flat rate
        # § 32a Abs. 1 Nr. 4 EStG
        if zve <= cfg.spitzensteuersatz_start:
            # Calculate tax up to zone2_end
            y = (cfg.zone1_end - cfg.grundfreibetrag) / Decimal("10000")
            zone1_tax = (Decimal("979.18") * y + Decimal("1400")) * y

            z = (cfg.zone2_end - cfg.zone1_end) / Decimal("10000")
            zone2_tax = (Decimal("206.43") * z + Decimal("2397")) * z

            # Add 42% on amount above zone2_end
            zone3_tax = (zve - cfg.zone2_end) * Decimal("0.42")

            tax = zone1_tax + zone2_tax + zone3_tax
            return tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

        # Zone 4: 45% Reichensteuer
        # § 32a Abs. 1 Nr. 5 EStG
        # Calculate tax up to spitzensteuersatz_start
        y = (cfg.zone1_end - cfg.grundfreibetrag) / Decimal("10000")
        zone1_tax = (Decimal("979.18") * y + Decimal("1400")) * y

        z = (cfg.zone2_end - cfg.zone1_end) / Decimal("10000")
        zone2_tax = (Decimal("206.43") * z + Decimal("2397")) * z

        zone3_tax = (cfg.spitzensteuersatz_start - cfg.zone2_end) * Decimal("0.42")

        # Add 45% on amount above spitzensteuersatz_start
        zone4_tax = (zve - cfg.spitzensteuersatz_start) * Decimal("0.45")

        tax = zone1_tax + zone2_tax + zone3_tax + zone4_tax
        return tax.quantize(Decimal("1"), rounding=ROUND_DOWN)

    def _calculate_soli(self, einkommensteuer: Decimal) -> Decimal:
        """Calculate Solidaritätszuschlag (5.5% of income tax).

        Only applies if income tax exceeds threshold.
        § 3 SolzG - Solidaritätszuschlaggesetz

        Since 2021, most taxpayers are exempt due to the high threshold.
        The soli is gradually phased in above the threshold.

        Args:
            einkommensteuer: Calculated income tax

        Returns:
            Solidaritätszuschlag amount (may be 0)
        """
        # Full exemption below threshold
        if einkommensteuer <= self.config.soli_threshold:
            return Decimal("0")

        # Gleitzone (transition zone) - gradual phase-in
        # The soli is limited to 11.9% of the amount exceeding the threshold
        # to avoid a hard jump at the threshold
        gleitzone_end = self.config.soli_threshold * Decimal("1.2")  # ~20% above threshold

        if einkommensteuer <= gleitzone_end:
            # Gradual increase: soli capped at 11.9% of excess
            excess = einkommensteuer - self.config.soli_threshold
            limited_soli = excess * Decimal("0.119")
            full_soli = einkommensteuer * Decimal("0.055")
            soli = min(limited_soli, full_soli)
        else:
            # Full 5.5% above Gleitzone
            soli = einkommensteuer * Decimal("0.055")

        return soli.quantize(Decimal("0.01"))

    def _get_marginal_rate(self, zve: Decimal) -> Decimal:
        """Get marginal tax rate for income level.

        Args:
            zve: Taxable income

        Returns:
            Marginal rate as percentage (e.g., 42.00)
        """
        cfg = self.config

        if zve <= cfg.grundfreibetrag:
            return Decimal("0")
        elif zve <= cfg.zone1_end:
            # Progressive: 14% to 24%
            # Derivative of Zone 1 formula
            y = (zve - cfg.grundfreibetrag) / Decimal("10000")
            marginal = (Decimal("2") * Decimal("979.18") * y + Decimal("1400")) / Decimal("100")
            return marginal.quantize(Decimal("0.01"))
        elif zve <= cfg.zone2_end:
            # Progressive: 24% to 42%
            z = (zve - cfg.zone1_end) / Decimal("10000")
            marginal = (Decimal("2") * Decimal("206.43") * z + Decimal("2397")) / Decimal("100")
            return marginal.quantize(Decimal("0.01"))
        elif zve <= cfg.spitzensteuersatz_start:
            return Decimal("42.00")
        else:
            return Decimal("45.00")

    def calculate_quarterly_payment(self, annual_estimate: Decimal) -> Decimal:
        """Calculate quarterly Vorauszahlung amount.

        § 37 EStG - Quarterly prepayments due on:
        10. März, 10. Juni, 10. September, 10. Dezember

        Args:
            annual_estimate: Estimated annual tax liability

        Returns:
            Quarterly payment amount (1/4 of annual)
        """
        quarterly = (annual_estimate / 4).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return quarterly


def calculate_einkommensteuer(
    zu_versteuerndes_einkommen: Decimal,
    year: int = 2026
) -> EinkommensteuerResult:
    """Convenience function for quick tax calculation.

    Args:
        zu_versteuerndes_einkommen: Taxable income
        year: Tax year (default: 2026)

    Returns:
        EinkommensteuerResult with full breakdown
    """
    calc = EinkommensteuerCalculator(year)
    return calc.calculate(zu_versteuerndes_einkommen)
