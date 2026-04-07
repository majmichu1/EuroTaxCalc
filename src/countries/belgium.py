"""
Belgium — Capital gains tax configuration.

Legal basis:
- CIR/92 Art. 90, 9°: Capital gains from private management = 0% tax
- CIR/92 Art. 90, 1°: Speculative gains = 33% (rarely applied to stock investors)
- CIR/92 Art. 171: Dividends withheld at 30% (roerende voorheffing / precompte mobilier)

Capital gains for PRIVATE investors:
- ZERO tax on gains from "normal management of private patrimony" (normal beheer)
- 33% if classified as "speculative" — extremely rare for buy-and-hold investors
  who use regulated brokers with diversified portfolios

Dividend tax: 30% withholding tax (roerende voorheffing)
- Applied at source by Belgian companies
- Foreign dividends: declare and pay 30% (minus treaty credits)
- First €800 of dividends from Belgian shares: 0% (vrijstelling, subject to change)

TOB (Taxe sur les Operations de Bourse / Beurstaks):
- Transaction tax on trades (not income tax) — see extra["tob_rates"]
- Paid at time of transaction, tracked separately from income tax

Exchange rates: ECB reference rates
Filing: Tax-on-web (online), deadline 30 June (electronic) / 30 June (paper)
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="BE",
    name_en="Belgium",
    name_local="Belgie / Belgique",
    flag="🇧🇪",
    currency="EUR",
    currency_symbol="€",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=float('inf'), rate=0.0),  # 0% for normal management
    ],
    dividend_tax_rate=0.30,    # 30% roerende voorheffing
    interest_tax_rate=0.30,    # 30% on interest
    tax_free_allowance=0.0,
    rate_service="ECB",
    tax_form_name="Tax-on-web",
    filing_deadline="30 June (electronic)",
    tax_authority_url="https://finances.belgium.be",
    extra={
        # Speculative rate: 33% + communal surcharge (if gains deemed speculative)
        # In practice, this almost never applies to diversified stock investors
        "speculative_rate": 0.33,

        # TOB (Beurstaks) — transaction tax rates by security type
        # Paid per trade, not an income tax — informational only
        "tob_rates": {
            "stocks_etf_dist": 0.0035,   # 0.35% on individual stocks & distributing ETFs
            "etf_acc": 0.0132,           # 1.32% on accumulating ETFs (taxed as 'capitalization')
            "bonds": 0.0012,             # 0.12% on bonds
        },

        # Annual securities account tax: 0.15% if total account value > €1,000,000
        "securities_account_tax_rate": 0.0015,
        "securities_account_threshold": 1_000_000,

        # Belgian shares: first €800 of dividends exempt (annually, subject to change)
        "dividend_exemption_belgian_shares": 800.0,
    },
)

register_country(config)
