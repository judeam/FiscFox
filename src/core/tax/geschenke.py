"""Gift expense tracker (Geschenke).

Implements German gift deduction rules:
- 50 EUR net limit per recipient per year (§ 4 Abs. 5 Nr. 1 EStG)
- Cliff effect: exceeding limit makes entire amount non-deductible
- Optional 30% flat tax payment (§ 37b EStG)

Threshold raised from 35 EUR to 50 EUR by Wachstumschancengesetz 2024.

All monetary values use Decimal for precision.
"""
from dataclasses import dataclass
from decimal import Decimal

from src.core.models import (
    GIFT_LIMIT_PER_RECIPIENT,
    GiftExpense,
    GiftExpenseInput,
    GiftRecipientSummary,
)

# Flat tax rate for gifts (§ 37b EStG)
FLAT_TAX_RATE = Decimal("0.30")  # 30%


@dataclass
class GiftDeductibilityResult:
    """Result of gift deductibility check."""
    is_deductible: bool
    amount_net: Decimal
    cumulative_before: Decimal
    cumulative_after: Decimal
    remaining_allowance: Decimal
    flat_tax_amount: Decimal
    notes: list[str]


@dataclass
class RecipientLimitStatus:
    """Status of gift limit for a recipient."""
    recipient_name: str
    year: int
    total_gifts_net: Decimal
    limit: Decimal
    remaining: Decimal
    is_over_limit: bool
    warning_threshold: Decimal  # 80% of limit
    is_near_limit: bool


class GeschenkeCalculator:
    """Gift expense calculator for German tax law.

    Tracks per-recipient annual totals and enforces the 50 EUR cliff limit.

    Usage:
        calculator = GeschenkeCalculator()

        # Check if a new gift is deductible
        result = calculator.check_deductibility(
            recipient_name="Max Mustermann",
            amount_net=Decimal("30.00"),
            year=2026,
            existing_gifts=existing_gifts  # Previous gifts to this recipient
        )

        # Get recipient status
        status = calculator.get_recipient_status(
            recipient_name="Max Mustermann",
            year=2026,
            total_gifts_net=Decimal("40.00")
        )
    """

    def __init__(self, limit: Decimal = GIFT_LIMIT_PER_RECIPIENT):
        """Initialize calculator with gift limit.

        Args:
            limit: Annual per-recipient limit (default: 50 EUR)
        """
        self.limit = limit
        self.warning_threshold = (limit * Decimal("0.80")).quantize(Decimal("0.01"))

    def check_deductibility(
        self,
        recipient_name: str,
        amount_net: Decimal,
        year: int,
        cumulative_before: Decimal = Decimal("0"),
    ) -> GiftDeductibilityResult:
        """Check if a gift is deductible given the recipient's annual total.

        CRITICAL: The cliff effect means if cumulative exceeds 50 EUR,
        ALL gifts to that recipient become non-deductible for the year.

        Args:
            recipient_name: Name of gift recipient
            amount_net: Net value of new gift
            year: Tax year
            cumulative_before: Sum of previous gifts to this recipient this year

        Returns:
            GiftDeductibilityResult with deductibility status and notes
        """
        notes = []
        cumulative_after = (cumulative_before + amount_net).quantize(Decimal("0.01"))

        # Check if over limit
        is_deductible = cumulative_after <= self.limit

        # Calculate remaining allowance
        remaining = max(self.limit - cumulative_after, Decimal("0"))

        # Flat tax calculation (30% of net value)
        flat_tax = (amount_net * FLAT_TAX_RATE).quantize(Decimal("0.01"))

        # Generate notes
        if not is_deductible:
            notes.append(
                f"Geschenkegrenze ({self.limit} EUR) überschritten: "
                f"Gesamtwert {cumulative_after} EUR an {recipient_name} "
                "- nicht abzugsfähig (§ 4 Abs. 5 Nr. 1 EStG)"
            )
        elif cumulative_after >= self.warning_threshold:
            notes.append(
                f"Warnung: {remaining} EUR verbleibend für {recipient_name} "
                f"(Grenze: {self.limit} EUR)"
            )

        if is_deductible and remaining <= Decimal("10"):
            notes.append(
                f"Fast am Limit: Nur noch {remaining} EUR für {recipient_name} verfügbar"
            )

        return GiftDeductibilityResult(
            is_deductible=is_deductible,
            amount_net=amount_net,
            cumulative_before=cumulative_before,
            cumulative_after=cumulative_after,
            remaining_allowance=remaining,
            flat_tax_amount=flat_tax,
            notes=notes,
        )

    def get_recipient_status(
        self,
        recipient_name: str,
        year: int,
        total_gifts_net: Decimal,
    ) -> RecipientLimitStatus:
        """Get the limit status for a specific recipient.

        Args:
            recipient_name: Name of gift recipient
            year: Tax year
            total_gifts_net: Sum of all gifts to this recipient this year

        Returns:
            RecipientLimitStatus with limit tracking info
        """
        remaining = max(self.limit - total_gifts_net, Decimal("0"))
        is_over = total_gifts_net > self.limit
        is_near = total_gifts_net >= self.warning_threshold and not is_over

        return RecipientLimitStatus(
            recipient_name=recipient_name,
            year=year,
            total_gifts_net=total_gifts_net,
            limit=self.limit,
            remaining=remaining,
            is_over_limit=is_over,
            warning_threshold=self.warning_threshold,
            is_near_limit=is_near,
        )

    def calculate_flat_tax(self, amount_net: Decimal) -> Decimal:
        """Calculate 30% flat tax for recipient (§ 37b EStG).

        When the giver pays this flat tax, the gift becomes tax-free
        for the recipient.

        Args:
            amount_net: Net gift value

        Returns:
            Flat tax amount (30% of net value)
        """
        return (amount_net * FLAT_TAX_RATE).quantize(Decimal("0.01"))

    def create_gift_expense(
        self,
        gift_input: GiftExpenseInput,
        cumulative_before: Decimal = Decimal("0"),
    ) -> GiftExpense:
        """Create a GiftExpense with deductibility calculated.

        Args:
            gift_input: Input data from form
            cumulative_before: Previous gifts to this recipient this year

        Returns:
            GiftExpense with all fields populated
        """
        year = gift_input.date.year
        result = self.check_deductibility(
            recipient_name=gift_input.recipient_name,
            amount_net=gift_input.amount_net,
            year=year,
            cumulative_before=cumulative_before,
        )

        return GiftExpense(
            id=0,  # Will be assigned by DB
            date=gift_input.date,
            recipient_name=gift_input.recipient_name,
            recipient_company=gift_input.recipient_company,
            description=gift_input.description,
            amount_net=gift_input.amount_net,
            vat_rate=gift_input.vat_rate,
            flat_tax_paid=gift_input.flat_tax_paid,
            is_deductible=result.is_deductible,
            cumulative_year_total=result.cumulative_after,
        )

    def update_deductibility_retroactive(
        self,
        gifts: list[GiftExpense],
    ) -> list[GiftExpense]:
        """Recalculate deductibility for a list of gifts.

        Used when a new gift pushes the total over the limit,
        making all previous gifts to that recipient non-deductible.

        Args:
            gifts: List of gifts to same recipient in same year

        Returns:
            Updated list with is_deductible recalculated
        """
        if not gifts:
            return []

        # Sort by date to process in order
        sorted_gifts = sorted(gifts, key=lambda g: g.date)

        cumulative = Decimal("0")
        updated = []

        for gift in sorted_gifts:
            cumulative += gift.amount_net

            # If any gift pushes over limit, ALL become non-deductible
            is_deductible = cumulative <= self.limit

            # Create updated copy
            updated_gift = GiftExpense(
                id=gift.id,
                date=gift.date,
                recipient_name=gift.recipient_name,
                recipient_company=gift.recipient_company,
                description=gift.description,
                amount_net=gift.amount_net,
                vat_rate=gift.vat_rate,
                flat_tax_paid=gift.flat_tax_paid,
                is_deductible=is_deductible,
                cumulative_year_total=cumulative,
                expense_id=gift.expense_id,
            )
            updated.append(updated_gift)

        # If over limit, mark ALL as non-deductible (cliff effect)
        if cumulative > self.limit:
            for gift in updated:
                gift.is_deductible = False

        return updated

    def summarize_recipients(
        self,
        gifts: list[GiftExpense],
        year: int,
    ) -> list[GiftRecipientSummary]:
        """Summarize gifts by recipient for a given year.

        Args:
            gifts: All gifts in the year
            year: Tax year to filter

        Returns:
            List of per-recipient summaries sorted by total value
        """
        # Group by recipient
        by_recipient: dict[str, list[GiftExpense]] = {}
        for gift in gifts:
            if gift.date.year != year:
                continue
            key = gift.recipient_name.lower().strip()
            if key not in by_recipient:
                by_recipient[key] = []
            by_recipient[key].append(gift)

        summaries = []
        for recipient_key, recipient_gifts in by_recipient.items():
            # Use first gift's name for display (preserves case)
            display_name = recipient_gifts[0].recipient_name
            company = recipient_gifts[0].recipient_company

            total = sum(g.amount_net for g in recipient_gifts)
            is_over = total > self.limit
            remaining = max(self.limit - total, Decimal("0"))

            summaries.append(GiftRecipientSummary(
                recipient_name=display_name,
                recipient_company=company,
                year=year,
                gift_count=len(recipient_gifts),
                total_net=total,
                is_over_limit=is_over,
                remaining_allowance=remaining,
            ))

        # Sort by total value descending
        return sorted(summaries, key=lambda s: s.total_net, reverse=True)

    def get_at_risk_recipients(
        self,
        summaries: list[GiftRecipientSummary],
    ) -> list[GiftRecipientSummary]:
        """Filter recipients who are over limit or near limit.

        Args:
            summaries: Recipient summaries from summarize_recipients

        Returns:
            List of recipients at risk (>80% of limit)
        """
        return [
            s for s in summaries
            if s.is_over_limit or s.total_net >= self.warning_threshold
        ]


# Module-level calculator instance
geschenke_calculator = GeschenkeCalculator()
