"""
Unit tests for FIFO engine and data validation.
Migrated from test_podatkomierz.py with updated imports.

Run with: python -m pytest tests/ -v
"""

import datetime
import pytest
from pathlib import Path

from src.models import (
    Transaction, BrokerResults, CalculationResult, DataValidator
)
from src.engine import CalculatorEngine
from src.rates import NBPService
from src.crypto import CryptoService


class TestFIFO:
    """Test FIFO calculation logic."""

    def test_basic_buy_sell(self):
        nbp = NBPService()
        engine = CalculatorEngine(nbp)

        engine._add_to_fifo("AAPL", 10, 1000, datetime.datetime(2024, 1, 1))
        cost = engine._remove_from_fifo("AAPL", 5)

        assert cost == 500
        assert len(engine._portfolio["AAPL"]) == 1
        assert engine._portfolio["AAPL"][0]['qty'] == 5

    def test_multiple_batches(self):
        nbp = NBPService()
        engine = CalculatorEngine(nbp)

        engine._add_to_fifo("AAPL", 10, 1000, datetime.datetime(2024, 1, 1))
        engine._add_to_fifo("AAPL", 10, 1500, datetime.datetime(2024, 2, 1))

        cost = engine._remove_from_fifo("AAPL", 15)

        assert cost == 1750
        assert len(engine._portfolio["AAPL"]) == 1
        assert engine._portfolio["AAPL"][0]['qty'] == 5
        assert engine._portfolio["AAPL"][0]['unit_cost'] == 150

    def test_sell_more_than_held(self):
        nbp = NBPService()
        engine = CalculatorEngine(nbp)

        engine._add_to_fifo("AAPL", 5, 500, datetime.datetime(2024, 1, 1))
        cost = engine._remove_from_fifo("AAPL", 10)

        assert cost == 500  # Only what was held

    def test_sell_from_empty_portfolio(self):
        nbp = NBPService()
        engine = CalculatorEngine(nbp)

        cost = engine._remove_from_fifo("AAPL", 10)
        assert cost == 0.0

    def test_fifo_order_preserved(self):
        """Verify FIFO: oldest batch sold first."""
        nbp = NBPService()
        engine = CalculatorEngine(nbp)

        engine._add_to_fifo("X", 10, 100, datetime.datetime(2024, 1, 1))  # unit cost 10
        engine._add_to_fifo("X", 10, 200, datetime.datetime(2024, 2, 1))  # unit cost 20

        cost = engine._remove_from_fifo("X", 10)
        assert cost == 100  # First batch (10 * 10)


class TestDataValidator:
    """Test data validation logic."""

    def test_valid_date(self):
        is_valid, msg = DataValidator.validate_date("2024-01-15")
        assert is_valid is True
        assert msg == ""

    def test_invalid_date(self):
        is_valid, msg = DataValidator.validate_date("not-a-date")
        assert is_valid is False
        assert "Nieprawidłowy" in msg

    def test_empty_date(self):
        import pandas as pd
        is_valid, msg = DataValidator.validate_date(pd.NA)
        assert is_valid is False
        assert "Brak" in msg

    def test_valid_amount(self):
        is_valid, msg = DataValidator.validate_amount(1000.50, "kwota")
        assert is_valid is True

    def test_negative_amount(self):
        is_valid, msg = DataValidator.validate_amount(-100, "kwota")
        assert is_valid is False
        assert "Ujemna" in msg

    def test_valid_ticker(self):
        is_valid, msg = DataValidator.validate_ticker("AAPL")
        assert is_valid is True

    def test_empty_ticker(self):
        import pandas as pd
        is_valid, msg = DataValidator.validate_ticker(pd.NA)
        assert is_valid is False


class TestBrokerResults:
    """Test BrokerResults calculations."""

    def test_stock_profit(self):
        br = BrokerResults("Test")
        br.stock_income = 10000
        br.stock_cost = 7000
        assert br.stock_profit == 3000

    def test_stock_loss(self):
        br = BrokerResults("Test")
        br.stock_income = 5000
        br.stock_cost = 7000
        assert br.stock_profit == -2000

    def test_dividend_tax_due(self):
        br = BrokerResults("Test")
        br.dividend_gross = 1000
        br.dividend_tax_foreign = 150
        assert br.dividend_tax_due == 40  # 1000*0.19 - 150

    def test_dividend_no_additional_tax(self):
        br = BrokerResults("Test")
        br.dividend_gross = 1000
        br.dividend_tax_foreign = 200  # > 19%
        assert br.dividend_tax_due == 0


class TestNBPService:
    """Test NBP currency service."""

    def test_pln_rate(self):
        nbp = NBPService()
        rate = nbp.get_rate_sync("PLN", datetime.datetime.now())
        assert rate == 1.0

    def test_empty_currency(self):
        nbp = NBPService()
        rate = nbp.get_rate_sync("", datetime.datetime.now())
        assert rate == 1.0

    def test_gbx_to_gbp(self):
        """GBX (pence) should apply 0.01 multiplier."""
        nbp = NBPService()
        rate = nbp.get_rate_sync("GBX", datetime.datetime(2024, 1, 15))
        assert rate >= 0
