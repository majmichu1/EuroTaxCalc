"""
Unit tests for country tax configurations.

Validates tax calculations for each supported country
against known correct values derived from official tax rules.

Run with: python -m pytest tests/test_countries.py -v
"""

import pytest
from src.countries import get_country


class TestPoland:
    """Poland: 19% flat, FIFO, NBP rates."""

    def test_basic_tax(self):
        pl = get_country("PL")
        tax = pl.calculate_capital_gains_tax(10_000)
        assert abs(tax - 1900.0) < 0.01

    def test_loss_returns_zero(self):
        pl = get_country("PL")
        assert pl.calculate_capital_gains_tax(-500) == 0.0

    def test_dividend_tax(self):
        pl = get_country("PL")
        # 1000 * 0.19 - 150 foreign = 40
        assert abs(pl.calculate_dividend_tax(1000, 150) - 40.0) < 0.01

    def test_dividend_no_extra_if_foreign_exceeds(self):
        pl = get_country("PL")
        assert pl.calculate_dividend_tax(1000, 200) == 0.0

    def test_currency(self):
        pl = get_country("PL")
        assert pl.currency == "PLN"
        assert pl.rate_service == "NBP"


class TestGermany:
    """Germany: 25% Abgeltungssteuer + 5.5% Soli = 26.375%, €1,000 Sparerpauschbetrag."""

    def test_below_sparerpauschbetrag(self):
        """Profit below €1,000 allowance → 0 tax."""
        de = get_country("DE")
        assert de.calculate_capital_gains_tax(500) == 0.0
        assert de.calculate_capital_gains_tax(1000) == 0.0

    def test_above_sparerpauschbetrag_no_kirchensteuer(self):
        """€2,000 profit → taxable €1,000 * 25% * 1.055 = 263.75"""
        de = get_country("DE")
        de.extra["kirchensteuer"] = None
        tax = de.calculate_capital_gains_tax(2000)
        expected = 1000 * 0.25 * 1.055
        assert abs(tax - expected) < 0.01

    def test_kirchensteuer_8_percent(self):
        """Bayern/BW: base tax 250, Soli 13.75, KiSt 250*0.08 = 20 → total 283.75"""
        de = get_country("DE")
        de.extra["kirchensteuer"] = 0.08
        tax = de.calculate_capital_gains_tax(2000)
        base = 1000 * 0.25          # 250
        soli = base * 0.055          # 13.75
        kist = base * 0.08           # 20
        expected = base + soli + kist  # 283.75
        assert abs(tax - expected) < 0.01

    def test_kirchensteuer_9_percent(self):
        """Other Laender: base 250, Soli 13.75, KiSt 250*0.09 = 22.50 → 286.25"""
        de = get_country("DE")
        de.extra["kirchensteuer"] = 0.09
        tax = de.calculate_capital_gains_tax(2000)
        base = 1000 * 0.25
        soli = base * 0.055
        kist = base * 0.09
        expected = base + soli + kist
        assert abs(tax - expected) < 0.01

    def test_currency_and_source(self):
        de = get_country("DE")
        assert de.currency == "EUR"
        assert de.rate_service == "ECB"

    def test_dividend_tax_rate(self):
        de = get_country("DE")
        assert de.dividend_tax_rate == 0.25


class TestAustria:
    """Austria: 27.5% KESt flat rate."""

    def test_flat_27_5(self):
        at = get_country("AT")
        tax = at.calculate_capital_gains_tax(10_000)
        assert abs(tax - 2750.0) < 0.01

    def test_no_allowance(self):
        at = get_country("AT")
        # Even small profit taxed
        tax = at.calculate_capital_gains_tax(100)
        assert abs(tax - 27.5) < 0.01

    def test_zero_profit(self):
        at = get_country("AT")
        assert at.calculate_capital_gains_tax(0) == 0.0

    def test_dividend_27_5(self):
        at = get_country("AT")
        tax = at.calculate_dividend_tax(1000, 0)
        assert abs(tax - 275.0) < 0.01


class TestSpain:
    """Spain: progressive 19%-28% on base del ahorro."""

    def test_first_band(self):
        """€5,000 profit → 19%"""
        es = get_country("ES")
        tax = es.calculate_capital_gains_tax(5_000)
        assert abs(tax - 950.0) < 0.01

    def test_two_bands(self):
        """€10,000: 6000*19% + 4000*21% = 1140 + 840 = 1980"""
        es = get_country("ES")
        tax = es.calculate_capital_gains_tax(10_000)
        assert abs(tax - 1980.0) < 0.01

    def test_three_bands(self):
        """€60,000: 6000*19% + 44000*21% + 10000*23% = 1140 + 9240 + 2300 = 12680"""
        es = get_country("ES")
        tax = es.calculate_capital_gains_tax(60_000)
        expected = 6_000 * 0.19 + 44_000 * 0.21 + 10_000 * 0.23
        assert abs(tax - expected) < 0.01

    def test_top_band(self):
        """€400,000: all 5 bands"""
        es = get_country("ES")
        tax = es.calculate_capital_gains_tax(400_000)
        expected = (
            6_000 * 0.19 +
            44_000 * 0.21 +
            150_000 * 0.23 +
            100_000 * 0.27 +
            100_000 * 0.28
        )
        assert abs(tax - expected) < 0.01

    def test_no_allowance(self):
        es = get_country("ES")
        assert es.tax_free_allowance == 0.0


class TestBelgium:
    """Belgium: 0% CGT for normal management, 30% dividends."""

    def test_zero_cgt(self):
        be = get_country("BE")
        assert be.calculate_capital_gains_tax(100_000) == 0.0
        assert be.calculate_capital_gains_tax(1) == 0.0

    def test_dividend_30_percent(self):
        be = get_country("BE")
        tax = be.calculate_dividend_tax(1000, 0)
        assert abs(tax - 300.0) < 0.01

    def test_dividend_with_foreign_tax(self):
        be = get_country("BE")
        # 30% of 1000 = 300, already paid 150 → 150 more
        tax = be.calculate_dividend_tax(1000, 150)
        assert abs(tax - 150.0) < 0.01

    def test_interest_30_percent(self):
        be = get_country("BE")
        tax = be.calculate_interest_tax(1000)
        assert abs(tax - 300.0) < 0.01

    def test_has_tob_rates(self):
        be = get_country("BE")
        assert "tob_rates" in be.extra


class TestItaly:
    """Italy: 26% imposta sostitutiva flat."""

    def test_flat_26(self):
        it = get_country("IT")
        tax = it.calculate_capital_gains_tax(10_000)
        assert abs(tax - 2600.0) < 0.01

    def test_dividend_26(self):
        it = get_country("IT")
        tax = it.calculate_dividend_tax(1000, 0)
        assert abs(tax - 260.0) < 0.01

    def test_no_allowance(self):
        it = get_country("IT")
        assert it.tax_free_allowance == 0.0

    def test_filing_deadline(self):
        it = get_country("IT")
        assert "November" in it.filing_deadline


class TestCountryRegistry:
    """Test that all countries are properly registered."""

    def test_all_countries_present(self):
        from src.countries import get_all_countries
        countries = get_all_countries()
        for code in ["PL", "DE", "AT", "ES", "BE", "IT"]:
            assert code in countries, f"Country {code} not registered"

    def test_xml_export_only_poland(self):
        from src.countries import get_all_countries
        countries = get_all_countries()
        for code, country in countries.items():
            if code == "PL":
                assert country.has_xml_export is True
            else:
                assert country.has_xml_export is False

    def test_all_use_fifo(self):
        from src.countries import get_all_countries
        for code, country in get_all_countries().items():
            assert country.cost_method == "FIFO", f"{code} should use FIFO"

    def test_eurozone_use_ecb(self):
        from src.countries import get_all_countries
        for code, country in get_all_countries().items():
            if code == "PL":
                assert country.rate_service == "NBP"
            else:
                assert country.rate_service == "ECB"
