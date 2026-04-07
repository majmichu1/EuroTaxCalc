"""
Germany — Abgeltungssteuer capital gains tax configuration.

Legal basis:
- EStG §20: Kapitalertragsteuer (capital income tax)
- EStG §32d: Abgeltungsteuersatz (25% flat rate)
- EStG §43: Quellensteuer (withholding)
- §3 Nr. 26a EStG: Sparerpauschbetrag (€1,000/person since 2023)

Effective rates:
- Without Kirchensteuer: 25% × 1.055 = 26.375%
- With KiSt 8% (Bayern, Baden-Wuerttemberg): ~27.82%
- With KiSt 9% (all other Laender): ~27.99%

Exchange rates: ECB reference rates (published by Deutsche Bundesbank)
Filing: Anlage KAP with Einkommensteuererklärung, deadline 31 July

NOTE: Loss offset restriction — stock losses (§20 Abs. 2 EStG) can ONLY be
offset against other stock gains (Verlustverrechnungstopf für Aktien).
This is tracked as extra["loss_offset_stocks_only"].
"""

from src.countries import CountryConfig, TaxBand, register_country

config = CountryConfig(
    code="DE",
    name_en="Germany",
    name_local="Deutschland",
    flag="🇩🇪",
    currency="EUR",
    currency_symbol="€",
    cost_method="FIFO",
    capital_gains_bands=[
        TaxBand(threshold=float('inf'), rate=0.25),  # 25% Abgeltungssteuer
    ],
    dividend_tax_rate=0.25,    # Also Abgeltungssteuer
    interest_tax_rate=0.25,
    tax_free_allowance=1000.0,  # Sparerpauschbetrag: €1,000/person (€2,000 joint) since 2023
    rate_service="ECB",
    tax_form_name="Anlage KAP",
    filing_deadline="31 July",
    tax_authority_url="https://www.bundesfinanzministerium.de",
    extra={
        # Solidaritaetszuschlag: 5.5% on top of Abgeltungssteuer
        # Applied when taxable income > threshold (most investors pay it)
        "solidaritaetszuschlag": True,

        # Kirchensteuer: set to None (disabled) or 0.08 (Bayern/BW) or 0.09 (rest)
        # User can change this in Settings
        "kirchensteuer": None,

        # Sparerpauschbetrag for joint filers (married couples)
        "sparerpauschbetrag_joint": 2000.0,

        # Loss offset restriction: stock losses can ONLY offset stock gains
        # EStG §20 Abs. 6 Satz 5 (since 2020)
        "loss_offset_stocks_only": True,
    },
)

register_country(config)
