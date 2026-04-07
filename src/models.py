"""
Data models, constants, and validators for EuroTaxCalc.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import pandas as pd

# =============================================================================
# APP CONSTANTS
# =============================================================================

APP_VERSION = "2.0.0"
APP_NAME = "EuroTaxCalc"
CURRENT_DATE = datetime.date.today()
APP_YEAR = CURRENT_DATE.year - 1  # Settle previous year (e.g. in 2026 → 2025)

# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class Transaction:
    """Single transaction record."""
    date: datetime.datetime
    ticker: str
    tx_type: str       # 'BUY' or 'SELL'
    qty: float
    total_pln: float   # Always stored in base currency of the country
    source: str        # 'T212', 'IBKR', etc.
    unit_price_pln: float = 0.0

    def __post_init__(self):
        if self.qty > 0:
            self.unit_price_pln = self.total_pln / self.qty


@dataclass
class BrokerResults:
    name: str
    stock_income: float = 0.0
    stock_cost: float = 0.0
    dividend_gross: float = 0.0
    dividend_tax_foreign: float = 0.0
    interest_gross: float = 0.0
    interest_tax_foreign: float = 0.0
    bonuses: float = 0.0
    cashback: float = 0.0

    @property
    def stock_profit(self) -> float:
        return self.stock_income - self.stock_cost

    @property
    def dividend_tax_due(self) -> float:
        return max(0, self.dividend_gross * 0.19 - self.dividend_tax_foreign)

    @property
    def interest_tax_due(self) -> float:
        return max(0, self.interest_gross * 0.19 - self.interest_tax_foreign)


@dataclass
class CalculationResult:
    t212: BrokerResults
    ibkr: BrokerResults
    total: BrokerResults
    transactions: list[Transaction] = field(default_factory=list)
    open_positions: list[dict] = field(default_factory=list)
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    t212_path: str = ""
    ibkr_path: str = ""
    generic_brokers: dict = field(default_factory=dict)
    country_code: str = "PL"
    base_currency: str = "PLN"

    @property
    def total_tax_pit38(self) -> float:
        """Legacy property — used by Polish PIT-38 export."""
        stock_tax = max(0, self.total.stock_profit * 0.19)
        return stock_tax + self.total.dividend_tax_due + self.total.interest_tax_due

    @property
    def total_tax(self) -> float:
        """Country-aware total tax. Delegated to CountryConfig when available."""
        try:
            from src.countries import get_country
            country = get_country(self.country_code)
            stock_tax = country.calculate_capital_gains_tax(self.total.stock_profit)
            div_tax = country.calculate_dividend_tax(
                self.total.dividend_gross, self.total.dividend_tax_foreign
            )
            int_tax = max(0, self.total.interest_gross * country.interest_tax_rate)
            return stock_tax + div_tax + int_tax
        except Exception:
            return self.total_tax_pit38


# =============================================================================
# DATA VALIDATOR
# =============================================================================

class DataValidator:
    """Validates CSV data and provides helpful error messages."""

    @staticmethod
    def validate_date(date_val) -> tuple[bool, str]:
        if pd.isna(date_val):
            return False, "Brak daty"
        try:
            pd.to_datetime(date_val)
            return True, ""
        except Exception:
            return False, f"Nieprawidłowy format daty: {date_val}"

    @staticmethod
    def validate_amount(amount_val, field_name: str = "kwota") -> tuple[bool, str]:
        if pd.isna(amount_val):
            return False, f"Brak {field_name}"
        try:
            val = float(amount_val)
            if val < 0:
                return False, f"Ujemna {field_name}: {val}"
            return True, ""
        except Exception:
            return False, f"Nieprawidłowa {field_name}: {amount_val}"

    @staticmethod
    def validate_ticker(ticker_val) -> tuple[bool, str]:
        if pd.isna(ticker_val) or not str(ticker_val).strip():
            return False, "Brak tickera/symbolu"
        ticker = str(ticker_val).strip()
        if len(ticker) > 20:
            return False, f"Ticker zbyt długi: {ticker}"
        return True, ""

    @staticmethod
    def validate_currency(currency_val) -> tuple[bool, str]:
        valid_currencies = [
            'PLN', 'USD', 'EUR', 'GBP', 'CHF', 'SEK', 'NOK', 'DKK',
            'CAD', 'AUD', 'JPY', 'HKD', 'SGD', 'GBX', 'CZK', 'HUF'
        ]
        if pd.isna(currency_val) or not str(currency_val).strip():
            return True, ""  # defaults to USD
        curr = str(currency_val).upper().strip()
        if curr not in valid_currencies:
            return False, f"Nieznana waluta: {curr}"
        return True, ""

    @staticmethod
    def validate_csv_structure(df, broker: str) -> list[str]:
        warnings = []
        if len(df) == 0:
            warnings.append("Plik CSV jest pusty")
            return warnings
        if broker == 'T212':
            for col in ['Time', 'Action', 'Total']:
                if col not in df.columns:
                    warnings.append(f"Brak wymaganej kolumny: {col}")
        if len(df) > 10000:
            warnings.append(
                f"Bardzo dużo wierszy ({len(df)}) - obliczenia mogą potrwać dłużej"
            )
        return warnings
