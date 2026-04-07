"""
Italy — Imposta sostitutiva capital gains tax configuration.

Legal basis:
- TUIR Art. 67: Redditi diversi (capital gains as 'other income')
- TUIR Art. 68: Tax base calculation — FIFO method in regime dichiarativo
- D.Lgs. 461/1997: Imposta sostitutiva del 26% (since July 2014)
  Previously: 20% (2012-2014), 12.5% (before 2012)

Regime options:
1. Regime dichiarativo (self-reporting): taxpayer calculates tax, reports in Redditi PF
2. Regime amministrato: broker withholds tax automatically (most common for Italian residents)
3. Regime gestito: managed portfolio — broker reports

This app implements regime dichiarativo (option 1).

FIFO method: Standard for regime dichiarativo (Art. 68 TUIR)

Special rates:
- Standard securities: 26% imposta sostitutiva
- Italian/EU/EEA government bonds: 12.5% (Titoli di Stato)

Exchange rates: ECB reference rates (Banca d'Italia publishes ECB rates)
Filing: Modello Redditi PF (quadro RT), deadline 30 November
Loss carry-forward: 4 years (same type of income only)
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="IT",
    name_en="Italy",
    name_local="Italia",
    flag="🇮🇹",
    currency="EUR",
    currency_symbol="€",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=float('inf'), rate=0.26),  # 26% imposta sostitutiva
    ],
    dividend_tax_rate=0.26,    # 26% on dividends from non-Italian companies
    interest_tax_rate=0.26,    # 26% on interest (12.5% for govt bonds)
    tax_free_allowance=0.0,
    rate_service="ECB",
    tax_form_name="Modello Redditi PF (quadro RT)",
    filing_deadline="30 November",
    tax_authority_url="https://www.agenziaentrate.gov.it",
    extra={
        # Regime: 'dichiarativo' (self-report) or 'amministrato' (broker withholds)
        "regime": "dichiarativo",

        # Italian/EU/EEA government bonds taxed at reduced 12.5%
        # (not directly implemented — shown as disclaimer)
        "govt_bond_rate": 0.125,

        # Loss carry-forward: 4 years, same category only (quadro RT)
        "loss_carryforward_years": 4,

        # Tobin Tax (Imposta sulle Transazioni Finanziarie - ITF):
        # 0.2% on Italian shares traded on non-regulated markets
        # 0.1% on Italian shares on regulated markets
        # Informational only
        "itf_rates": {
            "regulated_market": 0.001,   # 0.1%
            "unregulated_market": 0.002, # 0.2%
        },
    },
)

register_country(config)
