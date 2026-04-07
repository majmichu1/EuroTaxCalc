"""
UniversalCSVParser — auto-detects broker CSV format and parses transactions.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd

from src.crypto import CryptoService


class UniversalCSVParser:
    """
    Universal CSV parser that auto-detects column mappings for any broker.
    Supports: T212, IBKR, Revolut, eToro, XTB, Degiro, and many more.
    """

    COLUMN_PATTERNS = {
        'date': ['time', 'date', 'trade date', 'dateandtime', 'timestamp', 'execution time', 'data', 'datum'],
        'ticker': ['ticker', 'symbol', 'instrument', 'isin', 'name', 'asset', 'stock', 'produkt'],
        'action': ['action', 'type', 'side', 'operation', 'transaction type', 'order type', 'rodzaj'],
        'quantity': ['quantity', 'qty', 'shares', 'amount', 'units', 'liczba', 'sztuk', 'no. of shares'],
        'price': ['price', 'unit price', 'price / share', 'price per share', 'execution price', 'kurs', 'cena'],
        'total': ['total', 'total amount', 'net amount', 'value', 'total value', 'amount', 'wartość'],
        'currency': ['currency', 'currency (total)', 'ccy', 'waluta'],
        'commission': ['commission', 'fee', 'fees', 'charges', 'prowizja'],
    }

    BUY_KEYWORDS = ['buy', 'market buy', 'limit buy', 'kupno', 'kup', 'purchase', 'bought']
    SELL_KEYWORDS = ['sell', 'market sell', 'limit sell', 'sprzedaż', 'sprzedaj', 'sold']

    def __init__(self, crypto_service: CryptoService | None = None):
        self._detected_columns: dict[str, str] = {}
        self.crypto = crypto_service

    def detect_columns(self, df: pd.DataFrame) -> dict[str, str]:
        detected = {}
        headers_lower = {col: col.lower().strip() for col in df.columns}
        for field, patterns in self.COLUMN_PATTERNS.items():
            for col, col_lower in headers_lower.items():
                if any(pattern in col_lower for pattern in patterns):
                    detected[field] = col
                    break
        self._detected_columns = detected
        return detected

    def validate_csv(self, df: pd.DataFrame, file_path: str) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        if df.empty:
            return False, ["CSV file is empty"]
        if len(df) > 50000:
            warnings.append(f"Very large file ({len(df)} rows) — processing may be slow")
        if 'date' not in self._detected_columns:
            return False, ["Could not detect date column. Check CSV format."]
        if 'ticker' not in self._detected_columns:
            return False, ["Could not detect ticker/symbol column."]
        if 'action' not in self._detected_columns:
            warnings.append("Could not detect transaction type column — some rows may be skipped")
        try:
            date_col = self._detected_columns.get('date', '')
            if date_col:
                dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                if len(dates) > 0:
                    if dates.min().year < 2010:
                        warnings.append(f"Very old dates detected (from {dates.min().year})")
                    if dates.max().year > datetime.datetime.now().year:
                        warnings.append(f"Future dates detected ({dates.max().year})")
        except Exception:
            pass
        return True, warnings

    def parse_csv(self, file_path: str, rate_service) -> list[dict]:
        transactions: list[dict] = []
        try:
            fp = Path(file_path)
            if not fp.exists() or fp.stat().st_size == 0:
                return []
            if fp.stat().st_size > 50 * 1024 * 1024:
                print(f"[Parser] File too large: {file_path}")
                return []

            df = None
            for enc in ['utf-8', 'latin1', 'cp1250', 'utf-8-sig']:
                try:
                    df = pd.read_csv(file_path, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                return []

            columns = self.detect_columns(df)
            if 'date' not in columns or 'ticker' not in columns:
                print(f"[Parser] Required columns not found in {file_path}")
                return []

            is_valid, warnings = self.validate_csv(df, file_path)
            for w in warnings:
                print(f"[Parser] Warning: {w}")
            if not is_valid:
                return []

            source = self._detect_broker(file_path, columns, df)
            print(f"[Parser] Processing {len(df)} rows from {file_path} (broker: {source})")

            for _, row in df.iterrows():
                try:
                    date_val = row.get(columns.get('date', ''))
                    if pd.isna(date_val):
                        continue
                    try:
                        tx_date = pd.to_datetime(date_val)
                    except Exception:
                        continue

                    ticker = str(row.get(columns.get('ticker', ''), '')).strip()
                    if not ticker or pd.isna(row.get(columns.get('ticker', ''))):
                        continue

                    action_col = columns.get('action', '')
                    if action_col:
                        action_str = str(row.get(action_col, '')).lower()
                        if any(kw in action_str for kw in self.BUY_KEYWORDS):
                            tx_type = 'BUY'
                        elif any(kw in action_str for kw in self.SELL_KEYWORDS):
                            tx_type = 'SELL'
                        else:
                            continue
                    else:
                        continue

                    qty = 0.0
                    if columns.get('quantity'):
                        qty_val = row.get(columns['quantity'])
                        if pd.notna(qty_val):
                            qty = abs(float(qty_val))
                    if qty <= 0:
                        continue

                    total = 0.0
                    if columns.get('total'):
                        total_val = row.get(columns['total'])
                        if pd.notna(total_val):
                            total = abs(float(total_val))
                    elif columns.get('price'):
                        price_val = row.get(columns['price'])
                        if pd.notna(price_val):
                            total = abs(float(price_val)) * qty
                    if total <= 0:
                        continue

                    currency = 'USD'
                    if columns.get('currency'):
                        curr_val = row.get(columns['currency'])
                        if pd.notna(curr_val):
                            currency = str(curr_val).upper().strip()

                    rate = 1.0
                    if self.crypto and currency in self.crypto.SUPPORTED:
                        rate = self.crypto.get_price_pln(currency, tx_date)
                    else:
                        rate = rate_service.get_rate_sync(currency, tx_date)

                    total_pln = total * rate

                    transactions.append({
                        'date': tx_date,
                        'ticker': ticker,
                        'type': tx_type,
                        'qty': qty,
                        'total_pln': total_pln,
                        'currency': currency,
                        'source': source,
                    })
                except Exception:
                    continue

        except Exception as e:
            print(f"[Parser] Error parsing {file_path}: {e}")

        return transactions

    def _detect_broker(self, file_path: str, columns: dict, df: pd.DataFrame) -> str:
        fl = file_path.lower()

        # Poland
        if 'xtb' in fl:
            return 'XTB'
        elif 'mbank' in fl or 'mbrokerage' in fl:
            return 'mBank'
        elif 'bossa' in fl:
            return 'BOŚ Bossa'
        elif 'cdm' in fl or 'pekao' in fl:
            return 'CDM Pekao'
        elif 'exante' in fl:
            return 'Exante'

        # International
        elif 'trading212' in fl or 't212' in fl:
            return 'T212'
        elif 'ibkr' in fl or 'interactive' in fl:
            return 'IBKR'
        elif 'revolut' in fl:
            return 'Revolut'
        elif 'etoro' in fl:
            return 'eToro'
        elif 'degiro' in fl:
            return 'Degiro'
        elif 'saxo' in fl:
            return 'Saxo'
        elif 'freedom' in fl:
            return 'Freedom24'
        elif 'flatex' in fl:
            return 'flatex'
        elif 'trade republic' in fl or 'traderepublic' in fl:
            return 'Trade Republic'
        elif 'scalable' in fl:
            return 'Scalable Capital'
        elif 'ing' in fl:
            return 'ING'
        elif 'comdirect' in fl:
            return 'comdirect'
        elif 'swissquote' in fl:
            return 'Swissquote'
        elif 'fineco' in fl:
            return 'Fineco'
        elif 'binck' in fl:
            return 'BinckBank'
        elif 'bolero' in fl:
            return 'Bolero'

        # US brokers
        elif 'schwab' in fl:
            return 'Charles Schwab'
        elif 'fidelity' in fl:
            return 'Fidelity'
        elif 'tdameritrade' in fl or 'td ameritrade' in fl:
            return 'TD Ameritrade'
        elif 'robinhood' in fl:
            return 'Robinhood'
        elif 'webull' in fl:
            return 'Webull'
        elif 'tastyworks' in fl or 'tastytrade' in fl:
            return 'Tastytrade'
        elif 'merrill' in fl:
            return 'Merrill Lynch'
        elif 'vanguard' in fl:
            return 'Vanguard'
        elif 'etrade' in fl or 'e-trade' in fl:
            return 'E*TRADE'

        return 'OTHER'
