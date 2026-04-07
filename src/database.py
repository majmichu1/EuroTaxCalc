"""
HistoryDatabase — SQLite storage for past calculation results.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models import CalculationResult


class HistoryDatabase:
    def __init__(self, db_path: Path | str = "tax_history.db"):
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calculations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    t212_path TEXT,
                    ibkr_path TEXT,
                    stock_income REAL,
                    stock_cost REAL,
                    dividend_gross REAL,
                    dividend_tax_foreign REAL,
                    interest_gross REAL,
                    total_tax REAL,
                    bonuses REAL,
                    cashback REAL,
                    country_code TEXT DEFAULT 'PL'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON calculations(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_total_tax ON calculations(total_tax)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_income ON calculations(stock_income)")
            # Add country_code column if upgrading from old schema
            try:
                conn.execute("ALTER TABLE calculations ADD COLUMN country_code TEXT DEFAULT 'PL'")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def save_calculation(self, result: CalculationResult) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO calculations
                (timestamp, t212_path, ibkr_path, stock_income, stock_cost,
                 dividend_gross, dividend_tax_foreign, interest_gross,
                 total_tax, bonuses, cashback, country_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.timestamp.isoformat(),
                str(result.t212_path) if result.t212_path else None,
                str(result.ibkr_path) if result.ibkr_path else None,
                result.total.stock_income,
                result.total.stock_cost,
                result.total.dividend_gross,
                result.total.dividend_tax_foreign,
                result.total.interest_gross,
                result.total_tax,
                result.total.bonuses,
                result.total.cashback,
                result.country_code,
            ))
            return cursor.lastrowid

    def get_all_calculations(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM calculations ORDER BY timestamp DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_calculation(self, calc_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM calculations WHERE id = ?", (calc_id,))
            return cursor.rowcount > 0

    def get_calculation(self, calc_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM calculations WHERE id = ?", (calc_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def restore_calculation(self, calc_data: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO calculations
                (timestamp, t212_path, ibkr_path, stock_income, stock_cost,
                 dividend_gross, dividend_tax_foreign, interest_gross,
                 total_tax, bonuses, cashback, country_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                calc_data.get('timestamp', ''),
                calc_data.get('t212_path', ''),
                calc_data.get('ibkr_path', ''),
                calc_data.get('stock_income', 0),
                calc_data.get('stock_cost', 0),
                calc_data.get('dividend_gross', 0),
                calc_data.get('dividend_tax_foreign', 0),
                calc_data.get('interest_gross', 0),
                calc_data.get('total_tax', 0),
                calc_data.get('bonuses', 0),
                calc_data.get('cashback', 0),
                calc_data.get('country_code', 'PL'),
            ))
