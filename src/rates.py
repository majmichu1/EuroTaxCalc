"""
Exchange rate services:
- NBPService   — Polish National Bank (PLN, for Poland)
- ECBService   — European Central Bank (EUR, for DE/AT/ES/BE/IT)
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger('TaxCalculator')


class NBPService:
    """NBP exchange rate fetcher with persistent disk cache."""

    BASE_URL = "http://api.nbp.pl/api/exchangerates/rates/a"
    CACHE_FILE = Path("nbp_rates_cache.json")

    def __init__(self):
        self._cache: dict[str, float] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._prefetched: set[tuple[str, int]] = set()
        self._load_cache()

    def _load_cache(self):
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                print(f"[NBP Cache] Loaded {len(self._cache)} cached rates from disk")
        except Exception:
            self._cache = {}

    def prefetch_rates(self, currency: str, year: int):
        """Fetch all rates for a given currency/year in one batch request."""
        currency = str(currency).upper().strip()
        if currency == 'PLN' or (currency, year) in self._prefetched:
            return

        cached_count = 0
        expected_count = 0

        start_date = datetime.date(year, 1, 1)
        end_date = datetime.date(year, 12, 31)
        if year == datetime.date.today().year:
            end_date = datetime.date.today()

        for i in range((end_date - start_date).days + 1):
            check_date = start_date + datetime.timedelta(days=i)
            if check_date.weekday() >= 5:
                continue
            expected_count += 1
            cache_key = f"{currency}_{check_date.strftime('%Y-%m-%d')}"
            if cache_key in self._cache:
                cached_count += 1

        if cached_count == expected_count and expected_count > 0:
            logger.info(f"[NBP Cache] {currency} {year}: 100% coverage — skipping API")
            self._prefetched.add((currency, year))
            return

        missing_count = expected_count - cached_count
        logger.info(f"[NBP Service] Fetching {currency} {year} ({missing_count} missing)...")

        start_date_str = f"{year}-01-01"
        end_date_str = f"{year}-12-31"
        today = datetime.date.today()
        if today.year == year:
            end_date_str = today.strftime('%Y-%m-%d')

        url = f"{self.BASE_URL}/{currency}/{start_date_str}/{end_date_str}/?format=json"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get('rates', [])
                    with self._lock:
                        count = 0
                        for r in rates:
                            cache_key = f"{currency}_{r['effectiveDate']}"
                            if cache_key not in self._cache:
                                self._cache[cache_key] = r['mid']
                                count += 1
                        if count > 0:
                            self._dirty = True
                            logger.info(f"[NBP Service] Added {count} new rates for {currency} {year}")
                    self._prefetched.add((currency, year))
                elif resp.status_code == 404:
                    raise Exception(f"NBP API: Not found for {currency} {year}")
                elif resp.status_code >= 500:
                    raise Exception(f"NBP API: Server error {resp.status_code}")
        except httpx.TimeoutException:
            raise Exception("NBP API: Connection timeout")
        except httpx.RequestError as e:
            raise Exception(f"NBP API: Request failed - {str(e)}")

    def save_to_disk(self):
        """Batch-save cache to disk (call once after calculation)."""
        if self._dirty:
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self._cache, f, indent=2)
                self._dirty = False
                print(f"[NBP Cache] Saved {len(self._cache)} rates to disk")
            except Exception:
                pass

    def get_rate_sync(self, currency: str, transaction_date: datetime.datetime) -> float:
        """Get PLN exchange rate, falling back to previous business day."""
        if pd.isna(currency) or str(currency).strip() == '':
            return 1.0

        currency = str(currency).upper().strip()
        if currency == 'PLN':
            return 1.0

        multiplier = 1.0
        if currency == 'GBX':
            currency = 'GBP'
            multiplier = 0.01

        search_date = transaction_date - datetime.timedelta(days=1)

        for _ in range(7):
            date_str = search_date.strftime('%Y-%m-%d')
            cache_key = f"{currency}_{date_str}"

            with self._lock:
                if cache_key in self._cache:
                    return self._cache[cache_key] * multiplier

            try:
                url = f"{self.BASE_URL}/{currency}/{date_str}/?format=json"
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        rate = resp.json()['rates'][0]['mid']
                        with self._lock:
                            self._cache[cache_key] = rate
                            self._dirty = True
                        return rate * multiplier
            except Exception:
                pass

            search_date -= datetime.timedelta(days=1)

        logger.warning(f"[NBP] No rate found for {currency} after 7 attempts")
        return 0.0


class ECBService:
    """ECB reference rate fetcher for eurozone countries (EUR base)."""

    CACHE_FILE = Path("ecb_rates_cache.json")
    API_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"

    def __init__(self):
        self._cache: dict[str, float] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._prefetched: set[tuple[str, int]] = set()
        self._load_cache()

    def _load_cache(self):
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                print(f"[ECB Cache] Loaded {len(self._cache)} cached rates from disk")
        except Exception:
            self._cache = {}

    def save_to_disk(self):
        if self._dirty:
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self._cache, f, indent=2)
                self._dirty = False
                print(f"[ECB Cache] Saved {len(self._cache)} rates to disk")
            except Exception:
                pass

    def prefetch_rates(self, currency: str, year: int):
        """Fetch all ECB rates for a currency/year in one batch request."""
        currency = str(currency).upper().strip()
        if currency == 'EUR' or (currency, year) in self._prefetched:
            return

        # Count already cached
        start_date = datetime.date(year, 1, 1)
        end_date = datetime.date(year, 12, 31)
        if year == datetime.date.today().year:
            end_date = datetime.date.today()

        expected = sum(
            1 for i in range((end_date - start_date).days + 1)
            if (start_date + datetime.timedelta(days=i)).weekday() < 5
        )
        cached = sum(
            1 for i in range((end_date - start_date).days + 1)
            if f"{currency}_{(start_date + datetime.timedelta(days=i)).strftime('%Y-%m-%d')}" in self._cache
        )

        if cached == expected and expected > 0:
            self._prefetched.add((currency, year))
            return

        # ECB uses currency/EUR pairs — we need EUR/currency (inverted)
        # ECB EXR dataset: D.USD.EUR.SP00.A gives USD per EUR
        # We want EUR per USD → invert
        ecb_currency = currency
        if currency == 'GBX':
            ecb_currency = 'GBP'

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        url = f"{self.API_BASE}/D.{ecb_currency}.EUR.SP00.A?startPeriod={start_str}&endPeriod={end_str}&format=jsondata"

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    # Parse ECB SDMX-JSON format
                    observations = data.get('dataSets', [{}])[0].get('series', {})
                    dates = data.get('structure', {}).get('dimensions', {}).get('observation', [{}])[0].get('values', [])

                    series_data = list(observations.values())
                    if series_data:
                        obs = series_data[0].get('observations', {})
                        count = 0
                        with self._lock:
                            for idx_str, values in obs.items():
                                idx = int(idx_str)
                                if idx < len(dates) and values[0] is not None:
                                    date_str = dates[idx]['id']
                                    rate_foreign_per_eur = values[0]
                                    # Invert: we want EUR per foreign currency unit
                                    if rate_foreign_per_eur > 0:
                                        rate_eur_per_unit = 1.0 / rate_foreign_per_eur
                                        cache_key = f"{currency}_{date_str}"
                                        if cache_key not in self._cache:
                                            self._cache[cache_key] = rate_eur_per_unit
                                            count += 1
                        if count > 0:
                            self._dirty = True
                            logger.info(f"[ECB Service] Added {count} new rates for {currency} {year}")
                    self._prefetched.add((currency, year))
                elif resp.status_code == 404:
                    logger.warning(f"[ECB] No data for {currency} {year}")
        except Exception as e:
            logger.error(f"[ECB] Error fetching {currency} {year}: {e}")

    def get_rate_sync(self, currency: str, transaction_date: datetime.datetime) -> float:
        """Get EUR exchange rate, falling back to previous business day."""
        if pd.isna(currency) or str(currency).strip() == '':
            return 1.0

        currency = str(currency).upper().strip()
        if currency == 'EUR':
            return 1.0

        multiplier = 1.0
        if currency == 'GBX':
            currency = 'GBP'
            multiplier = 0.01

        # ECB publishes previous day's rate — use day before transaction
        search_date = transaction_date - datetime.timedelta(days=1)

        for _ in range(7):
            date_str = search_date.strftime('%Y-%m-%d')
            cache_key = f"{currency}_{date_str}"

            with self._lock:
                if cache_key in self._cache:
                    return self._cache[cache_key] * multiplier

            # Single-day fallback fetch
            url = f"{self.API_BASE}/D.{currency}.EUR.SP00.A?startPeriod={date_str}&endPeriod={date_str}&format=jsondata"
            try:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        observations = data.get('dataSets', [{}])[0].get('series', {})
                        series_data = list(observations.values())
                        if series_data:
                            obs = series_data[0].get('observations', {})
                            if obs:
                                rate_foreign_per_eur = list(obs.values())[0][0]
                                if rate_foreign_per_eur and rate_foreign_per_eur > 0:
                                    rate_eur_per_unit = 1.0 / rate_foreign_per_eur
                                    with self._lock:
                                        self._cache[cache_key] = rate_eur_per_unit
                                        self._dirty = True
                                    return rate_eur_per_unit * multiplier
            except Exception:
                pass

            search_date -= datetime.timedelta(days=1)

        logger.warning(f"[ECB] No rate found for {currency} after 7 attempts")
        return 0.0


def get_rate_service(rate_service_name: str):
    """Factory: return correct rate service by name ('NBP' or 'ECB')."""
    if rate_service_name == 'ECB':
        return ECBService()
    return NBPService()
