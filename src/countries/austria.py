"""
Austria — KESt (Kapitalertragsteuer) configuration.

Legal basis:
- EStG §27: Einkünfte aus Kapitalvermögen
- EStG §27a: Besonderer Steuersatz (27.5% flat rate since 2016)
- Previously: 25% until 2015

Effective rate: 27.5% flat (KESt)
- Applies to: shares, ETFs, bonds, dividends, interest
- No tax-free allowance for securities gains

Exchange rates: ECB reference rates (Oesterreichische Nationalbank publishes ECB rates)
Filing: E1kv (Beilage zur Einkommensteuererklärung E1)
Deadline: 30 June (electronic), 30 April (paper)

Broker handling: In Austria, regulated brokers (KESt-Abzug) often withhold
the tax automatically. In self-reporting (Veranlagung), taxpayer declares via E1kv.
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="AT",
    name_en="Austria",
    name_local="Oesterreich",
    flag="🇦🇹",
    currency="EUR",
    currency_symbol="€",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=float('inf'), rate=0.275),  # 27.5% KESt
    ],
    dividend_tax_rate=0.275,
    interest_tax_rate=0.275,
    tax_free_allowance=0.0,
    rate_service="ECB",
    tax_form_name="E1kv",
    filing_deadline="30 June (electronic) / 30 April (paper)",
    tax_authority_url="https://www.bmf.gv.at",
    extra={
        # KESt is a final withholding tax (Endbesteuerungswirkung)
        # Losses within same year can offset capital gains (same category)
        "loss_offset_same_year": True,

        # Government bonds (Bundesanleihen) taxed at same 27.5% rate
        # Unlike Italy which has 12.5% for govt bonds
        "govt_bond_rate": 0.275,
    },
)

register_country(config)
