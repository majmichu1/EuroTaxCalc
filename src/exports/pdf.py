"""
PDF tax report export — country-aware, bilingual (PL/EN).
"""

from __future__ import annotations

import datetime

from src.models import CalculationResult
from src.i18n import t

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def export_to_professional_pdf(
    result: CalculationResult,
    output_path: str = "raport_podatkowy.pdf",
    year: int | None = None,
) -> str:
    """Generate a professional PDF tax report, country and language aware."""
    if not HAS_REPORTLAB:
        raise ImportError("reportlab not installed. Run: pip install reportlab")

    if year is None:
        year = result.timestamp.year - 1

    try:
        from src.countries import get_country
        country = get_country(result.country_code)
        fmt = country.format_currency
        cgt_rate_display = country.effective_cgt_rate_display
        form_name = country.tax_form_name
        currency_sym = country.currency_symbol
    except Exception:
        def fmt(v): return f"{v:,.2f} zł"
        cgt_rate_display = "19%"
        form_name = "PIT-38"
        currency_sym = "zł"

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20, alignment=1)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, spaceAfter=10,
                                   textColor=colors.HexColor('#4f46e5'))
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10)

    elements = []

    elements.append(Paragraph(f"{t('pdf.title')} — {form_name}", title_style))
    elements.append(Paragraph(f"{t('pdf.tax_year')}: {year}", normal_style))
    elements.append(Paragraph(f"{t('pdf.generated')}: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style))
    elements.append(Spacer(1, 20))

    # Summary table
    elements.append(Paragraph(f"📊 {t('pdf.summary')}", heading_style))

    tr = result.total
    try:
        stock_tax = get_country(result.country_code).calculate_capital_gains_tax(tr.stock_profit)
        div_tax = get_country(result.country_code).calculate_dividend_tax(tr.dividend_gross, tr.dividend_tax_foreign)
        int_tax = get_country(result.country_code).calculate_interest_tax(tr.interest_gross)
    except Exception:
        stock_tax = max(0, tr.stock_profit * 0.19)
        div_tax = tr.dividend_tax_due
        int_tax = tr.interest_tax_due

    summary_data = [
        [t('pdf.category'), t('pdf.income'), t('pdf.cost'), t('pdf.profit'), t('pdf.tax')],
        [t('pdf.stocks'), fmt(tr.stock_income), fmt(tr.stock_cost), fmt(tr.stock_profit), fmt(stock_tax)],
        [t('pdf.dividends'), fmt(tr.dividend_gross), fmt(tr.dividend_tax_foreign), fmt(tr.dividend_gross - tr.dividend_tax_foreign), fmt(div_tax)],
        [t('pdf.interest'), fmt(tr.interest_gross), '-', fmt(tr.interest_gross), fmt(int_tax)],
    ]

    summary_table = Table(summary_data, colWidths=[3.5*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Total tax box
    elements.append(Paragraph(f"💰 {t('pdf.total_tax')}", heading_style))
    total_tax = stock_tax + div_tax + int_tax

    tax_data = [
        [t('pdf.category'), f"{t('pdf.tax')} ({currency_sym})"],
        [f"{t('pdf.stocks')} ({cgt_rate_display})", fmt(stock_tax)],
        [t('pdf.dividends'), fmt(div_tax)],
        [t('pdf.interest'), fmt(int_tax)],
        [t('pdf.total_tax'), fmt(total_tax)],
    ]

    tax_table = Table(tax_data, colWidths=[10*cm, 5*cm])
    tax_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ffffcc')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
    ]))
    elements.append(tax_table)
    elements.append(Spacer(1, 20))

    # Broker breakdown
    elements.append(Paragraph(f"🏦 {t('pdf.brokers')}", heading_style))
    broker_data = [[t('pdf.broker'), t('pdf.income'), t('pdf.cost'), t('pdf.profit')]]

    if result.t212.stock_income > 0 or result.t212.stock_cost > 0:
        broker_data.append(['Trading 212', fmt(result.t212.stock_income),
                            fmt(result.t212.stock_cost), fmt(result.t212.stock_profit)])
    if result.ibkr.stock_income > 0 or result.ibkr.stock_cost > 0:
        broker_data.append(['Interactive Brokers', fmt(result.ibkr.stock_income),
                            fmt(result.ibkr.stock_cost), fmt(result.ibkr.stock_profit)])
    for name, br in result.generic_brokers.items():
        if br.stock_income > 0 or br.stock_cost > 0:
            broker_data.append([name, fmt(br.stock_income), fmt(br.stock_cost), fmt(br.stock_profit)])

    if len(broker_data) > 1:
        bt = Table(broker_data, colWidths=[5*cm, 4*cm, 4*cm, 4*cm])
        bt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        elements.append(bt)
    elements.append(Spacer(1, 20))

    # Disclaimer
    elements.append(Paragraph(f"{t('pdf.disclaimer')}", heading_style))
    elements.append(Paragraph(t('pdf.disclaimer_text'), normal_style))

    doc.build(elements)
    return output_path
