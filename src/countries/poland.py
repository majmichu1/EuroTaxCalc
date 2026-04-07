"""
Poland — PIT-38 capital gains tax configuration.

Legal basis: Ustawa o podatku dochodowym od osób fizycznych (updof)
- Art. 30b: 19% flat tax on capital gains
- Art. 39: exchange rates from NBP (previous business day)
- Filing: PIT-38, deadline 30 April of following year
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="PL",
    name_en="Poland",
    name_local="Polska",
    flag="🇵🇱",
    currency="PLN",
    currency_symbol="zł",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=float('inf'), rate=0.19),  # 19% flat
    ],
    dividend_tax_rate=0.19,
    interest_tax_rate=0.19,
    tax_free_allowance=0.0,
    rate_service="NBP",
    tax_form_name="PIT-38",
    filing_deadline="30 April",
    tax_authority_url="https://www.podatki.gov.pl",
    extra={
        "loss_carryforward_years": 5,  # Art. 9 ust. 3 updof
    },
)

register_country(config)
