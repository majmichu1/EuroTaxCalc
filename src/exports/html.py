"""
HTML export — bilingual tax report and PIT-38 instructions (Poland only).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from src.models import CalculationResult
from src.i18n import t


def export_to_html(result: CalculationResult, output_path: str = "raport_podatkowy.html") -> str:
    """Export calculation results to printable HTML report."""
    try:
        from src.countries import get_country
        country = get_country(result.country_code)
        fmt = country.format_currency
        form_name = country.tax_form_name
        cgt_rate = country.effective_cgt_rate_display
        stock_tax = country.calculate_capital_gains_tax(result.total.stock_profit)
        div_tax = country.calculate_dividend_tax(result.total.dividend_gross, result.total.dividend_tax_foreign)
        int_tax = country.calculate_interest_tax(result.total.interest_gross)
    except Exception:
        def fmt(v): return f"{v:,.2f} zł"
        form_name = "PIT-38"
        cgt_rate = "19%"
        stock_tax = max(0, result.total.stock_profit * 0.19)
        div_tax = result.total.dividend_tax_due
        int_tax = result.total.interest_tax_due

    tr = result.total
    total_tax = stock_tax + div_tax + int_tax
    profit_class = 'positive' if tr.stock_profit >= 0 else 'negative'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{t('pdf.title')} — {form_name} ({result.timestamp.year})</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 24px; color: #333; }}
        h1 {{ color: #4f46e5; border-bottom: 2px solid #6366f1; padding-bottom: 12px; }}
        h2 {{ color: #6366f1; margin-top: 32px; }}
        .section {{ background: #f5f5f5; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e0e0e0; }}
        .row:last-child {{ border-bottom: none; }}
        .label {{ color: #666; }}
        .value {{ font-weight: bold; color: #333; }}
        .positive {{ color: #2e7d32; }}
        .negative {{ color: #c62828; }}
        .total-box {{ background: linear-gradient(135deg, #ffd54f, #ffb300); border-radius: 8px; padding: 24px; margin: 24px 0; text-align: center; }}
        .total-label {{ font-size: 18px; color: #333; }}
        .total-value {{ font-size: 36px; font-weight: bold; color: #1a237e; }}
        .meta {{ background: #e8eaf6; padding: 12px; border-radius: 6px; margin-bottom: 20px; font-size: 13px; }}
        .footer {{ margin-top: 48px; font-size: 12px; color: #999; text-align: center; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <h1>📊 {t('pdf.title')}</h1>
    <div class="meta">
        <strong>{t('pdf.tax_year')}:</strong> {result.timestamp.year - 1} &nbsp;|&nbsp;
        <strong>{t('results.form_name', form=form_name)}</strong> &nbsp;|&nbsp;
        {t('pdf.generated')}: {result.timestamp.strftime('%Y-%m-%d %H:%M')}
    </div>

    <h2>📈 {t('pdf.stocks')} ({cgt_rate})</h2>
    <div class="section">
        <div class="row"><span class="label">{t('results.stock_income')}</span><span class="value">{fmt(tr.stock_income)}</span></div>
        <div class="row"><span class="label">{t('results.stock_cost')}</span><span class="value">{fmt(tr.stock_cost)}</span></div>
        <div class="row"><span class="label">{t('results.profit_loss')}</span><span class="value {profit_class}">{fmt(tr.stock_profit)}</span></div>
        <div class="row"><span class="label">{t('pdf.tax')} ({cgt_rate})</span><span class="value">{fmt(stock_tax)}</span></div>
    </div>

    <h2>💰 {t('pdf.dividends')}</h2>
    <div class="section">
        <div class="row"><span class="label">{t('results.dividend_gross')}</span><span class="value">{fmt(tr.dividend_gross)}</span></div>
        <div class="row"><span class="label">{t('results.dividend_foreign_tax')}</span><span class="value">{fmt(tr.dividend_tax_foreign)}</span></div>
        <div class="row"><span class="label">{t('results.dividend_due')}</span><span class="value">{fmt(div_tax)}</span></div>
    </div>

    <h2>💵 {t('pdf.interest')}</h2>
    <div class="section">
        <div class="row"><span class="label">{t('results.interest_gross')}</span><span class="value">{fmt(tr.interest_gross)}</span></div>
        <div class="row"><span class="label">{t('pdf.tax')}</span><span class="value">{fmt(int_tax)}</span></div>
    </div>

    <div class="total-box">
        <div class="total-label">{t('results.total_tax')} — {form_name}</div>
        <div class="total-value">{fmt(total_tax)}</div>
    </div>

    <div class="footer">
        <p>{t('pdf.disclaimer_text')}</p>
        <button class="no-print" onclick="window.print()">🖨️ Print / Save as PDF</button>
    </div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path
