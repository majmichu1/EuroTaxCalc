"""
CalculatorEngine — FIFO-based tax calculation engine.

DO NOT MODIFY THE FIFO CALCULATION LOGIC (_add_to_fifo, _remove_from_fifo).
This logic has been verified for tax compliance.
"""

from __future__ import annotations

import csv
import datetime
import time
from collections import deque
from pathlib import Path
from typing import Callable

import pandas as pd

from src.models import BrokerResults, CalculationResult, Transaction
from src.rates import NBPService, ECBService
from src.crypto import CryptoService


class CalculatorEngine:
    """Tax calculation engine using FIFO method. DO NOT MODIFY THE CALCULATION LOGIC."""

    def __init__(self, nbp_service: NBPService, crypto_service: CryptoService = None):
        self.nbp = nbp_service
        self.crypto = crypto_service
        self._portfolio: dict[str, deque] = {}
        self._progress_callback: Callable[[str, float], None] | None = None

    def set_progress_callback(self, callback: Callable[[str, float], None]):
        self._progress_callback = callback

    def _report_progress(self, message: str, progress: float):
        if self._progress_callback:
            self._progress_callback(message, progress)

    # -------------------------------------------------------------------------
    # FIFO CORE — DO NOT MODIFY
    # -------------------------------------------------------------------------

    def _add_to_fifo(self, ticker: str, qty: float, total_cost_pln: float, purchase_date: datetime.datetime):
        if qty <= 0:
            return
        if ticker not in self._portfolio:
            self._portfolio[ticker] = deque()
        cost_per_share = total_cost_pln / qty
        self._portfolio[ticker].append({'qty': qty, 'unit_cost': cost_per_share, 'date': purchase_date})

    def _remove_from_fifo(self, ticker: str, qty_to_sell: float) -> float:
        if ticker not in self._portfolio or not self._portfolio[ticker]:
            return 0.0

        cost_basis = 0.0
        remaining_qty = qty_to_sell
        queue = self._portfolio[ticker]

        while remaining_qty > 0.000001 and queue:
            batch = queue[0]
            if batch['qty'] > remaining_qty:
                cost_basis += remaining_qty * batch['unit_cost']
                batch['qty'] -= remaining_qty
                remaining_qty = 0
            else:
                cost_basis += batch['qty'] * batch['unit_cost']
                remaining_qty -= batch['qty']
                queue.popleft()

        return cost_basis

    # -------------------------------------------------------------------------

    def get_open_positions(self) -> list[dict]:
        positions = []
        for ticker, queue in self._portfolio.items():
            total_qty = sum(batch['qty'] for batch in queue)
            total_cost = sum(batch['qty'] * batch['unit_cost'] for batch in queue)
            if total_qty > 0.0001:
                avg_cost = total_cost / total_qty
                positions.append({
                    'ticker': ticker,
                    'qty': total_qty,
                    'total_cost_pln': total_cost,
                    'avg_cost_pln': avg_cost,
                })
        return positions

    def calculate(
        self,
        t212_path: str | None,
        ibkr_path: str | None,
        xtb_path: str | None = None,
        bossa_path: str | None = None,
        mbank_path: str | None = None,
        generic_paths: list[str] | None = None,
        country_code: str = "PL",
    ) -> CalculationResult:
        total_start = time.time()
        self._portfolio.clear()

        # Determine which rate service to use based on country
        try:
            from src.countries import get_country
            country = get_country(country_code)
            rate_service_name = country.rate_service
            base_currency = country.currency
        except Exception:
            rate_service_name = "NBP"
            base_currency = "PLN"

        # Use the engine's default service (NBP or ECB)
        if rate_service_name == "ECB" and not isinstance(self.nbp, ECBService):
            rate_svc = ECBService()
        else:
            rate_svc = self.nbp

        results = {
            'T212': BrokerResults('Trading 212'),
            'IBKR': BrokerResults('Interactive Brokers'),
            'RAZEM': BrokerResults('TOTAL'),
        }

        generic_broker_results: dict[str, BrokerResults] = {}
        all_transactions: list[dict] = []

        # --- Process T212 ---
        if t212_path and Path(t212_path).exists():
            self._report_progress("Processing Trading 212...", 0.1)
            try:
                df = pd.read_csv(t212_path)
                df['Time'] = pd.to_datetime(df['Time'])

                currencies_to_prefetch = set()
                for _, row in df.iterrows():
                    curr = row.get('Currency (Total)', 'USD')
                    if pd.notna(curr):
                        currencies_to_prefetch.add((str(curr).upper().strip(), row['Time'].year))

                for curr, year in currencies_to_prefetch:
                    rate_svc.prefetch_rates(curr, year)

                for _, row in df.iterrows():
                    action = str(row['Action']).lower()
                    notes = str(row['Notes']).lower()

                    if 'deposit' in action and ('free shares' in notes or 'promotion' in notes):
                        k = rate_svc.get_rate_sync(row['Currency (Total)'], row['Time'])
                        results['T212'].bonuses += (row['Total'] * k)
                        continue

                    if 'cashback' in action:
                        k = rate_svc.get_rate_sync(row['Currency (Total)'], row['Time'])
                        results['T212'].cashback += (row['Total'] * k)
                        continue

                    if 'buy' in action or 'sell' in action:
                        ticker = str(row['Ticker']) if not pd.isna(row['Ticker']) else str(row['ISIN'])
                        base_curr = base_currency
                        if row['Currency (Total)'] == base_curr:
                            k = 1.0
                        else:
                            k = rate_svc.get_rate_sync(row['Currency (Total)'], row['Time'])
                        val = row['Total'] * k
                        qty = row['No. of shares']
                        if not pd.isna(qty):
                            tx_type = 'BUY' if 'buy' in action else 'SELL'
                            all_transactions.append({
                                'date': row['Time'], 'ticker': ticker, 'type': tx_type,
                                'qty': float(qty), 'total_pln': abs(float(val)),
                                'source': 'T212'
                            })

                    if 'Dividend' in str(row['Action']):
                        rate_svc.prefetch_rates(row['Currency (Total)'], row['Time'].year)
                        k = rate_svc.get_rate_sync(row['Currency (Total)'], row['Time'])
                        results['T212'].dividend_gross += row['Total'] * k
                        if pd.notna(row.get('Withholding tax')) and row['Withholding tax'] > 0:
                            k_wht = rate_svc.get_rate_sync(row['Currency (Withholding tax)'], row['Time'])
                            results['T212'].dividend_tax_foreign += row['Withholding tax'] * k_wht

                    if 'Interest' in str(row['Action']):
                        rate_svc.prefetch_rates(row['Currency (Total)'], row['Time'].year)
                        k = rate_svc.get_rate_sync(row['Currency (Total)'], row['Time'])
                        results['T212'].interest_gross += row['Total'] * k

            except Exception as e:
                raise ValueError(f"T212 CSV Error: {e}")

        # --- Process IBKR ---
        if ibkr_path and Path(ibkr_path).exists():
            self._report_progress("Processing IBKR...", 0.4)
            try:
                with open(ibkr_path, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    header_map, cols_div, cols_wht, cols_syep = {}, {}, {}, {}

                    for row in reader:
                        if not row:
                            continue

                        if row[0] == 'Trades' and row[1] == 'Header':
                            header_map = {n: i for i, n in enumerate(row)}

                        if row[0] == 'Trades' and row[1] == 'Data' and 'Symbol' in header_map:
                            try:
                                proc_idx = header_map['Proceeds']
                                if not row[proc_idx] or row[proc_idx] == '0':
                                    continue

                                ticker = row[header_map['Symbol']]
                                if '.' in ticker:
                                    continue

                                dt = datetime.datetime.strptime(
                                    row[header_map['Date/Time']].split(',')[0], '%Y-%m-%d'
                                )
                                rate_svc.prefetch_rates(row[header_map['Currency']], dt.year)
                                k = rate_svc.get_rate_sync(row[header_map['Currency']], dt)
                                qty = float(row[header_map['Quantity']])
                                val = abs(float(row[proc_idx]) * k)
                                comm = abs(float(row[header_map['Comm/Fee']]) * k)
                                tx_type = 'BUY' if qty > 0 else 'SELL'
                                total = val + comm if tx_type == 'BUY' else val

                                all_transactions.append({
                                    'date': dt, 'ticker': ticker, 'type': tx_type,
                                    'qty': abs(qty), 'total_pln': total,
                                    'comm_pln': comm if tx_type == 'SELL' else 0,
                                    'source': 'IBKR'
                                })
                            except Exception as e:
                                print(f"[IBKR ERROR] Trade Parse: {e}")

                        if row[0] == 'Dividends' and row[1] == 'Header':
                            cols_div = {n: i for i, n in enumerate(row)}
                        if row[0] == 'Dividends' and row[1] == 'Data' and 'Amount' in cols_div:
                            try:
                                if 'Total' in row[cols_div['Description']]:
                                    continue
                                amt = float(row[cols_div['Amount']])
                                date_str = row[cols_div.get('Date', 'Date')]
                                if not date_str or date_str.strip() == '':
                                    continue
                                k = rate_svc.get_rate_sync(
                                    row[cols_div['Currency']],
                                    datetime.datetime.strptime(date_str, '%Y-%m-%d')
                                )
                                results['IBKR'].dividend_gross += amt * k
                            except Exception as e:
                                print(f"[IBKR WARN] Div: {e}")

                        if row[0] == 'Withholding Tax' and row[1] == 'Header':
                            cols_wht = {n: i for i, n in enumerate(row)}
                        if row[0] == 'Withholding Tax' and row[1] == 'Data' and 'Amount' in cols_wht:
                            try:
                                if 'Total' in row[cols_wht['Description']]:
                                    continue
                                amt = float(row[cols_wht['Amount']])
                                date_str = row[cols_wht.get('Date', 'Date')]
                                if not date_str or date_str.strip() == '':
                                    continue
                                k = rate_svc.get_rate_sync(
                                    row[cols_wht['Currency']],
                                    datetime.datetime.strptime(date_str, '%Y-%m-%d')
                                )
                                results['IBKR'].dividend_tax_foreign += abs(amt * k)
                            except Exception:
                                pass

                        if 'Interest' in row[0] and row[1] == 'Header':
                            cols_syep = {n: i for i, n in enumerate(row)}
                        if 'Interest' in row[0] and row[1] == 'Data' and 'Interest Paid to Customer' in cols_syep:
                            try:
                                if 'Total' in row[0]:
                                    continue
                                amt = float(row[cols_syep['Interest Paid to Customer']])
                                if amt > 0:
                                    d_idx = cols_syep.get('Value Date', cols_syep.get('Start Date'))
                                    k = rate_svc.get_rate_sync(
                                        row[cols_syep['Currency']],
                                        datetime.datetime.strptime(row[d_idx], '%Y-%m-%d')
                                    )
                                    results['IBKR'].interest_gross += amt * k
                            except Exception:
                                pass

            except Exception as e:
                raise ValueError(f"IBKR CSV Error: {e}")

        # --- Process Polish Brokers (XTB, BOŚ, mBank) ---
        from src.parser import UniversalCSVParser
        parser = UniversalCSVParser(crypto_service=self.crypto)

        for path, source_name in [
            (xtb_path, 'XTB'),
            (bossa_path, 'BOŚ'),
            (mbank_path, 'mBank'),
        ]:
            if path and Path(path).exists():
                self._report_progress(f"Processing {source_name}...", 0.55)
                try:
                    trades = parser.parse_csv(path, rate_svc)
                    for tx in trades:
                        tx['source'] = source_name
                        all_transactions.append(tx)
                except Exception as e:
                    print(f"[{source_name} ERROR] {e}")

        # --- Process Generic Files ---
        if generic_paths:
            for gpath in generic_paths:
                gpath_obj = Path(gpath)
                if not gpath_obj.exists():
                    continue
                self._report_progress(f"Processing {gpath_obj.name}...", 0.6)
                try:
                    trades = parser.parse_csv(gpath, rate_svc)
                    broker_name = trades[0]['source'] if trades else gpath_obj.stem

                    if broker_name not in generic_broker_results:
                        generic_broker_results[broker_name] = BrokerResults(broker_name)

                    for tx in trades:
                        tx['source'] = broker_name
                        all_transactions.append(tx)
                except Exception as e:
                    print(f"[WARN] Could not parse {gpath}: {e}")

        # --- FIFO Calculation ---
        self._report_progress("Calculating FIFO...", 0.7)
        all_transactions.sort(key=lambda x: x['date'])

        for tx in all_transactions:
            src = tx['source']
            if tx['type'] == 'BUY':
                self._add_to_fifo(tx['ticker'], tx['qty'], tx['total_pln'], tx['date'])
            elif tx['type'] == 'SELL':
                cost = self._remove_from_fifo(tx['ticker'], tx['qty'])
                if cost > 0:
                    if src in results:
                        results[src].stock_income += tx['total_pln']
                        results[src].stock_cost += (cost + tx.get('comm_pln', 0.0))
                    elif src in generic_broker_results:
                        generic_broker_results[src].stock_income += tx['total_pln']
                        generic_broker_results[src].stock_cost += (cost + tx.get('comm_pln', 0.0))

        self._report_progress("Finalizing...", 0.9)
        t = results['T212']
        i = results['IBKR']
        r = results['RAZEM']

        r.stock_income = t.stock_income + i.stock_income
        r.stock_cost = t.stock_cost + i.stock_cost
        r.dividend_gross = t.dividend_gross + i.dividend_gross
        r.dividend_tax_foreign = t.dividend_tax_foreign + i.dividend_tax_foreign
        r.interest_gross = t.interest_gross + i.interest_gross
        r.interest_tax_foreign = t.interest_tax_foreign + i.interest_tax_foreign
        r.bonuses = t.bonuses
        r.cashback = t.cashback

        for gbr in generic_broker_results.values():
            r.stock_income += gbr.stock_income
            r.stock_cost += gbr.stock_cost
            r.dividend_gross += gbr.dividend_gross
            r.dividend_tax_foreign += gbr.dividend_tax_foreign
            r.interest_gross += gbr.interest_gross

        transaction_objects = [
            Transaction(
                date=tx['date'],
                ticker=tx['ticker'],
                tx_type=tx['type'],
                qty=tx['qty'],
                total_pln=tx['total_pln'],
                source=tx['source'],
            )
            for tx in all_transactions
        ]

        self._report_progress("Complete!", 1.0)
        print(f"[TIMING] TOTAL CALCULATION TIME: {time.time() - total_start:.2f}s")

        rate_svc.save_to_disk()

        return CalculationResult(
            t212=t,
            ibkr=i,
            total=r,
            transactions=transaction_objects,
            open_positions=self.get_open_positions(),
            t212_path=t212_path or "",
            ibkr_path=ibkr_path or "",
            generic_brokers=generic_broker_results,
            country_code=country_code,
            base_currency=base_currency,
        )
