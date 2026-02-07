"""Domain models with strict financial typing.

All monetary values use Decimal for precision.
No float arithmetic allowed for financial calculations.

Tax parameters based on German tax law (EStG, UStG).
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel, Field, computed_field, field_validator

from src.core.exceptions import InvalidTaxYearError

# =============================================================================
# Tax Year Configuration (§ 32a EStG)
# =============================================================================

class TaxYearConfig(BaseModel):
    """Configuration for § 32a EStG income tax parameters by year.

    German income tax uses progressive zones with varying formulas:
    - Zone 0: Up to Grundfreibetrag (0%)
    - Zone 1: Progressive 14% → 24%
    - Zone 2: Progressive 24% → 42%
    - Zone 3: Flat 42%
    - Zone 4: Flat 45% (Reichensteuer)
    """
    year: int
    grundfreibetrag: Decimal  # § 32a Abs. 1 Nr. 1 EStG - Basic allowance
    zone1_end: Decimal        # End of first progressive zone
    zone2_end: Decimal        # End of second progressive zone (start of 42%)
    spitzensteuersatz_start: Decimal  # Start of 45% (Reichensteuer)
    soli_threshold: Decimal   # Solidaritätszuschlag threshold

    # VAT thresholds for Kleinunternehmerregelung (§ 19 UStG) - 2025 reform
    kleinunternehmer_prev_year: Decimal = Decimal("25000")   # Previous year NET limit
    kleinunternehmer_curr_year: Decimal = Decimal("100000")  # Current year NET limit


# Tax configurations for supported years
# Source: Bundesfinanzministerium, § 32a EStG
TAX_CONFIGS: dict[int, TaxYearConfig] = {
    2025: TaxYearConfig(
        year=2025,
        grundfreibetrag=Decimal("12096"),
        zone1_end=Decimal("17005"),
        zone2_end=Decimal("66760"),
        spitzensteuersatz_start=Decimal("277826"),
        soli_threshold=Decimal("18130"),
    ),
    2026: TaxYearConfig(
        year=2026,
        grundfreibetrag=Decimal("12348"),
        zone1_end=Decimal("17443"),
        zone2_end=Decimal("68480"),
        spitzensteuersatz_start=Decimal("277826"),
        soli_threshold=Decimal("18130"),
    ),
}


@lru_cache(maxsize=8)
def get_tax_config(year: int) -> TaxYearConfig:
    """Get tax configuration for a specific year.

    Cached for performance since tax configs are static.

    Raises:
        InvalidTaxYearError: If year is not supported
    """
    if year not in TAX_CONFIGS:
        raise InvalidTaxYearError(year, list(TAX_CONFIGS.keys()))
    return TAX_CONFIGS[year]


# =============================================================================
# Client Models
# =============================================================================


class ClientInput(BaseModel):
    """Input model for client forms.

    Contains all client details needed for invoicing and tax compliance.
    Supports both domestic and international clients (Reverse Charge, § 13b UStG).
    """
    name: str = Field(..., min_length=1, max_length=200)
    # Address
    street: str = Field(default="", max_length=200)
    address_details: str = Field(default="", max_length=100)  # Building, apartment, etc.
    zip_code: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=100)
    country: str = Field(default="DE", max_length=2)  # ISO 3166-1 alpha-2
    # Contact
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=30)
    # Tax Information (for Reverse Charge / Zusammenfassende Meldung)
    vat_id: str = Field(default="", max_length=20)  # EU VAT ID (e.g., DE123456789)
    # Notes
    notes: str = Field(default="", max_length=500)

    @property
    def is_eu_client(self) -> bool:
        """Check if client is from EU (excluding Germany)."""
        eu_countries = {
            "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
            "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL",
            "PT", "RO", "SK", "SI", "ES", "SE"
        }
        return self.country.upper() in eu_countries

    @property
    def is_domestic(self) -> bool:
        """Check if client is domestic (Germany)."""
        return self.country.upper() == "DE"

    @property
    def is_reverse_charge_eligible(self) -> bool:
        """Check if Reverse Charge applies (§ 13b UStG).

        Applies to B2B services to EU clients with valid VAT ID,
        or to non-EU clients (always Reverse Charge).
        """
        if self.is_domestic:
            return False
        if self.is_eu_client:
            return bool(self.vat_id)  # EU: requires VAT ID
        return True  # Non-EU: always Reverse Charge

    @property
    def full_address(self) -> str:
        """Format full address for display."""
        parts = [self.street]
        if self.address_details:
            parts.append(self.address_details)
        if self.zip_code or self.city:
            parts.append(f"{self.zip_code} {self.city}".strip())
        if self.country and self.country != "DE":
            parts.append(self.country)
        return "\n".join(filter(None, parts))


class Client(ClientInput):
    """Client with ID."""
    id: int


# =============================================================================
# Tax Result Models
# =============================================================================

class EinkommensteuerResult(BaseModel):
    """Result of income tax calculation (§ 32a EStG)."""
    year: int
    zu_versteuerndes_einkommen: Decimal  # Taxable income
    einkommensteuer: Decimal             # Income tax amount
    solidaritaetszuschlag: Decimal       # 5.5% soli (if applicable)
    total_tax: Decimal                   # ESt + Soli
    effective_rate: Decimal              # Effective tax rate in %
    marginal_rate: Decimal               # Marginal rate in %


class UmsatzsteuerResult(BaseModel):
    """Result of VAT calculation (USt, § 12 UStG)."""
    period: str                          # '2026-01' or '2026-Q1'
    umsatzsteuer_collected: Decimal      # USt from invoices
    vorsteuer_paid: Decimal              # Input VAT from expenses
    zahllast: Decimal                    # Net VAT liability (USt - Vorst)
    is_nullmeldung: bool                 # True if all Reverse Charge
    kleinunternehmer_eligible: bool      # § 19 UStG eligibility


class TaxEstimate(BaseModel):
    """Comprehensive tax estimate for dashboard."""
    estimated_income: Decimal
    estimated_expenses: Decimal
    taxable_income: Decimal
    einkommensteuer: Decimal
    solidaritaetszuschlag: Decimal
    umsatzsteuer_liability: Decimal
    total_tax_burden: Decimal
    effective_rate: Decimal
    quarterly_payment: Decimal  # Suggested quarterly prepayment


# =============================================================================
# Enumerations
# =============================================================================


class VatRate(StrEnum):
    """German VAT rates (Mehrwertsteuer/Umsatzsteuer)."""
    STANDARD = "0.19"  # 19% - Standard rate
    REDUCED = "0.07"   # 7% - Reduced rate (food, books, etc.)
    ZERO = "0.00"      # 0% - Tax-exempt (insurance, education)


class ExpenseCategory(StrEnum):
    """Expense categories for tax deduction (Betriebsausgaben)."""
    BUERO = "buero"                    # Office supplies
    SOFTWARE = "software"              # Software & licenses
    HARDWARE = "hardware"              # Hardware & equipment
    REISE = "reise"                    # Travel expenses
    KOMMUNIKATION = "kommunikation"    # Communication (phone, internet)
    VERSICHERUNG = "versicherung"      # Insurance
    FORTBILDUNG = "fortbildung"        # Professional development
    BEWIRTUNG = "bewirtung"            # Business meals (70% deductible)
    GESCHENKE = "geschenke"            # Gifts (50 EUR limit per recipient)
    SONSTIGES = "sonstiges"            # Other


# =============================================================================
# Asset & Depreciation Models (AfA)
# =============================================================================


class AssetCategory(StrEnum):
    """Asset categories for depreciation (AfA-Tabelle)."""
    COMPUTER = "computer"      # 1 year (Digital AfA, BMF 2021)
    SOFTWARE = "software"      # 1 year (Digital AfA, BMF 2021)
    OFFICE = "office"          # 13 years (Büroausstattung)
    VEHICLE = "vehicle"        # 6 years (PKW)
    FURNITURE = "furniture"    # 13 years (Möbel)
    MACHINERY = "machinery"    # Varies by type
    OTHER = "other"            # User-specified useful life


class DepreciationMethod(StrEnum):
    """Depreciation methods per German tax law.

    Reference:
    - § 6 Abs. 2 EStG: GWG (Geringwertige Wirtschaftsgüter)
    - § 6 Abs. 2a EStG: Sammelposten (Pool)
    - § 7 Abs. 1 EStG: Linear depreciation
    - § 7 Abs. 2 EStG: Degressive depreciation (Wachstumschancengesetz 2024)
    - BMF 2021-02-26: Digital AfA for IT assets
    """
    IMMEDIATE = "immediate"    # GWG < 800 EUR or trivial < 250 EUR
    LINEAR = "linear"          # Standard linear AfA
    DEGRESSIVE = "degressive"  # 2.5x linear, max 25% (Wachstumschancengesetz)
    POOL = "pool"              # Sammelposten: 5 years for 250-1000 EUR
    DIGITAL = "digital"        # 1-year write-off for IT (BMF 2021)


# Standard useful life years from AfA-Tabelle
AFA_USEFUL_LIFE: dict[AssetCategory, int] = {
    AssetCategory.COMPUTER: 1,     # Digital AfA
    AssetCategory.SOFTWARE: 1,     # Digital AfA
    AssetCategory.OFFICE: 13,
    AssetCategory.VEHICLE: 6,
    AssetCategory.FURNITURE: 13,
    AssetCategory.MACHINERY: 10,   # Default, varies
    AssetCategory.OTHER: 10,       # Default
}


class AssetInput(BaseModel):
    """Input model for asset creation forms.

    Implements German depreciation rules:
    - < 250 EUR net: Trivial expense (not tracked as asset)
    - 250-800 EUR net: GWG immediate write-off (§ 6 Abs. 2 EStG)
    - 250-1000 EUR net: Pool option (§ 6 Abs. 2a EStG)
    - IT assets: 1-year Digital AfA (BMF 2021)
    - > 1000 EUR: Standard AfA (linear or degressive)
    """
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    purchase_date: date
    acquisition_cost: Decimal = Field(..., gt=0, decimal_places=2)  # Net
    vat_rate: VatRate = VatRate.STANDARD
    category: AssetCategory = AssetCategory.OTHER
    useful_life_years: int = Field(default=10, ge=1, le=50)
    depreciation_method: DepreciationMethod | None = None  # Auto-suggested if None
    private_use_percent: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )

    @field_validator("acquisition_cost")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))

    @computed_field
    @property
    def vat_amount(self) -> Decimal:
        """Calculate VAT (Vorsteuer) on purchase."""
        rate = Decimal(self.vat_rate.value)
        return (self.acquisition_cost * rate).quantize(Decimal("0.01"))

    @computed_field
    @property
    def gross_cost(self) -> Decimal:
        """Calculate gross purchase price (incl. VAT)."""
        return (self.acquisition_cost + self.vat_amount).quantize(Decimal("0.01"))


class Asset(AssetInput):
    """Asset with ID and depreciation tracking."""
    id: int
    current_book_value: Decimal = Decimal("0")
    total_depreciated: Decimal = Decimal("0")
    depreciation_complete: bool = False
    pool_year: int | None = None
    disposal_date: date | None = None
    disposal_amount: Decimal | None = None


class DepreciationRecord(BaseModel):
    """Annual depreciation entry for an asset."""
    id: int
    asset_id: int
    year: int
    depreciation_amount: Decimal
    book_value_start: Decimal
    book_value_end: Decimal
    method_applied: DepreciationMethod
    months_applicable: int = 12
    notes: str = ""


# =============================================================================
# Travel Expense Models (Reisekosten)
# =============================================================================

# Domestic per diem rates 2024/2025 (§ 9 Abs. 4a EStG)
PER_DIEM_RATES_DOMESTIC = {
    "8+": Decimal("14"),      # > 8 hours absence
    "24": Decimal("28"),      # Full 24-hour day
    "travel_day": Decimal("14"),  # Arrival/departure day (An-/Abreisetag)
}

# Meal reduction percentages (from full 24h rate)
MEAL_REDUCTION_RATES = {
    "breakfast": Decimal("0.20"),  # 20% = 5.60 EUR
    "lunch": Decimal("0.40"),      # 40% = 11.20 EUR
    "dinner": Decimal("0.40"),     # 40% = 11.20 EUR
}

# Km rates (Entfernungspauschale, § 9 Abs. 1 Nr. 4 EStG)
KM_RATE_FIRST_20 = Decimal("0.30")   # First 20 km
KM_RATE_BEYOND_20 = Decimal("0.38")  # Beyond 20 km

# Top foreign per diem rates (BMF annual publication, simplified)
PER_DIEM_RATES_FOREIGN: dict[str, dict[str, Decimal]] = {
    "US": {"8+": Decimal("48"), "24": Decimal("64")},
    "GB": {"8+": Decimal("41"), "24": Decimal("62")},
    "FR": {"8+": Decimal("38"), "24": Decimal("58")},
    "CH": {"8+": Decimal("47"), "24": Decimal("64")},
    "AT": {"8+": Decimal("32"), "24": Decimal("47")},
    "NL": {"8+": Decimal("36"), "24": Decimal("53")},
    "BE": {"8+": Decimal("36"), "24": Decimal("53")},
    "ES": {"8+": Decimal("26"), "24": Decimal("34")},
    "IT": {"8+": Decimal("30"), "24": Decimal("42")},
    "SE": {"8+": Decimal("47"), "24": Decimal("66")},
}


class TravelExpenseInput(BaseModel):
    """Input model for travel expense forms.

    Implements:
    - Per diem (Verpflegungsmehraufwand) per § 9 Abs. 4a EStG
    - Km allowance (Entfernungspauschale) per § 9 Abs. 1 Nr. 4 EStG
    - Meal reductions for provided meals
    """
    date: date
    destination: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(..., min_length=3, max_length=500)
    # Time tracking
    departure_time: str | None = None  # HH:MM format
    return_time: str | None = None
    absence_hours: Decimal = Field(..., ge=0)
    is_overnight: bool = False
    is_travel_day: bool = False  # An-/Abreisetag
    # Km tracking
    km_driven: Decimal = Field(default=Decimal("0"), ge=0)
    # Country for per diem rates
    country_code: str = Field(default="DE", max_length=2)
    # Meal provisions (reduces per diem)
    breakfast_provided: bool = False
    lunch_provided: bool = False
    dinner_provided: bool = False

    @field_validator("absence_hours", "km_driven")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class TravelExpense(TravelExpenseInput):
    """Travel expense with ID and calculated deductions."""
    id: int
    # Calculated fields
    km_rate: Decimal = KM_RATE_FIRST_20
    km_deduction: Decimal = Decimal("0")
    per_diem_rate: Decimal = Decimal("0")
    meal_reduction: Decimal = Decimal("0")
    per_diem_deduction: Decimal = Decimal("0")
    total_deduction: Decimal = Decimal("0")
    linked_expense_id: int | None = None


# =============================================================================
# Gift Expense Models (Geschenke)
# =============================================================================

# Gift deductibility limit per recipient per year (§ 4 Abs. 5 Nr. 1 EStG)
# Raised from 35 EUR to 50 EUR by Wachstumschancengesetz 2024
GIFT_LIMIT_PER_RECIPIENT = Decimal("50.00")


class GiftExpenseInput(BaseModel):
    """Input model for gift expense forms.

    Implements:
    - 50 EUR net limit per recipient per year (§ 4 Abs. 5 Nr. 1 EStG)
    - Cliff effect: 50.01 EUR = entire amount non-deductible
    - Optional 30% flat tax (§ 37b EStG)
    """
    date: date
    recipient_name: str = Field(..., min_length=1, max_length=200)
    recipient_company: str = Field(default="", max_length=200)
    description: str = Field(..., min_length=3, max_length=500)
    amount_net: Decimal = Field(..., gt=0, decimal_places=2)
    vat_rate: VatRate = VatRate.STANDARD
    flat_tax_paid: bool = False  # 30% flat tax for recipient

    @field_validator("amount_net")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))

    @computed_field
    @property
    def vat_amount(self) -> Decimal:
        """Calculate VAT on gift."""
        rate = Decimal(self.vat_rate.value)
        return (self.amount_net * rate).quantize(Decimal("0.01"))

    @computed_field
    @property
    def flat_tax_amount(self) -> Decimal:
        """Calculate 30% flat tax if paid (§ 37b EStG)."""
        if self.flat_tax_paid:
            return (self.amount_net * Decimal("0.30")).quantize(Decimal("0.01"))
        return Decimal("0")


class GiftExpense(GiftExpenseInput):
    """Gift expense with ID and deductibility tracking."""
    id: int
    is_deductible: bool = True
    cumulative_year_total: Decimal = Decimal("0")
    expense_id: int | None = None  # Link to expenses table


class GiftRecipientSummary(BaseModel):
    """Summary of gifts to a single recipient for limit tracking."""
    recipient_name: str
    recipient_company: str = ""
    year: int
    gift_count: int
    total_net: Decimal
    is_over_limit: bool
    remaining_allowance: Decimal


# =============================================================================
# Home Office Models
# =============================================================================

# Home Office Pauschale rates (2023+ rules)
HOME_OFFICE_DAILY_RATE = Decimal("6")     # EUR per day
HOME_OFFICE_MAX_DAYS = 210                 # Max claimable days
HOME_OFFICE_MAX_DEDUCTION = Decimal("1260")  # 6 * 210

# Arbeitszimmer flat rate option (2023+)
ARBEITSZIMMER_FLAT_RATE = Decimal("1260")

# Alias for service layer
HOME_OFFICE_ANNUAL_CAP = HOME_OFFICE_MAX_DEDUCTION


class HomeOfficeType(StrEnum):
    """Home office deduction type (2023+ rules)."""
    PAUSCHALE = "pauschale"        # 6 EUR/day flat rate (work corner)
    ARBEITSZIMMER = "arbeitszimmer"  # Separate room, center of activity


class HomeOfficeDayInput(BaseModel):
    """Input for recording a home office day."""
    date: date
    deduction_type: HomeOfficeType = HomeOfficeType.PAUSCHALE
    notes: str = Field(default="", max_length=200)


class HomeOfficeDay(HomeOfficeDayInput):
    """Home office day with calculated deduction."""
    id: int
    amount: Decimal = HOME_OFFICE_DAILY_RATE


class HomeOfficeSettings(BaseModel):
    """Annual home office configuration.

    For Arbeitszimmer (separate room):
    - Must be center of all professional activity
    - Deduction = (room_sqm / total_sqm) * (rent + utilities)
    - OR use 1,260 EUR flat rate option (2023+)
    """
    year: int
    deduction_type: HomeOfficeType
    # Arbeitszimmer details
    room_size_sqm: Decimal | None = None
    total_home_sqm: Decimal | None = None
    monthly_rent: Decimal | None = None
    monthly_utilities: Decimal | None = None
    use_flat_rate: bool = True  # Use 1260 EUR flat vs actual
    annual_deduction: Decimal | None = None

    @computed_field
    @property
    def calculated_deduction(self) -> Decimal:
        """Calculate annual deduction based on settings."""
        if self.deduction_type == HomeOfficeType.PAUSCHALE:
            return HOME_OFFICE_MAX_DEDUCTION  # Max possible
        if self.use_flat_rate:
            return ARBEITSZIMMER_FLAT_RATE
        if all([self.room_size_sqm, self.total_home_sqm,
                self.monthly_rent, self.monthly_utilities]):
            ratio = self.room_size_sqm / self.total_home_sqm
            annual_costs = (self.monthly_rent + self.monthly_utilities) * 12
            return (annual_costs * ratio).quantize(Decimal("0.01"))
        return Decimal("0")


class HomeOfficeSummary(BaseModel):
    """Annual home office summary."""
    year: int
    days_claimed: int
    total_deduction: Decimal
    deduction_type: HomeOfficeType
    remaining_days: int  # For pauschale: 210 - days_claimed
    at_limit: bool       # True if 210 days reached


class HomeOfficeSettingsInput(BaseModel):
    """Input for saving home office settings.

    Supports three methods:
    - pauschale: 6 EUR/day (no room details needed)
    - arbeitszimmer_flat: 1,260 EUR flat rate (no room details needed)
    - arbeitszimmer_actual: Pro-rata actual costs (room details required)
    """
    year: int
    method: str = "pauschale"  # pauschale, arbeitszimmer_flat, arbeitszimmer_actual
    room_sqm: Decimal | None = None
    total_sqm: Decimal | None = None
    monthly_costs: Decimal | None = None  # Combined rent + utilities


# =============================================================================
# Business Meals Models (Bewirtungskosten)
# =============================================================================

# Business meal deduction rules (§ 4 Abs. 5 Nr. 2 EStG)
BUSINESS_MEAL_DEDUCTION_RATE = Decimal("0.70")  # 70% deductible for clients
STAFF_EVENT_LIMIT_PER_PERSON = Decimal("110")   # Max per person for 100% deduction

# Aliases for service layer
BEWIRTUNG_DEDUCTION_RATE = BUSINESS_MEAL_DEDUCTION_RATE
INTERNAL_EVENT_CAP_PER_PERSON = STAFF_EVENT_LIMIT_PER_PERSON


class BusinessMealInput(BaseModel):
    """Input for standalone business meal tracking.

    Implements (§ 4 Abs. 5 Nr. 2 EStG):
    - 70% deduction for client entertainment
    - 100% deduction for staff events (max 110 EUR/person)
    - Required: attendees list and business purpose
    """
    date: date
    restaurant_name: str = Field(..., min_length=1, max_length=200)
    business_purpose: str = Field(..., min_length=10, max_length=500)
    attendees: str = Field(..., min_length=1, max_length=500)  # Comma-separated names
    attendee_count: int = Field(default=1, ge=1)
    total_amount: Decimal = Field(..., gt=0)
    tip_amount: Decimal = Field(default=Decimal("0"), ge=0)
    is_internal: bool = False  # Staff event vs client meal

    @computed_field
    @property
    def amount_net(self) -> Decimal:
        """Total meal cost including tip."""
        return self.total_amount + self.tip_amount


class BusinessMeal(BaseModel):
    """Business meal with ID and calculated deductions."""
    id: int
    date: date
    restaurant_name: str
    business_purpose: str
    attendees: str
    attendee_count: int
    total_amount: Decimal
    tip_amount: Decimal
    is_internal: bool
    deductible_amount: Decimal
    non_deductible_amount: Decimal

    @computed_field
    @property
    def amount_net(self) -> Decimal:
        """Total meal cost including tip."""
        return self.total_amount + self.tip_amount


class InvoiceStatus(StrEnum):
    """Invoice payment status."""
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"


class ExpenseInput(BaseModel):
    """Input model for expense forms (HTMX payloads)."""
    date: date
    vendor: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=3, max_length=500)
    amount_gross: Decimal = Field(..., gt=0, decimal_places=2)
    vat_rate: VatRate = VatRate.STANDARD
    category: ExpenseCategory = ExpenseCategory.SONSTIGES

    @field_validator("amount_gross")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        """Ensure strict 2-decimal precision."""
        return v.quantize(Decimal("0.01"))


class Expense(ExpenseInput):
    """Expense with ID and computed fields."""
    id: int

    @computed_field
    @property
    def amount_net(self) -> Decimal:
        """Calculate net amount (before VAT). Nettobetrag."""
        rate = Decimal(self.vat_rate.value)
        return (self.amount_gross / (1 + rate)).quantize(Decimal("0.01"))

    @computed_field
    @property
    def vat_amount(self) -> Decimal:
        """Calculate VAT portion. Vorsteuer."""
        return (self.amount_gross - self.amount_net).quantize(Decimal("0.01"))


class InvoiceInput(BaseModel):
    """Input model for invoice forms."""
    client: str = Field(..., min_length=1, max_length=200)
    invoice_number: str = Field(..., min_length=1, max_length=50)
    date: date
    due_date: date | None = None
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    vat_rate: VatRate = VatRate.STANDARD
    description: str = Field(..., min_length=3, max_length=1000)

    @field_validator("amount")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class Invoice(InvoiceInput):
    """Invoice with status tracking."""
    id: int
    status: InvoiceStatus = InvoiceStatus.PENDING
    paid_date: date | None = None
    pdf_path: str | None = None  # Path to associated PDF (imported or exported)

    @computed_field
    @property
    def amount_net(self) -> Decimal:
        """Net amount before VAT."""
        rate = Decimal(self.vat_rate.value)
        return (self.amount / (1 + rate)).quantize(Decimal("0.01"))

    @computed_field
    @property
    def vat_amount(self) -> Decimal:
        """VAT collected (Umsatzsteuer)."""
        return (self.amount - self.amount_net).quantize(Decimal("0.01"))


class TaxDeadline(BaseModel):
    """Upcoming tax deadline."""
    name: str
    type: str  # 'einkommensteuer' | 'umsatzsteuer' | 'gewerbesteuer'
    description: str
    date: date
    days_until: int
    amount: Decimal | None = None
    completed: bool = False
    deadline_id: str = ""  # Unique ID for persistence (e.g., "ust_2025_01")


class QuarterlyPayment(BaseModel):
    """Quarterly tax prepayment (Einkommensteuer-Vorauszahlung, § 37 EStG)."""
    quarter: int
    year: int
    due_date: date
    amount: Decimal
    paid: bool = False
    days_until: int | None = None


class DashboardStats(BaseModel):
    """Dashboard summary statistics."""
    total_revenue: Decimal
    total_expenses: Decimal
    vat_collected: Decimal
    estimated_tax: Decimal
    revenue_change: Decimal  # Percentage vs last month
    expense_change: Decimal
    tax_rate: Decimal  # Effective tax rate
    next_ust_date: str  # Next USt declaration date


# =============================================================================
# Invoice Template Models
# =============================================================================


class SenderInfo(BaseModel):
    """Business sender information for invoices."""
    name: str
    street: str
    details: str = ""  # Building/apartment number
    zip: str
    city: str
    country: str = "Germany"
    phone: str = ""
    email: str
    vat_id: str  # USt-IdNr.
    bank: str
    iban: str
    swift: str


class InvoiceItem(BaseModel):
    """Line item on an invoice."""
    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "Stk."  # Stück, Stunden, Tage, etc.
    unit_price: Decimal
    service_date: date | None = None
    note: str | None = None

    @computed_field
    @property
    def total(self) -> Decimal:
        """Calculate line item total."""
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


# Default sender info (can be overridden via settings)
DEFAULT_SENDER = SenderInfo(
    name="Max Mustermann",
    street="Musterstraße 123",
    details="",
    zip="10115",
    city="Berlin",
    country="Germany",
    phone="+49 30 12345678",
    email="max@mustermann.dev",
    vat_id="DE123456789",
    bank="Commerzbank",
    iban="DE89 3704 0044 0532 0130 00",
    swift="COBADEFFXXX",
)


# =============================================================================
# User Settings Model
# =============================================================================


class UserSettings(BaseModel):
    """User settings for invoice generation and business information.

    All fields needed for German tax-compliant invoices (§14 UStG).
    """
    # Business Identity
    business_name: str = Field(default="", max_length=200)

    # Address
    street: str = Field(default="", max_length=200)
    address_details: str = Field(default="", max_length=100)  # Building, apartment, etc.
    zip_code: str = Field(default="", max_length=10)
    city: str = Field(default="", max_length=100)
    country: str = Field(default="Germany", max_length=100)

    # Contact
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=200)

    # Tax Information (§14 UStG mandatory)
    vat_id: str = Field(default="", max_length=20)  # USt-IdNr. (e.g., DE123456789)
    tax_number: str = Field(default="", max_length=20)  # Steuernummer

    # Bank Details
    bank_name: str = Field(default="", max_length=100)
    iban: str = Field(default="", max_length=34)
    bic_swift: str = Field(default="", max_length=11)

    # Invoice Preferences
    default_payment_terms: int = Field(default=14, ge=0, le=365)  # Days until due
    default_vat_rate: VatRate = Field(default=VatRate.ZERO)  # Default for new invoices
    invoice_prefix: str = Field(default="", max_length=10)  # e.g., "INV-" or "2026-"

    # Display Preferences
    preferred_currency: str = Field(default="EUR", max_length=3)
    date_format: str = Field(default="iso", max_length=20)  # iso, german, us
    language: str = Field(default="de", max_length=5)  # de, en
    tax_year: int | None = Field(default=None)  # None = current year

    # Tax Obligation Settings
    is_freiberufler: bool = Field(default=True)  # Exempt from Gewerbesteuer (§ 18 EStG)
    has_eu_clients: bool = Field(default=False)  # Requires Zusammenfassende Meldung
    ust_frequency: str = Field(default="monthly", max_length=20)  # monthly, quarterly, annual
    quarterly_est_amount: Decimal = Field(default=Decimal("0"))  # ESt quarterly prepayment
    activity_start_date: date | None = Field(default=None)  # Data before this date is ignored

    def to_sender_info(self) -> SenderInfo:
        """Convert settings to SenderInfo for invoice templates."""
        return SenderInfo(
            name=self.business_name or "Your Business Name",
            street=self.street,
            details=self.address_details,
            zip=self.zip_code,
            city=self.city,
            country=self.country,
            phone=self.phone,
            email=self.email,
            vat_id=self.vat_id,
            bank=self.bank_name,
            iban=self.iban,
            swift=self.bic_swift,
        )


# =============================================================================
# Client Statistics Models (Scheinselbständigkeit Detection)
# =============================================================================

# Scheinselbständigkeit threshold per German tax authority guidelines
# Income concentration >83% from single client triggers false self-employment risk
SCHEINSELBSTAENDIG_THRESHOLD = Decimal("0.83")


class ClientStats(BaseModel):
    """Aggregated client statistics with invoice and payment data.

    Used for Scheinselbständigkeit risk analysis (§ 7 SGB IV).
    German tax authorities flag freelancers with >83% income from one client.
    """
    client: Client
    invoice_count: int = 0
    paid_invoice_count: int = 0
    total_invoiced: Decimal = Decimal("0.00")  # Total amount invoiced (net)
    total_paid: Decimal = Decimal("0.00")      # Amount from paid invoices (net)
    outstanding: Decimal = Decimal("0.00")     # Unpaid amount (net)
    income_percentage: Decimal = Decimal("0.00")  # % of total income from this client
    is_scheinselbstaendig_risk: bool = False   # True if >83% income concentration

    @computed_field
    @property
    def risk_level(self) -> str:
        """Categorize risk level for UI display.

        Returns: 'high' (>83%), 'medium' (50-83%), 'low' (<50%)
        """
        if self.income_percentage >= SCHEINSELBSTAENDIG_THRESHOLD:
            return "high"
        elif self.income_percentage >= Decimal("0.50"):
            return "medium"
        return "low"


class IncomeDistribution(BaseModel):
    """Overall income distribution analysis for Scheinselbständigkeit detection.

    Scheinselbständigkeit (false self-employment) is a legal concept in Germany
    where a freelancer is economically dependent on a single client and may be
    reclassified as an employee for tax and social security purposes.

    Key indicators per § 7 SGB IV:
    - >83% income from single client
    - No own employees
    - Work instructions from client
    - Fixed working hours/location
    """
    total_income: Decimal = Decimal("0.00")
    client_breakdown: list[ClientStats] = []
    max_concentration: Decimal = Decimal("0.00")  # Highest single-client percentage
    scheinselbstaendig_warning: bool = False       # True if any client >83%
    warning_threshold: Decimal = SCHEINSELBSTAENDIG_THRESHOLD
    clients_at_risk: int = 0                       # Number of clients exceeding threshold

    @computed_field
    @property
    def top_client(self) -> ClientStats | None:
        """Get the client with highest income concentration."""
        if not self.client_breakdown:
            return None
        return max(self.client_breakdown, key=lambda x: x.income_percentage)


# =============================================================================
# Health Insurance Models (Krankenversicherung)
# Implements § 10 Abs. 1 Nr. 3 EStG - Vorsorgeaufwand
# =============================================================================

# Tax deduction limits for Sonderausgaben (§ 10 Abs. 4 EStG)
# Freelancers get 2,800 EUR (no employer subsidy), employees get 1,900 EUR
HEALTH_INSURANCE_SONDERAUSGABEN_LIMIT = Decimal("2800")

# GKV Krankengeld reduction: 4% reduction for those with Krankengeldanspruch
KRANKENGELD_REDUCTION_RATE = Decimal("0.04")


class InsuranceType(StrEnum):
    """Health insurance type in Germany."""
    GKV = "gkv"  # Gesetzliche Krankenversicherung (statutory)
    PKV = "pkv"  # Private Krankenversicherung (private)


class CoverageType(StrEnum):
    """Health insurance coverage types per § 10 EStG.

    Determines tax deductibility:
    - Basis/Pflege: Unlimited deduction (§ 10 Abs. 1 Nr. 3 Buchst. a)
    - Wahlleistungen/Zusatz: Limited to 2,800 EUR (§ 10 Abs. 4 EStG)
    """
    BASIS_KRANKENVERSICHERUNG = "basis_krankenversicherung"  # Basic health (unlimited)
    PFLEGEPFLICHTVERSICHERUNG = "pflegepflichtversicherung"  # Mandatory care (unlimited)
    WAHLLEISTUNGEN = "wahlleistungen"                        # Optional PKV (limited)
    ZUSATZVERSICHERUNG = "zusatzversicherung"                # Supplementary (limited)


class HealthInsuranceProvider(BaseModel):
    """Health insurance provider (GKV or PKV)."""
    id: int
    name: str
    short_name: str | None = None
    type: InsuranceType
    logo_filename: str | None = None
    website: str | None = None
    is_nationwide: bool = True


class HealthInsuranceInput(BaseModel):
    """Input model for health insurance payment recording.

    Implements German tax deduction rules:
    - Basisabsicherung (basic health + care): Unlimited deduction
    - GKV with Krankengeld: 4% reduction applies
    - Wahlleistungen: Limited to 2,800 EUR total/year
    """
    date: date
    provider_id: int
    insurance_type: InsuranceType
    coverage_type: CoverageType
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    has_krankengeld: bool = False  # Only for GKV (triggers 4% reduction)
    policy_number: str = Field(default="", max_length=50)
    notes: str = Field(default="", max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        """Ensure strict 2-decimal precision."""
        return v.quantize(Decimal("0.01"))


class HealthInsurance(HealthInsuranceInput):
    """Health insurance payment with provider details and deduction calculation."""
    id: int
    provider: HealthInsuranceProvider | None = None

    @computed_field
    @property
    def deductible_amount(self) -> Decimal:
        """Calculate tax-deductible amount per § 10 EStG.

        Rules:
        - Basis + Pflege: 100% deductible (unlimited)
        - GKV with Krankengeld: 96% deductible (4% reduction)
        - Wahlleistungen: 100% but subject to 2,800 EUR annual limit
        """
        if self.coverage_type in [
            CoverageType.BASIS_KRANKENVERSICHERUNG,
            CoverageType.PFLEGEPFLICHTVERSICHERUNG,
        ]:
            # Unlimited deduction, but 4% reduction for GKV with Krankengeld
            if self.insurance_type == InsuranceType.GKV and self.has_krankengeld:
                reduction = self.amount * KRANKENGELD_REDUCTION_RATE
                return (self.amount - reduction).quantize(Decimal("0.01"))
            return self.amount
        # Wahlleistungen/Zusatzversicherung - full amount but subject to annual limit
        return self.amount


class HealthInsuranceSummary(BaseModel):
    """Annual health insurance summary for Anlage Vorsorgeaufwand.

    Provides all values needed for German tax return:
    - Line 16-17: Basisabsicherung (unlimited)
    - Line 18-19: Pflegepflichtversicherung (unlimited)
    - Line 20-21: Wahlleistungen/Zusatz (limited to 2,800 EUR)
    """
    year: int
    total_paid: Decimal                    # Total payments
    basis_total: Decimal                   # Basis + Pflege (unlimited category)
    basis_deductible: Decimal              # After 4% GKV reduction if applicable
    wahlleistungen_total: Decimal          # Optional services (limited category)
    wahlleistungen_deductible: Decimal     # Min(total, 2800)
    total_deductible: Decimal              # Sum of all deductible amounts
    remaining_limit: Decimal               # 2,800 - wahlleistungen_deductible
    payment_count: int
    by_coverage: dict[str, Decimal]        # Breakdown by coverage type
    by_provider: list[dict]                # Breakdown by provider


class HealthInsuranceDeduction(BaseModel):
    """Calculated health insurance deduction for tax purposes.

    § 10 Abs. 1 Nr. 3 EStG calculation result:
    - Basis/Pflege: Sum of all payments (4% reduction for GKV with Krankengeld)
    - Wahlleistungen: Capped at 2,800 EUR for freelancers
    """
    year: int
    # Basis category (unlimited, for Anlage Vorsorgeaufwand lines 16-19)
    krankenversicherung_basis: Decimal     # Line 16/17
    pflegeversicherung: Decimal            # Line 18/19
    krankengeld_reduction: Decimal         # 4% reduction applied (informational)
    # Limited category (for Anlage Vorsorgeaufwand lines 20-21)
    wahlleistungen_paid: Decimal           # Total Wahlleistungen paid
    wahlleistungen_deductible: Decimal     # Min(paid, 2800)
    wahlleistungen_exceeded: Decimal       # Amount over 2,800 EUR (not deductible)
    # Totals
    total_paid: Decimal                    # Grand total of all payments
    total_deductible: Decimal              # Sum of all deductible amounts
    effective_deduction_rate: Decimal      # total_deductible / total_paid as %
