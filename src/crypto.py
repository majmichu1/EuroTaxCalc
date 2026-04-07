"""
CryptoService — fetches historical crypto prices from CoinGecko (free API).
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

import httpx


class CryptoService:
    """Fetch historical crypto prices from CoinGecko (free API)."""

    BASE_URL = "https://api.coingecko.com/api/v3"
    CACHE_FILE = Path("crypto_prices_cache.json")

    SUPPORTED = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'USDT': 'tether',
        'USDC': 'usd-coin',
    }

    def __init__(self):
        self._cache: dict[str, float] = {}
        self._load_cache()
        self._api_calls = 0
        self._last_api_call = 0.0

    def _load_cache(self):
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                print(f"[Crypto Cache] Loaded {len(self._cache)} cached prices from disk")
        except Exception as e:
            print(f"[Crypto Cache] Warning: Could not load cache: {e}")
            self._cache = {}

    def _save_cache(self):
        try:
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            print(f"[Crypto Cache] Warning: Could not save cache: {e}")

    def _rate_limit(self):
        """Simple rate limiting — CoinGecko free API allows ~10-30 calls/min."""
        min_interval = 2.0
        elapsed = time.time() - self._last_api_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_api_call = time.time()
        self._api_calls += 1

    def get_price_pln(self, symbol: str, date: datetime.datetime) -> float:
        """Get crypto price in PLN for a specific date."""
        symbol = symbol.upper()
        if symbol not in self.SUPPORTED:
            print(f"[Crypto Service] Unsupported crypto: {symbol}")
            return 0.0

        date_str = date.strftime('%d-%m-%Y')
        cache_key = f"{symbol}_{date_str}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        self._rate_limit()

        try:
            coin_id = self.SUPPORTED[symbol]
            url = f"{self.BASE_URL}/coins/{coin_id}/history?date={date_str}&localization=false"

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)

                if resp.status_code == 200:
                    data = resp.json()
                    price_pln = data.get('market_data', {}).get('current_price', {}).get('pln', 0.0)

                    if price_pln and price_pln > 0:
                        self._cache[cache_key] = price_pln
                        self._save_cache()
                        print(f"[Crypto Service] Fetched {symbol} price for {date_str}: {price_pln:.2f} PLN")
                        return price_pln
                    else:
                        print(f"[Crypto Service] No price data for {symbol} on {date_str}")

                elif resp.status_code == 429:
                    print(f"[Crypto Service] Rate limit exceeded. Using cached data only.")
                elif resp.status_code == 404:
                    print(f"[Crypto Service] No data available for {symbol} on {date_str} (404)")
                else:
                    print(f"[Crypto Service] API error for {symbol}: HTTP {resp.status_code}")

        except httpx.TimeoutException:
            print(f"[Crypto Service] Timeout fetching {symbol} price for {date_str}")
        except httpx.RequestError as e:
            print(f"[Crypto Service] Request error for {symbol}: {e}")
        except Exception as e:
            print(f"[Crypto Service] Unexpected error for {symbol}: {e}")

        return 0.0

    def get_api_stats(self) -> dict:
        return {
            'cache_size': len(self._cache),
            'api_calls': self._api_calls,
            'supported_coins': list(self.SUPPORTED.keys()),
        }
