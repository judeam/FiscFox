"""Semantic intent router for FiscFox LLM system.

Routes user queries to appropriate agents based on intent classification:
- TAX_LAW: German tax law Q&A → Tax RAG Agent
- FINANCIAL_QUERY: Data queries → Text-to-SQL Agent
- AFA_ASSIST: Depreciation assistance → AfA Agent
- EXPENSE_CATEGORIZE: Expense classification → Categorization Agent
- GENERAL_CHAT: General conversation → Base LLM
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class IntentType(StrEnum):
    """Types of user intents."""

    TAX_LAW = "tax_law"  # German tax law questions
    FINANCIAL_QUERY = "financial_query"  # Data/reporting queries
    AFA_ASSIST = "afa_assist"  # Depreciation/asset assistance
    EXPENSE_CATEGORIZE = "expense_categorize"  # Expense classification
    INVOICE_RISK = "invoice_risk"  # Invoice risk assessment
    GENERAL_CHAT = "general_chat"  # General conversation


@dataclass
class ExtractedEntities:
    """Entities extracted from user query."""

    # Temporal
    years: list[int] = field(default_factory=list)
    quarters: list[int] = field(default_factory=list)  # 1-4
    months: list[int] = field(default_factory=list)  # 1-12

    # Financial
    amounts: list[str] = field(default_factory=list)  # Keep as strings for precision
    categories: list[str] = field(default_factory=list)

    # Legal references
    law_sections: list[str] = field(default_factory=list)  # e.g., ["§ 7 EStG"]
    law_types: list[str] = field(default_factory=list)  # e.g., ["EStG", "UStG"]

    # Business entities
    client_names: list[str] = field(default_factory=list)
    asset_types: list[str] = field(default_factory=list)


@dataclass
class RoutingResult:
    """Result of intent routing."""

    intent: IntentType
    confidence: float  # 0.0 to 1.0
    entities: ExtractedEntities
    reasoning: str  # Explanation for routing decision

    # Suggested parameters for agent
    suggested_params: dict[str, Any] = field(default_factory=dict)


class SemanticRouter:
    """Routes queries to appropriate agents based on semantic analysis.

    Uses pattern matching and keyword analysis for fast, deterministic routing.
    Falls back to LLM classification for ambiguous queries.
    """

    # ==========================================================================
    # Pattern Definitions
    # ==========================================================================

    # Tax law patterns (German)
    TAX_LAW_PATTERNS = [
        # Direct law questions
        r"\b(?:wie|was|wann|wo|wer|warum|welche?r?)\s+.*?(?:steuer|absetzen|absetzbar|abzugsfähig)",
        r"\b(?:kann|darf|muss)\s+(?:ich|man)\s+.*?(?:absetzen|abziehen|geltend\s+machen)",
        r"\b(?:betriebsausgabe|werbungskosten|sonderausgabe|außergewöhnliche\s+belastung)",
        r"\b(?:vorsteuer|umsatzsteuer|mehrwertsteuer|ust|mwst)\b",
        r"\b(?:einkommensteuer|est|gewinnermittlung|eür)\b",
        # Legal references
        r"§\s*\d+[a-z]?\s*(?:abs\.?\s*\d+)?\s*(?:estg|ustg|ao|hgb|bgb)",
        r"\b(?:estg|ustg|ao|hgb|bgb|bmf|bfh)\b",
        # Tax concepts
        r"\b(?:kleinunternehmer|reverse.?charge|innergemeinschaftlich)",
        r"\b(?:freibetrag|grundfreibetrag|pauschale|pauschbetrag)",
    ]

    # Financial query patterns
    FINANCIAL_QUERY_PATTERNS = [
        # Aggregation queries
        r"\b(?:wie\s+viel|wieviel|summe|gesamt|total)\s+.*?(?:umsatz|einnahmen|ausgaben|gewinn|verlust)",
        r"\b(?:zeig|liste|gib)\s+.*?(?:alle|meine?|die)\s+(?:rechnungen|ausgaben|einnahmen|kunden|clients)",
        # Invoice queries
        r"\b(?:welche|was|wieviele?)\s+(?:rechnungen|invoices)\b",
        r"\b(?:offene?|unbezahlte?|fällige?|überfällige?)\s+(?:rechnungen|invoices)\b",
        r"\brechnungen\s+(?:sind|noch)\s+(?:offen|unbezahlt|fällig)\b",
        r"\b(?:ausstehende?|pending)\s+(?:rechnungen|zahlungen)\b",
        # Expense queries
        r"\b(?:welche|was|wieviele?)\s+(?:ausgaben|expenses|kosten)\b",
        r"\b(?:meine?|alle)\s+(?:ausgaben|expenses|einnahmen|revenue)\b",
        # Time-based queries
        r"\b(?:im|in)\s+(?:q[1-4]|quartal\s*[1-4]|januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)",
        r"\b(?:dieses?|letztes?|vergangene?[sn]?)\s+(?:jahr|monat|quartal|woche)",
        r"\b(?:2[0-9]{3})\b",  # Year pattern
        # Comparison queries
        r"\b(?:vergleich|unterschied|differenz|entwicklung|trend)\s+.*?(?:zwischen|von|zu)",
        # Report queries
        r"\b(?:bericht|report|übersicht|zusammenfassung|statistik|analyse)\b",
    ]

    # AfA/Depreciation patterns
    AFA_PATTERNS = [
        # Direct AfA queries
        r"\b(?:afa|abschreibung|absetzung\s+für\s+abnutzung)\b",
        r"\b(?:nutzungsdauer|lebensdauer|abschreibungsdauer)\b",
        r"\b(?:gwg|geringwertige?\s+wirtschaftsgüter?|sammelposten|pool)\b",
        r"\b(?:linear|degressiv|sonderabschreibung)\b",
        # Asset mentions with price
        r"\b(?:laptop|computer|rechner|monitor|drucker|handy|smartphone|tablet)\s+.*?\d+\s*(?:€|euro|eur)",
        r"\b(?:möbel|schreibtisch|stuhl|bürostuhl|regal)\s+.*?\d+\s*(?:€|euro|eur)",
        r"\b(?:kamera|objektiv|software|lizenz)\s+.*?\d+\s*(?:€|euro|eur)",
        # Asset categorization
        r"\b(?:anlagevermögen|betriebsmittel|arbeitsmittel)\b",
    ]

    # Expense categorization patterns
    EXPENSE_PATTERNS = [
        # Category questions
        r"\b(?:welche|was\s+für\s+eine?)\s+(?:kategorie|art|typ)\b",
        r"\b(?:wie|wo|wohin)\s+.*?(?:buchen|kategorisieren|einordnen|zuordnen)",
        # Specific expense types
        r"\b(?:buero|büro|software|hardware|reise|fahrt|bewirtung|geschenk)",
        r"\b(?:telefon|internet|versicherung|fortbildung|fachliteratur)",
        # Amount with category question
        r"\d+[,.]?\d*\s*(?:€|euro|eur)\s+(?:für|von|bei|an)\s+",
    ]

    # Invoice risk patterns
    INVOICE_PATTERNS = [
        r"\b(?:risiko|gefahr|problem)\s+.*?(?:rechnung|zahlung|kunde)",
        r"\b(?:zahlungsausfall|mahnwesen|fälligkeit|überfällig)",
        r"\b(?:bonität|kreditwürdigkeit|zahlungsmoral)",
    ]

    # ==========================================================================
    # English Pattern Definitions
    # ==========================================================================

    # Tax law patterns (English)
    TAX_LAW_PATTERNS_EN = [
        # Direct law questions
        r"\b(?:how|what|when|where|who|why|which)\s+.*?(?:tax|deduct|deductible|deduction)",
        r"\b(?:can|may|must)\s+(?:I|one)\s+.*?(?:deduct|claim|write.?off)",
        r"\b(?:business\s+expense|operating\s+expense|operating\s+cost)",
        r"\b(?:input\s+vat|output\s+vat|value\s+added\s+tax|vat)\b",
        r"\b(?:income\s+tax|profit\s+calculation|tax\s+return)\b",
        # Legal references (German laws still use German abbreviations)
        r"§\s*\d+[a-z]?\s*(?:abs\.?\s*\d+)?\s*(?:estg|ustg|ao|hgb|bgb)",
        r"\b(?:estg|ustg|ao|hgb|bgb|bmf|bfh)\b",
        # Tax concepts
        r"\b(?:small\s+business\s+exemption|reverse.?charge|intra.?community)",
        r"\b(?:tax\s+allowance|tax\s+exemption|flat.?rate|lump.?sum)",
        r"\b(?:freelancer|self.?employed|sole\s+proprietor)\s+.*?(?:tax|deduct)",
    ]

    # Financial query patterns (English)
    FINANCIAL_QUERY_PATTERNS_EN = [
        # Aggregation queries
        r"\b(?:how\s+much|total|sum|overall)\s+.*?(?:revenue|income|expenses|profit|loss)",
        r"\b(?:show|list|give)\s+.*?(?:all|my|the)\s+(?:invoices|expenses|income|clients)",
        # Invoice queries
        r"\b(?:which|what|how\s+many)\s+(?:invoices?|bills?)\b",
        r"\b(?:open|unpaid|due|overdue|outstanding)\s+(?:invoices?|bills?|payments?)\b",
        r"\binvoices?\s+(?:are|still)\s+(?:open|unpaid|due)\b",
        r"\b(?:pending)\s+(?:invoices?|payments?)\b",
        # Expense queries
        r"\b(?:which|what|how\s+many)\s+(?:expenses?|costs?)\b",
        r"\b(?:my|all)\s+(?:expenses?|costs?|income|revenue)\b",
        # Time-based queries
        r"\b(?:in|for)\s+(?:q[1-4]|quarter\s*[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)",
        r"\b(?:this|last|previous|past)\s+(?:year|month|quarter|week)",
        r"\b(?:2[0-9]{3})\b",  # Year pattern
        # Comparison queries
        r"\b(?:compare|comparison|difference|trend|development)\s+.*?(?:between|from|to)",
        # Report queries
        r"\b(?:report|overview|summary|statistics|analysis)\b",
    ]

    # AfA/Depreciation patterns (English)
    AFA_PATTERNS_EN = [
        # Direct depreciation queries
        r"\b(?:depreciation|amortization|write.?off)\b",
        r"\b(?:useful\s+life|service\s+life|depreciation\s+period)\b",
        r"\b(?:low.?value\s+asset|minor\s+asset|pool\s+depreciation)\b",
        r"\b(?:straight.?line|declining.?balance|special\s+depreciation)\b",
        # Asset mentions with price
        r"\b(?:laptop|computer|pc|monitor|printer|phone|smartphone|tablet)\s+.*?\d+\s*(?:€|euro|eur)",
        r"\b(?:furniture|desk|chair|office\s+chair|shelf)\s+.*?\d+\s*(?:€|euro|eur)",
        r"\b(?:camera|lens|software|license)\s+.*?\d+\s*(?:€|euro|eur)",
        # Asset categorization
        r"\b(?:fixed\s+assets?|capital\s+assets?|business\s+equipment)\b",
    ]

    # Expense categorization patterns (English)
    EXPENSE_PATTERNS_EN = [
        # Category questions
        r"\b(?:which|what\s+kind\s+of)\s+(?:category|type)\b",
        r"\b(?:how|where)\s+.*?(?:book|categorize|classify|assign)",
        # Specific expense types
        r"\b(?:office|software|hardware|travel|trip|entertainment|gift)",
        r"\b(?:phone|internet|insurance|training|professional\s+development)",
        # Amount with category question
        r"\d+[,.]?\d*\s*(?:€|euro|eur)\s+(?:for|from|at|to)\s+",
    ]

    # Invoice risk patterns (English)
    INVOICE_PATTERNS_EN = [
        r"\b(?:risk|danger|problem)\s+.*?(?:invoice|payment|client|customer)",
        r"\b(?:payment\s+default|dunning|due\s+date|overdue)",
        r"\b(?:creditworthiness|credit\s+rating|payment\s+behavior)",
    ]

    # English month map
    MONTH_MAP_EN = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    # English category keywords
    CATEGORY_KEYWORDS_EN = {
        "buero": ["office", "office supplies", "stationery", "paper"],
        "software": ["software", "app", "license", "subscription", "saas"],
        "hardware": ["hardware", "computer", "laptop", "monitor", "printer", "pc"],
        "reise": ["travel", "trip", "train", "flight", "hotel", "accommodation", "business trip"],
        "bewirtung": ["entertainment", "meal", "restaurant", "cafe", "coffee", "meeting"],
        "telefon": ["phone", "mobile", "smartphone", "internet", "cellular"],
        "versicherung": ["insurance", "policy", "premium"],
        "fortbildung": ["training", "seminar", "course", "professional development", "education"],
        "fachliteratur": ["book", "books", "professional book", "magazine", "literature"],
        "beratung": ["consulting", "lawyer", "tax advisor", "consultant"],
        "miete": ["rent", "office space", "coworking"],
        "werbung": ["advertising", "marketing", "ad", "promotion"],
        "kfzkosten": ["car", "vehicle", "gas", "fuel", "km", "kilometer", "mileage"],
        "geschenke": ["gift", "present", "client gift"],
    }

    # Entity extraction patterns
    YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
    QUARTER_PATTERN = re.compile(r"\bq([1-4])\b|\bquartal\s*([1-4])\b|\bquarter\s*([1-4])\b", re.IGNORECASE)
    # German and English months
    MONTH_PATTERN = re.compile(
        r"\b(januar|februar|märz|april|mai|juni|juli|august|"
        r"september|oktober|november|dezember|"
        r"january|february|march|may|june|july|october|december)\b",
        re.IGNORECASE,
    )
    AMOUNT_PATTERN = re.compile(r"\b(\d+(?:[.,]\d{1,2})?)\s*(?:€|euro|eur)\b", re.IGNORECASE)
    SECTION_PATTERN = re.compile(
        r"§\s*(\d+[a-z]?)\s*(?:abs\.?\s*(\d+))?\s*(estg|ustg|ao|hgb|bgb)?",
        re.IGNORECASE,
    )
    LAW_PATTERN = re.compile(r"\b(estg|ustg|ao|hgb|bgb|bmf|bfh)\b", re.IGNORECASE)

    # Category keywords
    CATEGORY_KEYWORDS = {
        "buero": ["büro", "buero", "bürobedarf", "schreibwaren", "papier"],
        "software": ["software", "app", "lizenz", "subscription", "saas"],
        "hardware": ["hardware", "computer", "laptop", "monitor", "drucker", "rechner"],
        "reise": ["reise", "fahrt", "bahn", "flug", "hotel", "übernachtung", "dienstreise"],
        "bewirtung": ["bewirtung", "essen", "restaurant", "cafe", "kaffee", "meeting"],
        "telefon": ["telefon", "handy", "smartphone", "internet", "mobilfunk"],
        "versicherung": ["versicherung", "police", "beitrag"],
        "fortbildung": ["fortbildung", "seminar", "kurs", "weiterbildung", "schulung"],
        "fachliteratur": ["buch", "bücher", "fachbuch", "zeitschrift", "literatur"],
        "beratung": ["beratung", "anwalt", "steuerberater", "consulting"],
        "miete": ["miete", "büroräume", "coworking"],
        "werbung": ["werbung", "marketing", "anzeige", "promotion"],
        "kfzkosten": ["auto", "kfz", "fahrzeug", "benzin", "tanken", "km", "kilometer"],
        "geschenke": ["geschenk", "präsent", "kundengeschenk"],
    }

    MONTH_MAP = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    }

    # ==========================================================================
    # Routing Logic
    # ==========================================================================

    def __init__(self):
        """Initialize semantic router."""
        # Compile German patterns
        self._tax_patterns_de = [re.compile(p, re.IGNORECASE) for p in self.TAX_LAW_PATTERNS]
        self._financial_patterns_de = [re.compile(p, re.IGNORECASE) for p in self.FINANCIAL_QUERY_PATTERNS]
        self._afa_patterns_de = [re.compile(p, re.IGNORECASE) for p in self.AFA_PATTERNS]
        self._expense_patterns_de = [re.compile(p, re.IGNORECASE) for p in self.EXPENSE_PATTERNS]
        self._invoice_patterns_de = [re.compile(p, re.IGNORECASE) for p in self.INVOICE_PATTERNS]

        # Compile English patterns
        self._tax_patterns_en = [re.compile(p, re.IGNORECASE) for p in self.TAX_LAW_PATTERNS_EN]
        self._financial_patterns_en = [re.compile(p, re.IGNORECASE) for p in self.FINANCIAL_QUERY_PATTERNS_EN]
        self._afa_patterns_en = [re.compile(p, re.IGNORECASE) for p in self.AFA_PATTERNS_EN]
        self._expense_patterns_en = [re.compile(p, re.IGNORECASE) for p in self.EXPENSE_PATTERNS_EN]
        self._invoice_patterns_en = [re.compile(p, re.IGNORECASE) for p in self.INVOICE_PATTERNS_EN]

        # Combined patterns for scoring (German + English)
        self._tax_patterns = self._tax_patterns_de + self._tax_patterns_en
        self._financial_patterns = self._financial_patterns_de + self._financial_patterns_en
        self._afa_patterns = self._afa_patterns_de + self._afa_patterns_en
        self._expense_patterns = self._expense_patterns_de + self._expense_patterns_en
        self._invoice_patterns = self._invoice_patterns_de + self._invoice_patterns_en

        # Combined month maps
        self._month_map = {**self.MONTH_MAP, **self.MONTH_MAP_EN}

        # Combined category keywords
        self._category_keywords = {}
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            self._category_keywords[cat] = keywords + self.CATEGORY_KEYWORDS_EN.get(cat, [])

    def route(self, query: str) -> RoutingResult:
        """Route query to appropriate agent.

        Args:
            query: User query text

        Returns:
            RoutingResult with intent, confidence, and entities
        """
        # Normalize query
        query_lower = query.lower().strip()

        # Extract entities first
        entities = self._extract_entities(query)

        # Score each intent category
        scores = {
            IntentType.TAX_LAW: self._score_patterns(query_lower, self._tax_patterns),
            IntentType.FINANCIAL_QUERY: self._score_patterns(query_lower, self._financial_patterns),
            IntentType.AFA_ASSIST: self._score_patterns(query_lower, self._afa_patterns),
            IntentType.EXPENSE_CATEGORIZE: self._score_patterns(query_lower, self._expense_patterns),
            IntentType.INVOICE_RISK: self._score_patterns(query_lower, self._invoice_patterns),
        }

        # Boost scores based on entities
        if entities.law_sections or entities.law_types:
            scores[IntentType.TAX_LAW] += 0.3

        if entities.years or entities.quarters or entities.months:
            scores[IntentType.FINANCIAL_QUERY] += 0.2

        if entities.amounts and any(
            kw in query_lower for kw in [
                "laptop", "computer", "monitor", "möbel", "gerät",  # German
                "furniture", "desk", "chair", "equipment", "device",  # English
            ]
        ):
            scores[IntentType.AFA_ASSIST] += 0.3

        if entities.categories:
            scores[IntentType.EXPENSE_CATEGORIZE] += 0.2

        # Find best intent
        best_intent = max(scores, key=scores.get)  # type: ignore
        best_score = scores[best_intent]

        # Fall back to general chat if no strong signal
        if best_score < 0.2:
            best_intent = IntentType.GENERAL_CHAT
            best_score = 0.5

        # Normalize confidence to 0-1 range
        confidence = min(1.0, best_score)

        # Generate reasoning
        reasoning = self._generate_reasoning(query, best_intent, scores, entities)

        # Suggest parameters based on intent
        suggested_params = self._suggest_params(best_intent, entities)

        return RoutingResult(
            intent=best_intent,
            confidence=confidence,
            entities=entities,
            reasoning=reasoning,
            suggested_params=suggested_params,
        )

    def _score_patterns(
        self,
        query: str,
        patterns: list[re.Pattern[str]],
    ) -> float:
        """Score query against pattern list.

        Args:
            query: Query text
            patterns: Compiled regex patterns

        Returns:
            Score (0.0 to 1.0+)
        """
        matches = sum(1 for p in patterns if p.search(query))
        # Normalize but allow > 1.0 for very strong matches
        return matches * 0.25

    def _extract_entities(self, query: str) -> ExtractedEntities:
        """Extract entities from query.

        Args:
            query: Query text

        Returns:
            ExtractedEntities
        """
        entities = ExtractedEntities()

        # Years
        for match in self.YEAR_PATTERN.finditer(query):
            year = int(match.group(1))
            if 2020 <= year <= 2030:  # Reasonable range
                entities.years.append(year)

        # Quarters
        for match in self.QUARTER_PATTERN.finditer(query):
            q = match.group(1) or match.group(2)
            entities.quarters.append(int(q))

        # Months (German and English)
        for match in self.MONTH_PATTERN.finditer(query):
            month_name = match.group(1).lower()
            if month_name in self._month_map:
                entities.months.append(self._month_map[month_name])

        # Amounts
        for match in self.AMOUNT_PATTERN.finditer(query):
            amount = match.group(1).replace(",", ".")
            entities.amounts.append(amount)

        # Law sections
        for match in self.SECTION_PATTERN.finditer(query):
            section = f"§ {match.group(1)}"
            if match.group(2):
                section += f" Abs. {match.group(2)}"
            if match.group(3):
                section += f" {match.group(3).upper()}"
            entities.law_sections.append(section)

        # Law types
        for match in self.LAW_PATTERN.finditer(query):
            law = match.group(1).upper()
            if law not in entities.law_types:
                entities.law_types.append(law)

        # Categories (German and English keywords)
        query_lower = query.lower()
        for category, keywords in self._category_keywords.items():
            if any(kw in query_lower for kw in keywords):
                entities.categories.append(category)

        return entities

    def _generate_reasoning(
        self,
        query: str,
        intent: IntentType,
        scores: dict[IntentType, float],
        entities: ExtractedEntities,
    ) -> str:
        """Generate human-readable reasoning for routing decision.

        Args:
            query: Original query
            intent: Selected intent
            scores: All intent scores
            entities: Extracted entities

        Returns:
            Reasoning string
        """
        reasons = []

        if intent == IntentType.TAX_LAW:
            if entities.law_sections:
                reasons.append(f"Found legal references: {', '.join(entities.law_sections)}")
            if entities.law_types:
                reasons.append(f"Mentions tax laws: {', '.join(entities.law_types)}")
            if not reasons:
                reasons.append("Query contains tax-related terminology")

        elif intent == IntentType.FINANCIAL_QUERY:
            if entities.years:
                reasons.append(f"References years: {', '.join(map(str, entities.years))}")
            if entities.quarters:
                reasons.append(f"References quarters: Q{', Q'.join(map(str, entities.quarters))}")
            if not reasons:
                reasons.append("Query requests financial data or reports")

        elif intent == IntentType.AFA_ASSIST:
            if entities.amounts:
                reasons.append(f"Contains purchase amounts: {', '.join(entities.amounts)} EUR")
            reasons.append("Query relates to depreciation or asset classification")

        elif intent == IntentType.EXPENSE_CATEGORIZE:
            if entities.categories:
                reasons.append(f"Detected categories: {', '.join(entities.categories)}")
            reasons.append("Query asks about expense categorization")

        elif intent == IntentType.INVOICE_RISK:
            reasons.append("Query relates to invoice or payment risk")

        else:  # GENERAL_CHAT
            reasons.append("No specific intent pattern detected")

        # Add confidence context
        other_scores = {k: v for k, v in scores.items() if k != intent and v > 0.1}
        if other_scores:
            alts = [f"{k.value}={v:.2f}" for k, v in sorted(other_scores.items(), key=lambda x: -x[1])[:2]]
            reasons.append(f"Alternative intents: {', '.join(alts)}")

        return "; ".join(reasons)

    def _suggest_params(
        self,
        intent: IntentType,
        entities: ExtractedEntities,
    ) -> dict[str, Any]:
        """Suggest parameters for the target agent.

        Args:
            intent: Selected intent
            entities: Extracted entities

        Returns:
            Parameter suggestions
        """
        params: dict[str, Any] = {}

        if intent == IntentType.TAX_LAW:
            if entities.law_types:
                params["source_types"] = [t.lower() for t in entities.law_types]
            if entities.law_sections:
                params["focus_sections"] = entities.law_sections
            if entities.categories:
                params["boost_categories"] = entities.categories

        elif intent == IntentType.FINANCIAL_QUERY:
            if entities.years:
                params["years"] = entities.years
            if entities.quarters:
                params["quarters"] = entities.quarters
            if entities.months:
                params["months"] = entities.months
            if entities.categories:
                params["categories"] = entities.categories

        elif intent == IntentType.AFA_ASSIST:
            if entities.amounts:
                # Use first amount as primary
                params["purchase_amount"] = entities.amounts[0]
            if entities.categories:
                params["suggested_category"] = entities.categories[0]

        elif intent == IntentType.EXPENSE_CATEGORIZE:
            if entities.amounts:
                params["amount"] = entities.amounts[0]
            if entities.categories:
                params["suggested_categories"] = entities.categories

        return params

    def get_intent_description(self, intent: IntentType) -> str:
        """Get human-readable description of intent.

        Args:
            intent: Intent type

        Returns:
            Description string
        """
        descriptions = {
            IntentType.TAX_LAW: "German tax law question (EStG, UStG, AO)",
            IntentType.FINANCIAL_QUERY: "Financial data query (invoices, expenses, reports)",
            IntentType.AFA_ASSIST: "Depreciation/AfA assistance",
            IntentType.EXPENSE_CATEGORIZE: "Expense categorization help",
            IntentType.INVOICE_RISK: "Invoice risk assessment",
            IntentType.GENERAL_CHAT: "General conversation",
        }
        return descriptions.get(intent, "Unknown intent")


# =============================================================================
# Singleton Instance
# =============================================================================

_router: SemanticRouter | None = None


def get_semantic_router() -> SemanticRouter:
    """Get or create the semantic router singleton."""
    global _router
    if _router is None:
        _router = SemanticRouter()
    return _router
