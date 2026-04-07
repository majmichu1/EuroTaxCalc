"""
JSON export — backup/restore of calculation data.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models import CalculationResult


def export_to_json(result: CalculationResult, output_path: str = "backup_data.json") -> str:
    """Export all data to JSON for backup/restore."""
    data = {
        'timestamp': result.timestamp.isoformat(),
        'country_code': result.country_code,
        'base_currency': result.base_currency,
        't212': _broker_dict(result.t212),
        'ibkr': _broker_dict(result.ibkr),
        'total': _broker_dict(result.total),
        'total_tax': result.total_tax,
        'open_positions': result.open_positions,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path


def _broker_dict(broker) -> dict:
    return {
        'stock_income': broker.stock_income,
        'stock_cost': broker.stock_cost,
        'stock_profit': broker.stock_profit,
        'dividend_gross': broker.dividend_gross,
        'dividend_tax_foreign': broker.dividend_tax_foreign,
        'dividend_tax_due': broker.dividend_tax_due,
        'interest_gross': broker.interest_gross,
        'interest_tax_due': broker.interest_tax_due,
        'bonuses': broker.bonuses,
        'cashback': broker.cashback,
    }
