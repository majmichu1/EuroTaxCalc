"""
Country tax configuration system.

Each country is defined in its own module (poland.py, germany.py, etc.)
and registered in the global registry on import.

To add a new country, create e.g. src/countries/slovenia.py following the
same pattern, then import it here at the bottom of this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaxBand:
    """A single bracket in a progressive tax system."""
    threshold: float   # Upper limit of this band (float('inf') for the last one)
    rate: float        # Tax rate, e.g. 0.19 = 19%


@dataclass
class CountryConfig:
    """
    Complete tax configuration for one country.

    All monetary values in the country's base currency (PLN for Poland, EUR for eurozone).
    """
    code: str                          # ISO 3166-1 alpha-2, e.g. "PL", "DE"
    name_en: str                       # English name
    name_local: str                    # Local name
    flag: str                          # Emoji flag
    currency: str                      # "PLN" or "EUR"
    currency_symbol: str               # "zł" or "€"

    # Calculation method
    cost_method: str                   # "FIFO" (all 6 countries use FIFO)

    # Capital gains tax bands (progressive or single flat rate)
    capital_gains_bands: list[TaxBand]

    # Other income tax rates
    dividend_tax_rate: float           # e.g. 0.19 = 19%
    interest_tax_rate: float           # e.g. 0.19 = 19%

    # Annual tax-free allowance on capital gains
    tax_free_allowance: float          # e.g. 1000 for Germany, 0 for Poland

    # Exchange rate data source
    rate_service: str                  # "NBP" or "ECB"

    # Filing information
    tax_form_name: str                 # e.g. "PIT-38", "Anlage KAP"
    filing_deadline: str               # Human-readable, e.g. "30 April"
    tax_authority_url: str             # Official tax authority URL

    # Country-specific extra options
    extra: dict = field(default_factory=dict)

    # -------------------------------------------------------------------------
    # Tax calculation methods
    # -------------------------------------------------------------------------

    def calculate_capital_gains_tax(self, profit: float) -> float:
        """
        Calculate capital gains tax on realised profit.

        Applies tax-free allowance first, then progressive bands,
        then any country-specific surcharges (Soli, Kirchensteuer).
        """
        if profit <= 0:
            return 0.0

        taxable = max(0.0, profit - self.tax_free_allowance)
        if taxable <= 0:
            return 0.0

        tax = 0.0
        remaining = taxable
        prev_threshold = 0.0

        for band in self.capital_gains_bands:
            band_amount = min(remaining, band.threshold - prev_threshold)
            tax += band_amount * band.rate
            remaining -= band_amount
            prev_threshold = band.threshold
            if remaining <= 0:
                break

        # Germany: Solidaritaetszuschlag (5.5% on top of Abgeltungssteuer)
        if self.extra.get("solidaritaetszuschlag"):
            tax *= 1.055

        # Germany: Kirchensteuer (church tax, 8% or 9% of base tax)
        kirchensteuer = self.extra.get("kirchensteuer")
        if kirchensteuer:
            # KiSt is calculated on the base 25% tax, NOT on Soli-inflated amount
            base_tax = taxable * self.capital_gains_bands[0].rate
            tax += base_tax * kirchensteuer

        return round(tax, 2)

    def calculate_dividend_tax(self, gross: float, foreign_tax_paid: float) -> float:
        """
        Calculate additional dividend tax after crediting foreign tax already paid.
        """
        if gross <= 0:
            return 0.0
        domestic_tax = gross * self.dividend_tax_rate
        return max(0.0, round(domestic_tax - foreign_tax_paid, 2))

    def calculate_interest_tax(self, gross: float) -> float:
        if gross <= 0:
            return 0.0
        return round(gross * self.interest_tax_rate, 2)

    def format_currency(self, value: float) -> str:
        """Format a monetary value in the country's currency."""
        if self.currency == "PLN":
            return f"{value:,.2f} {self.currency_symbol}"
        return f"{self.currency_symbol}{value:,.2f}"

    @property
    def effective_cgt_rate_display(self) -> str:
        """Human-readable effective CGT rate for display."""
        if len(self.capital_gains_bands) == 1:
            base = self.capital_gains_bands[0].rate * 100
            if self.extra.get("solidaritaetszuschlag"):
                total = base * 1.055
                return f"{total:.3f}% ({base:.0f}% + 5.5% Soli)"
            return f"{base:.1f}%"
        rates = [f"{b.rate * 100:.0f}%" for b in self.capital_gains_bands]
        return f"{rates[0]}-{rates[-1]}"

    @property
    def has_xml_export(self) -> bool:
        """Only Poland has KAS-compliant XML export."""
        return self.code == "PL"


# =============================================================================
# Country Registry
# =============================================================================

_countries: dict[str, CountryConfig] = {}


def register_country(config: CountryConfig) -> None:
    _countries[config.code] = config


def get_country(code: str) -> CountryConfig:
    if code not in _countries:
        raise KeyError(f"Country '{code}' not registered. Available: {list(_countries.keys())}")
    return _countries[code]


def get_all_countries() -> dict[str, CountryConfig]:
    return dict(_countries)


# Auto-register all supported countries on import
from src.countries import poland, germany, austria, spain, belgium, italy  # noqa: E402, F401
