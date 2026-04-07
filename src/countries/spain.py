"""
Spain — IRPF (Impuesto sobre la Renta de las Personas Fisicas) configuration.

Legal basis:
- LIRPF Art. 46: Renta del ahorro (savings income)
- LIRPF Art. 49: Tax rates for savings income (base del ahorro)
- LIRPF Art. 35: FIFO method for stock cost basis

Progressive rates on base del ahorro (2025):
  €0 – €6,000:         19%
  €6,001 – €50,000:    21%
  €50,001 – €200,000:  23%
  €200,001 – €300,000: 27%
  > €300,000:          28%

Same progressive rates apply to: capital gains, dividends, interest.

Exchange rates: Official ECB reference rates published by Banco de Espana
Filing: Modelo 100 (Declaracion de IRPF), deadline 30 June
Foreign assets > €50,000: Modelo 720 declaration required

Loss carry-forward: 4 years (Art. 49 LIRPF)
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="ES",
    name_en="Spain",
    name_local="Espana",
    flag="🇪🇸",
    currency="EUR",
    currency_symbol="€",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=6_000,       rate=0.19),
        TaxBand(threshold=50_000,      rate=0.21),
        TaxBand(threshold=200_000,     rate=0.23),
        TaxBand(threshold=300_000,     rate=0.27),
        TaxBand(threshold=float('inf'), rate=0.28),
    ],
    dividend_tax_rate=0.19,    # First €6k at 19%; same progressive table applies
    interest_tax_rate=0.19,
    tax_free_allowance=0.0,
    rate_service="ECB",
    tax_form_name="Modelo 100 (IRPF)",
    filing_deadline="30 June",
    tax_authority_url="https://sede.agenciatributaria.gob.es",
    extra={
        "loss_carryforward_years": 4,

        # Modelo 720: declaration required for foreign assets > €50,000
        # (not a tax, but mandatory reporting with penalties for non-compliance)
        "modelo_720_threshold": 50_000,

        # Dividend tax uses same progressive bands (base del ahorro)
        # — dividend_tax_rate above is only the first-band rate for display
        "dividend_uses_progressive_bands": True,
    },
)

register_country(config)
