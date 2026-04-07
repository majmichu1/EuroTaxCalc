# EuroTaxCalc 2.0

**Capital Gains Tax Calculator for EU Investors**

> **IMPORTANT LEGAL NOTICE:** This tool is ONLY an aid for tax calculations.
> ❌ Does NOT constitute legal or tax advice
> ❌ Does NOT replace consultation with a qualified tax advisor
> ⚠️ Results may contain errors — ALWAYS verify calculations
> ✅ Responsibility for accuracy of your tax return rests with you

---

## Overview

EuroTaxCalc is a free desktop application that calculates capital gains tax from broker CSV exports. It supports 6 EU countries with country-specific tax rates, allowances, and forms.

### Supported Countries

| Country | Form | Rate | Allowance |
|---------|------|------|-----------|
| 🇵🇱 Poland | PIT-38 | 19% flat | none |
| 🇩🇪 Germany | Anlage KAP | 25% + Soli (≈26.375%) | €1,000 |
| 🇦🇹 Austria | E1kv | 27.5% KESt | none |
| 🇪🇸 Spain | Modelo 100 | 19%–28% progressive | none |
| 🇧🇪 Belgium | Tax-on-web | 0% CGT / 30% dividends | none |
| 🇮🇹 Italy | Quadro RT | 26% flat | none |

### Supported Brokers

- **Trading 212** — native CSV parser
- **Interactive Brokers** — native CSV parser
- **XTB xStation** — native CSV parser
- **BOŚ Bossa** — native CSV parser
- **mBank mTrader** — native CSV parser
- **Auto-detect** — Revolut, eToro, Degiro, Freedom24, Saxo, Schwab, and 15+ more

---

## Quick Start

### Requirements
- Python 3.12+
- Windows 10/11, Linux (Ubuntu, Fedora, Bazzite) or macOS

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/eurotaxcalc/eurotaxcalc.git
cd eurotaxcalc

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python main.py
```

### First Use

1. Go to **Settings** → select your country and language
2. In **Calculator** → click the broker button and select your CSV export
3. Click **CALCULATE TAX** and wait for results (~5–20 seconds)
4. Export to **PDF**, **Excel**, or for Poland: **XML** (PIT-38) or **HTML instructions**

---

## Project Structure

```
eurotaxcalc/
├── main.py                    # Entry point + UI
├── src/
│   ├── engine.py              # FIFO calculation engine
│   ├── parser.py              # Universal CSV parser (15+ broker formats)
│   ├── rates.py               # NBP + ECB exchange rate services
│   ├── models.py              # Data models (Transaction, BrokerResults, CalculationResult)
│   ├── database.py            # SQLite history storage
│   ├── crypto.py              # CoinGecko crypto price service
│   ├── countries/             # Tax configs per country (PL, DE, AT, ES, BE, IT)
│   ├── exports/               # PDF, Excel, XML, HTML, JSON export functions
│   ├── i18n/                  # Translations (Polish, English)
│   └── ui/                    # UI components (theme, settings view)
├── tests/                     # Unit tests (54 tests)
├── requirements.txt
└── settings_manager.py        # Settings persistence helper
```

---

## How Tax Calculation Works

### FIFO Method (First In, First Out)
When you sell shares, those bought earliest are treated as sold first.

```
Example (Poland):
01.01.2024: Buy  10 AAPL @ $100, rate 4.00 → cost   4,000 PLN
15.06.2024: Buy  10 AAPL @ $150, rate 4.20 → cost   6,300 PLN
01.09.2024: Sell 15 AAPL @ $140, rate 4.10 → income 8,610 PLN

FIFO cost: (10 × 400) + (5 × 630) = 7,150 PLN
Profit: 8,610 − 7,150 = 1,460 PLN
Tax (19%): 277.40 PLN
```

### Currency Conversion
- **Poland**: NBP (National Bank of Poland) rates — previous business day
- **All other countries**: ECB (European Central Bank) reference rates

---

## Exports

| Format | Description | Countries |
|--------|-------------|-----------|
| **PDF** | Professional tax report | All |
| **Excel** | Spreadsheet with all data | All |
| **XML** | Official PIT-38(18) for e-Urząd Skarbowy | Poland only |
| **HTML** | Step-by-step filing instructions | Poland only |
| **JSON** | Full data backup | All |

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test class
python -m pytest tests/test_engine.py -v
python -m pytest tests/test_countries.py -v
```

---

## Troubleshooting

### Exchange rate API error
1. Check your internet connection
2. Try again in a moment (NBP/ECB APIs occasionally have downtime)
3. Clear the cache: delete `nbp_rates_cache.json` or `ecb_rates_cache.json`

### CSV not recognised
1. Make sure you export the **full year** from your broker
2. Check the FAQ tab in the app for broker-specific export instructions

---

## Legal

MIT License — see [LICENSE](LICENSE)

This software is provided "as is" without warranty. The authors accept no liability for errors or tax calculation inaccuracies. Always verify results with a qualified tax advisor.

---

**Version:** 2.0.0 | **Python:** 3.12+ | **Framework:** Flet 0.80+
