"""
EuroTaxCalc - Capital Gains Tax Calculator
==========================================
Professional tax calculation tool for EU investors.
Supports: Poland (PIT-38), Germany, Austria, Spain, Belgium, Italy.
Brokers: Trading 212, Interactive Brokers, XTB, BOŚ, mBank and many more.

Author: EuroTaxCalc Team
Version: 2.0.0
Python: 3.12+
Framework: Flet 0.80+
"""

from __future__ import annotations

import asyncio
import csv
import datetime
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import xml.etree.ElementTree as ET
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tax_calculator.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TaxCalculator')

# Reduce httpx noise (404 for NBP weekends is normal)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

import flet as ft
import httpx
import pandas as pd

# EuroTaxCalc modules
from src.i18n import t, set_language, get_language
from src.countries import get_country, get_all_countries
from src.ui.theme import AppColors, AppTheme
from src.engine import CalculatorEngine
from src.rates import NBPService
from src.crypto import CryptoService
from src.database import HistoryDatabase
from src.models import (Transaction, BrokerResults, CalculationResult,
                        DataValidator, APP_VERSION, APP_NAME, APP_YEAR)
from src.exports import (export_to_professional_pdf, export_to_excel,
                         export_to_html, export_to_official_pit38_xml, export_to_json)

# PDF and Excel exports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils.dataframe import dataframe_to_rows
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# =============================================================================
# SETTINGS PERSISTENCE
# =============================================================================

class SettingsManager:
    FILE_PATH = Path("settings.json")

    @staticmethod
    def load():
        if SettingsManager.FILE_PATH.exists():
            try:
                with open(SettingsManager.FILE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def save(settings):
        try:
            with open(SettingsManager.FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

# =============================================================================
# HELPERS
# =============================================================================

def format_pln(value: float) -> str:
    return f"{value:,.2f} zł".replace(",", " ")

def format_money(value: float, country_code: str = "PL") -> str:
    """Format value in the country's base currency."""
    try:
        from src.countries import get_country
        return get_country(country_code).format_currency(value)
    except Exception:
        return format_pln(value)

def export_and_open_html(result: CalculationResult, page):
    """Export to HTML and open in browser."""
    import webbrowser
    output_path = Path("raport_podatkowy.html").resolve()
    export_to_html(result, str(output_path))
    # Use pathlib for cross-platform file URI
    file_uri = output_path.as_uri()
    webbrowser.open(file_uri)
    page.snack_bar = ft.SnackBar(
        content=ft.Text(f"📄 Raport wyeksportowany: {output_path}", color=AppColors.TEXT_PRIMARY),
        bgcolor=AppColors.PRIMARY,
    )
    page.snack_bar.open = True
    page.update()

def export_and_notify_json(result: CalculationResult, page):
    """Export to JSON and show notification."""
    output_path = Path("backup_data.json").resolve()
    export_to_json(result, str(output_path))
    page.snack_bar = ft.SnackBar(
        content=ft.Text(f"💾 Backup zapisany: {output_path}", color=AppColors.TEXT_PRIMARY),
        bgcolor=AppColors.SECONDARY,
    )
    page.snack_bar.open = True
    page.update()

def generate_pit38_instructions(result: CalculationResult, year: int = APP_YEAR, taxpayer_data: dict = None, output_path: str = "PIT-38_instrukcja.html") -> str:
    """Generate clean, professional HTML instructions for filling official PIT-38 form."""
    
    t = result.total
    
    # Calculate all values (rounded to whole PLN)
    stock_income = int(round(t.stock_income))
    stock_cost = int(round(t.stock_cost))
    stock_profit = int(round(max(0, t.stock_profit)))
    stock_loss = int(round(abs(min(0, t.stock_profit))))
    
    div_gross = int(round(t.dividend_gross))
    div_tax_foreign = int(round(t.dividend_tax_foreign))
    div_tax_due = int(round(max(0, t.dividend_gross * 0.19 - t.dividend_tax_foreign)))
    
    int_gross = int(round(t.interest_gross))
    int_tax = int(round(t.interest_gross * 0.19))
    
    stock_tax = int(round(stock_profit * 0.19))
    total_tax = stock_tax + div_tax_due + int_tax
    
    # Taxpayer data
    nip = taxpayer_data.get('nip', '_______________') if taxpayer_data else '_______________'
    pesel = taxpayer_data.get('pesel', '_______________') if taxpayer_data else '_______________'
    address = taxpayer_data.get('address', {}) if taxpayer_data else {}
    
    html = f'''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>Instrukcja PIT-38({year}) - Tax Calculator Pro</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 24px; background: #fff; color: #333; }}
        h1 {{ color: #1a237e; border-bottom: 2px solid #1a237e; padding-bottom: 12px; margin-bottom: 24px; font-size: 28px; }}
        h2 {{ color: #283593; margin: 24px 0 12px 0; background: #e8eaf6; padding: 12px 16px; border-radius: 4px; font-size: 20px; }}
        .section {{ background: #fafafa; border: 1px solid #ddd; padding: 20px; margin: 16px 0; border-radius: 4px; }}
        .field {{ display: flex; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid #e0e0e0; background: white; }}
        .field:last-child {{ border-bottom: none; }}
        .field-num {{ background: #37474f; color: white; padding: 6px 14px; border-radius: 3px; font-weight: bold; min-width: 50px; text-align: center; font-family: monospace; }}
        .field-label {{ flex: 1; padding: 0 20px; color: #555; line-height: 1.5; }}
        .field-value {{ font-weight: bold; color: #1a237e; font-size: 18px; min-width: 140px; text-align: right; font-family: monospace; }}
        .field-value.big {{ background: #c8e6c9; padding: 10px 16px; border-radius: 4px; font-size: 22px; color: #2e7d32; }}
        .info-box {{ background: #fff3e0; border-left: 4px solid #ff9800; padding: 16px; margin: 16px 0; }}
        .warning-box {{ background: #ffebee; border-left: 4px solid #e53935; padding: 16px; margin: 16px 0; }}
        .success-box {{ background: #e8f5e9; border-left: 4px solid #43a047; padding: 16px; margin: 16px 0; }}
        .step {{ background: #e3f2fd; padding: 16px; margin: 12px 0; border-left: 4px solid #1976d2; }}
        .step-num {{ display: inline-block; background: #1976d2; color: white; width: 28px; height: 28px; text-align: center; line-height: 28px; border-radius: 50%; margin-right: 12px; font-weight: bold; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; background: white; }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
        th {{ background: #37474f; color: white; font-weight: 600; }}
        tr:last-child td {{ border-bottom: none; }}
        .print-btn {{ display: block; margin: 24px auto; padding: 14px 40px; background: #1a237e; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; font-weight: 500; }}
        .print-btn:hover {{ background: #283593; }}
        .footer {{ text-align: center; color: #999; margin-top: 32px; font-size: 12px; border-top: 1px solid #e0e0e0; padding-top: 16px; }}
        @media print {{ .print-btn, .no-print {{ display: none; }} body {{ background: white; }} .section {{ box-shadow: none; border: 1px solid #ccc; }} }}
    </style>
</head>
<body>
    <h1>Instrukcja wypełnienia PIT-38({year})</h1>
    <p style="color: #666; margin-bottom: 24px;">Wygenerowano: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} | Tax Calculator Pro</p>
    
    <div class="info-box">
        <strong>Jak użyć tej instrukcji:</strong>
        <ol style="margin: 12px 0 0 24px; line-height: 1.8;">
            <li>Otwórz oficjalny formularz PIT-38({year}) na podatki.gov.pl lub w e-Urzędzie Skarbowym</li>
            <li>Wypełnij dane osobiste (sekcja B)</li>
            <li>Przepisz wartości z poniższej instrukcji do odpowiednich pól formularza</li>
            <li>Pola oznaczone "0" lub "—" pozostaw puste jeśli nie dotyczą Twojej sytuacji</li>
        </ol>
    </div>
    
    <h2>Sekcja B - Dane podatnika</h2>
    <div class="section">
        <div class="field">
            <span class="field-num">1</span>
            <span class="field-label">NIP</span>
            <span class="field-value">{nip}</span>
        </div>
        <div class="field">
            <span class="field-num">2</span>
            <span class="field-label">PESEL</span>
            <span class="field-value">{pesel}</span>
        </div>
        <div class="field">
            <span class="field-num">—</span>
            <span class="field-label">Adres zamieszkania</span>
            <span class="field-value" style="font-size: 14px;">{address.get('street', '')} {address.get('building', '')}, {address.get('city', '')}</span>
        </div>
    </div>
    
    <h2>Sekcja C.1 - Papiery wartościowe</h2>
    <div class="section">
        <div class="field">
            <span class="field-num">22</span>
            <span class="field-label">Przychód z odpłatnego zbycia papierów wartościowych</span>
            <span class="field-value">{stock_income:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">23</span>
            <span class="field-label">Koszty uzyskania przychodów</span>
            <span class="field-value">{stock_cost:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">24</span>
            <span class="field-label">Dochód (poz. 22 − poz. 23)</span>
            <span class="field-value big">{stock_profit:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">25</span>
            <span class="field-label">Strata (poz. 23 − poz. 22)</span>
            <span class="field-value">{stock_loss:,} zł</span>
        </div>
    </div>
    
    <h2>Sekcja D - Dywidendy</h2>
    <div class="section">
        <div class="field">
            <span class="field-num">34</span>
            <span class="field-label">Przychody z dywidend i innych udziałów w zyskach osób prawnych</span>
            <span class="field-value">{div_gross:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">35</span>
            <span class="field-label">Podatek zapłacony za granicą</span>
            <span class="field-value">{div_tax_foreign:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">36</span>
            <span class="field-label">Podatek należny (poz. 34 × 19% − poz. 35)</span>
            <span class="field-value">{div_tax_due:,} zł</span>
        </div>
    </div>
    
    <h2>Sekcja E - Odsetki</h2>
    <div class="section">
        <div class="field">
            <span class="field-num">37</span>
            <span class="field-label">Przychody z odsetek</span>
            <span class="field-value">{int_gross:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">38</span>
            <span class="field-label">Podatek należny (19%)</span>
            <span class="field-value">{int_tax:,} zł</span>
        </div>
    </div>
    
    <h2>Sekcja G - Obliczenie zobowiązania podatkowego</h2>
    <div class="section">
        <div class="field">
            <span class="field-num">42</span>
            <span class="field-label">Podatek od dochodu z papierów wartościowych (19%)</span>
            <span class="field-value">{stock_tax:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">43</span>
            <span class="field-label">Podatek od dywidend (z poz. 36)</span>
            <span class="field-value">{div_tax_due:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">44</span>
            <span class="field-label">Podatek od odsetek (z poz. 38)</span>
            <span class="field-value">{int_tax:,} zł</span>
        </div>
        <div class="field">
            <span class="field-num">45</span>
            <span class="field-label"><strong>RAZEM DO ZAPŁATY (poz. 42 + 43 + 44)</strong></span>
            <span class="field-value big">{total_tax:,} zł</span>
        </div>
    </div>
    
    <div class="success-box">
        <strong>Podsumowanie</strong>
        <table style="margin-top: 12px;">
            <tr><th>Składnik</th><th>Kwota</th></tr>
            <tr><td>Dochód z akcji</td><td>{stock_profit:,} zł</td></tr>
            <tr><td>Dywidendy brutto</td><td>{div_gross:,} zł</td></tr>
            <tr><td>Odsetki</td><td>{int_gross:,} zł</td></tr>
            <tr style="background: #c8e6c9; font-weight: bold;"><td>Podatek do zapłaty</td><td>{total_tax:,} zł</td></tr>
        </table>
    </div>
    
    <div class="warning-box">
        <strong>Ważne informacje</strong>
        <ul style="margin: 12px 0 0 24px; line-height: 1.8;">
            <li>Termin złożenia PIT-38: <strong>30 kwietnia {year+1} roku</strong></li>
            <li>Podatek wpłać na rachunek swojego Urzędu Skarbowego</li>
            <li>Ta instrukcja jest pomocnicza - zawsze weryfikuj dane w oficjalnym formularzu</li>
            <li>Jeśli masz stratę z lat ubiegłych, możesz ją odliczyć w odpowiednich polach</li>
        </ul>
    </div>
    
    <div class="step">
        <span class="step-num">1</span>
        <strong>Złóż deklarację elektronicznie:</strong> Przejdź na <a href="https://www.podatki.gov.pl" target="_blank" style="color: #1976d2;">podatki.gov.pl</a> lub użyj aplikacji e-Urząd Skarbowy
    </div>
    
    <div class="step">
        <span class="step-num">2</span>
        <strong>Wyślij XML:</strong> Jeśli wygenerowałeś plik XML, załącz go do deklaracji
    </div>
    
    <div class="step">
        <span class="step-num">3</span>
        <strong>Zachowaj kopię:</strong> Wydrukuj tę instrukcję i dołącz do swojej dokumentacji podatkowej
    </div>
    
    <button class="print-btn" onclick="window.print()">Drukuj instrukcję</button>
    
    <div class="footer">
        Wygenerowano w Tax Calculator Pro | Ten dokument jest pomocniczy i nie zastępuje oficjalnego formularza
    </div>
</body>
</html>'''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"[Instructions] Generated PIT-38 instructions: {output_path}")
    return output_path
    draw_money(390, current_y, 90, 30, "22. Dochód", stock_profit, bold=True)
    draw_money(490, current_y, 80, 30, "23. Strata", stock_loss)
    
    current_y -= 80
    
    # --- E. ODSETKI / DYWIDENDY ---
    c.setFillColor(colors.lightgrey)
    c.rect(20, current_y, width - 40, 15, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25, current_y + 4, "E. / G. OBLICZENIE PODATKU (Dywidendy i Odsetki)")
    current_y -= 50
    
    draw_money(20, current_y, 170, 40, "Kwota przychodu (Dywidendy)", div_gross)
    draw_money(200, current_y, 170, 40, "Podatek zapłacony (u źródła)", div_tax_paid)
    draw_money(380, current_y, 170, 40, "Podatek należny (19% - zapłacony)", div_tax_due, bold=True)
    
    current_y -= 50
    draw_money(20, current_y, 170, 40, "Kwota przychodu (Odsetki)", int_gross)
    draw_money(200, current_y, 170, 40, "Podatek należny (19%)", int_tax, bold=True)
    
    current_y -= 80
    
    # --- G. PODATEK DO ZAPŁATY ---
    c.setFillColor(colors.lightgrey)
    c.rect(20, current_y, width - 40, 15, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25, current_y + 4, "G. OBLICZENIE ZOBOWIĄZANIA PODATKOWEGO")
    current_y -= 50
    
    draw_money(20, current_y, 130, 40, "44. Podatek od akcji", stock_tax)
    draw_money(160, current_y, 130, 40, "45. Podatek od dywidend", div_tax_due)
    draw_money(300, current_y, 130, 40, "46. Podatek od odsetek", int_tax)
    
    draw_money(450, current_y, 120, 40, "47. RAZEM DO ZAPŁATY", total_tax, bold=True)

    current_y -= 80

    # --- H. PODPIS ---
    c.setFillColor(colors.lightgrey)
    c.rect(20, current_y, width - 40, 15, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25, current_y + 4, "H. OŚWIADCZENIE I PODPIS PODATNIKA")
    current_y -= 10
    
    c.setFont("Helvetica", 8)
    c.drawString(25, current_y - 10, "Oświadczam, że znane mi są przepisy Kodeksu karnego skarbowego o odpowiedzialności za podanie danych niezgodnych z rzeczywistością.")
    
    current_y -= 60
    draw_field(20, current_y, 250, 40, "Data wypełnienia (dd-mm-rrrr)", datetime.date.today().strftime("%d-%m-%Y"))
    draw_field(280, current_y, 290, 40, "Podpis podatnika", "")
    
    # Disclaimer footer
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.grey)
    c.drawString(width/2 - 100, 30, f"Wygenerowano automatycznie w Tax Calculator Pro v1.0 | Data: {datetime.datetime.now()}")
    c.drawString(width/2 - 100, 20, "Dokument pomocniczy. Należy sprawdzić poprawność przed wysłaniem.")

    c.save()
    return output_path

def generate_pit38_html(result: CalculationResult, year: int = APP_YEAR, output_path: str = "PIT-38.html") -> str:
    """Generate official PIT-38 (17) form exactly matching Ministry of Finance layout."""
    t = result.total
    
    # Calculate all tax values (rounded to whole PLN as per tax rules)
    stock_income = round(t.stock_income, 0)
    stock_cost = round(t.stock_cost, 0)
    stock_profit = round(max(0, t.stock_profit), 0)
    stock_loss = round(abs(min(0, t.stock_profit)), 0)
    
    dividend_gross = round(t.dividend_gross, 0)
    dividend_tax_paid = round(t.dividend_tax_foreign, 0)
    dividend_tax_due = round(t.dividend_tax_due, 0)
    
    interest_gross = round(t.interest_gross, 0)
    interest_tax = round(t.interest_tax_due, 0)
    
    stock_tax = round(max(0, t.stock_profit) * 0.19, 0)
    total_tax = round(stock_tax + dividend_tax_due + interest_tax, 0)
    
    # Official PIT-38 Form HTML (wersja 17 - 2024)
    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>PIT-38 (17) - Zeznanie za rok {year}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: Arial, Helvetica, sans-serif; font-size: 10pt; background: #fff; }}
        .page {{ width: 210mm; min-height: 297mm; margin: 0 auto; padding: 10mm; background: white; }}
        
        /* Official header - green stripe */
        .official-header {{ 
            background: linear-gradient(180deg, #2e7d32 0%, #1b5e20 100%);
            color: white; 
            padding: 8px 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-radius: 4px 4px 0 0;
        }}
        .official-header h1 {{ font-size: 18pt; font-weight: bold; }}
        .official-header .version {{ font-size: 9pt; }}
        
        /* Form container */
        .form-box {{
            border: 2px solid #333;
            border-top: none;
        }}
        
        /* Section styling */
        .section {{
            border-bottom: 1px solid #333;
            padding: 0;
        }}
        .section:last-child {{ border-bottom: none; }}
        
        .section-header {{
            background: #e8e8e8;
            padding: 6px 10px;
            font-weight: bold;
            font-size: 9pt;
            border-bottom: 1px solid #999;
        }}
        .section-content {{ padding: 8px 10px; }}
        
        /* Field rows */
        .field-row {{
            display: flex;
            align-items: stretch;
            margin: 4px 0;
            min-height: 28px;
        }}
        .field-num {{
            width: 32px;
            min-width: 32px;
            background: #d0d0d0;
            border: 1px solid #666;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 9pt;
        }}
        .field-label {{
            flex: 1;
            padding: 4px 8px;
            font-size: 9pt;
            display: flex;
            align-items: center;
            border: 1px solid #ccc;
            border-left: none;
            background: #fafafa;
        }}
        .field-value {{
            width: 140px;
            min-width: 140px;
            border: 1px solid #333;
            border-left: none;
            background: #ffffcc;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 8px;
            font-weight: bold;
            font-size: 10pt;
        }}
        .field-value.empty {{ background: #f5f5f5; }}
        .field-value.total {{ background: #c8e6c9; font-size: 11pt; }}
        
        /* Subsection */
        .subsection {{ margin: 8px 0; }}
        .subsection-title {{ font-weight: bold; font-size: 9pt; margin-bottom: 4px; }}
        
        /* Two column layout */
        .two-col {{ display: flex; gap: 20px; }}
        .two-col > div {{ flex: 1; }}
        
        /* Header info */
        .header-info {{
            display: flex;
            justify-content: space-between;
            padding: 8px 10px;
            border-bottom: 1px solid #333;
            background: #f9f9f9;
        }}
        .header-info .nip {{ font-size: 10pt; }}
        .header-info .year {{ font-size: 14pt; font-weight: bold; }}
        
        /* Footer */
        .footer {{
            margin-top: 20px;
            padding: 10px;
            background: #fff3e0;
            border: 2px solid #ff9800;
            border-radius: 4px;
            font-size: 9pt;
        }}
        .footer h4 {{ color: #e65100; margin-bottom: 8px; }}
        .footer ul {{ margin-left: 20px; }}
        
        .print-info {{
            margin-top: 15px;
            text-align: center;
            font-size: 8pt;
            color: #666;
        }}
        
        @media print {{
            body {{ background: white; }}
            .page {{ margin: 0; padding: 5mm; }}
            .no-print {{ display: none !important; }}
        }}
        
        .print-btn {{
            display: block;
            margin: 20px auto;
            padding: 12px 24px;
            background: #2e7d32;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 14pt;
            cursor: pointer;
        }}
        .print-btn:hover {{ background: #1b5e20; }}
    </style>
</head>
<body>
    <div class="page">
        <!-- Official Header -->
        <div class="official-header">
            <div>
                <h1>PIT-38</h1>
                <span class="version">wersja 17</span>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 8pt;">ZEZNANIE O WYSOKOŚCI OSIĄGNIĘTEGO DOCHODU</div>
                <div style="font-size: 8pt;">(PONIESIONEJ STRATY) W ROKU PODATKOWYM</div>
            </div>
        </div>
        
        <div class="form-box">
            <!-- Rok podatkowy -->
            <div class="header-info">
                <div class="nip">
                    <strong>1.</strong> Identyfikator podatkowy NIP / PESEL: ____________________
                </div>
                <div class="year">
                    Rok: <span style="border: 2px solid #333; padding: 4px 16px; background: #ffffcc;">{year}</span>
                </div>
            </div>
            
            <!-- Sekcja A -->
            <div class="section">
                <div class="section-header">A. MIEJSCE I CEL SKŁADANIA ZEZNANIA</div>
                <div class="section-content">
                    <div class="two-col">
                        <div>
                            <strong>4.</strong> Urząd skarbowy: ________________________________
                        </div>
                        <div>
                            <strong>5.</strong> Cel złożenia: ☑ złożenie zeznania ☐ korekta
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Sekcja B -->
            <div class="section">
                <div class="section-header">B. DANE IDENTYFIKACYJNE I ADRES ZAMIESZKANIA</div>
                <div class="section-content">
                    <div style="display: flex; gap: 20px; margin-bottom: 8px;">
                        <div><strong>6.</strong> Nazwisko: ____________________</div>
                        <div><strong>7.</strong> Pierwsze imię: ____________________</div>
                        <div><strong>8.</strong> Data urodzenia: ____/____/________</div>
                    </div>
                    <div style="margin-top: 8px;">
                        <strong>Adres zamieszkania:</strong> ________________________________________________________________
                    </div>
                </div>
            </div>
            
            <!-- Sekcja C - Przychody z papierów wartościowych -->
            <div class="section">
                <div class="section-header">C. PRZYCHODY Z ODPŁATNEGO ZBYCIA PAPIERÓW WARTOŚCIOWYCH I POCHODNYCH INSTRUMENTÓW FINANSOWYCH</div>
                <div class="section-content">
                    <div class="subsection">
                        <div class="subsection-title">C.1. PAPIERY WARTOŚCIOWE</div>
                        
                        <div class="field-row">
                            <div class="field-num">22</div>
                            <div class="field-label">Przychód z odpłatnego zbycia papierów wartościowych</div>
                            <div class="field-value">{stock_income:,.0f}</div>
                        </div>
                        
                        <div class="field-row">
                            <div class="field-num">23</div>
                            <div class="field-label">Koszty uzyskania przychodów</div>
                            <div class="field-value">{stock_cost:,.0f}</div>
                        </div>
                        
                        <div class="field-row">
                            <div class="field-num">24</div>
                            <div class="field-label">Dochód (poz. 22 - poz. 23, jeżeli wynik &gt; 0)</div>
                            <div class="field-value">{stock_profit:,.0f}</div>
                        </div>
                        
                        <div class="field-row">
                            <div class="field-num">25</div>
                            <div class="field-label">Strata (poz. 23 - poz. 22, jeżeli wynik &gt; 0)</div>
                            <div class="field-value {'empty' if stock_loss == 0 else ''}">{stock_loss:,.0f}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Sekcja D - Dywidendy -->
            <div class="section">
                <div class="section-header">D. DOCHODY Z DYWIDEND I INNYCH PRZYCHODÓW Z TYTUŁU UDZIAŁU W ZYSKACH OSÓB PRAWNYCH</div>
                <div class="section-content">
                    <div class="field-row">
                        <div class="field-num">34</div>
                        <div class="field-label">Przychody z dywidend i innych udziałów w zyskach osób prawnych</div>
                        <div class="field-value">{dividend_gross:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">35</div>
                        <div class="field-label">Podatek zapłacony za granicą (przeliczony na PLN)</div>
                        <div class="field-value">{dividend_tax_paid:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">36</div>
                        <div class="field-label">Podatek należny (poz. 34 × 19% - poz. 35, nie mniej niż 0)</div>
                        <div class="field-value">{dividend_tax_due:,.0f}</div>
                    </div>
                </div>
            </div>
            
            <!-- Sekcja E - Odsetki -->
            <div class="section">
                <div class="section-header">E. DOCHODY Z ODSETEK OD PAPIERÓW WARTOŚCIOWYCH</div>
                <div class="section-content">
                    <div class="field-row">
                        <div class="field-num">37</div>
                        <div class="field-label">Przychody z odsetek</div>
                        <div class="field-value">{interest_gross:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">38</div>
                        <div class="field-label">Podatek od odsetek (19%)</div>
                        <div class="field-value">{interest_tax:,.0f}</div>
                    </div>
                </div>
            </div>
            
            <!-- Sekcja G - Obliczenie podatku -->
            <div class="section">
                <div class="section-header">G. OBLICZENIE ZOBOWIĄZANIA PODATKOWEGO</div>
                <div class="section-content">
                    <div class="field-row">
                        <div class="field-num">42</div>
                        <div class="field-label">Podatek od dochodu z odpłatnego zbycia papierów wartościowych (poz. 24 × 19%)</div>
                        <div class="field-value">{stock_tax:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">43</div>
                        <div class="field-label">Podatek od dywidend (z poz. 36)</div>
                        <div class="field-value">{dividend_tax_due:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">44</div>
                        <div class="field-label">Podatek od odsetek (z poz. 38)</div>
                        <div class="field-value">{interest_tax:,.0f}</div>
                    </div>
                    
                    <div class="field-row">
                        <div class="field-num">45</div>
                        <div class="field-label"><strong>SUMA PODATKU NALEŻNEGO (poz. 42 + 43 + 44)</strong></div>
                        <div class="field-value total">{total_tax:,.0f}</div>
                    </div>
                </div>
            </div>
            
            <!-- Sekcja H - Podpis -->
            <div class="section">
                <div class="section-header">H. PODPIS PODATNIKA</div>
                <div class="section-content" style="padding: 15px 10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div style="width: 45%;">
                            <div style="border-bottom: 1px solid #333; height: 40px; margin-bottom: 4px;"></div>
                            <div style="font-size: 8pt; text-align: center;">Data wypełnienia (dd-mm-rrrr)</div>
                        </div>
                        <div style="width: 45%;">
                            <div style="border-bottom: 1px solid #333; height: 40px; margin-bottom: 4px;"></div>
                            <div style="font-size: 8pt; text-align: center;">Podpis podatnika</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Warning -->
        <div class="footer">
            <h4>⚠️ WAŻNE INFORMACJE:</h4>
            <ul>
                <li>Ten dokument jest <strong>POMOCNICZY</strong> - przepisz dane do oficjalnego formularza e-PIT lub złóż elektronicznie przez <strong>podatki.gov.pl</strong></li>
                <li>Zweryfikuj wszystkie kwoty z dokumentami źródłowymi od brokerów</li>
                <li>W razie wątpliwości skonsultuj się z doradcą podatkowym</li>
                <li>Termin składania zeznania: <strong>30 kwietnia {year + 1}</strong></li>
            </ul>
        </div>
        
        <div class="print-info">
            Wygenerowano: {result.timestamp.strftime("%Y-%m-%d %H:%M")} | EuroTaxCalc v{APP_VERSION}
        </div>
        
        <button class="print-btn no-print" onclick="window.print()">🖨️ Drukuj formularz PIT-38</button>
    </div>
</body>
</html>"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_path



# =============================================================================
# TAX LOSS HARVESTING
# =============================================================================

def create_tax_loss_harvesting_section(result: 'CalculationResult') -> ft.Container:
    """Create Tax Loss Harvesting suggestions based on open positions with unrealized losses."""
    if not result.open_positions:
        return ft.Container()
    
    # Calculate potential savings for positions at loss
    loss_positions = []
    for pos in result.open_positions:
        ticker = pos.get('ticker', 'UNKNOWN')
        qty = pos.get('qty', 0)
        avg_cost = pos.get('avg_cost', 0)
        # Estimate current value (we don't have real-time prices, use cost as proxy)
        # In real implementation, you'd fetch current prices
        unrealized_loss = pos.get('unrealized_loss', 0)  # If available
        
        # For now, show positions with high cost that could be harvested
        total_cost = qty * avg_cost
        if total_cost > 500:  # Show positions worth > 500 PLN
            loss_positions.append({
                'ticker': ticker,
                'qty': qty,
                'total_cost': total_cost,
                'potential_tax_saving': total_cost * 0.19  # Theoretical max if sold at 0
            })
    
    if not loss_positions:
        return ft.Container()
    
    # Sort by total cost (highest first)
    loss_positions.sort(key=lambda x: x['total_cost'], reverse=True)
    
    position_rows = []
    for i, pos in enumerate(loss_positions[:5]):  # Show top 5
        position_rows.append(
            ft.Container(
                content=ft.Row([
                    ft.Text(pos['ticker'], color=AppColors.TEXT_PRIMARY, size=13, weight=ft.FontWeight.W_500),
                    ft.Text(f"{pos['qty']:.2f} szt.", color=AppColors.TEXT_SECONDARY, size=12),
                    ft.Text(f"{pos['total_cost']:.0f} zł", color=AppColors.ACCENT_GOLD, size=12),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.symmetric(vertical=6, horizontal=8),
                bgcolor=AppColors.SURFACE_VARIANT if i % 2 == 0 else None,
                border_radius=4,
            )
        )
    
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.TRENDING_DOWN, color=AppColors.ACCENT_RED, size=20),
                ft.Text("TAX LOSS HARVESTING", size=14, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_RED),
            ], spacing=8),
            ft.Text(t("tlh.hint_text"), size=11, color=AppColors.TEXT_SECONDARY, italic=True),
            ft.Divider(height=12, color=AppColors.BORDER),
            ft.Row([
                ft.Text("Ticker", color=AppColors.TEXT_MUTED, size=11),
                ft.Text(t("tlh.qty_col"), color=AppColors.TEXT_MUTED, size=11),
                ft.Text(t("tlh.value_col"), color=AppColors.TEXT_MUTED, size=11),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            *position_rows,
            ft.Container(
                content=ft.Text(t("tlh.footer_text"), size=10, color=AppColors.TEXT_MUTED, italic=True),
                padding=ft.Padding.only(top=8),
            ),
        ], spacing=4),
        bgcolor=AppColors.GRADIENT_START,
        border=ft.Border.all(1, AppColors.ACCENT_RED),
        border_radius=AppTheme.BORDER_RADIUS,
        padding=AppTheme.CARD_PADDING,
    )

# =============================================================================
# UI COMPONENTS
# =============================================================================

def create_result_card(title: str, broker: BrokerResults, is_total: bool = False, country_code: str = "PL") -> ft.Container:
    border_color = AppColors.ACCENT_GOLD if is_total else AppColors.BORDER
    title_color = AppColors.ACCENT_GOLD if is_total else AppColors.PRIMARY
    
    profit = broker.stock_profit
    profit_color = AppColors.ACCENT_GREEN if profit >= 0 else AppColors.ACCENT_RED
    
    bonus_section = []
    if broker.bonuses > 0 or broker.cashback > 0:
        bonus_section = [ft.Container(
            content=ft.Column([
                ft.Text(t("results.bonuses_cashback_hdr"), size=12, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                ft.Row([
                    ft.Text(t("results.bonuses_label"), color=AppColors.TEXT_SECONDARY, size=13),
                    ft.Text(format_money(broker.bonuses, country_code), color=AppColors.ACCENT_GREEN, size=13),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([
                    ft.Text(t("results.cashback_label"), color=AppColors.TEXT_SECONDARY, size=13),
                    ft.Text(format_money(broker.cashback, country_code), color=AppColors.ACCENT_GREEN, size=13),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=6),
            padding=ft.Padding.only(top=12),
        )]

    fmt = lambda v: format_money(v, country_code)
    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=title_color),
                padding=ft.Padding.only(bottom=12),
                border=ft.Border.only(bottom=ft.BorderSide(1, AppColors.BORDER)),
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text(t("results.stocks_section"), size=12, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                    ft.Row([
                        ft.Text(t("results.income_label"), color=AppColors.TEXT_SECONDARY, size=13),
                        ft.Text(fmt(broker.stock_income), color=AppColors.TEXT_PRIMARY, size=13),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text(t("results.cost_label"), color=AppColors.TEXT_SECONDARY, size=13),
                        ft.Text(fmt(broker.stock_cost), color=AppColors.TEXT_PRIMARY, size=13),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(t("results.profit_label"), color=AppColors.TEXT_PRIMARY, size=13, weight=ft.FontWeight.W_500),
                            ft.Text(fmt(profit), color=profit_color, size=13, weight=ft.FontWeight.BOLD),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor=AppColors.SURFACE_VARIANT,
                        border_radius=6,
                        padding=8,
                        margin=ft.Margin.only(top=4),
                    ),
                ], spacing=6),
                padding=ft.Padding.only(top=8),
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text(t("results.dividends_section"), size=12, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                    ft.Row([
                        ft.Text(t("results.gross_label"), color=AppColors.TEXT_SECONDARY, size=13),
                        ft.Text(fmt(broker.dividend_gross), color=AppColors.TEXT_PRIMARY, size=13),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text(t("results.foreign_tax_short"), color=AppColors.TEXT_SECONDARY, size=13),
                        ft.Text(fmt(broker.dividend_tax_foreign), color=AppColors.TEXT_PRIMARY, size=13),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=6),
                padding=ft.Padding.only(top=12),
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text(t("results.interest_section"), size=12, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                    ft.Row([
                        ft.Text(t("results.gross_label"), color=AppColors.TEXT_SECONDARY, size=13),
                        ft.Text(fmt(broker.interest_gross), color=AppColors.TEXT_PRIMARY, size=13),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=6),
                padding=ft.Padding.only(top=12),
            ),
            *bonus_section,
        ], spacing=0),
        bgcolor=AppColors.GRADIENT_START,  # Subtle purple gradient tint
        border=ft.Border.all(2 if is_total else 1, border_color),
        border_radius=AppTheme.BORDER_RADIUS,
        padding=AppTheme.CARD_PADDING,
        expand=True,
    )


def create_tax_summary_card(result: CalculationResult) -> ft.Container:
    try:
        from src.countries import get_country as _gc
        _country = _gc(result.country_code)
        stock_tax = _country.calculate_capital_gains_tax(result.total.stock_profit)
        fmt = lambda v: _country.format_currency(v)
    except Exception:
        stock_tax = max(0, result.total.stock_profit * 0.19)
        fmt = format_pln
    dividend_tax = result.total.dividend_tax_due
    interest_tax = result.total.interest_tax_due
    total_tax = result.total_tax
    
    bonus_section = []
    if result.total.bonuses > 0:
        bonus_section = [ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, color=AppColors.TEXT_MUTED, size=16),
                ft.Text(f"{t('results.bonus_pit37')} {fmt(result.total.bonuses)}", color=AppColors.TEXT_MUTED, size=12),
            ], spacing=8),
            padding=ft.Padding.only(top=12),
        )]

    try:
        _country = get_country(result.country_code)
        _form = _country.tax_form_name
    except Exception:
        _form = "PIT-38"

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=AppColors.ACCENT_GOLD, size=28),
                ft.Text(f"{t('results.summary_header')} ({_form})", size=18, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_GOLD),
            ], spacing=12),
            ft.Divider(height=20, color=AppColors.BORDER),
            ft.Row([
                ft.Text(t("results.stock_tax_label"), color=AppColors.TEXT_SECONDARY, size=14),
                ft.Text(fmt(stock_tax), color=AppColors.TEXT_PRIMARY, size=14),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.Text(t("results.dividend_topup"), color=AppColors.TEXT_SECONDARY, size=14),
                ft.Text(fmt(dividend_tax), color=AppColors.TEXT_PRIMARY, size=14),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.Text(t("results.interest_topup"), color=AppColors.TEXT_SECONDARY, size=14),
                ft.Text(fmt(interest_tax), color=AppColors.TEXT_PRIMARY, size=14),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=20, color=AppColors.BORDER),
            ft.Container(
                content=ft.Row([
                    ft.Text(t("results.total_due"), size=20, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                    ft.Text(fmt(total_tax), size=28, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_GOLD),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=AppColors.SURFACE_VARIANT,
                border_radius=10,
                padding=16,
            ),
            *bonus_section,
        ], spacing=8),
        bgcolor=AppColors.CARD,
        border=ft.Border.all(2, AppColors.ACCENT_GOLD),
        border_radius=AppTheme.BORDER_RADIUS,
        padding=24,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=20,
            color=f"{AppColors.ACCENT_GOLD}20",
            offset=ft.Offset(0, 4),
        ),
    )


def create_transaction_details_panel(result: CalculationResult) -> ft.Container:
    """Create expandable panel with transaction details grouped by broker and ticker."""
    
    if not result.transactions:
        return ft.Container()  # Empty if no transactions
    
    # Group transactions by source (broker) and ticker
    grouped: dict[str, dict[str, list[Transaction]]] = {}
    for tx in result.transactions:
        if tx.source not in grouped:
            grouped[tx.source] = {}
        if tx.ticker not in grouped[tx.source]:
            grouped[tx.source][tx.ticker] = []
        grouped[tx.source][tx.ticker].append(tx)
    
    # Create broker expansion tiles
    broker_tiles = []
    broker_names = {'T212': 'Trading 212', 'IBKR': 'Interactive Brokers'}
    
    for source, tickers in grouped.items():
        ticker_tiles = []
        total_transactions = sum(len(txs) for txs in tickers.values())
        
        for ticker, transactions in sorted(tickers.items()):
            # Calculate ticker summary
            buys = [tx for tx in transactions if tx.tx_type == 'BUY']
            sells = [tx for tx in transactions if tx.tx_type == 'SELL']
            total_qty_bought = sum(tx.qty for tx in buys)
            total_cost_bought = sum(tx.total_pln for tx in buys)
            avg_cost = total_cost_bought / total_qty_bought if total_qty_bought > 0 else 0
            
            # Transaction rows
            tx_rows = []
            for tx in sorted(transactions, key=lambda x: x.date):
                tx_color = AppColors.ACCENT_GREEN if tx.tx_type == 'BUY' else AppColors.ACCENT_RED
                tx_icon = ft.Icons.ADD_CIRCLE_OUTLINE if tx.tx_type == 'BUY' else ft.Icons.REMOVE_CIRCLE_OUTLINE
                tx_rows.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(tx_icon, color=tx_color, size=16),
                            ft.Text(tx.date.strftime("%Y-%m-%d"), size=12, color=AppColors.TEXT_MUTED, width=90),
                            ft.Text(tx.tx_type, size=12, color=tx_color, weight=ft.FontWeight.W_500, width=60),
                            ft.Text(f"{tx.qty:.4f} szt.", size=12, color=AppColors.TEXT_SECONDARY, width=100),
                            ft.Text(f"@ {tx.unit_price_pln:.2f} zł", size=12, color=AppColors.TEXT_SECONDARY, width=120),
                            ft.Text(f"= {format_pln(tx.total_pln)}", size=12, color=AppColors.TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                        ], spacing=8),
                        padding=ft.Padding.symmetric(vertical=4, horizontal=8),
                        bgcolor=AppColors.SURFACE_VARIANT if transactions.index(tx) % 2 == 0 else None,
                        border_radius=4,
                    )
                )
            
            # Ticker tile
            ticker_tiles.append(
                ft.ExpansionTile(
                    title=ft.Text(ticker, size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                    subtitle=ft.Text(
                        f"{len(transactions)} {t('tx.trans')} | {total_qty_bought:.2f} {t('tx.qty_unit')} {t('tx.bought')} | {t('tx.avg_cost')}: {avg_cost:.2f}",
                        size=11, color=AppColors.TEXT_MUTED
                    ),
                    controls=tx_rows,
                )
            )
        
        # Broker tile
        broker_tiles.append(
            ft.ExpansionTile(
                title=ft.Text(broker_names.get(source, source), size=16, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                subtitle=ft.Text(f"{len(tickers)} {t('tx.instruments')} | {total_transactions} {t('tx.transactions')}", size=12, color=AppColors.TEXT_SECONDARY),
                controls=ticker_tiles,
            )
        )
    
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.RECEIPT_LONG, color=AppColors.SECONDARY, size=24),
                ft.Text(t("tx.title"), size=16, weight=ft.FontWeight.BOLD, color=AppColors.SECONDARY),
            ], spacing=10),
            ft.Text(t("tx.expand_hint"), size=12, color=AppColors.TEXT_MUTED),
            ft.Divider(height=16, color=AppColors.BORDER),
            ft.Column(broker_tiles, spacing=8),
        ], spacing=8),
        bgcolor=AppColors.CARD,
        border=ft.Border.all(1, AppColors.BORDER),
        border_radius=AppTheme.BORDER_RADIUS,
        padding=20,
    )

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main(page: ft.Page):
    # --- Initialize language from saved settings ---
    try:
        _init_settings = SettingsManager.load()
        _saved_lang = _init_settings.get("language", "pl")
        _saved_country = _init_settings.get("country", "PL")
        set_language(_saved_lang)
        # Apply Kirchensteuer setting to Germany config
        _kist = _init_settings.get("kirchensteuer")
        try:
            _de = get_country("DE")
            _de.extra["kirchensteuer"] = _kist
            if _init_settings.get("joint_filing"):
                _de.tax_free_allowance = _de.extra.get("sparerpauschbetrag_joint", 2000.0)
        except Exception:
            pass
    except Exception:
        _saved_country = "PL"

    try:
        _country_cfg = get_country(_saved_country)
        _form_name = _country_cfg.tax_form_name
    except Exception:
        _country_cfg = None
        _form_name = "PIT-38"

    page.title = f"EuroTaxCalc v{APP_VERSION} | {_form_name}"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = AppColors.BACKGROUND
    page.padding = 0
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 900
    page.window.min_height = 600

    # FilePicker in Flet 0.80+ has async issues, use tkinter directly
    FILE_PICKER_AVAILABLE = False
    file_picker = None

    # --- LEGAL DISCLAIMER (first startup) - MORE VISIBLE ---
    DISCLAIMER_FILE = "disclaimer_accepted.txt"

    def close_window(pg):
        """Close the application window."""
        try:
            pg.window.close()
        except:
            import sys
            sys.exit(0)

    def show_disclaimer():
        # Checkboxes for mandatory consent
        consent_checkbox = ft.Checkbox(
            label="☑️ Akceptuję warunki - rozumiem że aplikacja NIE stanowi porady podatkowej i ponoszę pełną odpowiedzialność za poprawność zeznania",
            value=False,
        )
        notification_checkbox = ft.Checkbox(
            label="Wyrażam zgodę na powiadomienia o terminach podatkowych (opcjonalne)",
            value=True,
        )

        accept_btn = ft.Button(
            "✅ Akceptuję i kontynuuję",
            disabled=True,
            bgcolor=AppColors.TEXT_MUTED,
            color=AppColors.TEXT_PRIMARY,
        )

        def on_consent_change(e):
            if consent_checkbox.value:
                accept_btn.disabled = False
                accept_btn.bgcolor = AppColors.ACCENT_RED  # Red for emphasis
            else:
                accept_btn.disabled = True
                accept_btn.bgcolor = AppColors.TEXT_MUTED
            page.update()

        consent_checkbox.on_change = on_consent_change

        def accept_disclaimer(e):
            if not consent_checkbox.value:
                return
            with open(DISCLAIMER_FILE, 'w', encoding='utf-8') as f:
                f.write(f"Accepted: {datetime.datetime.now().isoformat()}\nNotifications: {notification_checkbox.value}")
            dialog.open = False
            page.update()
            if notification_checkbox.value:
                check_tax_deadline()

        accept_btn.on_click = accept_disclaimer

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠️ WAŻNA INFORMACJA PRAWNA", size=22, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_RED),
            content=ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Text(
                            "Ten program jest WYŁĄCZNIE narzędziem pomocniczym do obliczeń podatkowych.",
                            size=16, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_RED,
                        ),
                        bgcolor="#ffebee",  # Light red background
                        padding=ft.Padding.all(16),
                        border_radius=8,
                        border=ft.Border.all(2, AppColors.ACCENT_RED),
                    ),
                    ft.Divider(height=20),
                    ft.Text(
                        "❌ NIE stanowi porady prawnej ani podatkowej\n"
                        "❌ NIE zastępuje konsultacji z doradcą podatkowym\n"
                        "⚠️ Wyniki mogą zawierać błędy - ZAWSZE zweryfikuj obliczenia\n"
                        "✅ Odpowiedzialność za poprawność zeznania spoczywa na użytkowniku",
                        size=14, color=AppColors.TEXT_SECONDARY,
                    ),
                    ft.Divider(height=20),
                    ft.Container(
                        content=ft.Text(
                            "Klikając 'Akceptuję i kontynuujesz' oświadczasz, że:\n"
                            "• Zapoznałeś/aś się z informacją prawną\n"
                            "• Rozumiesz że to narzędzie pomocnicze\n"
                            "• Przyjmujesz pełną odpowiedzialność za decyzje podatkowe",
                            size=12, color=AppColors.TEXT_MUTED, italic=True,
                        ),
                        bgcolor=AppColors.SURFACE_VARIANT,
                        padding=ft.Padding.all(12),
                        border_radius=8,
                    ),
                    ft.Divider(height=16),
                    consent_checkbox,
                    notification_checkbox,
                ], spacing=8, tight=True),
                width=600,
            ),
            actions=[
                ft.TextButton("❌ Nie akceptuję - Zamknij", on_click=lambda e: close_window(page)),
                accept_btn,
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()
    
    def check_tax_deadline():
        """Show reminder if less than 60 days to April 30 tax deadline."""
        today = datetime.date.today()
        current_year = today.year
        
        # Tax deadline is April 30 of current year (or next year if already past)
        deadline = datetime.date(current_year, 4, 30)
        if today > deadline:
            deadline = datetime.date(current_year + 1, 4, 30)
        
        days_left = (deadline - today).days
        
        if days_left <= 60:
            urgency = "🔴 PILNE!" if days_left <= 14 else "🟡 UWAGA!"
            page.snack_bar = ft.SnackBar(
                content=ft.Row([
                    ft.Text(f"{urgency} Do terminu PIT-38 zostało {days_left} dni ({deadline.strftime('%d.%m.%Y')})", 
                           color=AppColors.TEXT_PRIMARY, weight=ft.FontWeight.BOLD),
                ]),
                bgcolor=AppColors.ACCENT_RED if days_left <= 14 else AppColors.ACCENT_GOLD,
                duration=8000,
            )
            page.snack_bar.open = True
            page.update()
    
    # Check if disclaimer was accepted
    DISCLAIMER_PATH = Path(DISCLAIMER_FILE)
    if not DISCLAIMER_PATH.exists():
        show_disclaimer()
    else:
        check_tax_deadline()

    nbp_service = NBPService()
    crypto_service = CryptoService()
    engine = CalculatorEngine(nbp_service, crypto_service)
    db = HistoryDatabase()
    executor = ThreadPoolExecutor(max_workers=2)

    t212_path: Path | None = None
    ibkr_path: Path | None = None
    xtb_path: Path | None = None
    bossa_path: Path | None = None
    mbank_path: Path | None = None

    # Load settings
    settings = SettingsManager.load()
    last_t212 = settings.get("t212_path")
    last_ibkr = settings.get("ibkr_path")
    last_xtb = settings.get("xtb_path")
    last_bossa = settings.get("bossa_path")
    last_mbank = settings.get("mbank_path")

    if last_t212 and Path(last_t212).exists():
        t212_path = Path(last_t212)
    if last_ibkr and Path(last_ibkr).exists():
        ibkr_path = Path(last_ibkr)
    if last_xtb and Path(last_xtb).exists():
        xtb_path = Path(last_xtb)
    if last_bossa and Path(last_bossa).exists():
        bossa_path = Path(last_bossa)
    if last_mbank and Path(last_mbank).exists():
        mbank_path = Path(last_mbank)
        
    generic_files: list[dict] = []  # [{'path': str, 'broker': str, 'name': str}, ...]
    current_result: CalculationResult | None = None
    
    t212_text = ft.Text(Path(t212_path).name if t212_path else t("calc.no_file"),
                       color=AppColors.ACCENT_GREEN if t212_path else AppColors.TEXT_MUTED, size=13)
    ibkr_text = ft.Text(Path(ibkr_path).name if ibkr_path else t("calc.no_file"),
                       color=AppColors.ACCENT_GREEN if ibkr_path else AppColors.TEXT_MUTED, size=13)
    xtb_text = ft.Text(Path(xtb_path).name if xtb_path else t("calc.no_file"),
                       color=AppColors.ACCENT_GREEN if xtb_path else AppColors.TEXT_MUTED, size=13)
    bossa_text = ft.Text(Path(bossa_path).name if bossa_path else t("calc.no_file"),
                         color=AppColors.ACCENT_GREEN if bossa_path else AppColors.TEXT_MUTED, size=13)
    mbank_text = ft.Text(Path(mbank_path).name if mbank_path else t("calc.no_file"),
                         color=AppColors.ACCENT_GREEN if mbank_path else AppColors.TEXT_MUTED, size=13)
    generic_text = ft.Text(t("calc.no_files_plural"), color=AppColors.TEXT_MUTED, size=13)
    results_container = ft.Column([], spacing=20)
    progress_ring = ft.ProgressRing(visible=False, color=AppColors.PRIMARY, stroke_width=3)
    progress_text = ft.Text("", color=AppColors.TEXT_SECONDARY, size=13, visible=False)
    calculate_btn: ft.Button | None = None
    history_table_container = ft.Column([])

    # Use tkinter file dialogs directly (more reliable than Flet FilePicker in 0.80+)
    # Variables to track which button was clicked
    pick_target = {"type": None}  # 't212', 'ibkr', or 'generic'

    def open_file_dialog_tkinter(file_type: str) -> list[str] | None:
        """File picker using zenity (GTK) - works on Linux without tkinter."""
        import subprocess
        import os
        
        try:
            if file_type == "multiple":
                # Zenity multiple file selection
                result = subprocess.run(
                    ['zenity', '--file-selection', '--multiple', 
                     '--title=Wybierz pliki CSV',
                     '--file-filter=*.csv', '--file-filter=*.*'],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Zenity returns pipe-separated paths
                    paths = result.stdout.strip().split('|')
                    return paths
                return None
            else:
                # Zenity single file selection
                result = subprocess.run(
                    ['zenity', '--file-selection',
                     '--title=Wybierz plik CSV',
                     '--file-filter=*.csv', '--file-filter=*.*'],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and result.stdout.strip():
                    return [result.stdout.strip()]
                return None
        except FileNotFoundError:
            # Zenity not available, try kdialog (KDE)
            try:
                if file_type == "multiple":
                    result = subprocess.run(
                        ['kdialog', '--getopenfilenames', '*.csv'],
                        capture_output=True, text=True, timeout=120
                    )
                else:
                    result = subprocess.run(
                        ['kdialog', '--getopenfilename', '*.csv'],
                        capture_output=True, text=True, timeout=120
                    )
                if result.returncode == 0 and result.stdout.strip():
                    paths = result.stdout.strip().split(' ')
                    return [p.strip() for p in paths if p.strip()]
                return None
            except:
                return None
        except Exception as e:
            print(f"[File Picker] Error: {e}")
            return None

    def process_file_paths(paths: list[str], target_type: str):
        """Process selected file paths."""
        nonlocal t212_path, ibkr_path, xtb_path, bossa_path, mbank_path, generic_files

        if not paths or len(paths) == 0:
            pick_target["type"] = None
            page.update()
            return

        if target_type == "t212":
            t212_path = Path(paths[0])
            t212_text.value = t212_path.name
            t212_text.color = AppColors.ACCENT_GREEN
            t212_clear_btn.visible = True
            settings = SettingsManager.load()
            settings["t212_path"] = str(t212_path)
            SettingsManager.save(settings)

        elif target_type == "ibkr":
            ibkr_path = Path(paths[0])
            ibkr_text.value = ibkr_path.name
            ibkr_text.color = AppColors.ACCENT_GREEN
            ibkr_clear_btn.visible = True
            settings = SettingsManager.load()
            settings["ibkr_path"] = str(ibkr_path)
            SettingsManager.save(settings)

        elif target_type == "xtb":
            xtb_path = Path(paths[0])
            xtb_text.value = xtb_path.name
            xtb_text.color = AppColors.ACCENT_GREEN
            xtb_clear_btn.visible = True
            settings = SettingsManager.load()
            settings["xtb_path"] = str(xtb_path)
            SettingsManager.save(settings)

        elif target_type == "bossa":
            bossa_path = Path(paths[0])
            bossa_text.value = bossa_path.name
            bossa_text.color = AppColors.ACCENT_GREEN
            bossa_clear_btn.visible = True
            settings = SettingsManager.load()
            settings["bossa_path"] = str(bossa_path)
            SettingsManager.save(settings)

        elif target_type == "mbank":
            mbank_path = Path(paths[0])
            mbank_text.value = mbank_path.name
            mbank_text.color = AppColors.ACCENT_GREEN
            mbank_clear_btn.visible = True
            settings = SettingsManager.load()
            settings["mbank_path"] = str(mbank_path)
            SettingsManager.save(settings)

        elif target_type == "generic":
            for path in paths:
                broker = detect_broker_by_name(path)
                generic_files.append({
                    'path': path,
                    'broker': broker,
                    'name': Path(path).name
                })
            if len(generic_files) == 1:
                generic_text.value = f"{generic_files[0]['name']} ({generic_files[0]['broker']})"
            else:
                brokers = set(gf['broker'] for gf in generic_files)
                generic_text.value = f"{len(generic_files)} plików ({', '.join(brokers)})"
            generic_text.color = AppColors.ACCENT_GREEN
            generic_clear_btn.visible = True

        pick_target["type"] = None
        page.update()

    def detect_broker_by_name(path: str) -> str:
        """Detect broker from filename."""
        f_lower = path.lower()
        if 'trading212' in f_lower or 't212' in f_lower:
            return 'Trading 212'
        elif 'ibkr' in f_lower or 'interactive' in f_lower:
            return 'IBKR'
        elif 'xtb' in f_lower:
            return 'XTB'
        elif 'revolut' in f_lower:
            return 'Revolut'
        elif 'etoro' in f_lower:
            return 'eToro'
        elif 'degiro' in f_lower:
            return 'Degiro'
        elif 'mbank' in f_lower:
            return 'mBank'
        elif 'bossa' in f_lower:
            return 'BOŚ Bossa'
        elif 'freedom' in f_lower:
            return 'Freedom24'
        elif 'saxo' in f_lower:
            return 'Saxo'
        else:
            return 'Inny broker'

    def pick_t212_file(e):
        """Open file picker for T212 CSV."""
        result = open_file_dialog_tkinter("t212")
        if result:
            process_file_paths(result, "t212")

    def pick_ibkr_file(e):
        """Open file picker for IBKR CSV."""
        result = open_file_dialog_tkinter("ibkr")
        if result:
            process_file_paths(result, "ibkr")

    def clear_t212_file(e):
        nonlocal t212_path
        t212_path = None
        t212_text.value = t("calc.no_file")
        t212_text.color = AppColors.TEXT_MUTED
        t212_clear_btn.visible = False

        # Clear setting
        settings = SettingsManager.load()
        if "t212_path" in settings:
            del settings["t212_path"]
            SettingsManager.save(settings)

        page.update()

    def clear_ibkr_file(e):
        nonlocal ibkr_path
        ibkr_path = None
        ibkr_text.value = t("calc.no_file")
        ibkr_text.color = AppColors.TEXT_MUTED
        ibkr_clear_btn.visible = False

        # Clear setting
        settings = SettingsManager.load()
        if "ibkr_path" in settings:
            del settings["ibkr_path"]
            SettingsManager.save(settings)

        page.update()

    def pick_xtb_file(e):
        """Open file picker for XTB CSV."""
        pick_target["type"] = "xtb"
        file_picker.pick_files(
            allowed_extensions=["csv"],
            dialog_title="Wybierz plik XTB",
            allow_multiple=False
        )

    def pick_bossa_file(e):
        """Open file picker for BOŚ Bossa CSV."""
        pick_target["type"] = "bossa"
        file_picker.pick_files(
            allowed_extensions=["csv"],
            dialog_title="Wybierz plik BOŚ Bossa",
            allow_multiple=False
        )

    def pick_mbank_file(e):
        """Open file picker for mBank CSV."""
        pick_target["type"] = "mbank"
        file_picker.pick_files(
            allowed_extensions=["csv"],
            dialog_title="Wybierz plik mBank",
            allow_multiple=False
        )

    def clear_xtb_file(e):
        nonlocal xtb_path
        xtb_path = None
        xtb_text.value = t("calc.no_file")
        xtb_text.color = AppColors.TEXT_MUTED
        xtb_clear_btn.visible = False
        # Clear setting
        settings = SettingsManager.load()
        if "xtb_path" in settings:
            del settings["xtb_path"]
            SettingsManager.save(settings)
        page.update()

    def clear_bossa_file(e):
        nonlocal bossa_path
        bossa_path = None
        bossa_text.value = t("calc.no_file")
        bossa_text.color = AppColors.TEXT_MUTED
        bossa_clear_btn.visible = False
        settings = SettingsManager.load()
        if "bossa_path" in settings:
            del settings["bossa_path"]
            SettingsManager.save(settings)
        page.update()

    def clear_mbank_file(e):
        nonlocal mbank_path
        mbank_path = None
        mbank_text.value = t("calc.no_file")
        mbank_text.color = AppColors.TEXT_MUTED
        mbank_clear_btn.visible = False
        settings = SettingsManager.load()
        if "mbank_path" in settings:
            del settings["mbank_path"]
            SettingsManager.save(settings)
        page.update()

    def pick_generic_files(e):
        """Pick multiple CSV files from any broker."""
        result = open_file_dialog_tkinter("multiple")
        if result:
            process_file_paths(result, "generic")

    def clear_generic_files(e):
        nonlocal generic_files
        generic_files = []
        generic_text.value = t("calc.no_files_plural")
        generic_text.color = AppColors.TEXT_MUTED
        generic_clear_btn.visible = False
        page.update()
    
    # Clear buttons (initially hidden)
    t212_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR,
        icon_color=AppColors.ACCENT_RED,
        tooltip="Usuń plik",
        on_click=clear_t212_file,
        visible=bool(t212_path),
    )

    ibkr_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR,
        icon_color=AppColors.ACCENT_RED,
        tooltip="Usuń plik",
        on_click=clear_ibkr_file,
        visible=bool(ibkr_path),
    )

    xtb_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR,
        icon_color=AppColors.ACCENT_RED,
        tooltip="Usuń plik",
        on_click=clear_xtb_file,
        visible=bool(xtb_path),
    )

    bossa_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR,
        icon_color=AppColors.ACCENT_RED,
        tooltip="Usuń plik",
        on_click=clear_bossa_file,
        visible=bool(bossa_path),
    )

    mbank_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR,
        icon_color=AppColors.ACCENT_RED,
        tooltip="Usuń plik",
        on_click=clear_mbank_file,
        visible=bool(mbank_path),
    )

    generic_clear_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=AppColors.ACCENT_RED,
        icon_size=18,
        on_click=clear_generic_files,
        visible=False,
        tooltip="Usuń wszystkie pliki",
    )
    
    def on_progress(message: str, progress: float):
        progress_text.value = message
        page.update()

    def export_pdf_and_open(result, pg):
        """Export to professional PDF and open in browser."""
        try:
            output_path = Path(export_to_professional_pdf(result, "raport_podatkowy.pdf", 2024)).resolve()
            webbrowser.open(output_path.as_uri())
            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ Raport PDF zapisany!", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_GREEN,
            )
            pg.snack_bar.open = True
            pg.update()
        except Exception as ex:
            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Błąd eksportu PDF: {ex}", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_RED,
            )
            pg.snack_bar.open = True
            pg.update()

    def export_excel_and_open(result, pg):
        """Export to Excel and open - cross-platform."""
        try:
            output_path = Path(export_to_excel(result, "raport_podatkowy.xlsx", 2024)).resolve()

            # Cross-platform file opening
            if os.name == 'nt':  # Windows
                os.startfile(str(output_path))
            elif os.name == 'posix':  # Linux/macOS
                import subprocess
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', str(output_path)], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', str(output_path)], check=True)
            else:
                # Fallback: just show notification
                pg.snack_bar = ft.SnackBar(
                    content=ft.Text(f"📊 Raport Excel zapisany: {output_path}", color=AppColors.TEXT_PRIMARY),
                    bgcolor=AppColors.ACCENT_GREEN,
                )
                pg.snack_bar.open = True
                pg.update()
                return

            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ Raport Excel zapisany!", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_GREEN,
            )
            pg.snack_bar.open = True
            pg.update()
        except Exception as ex:
            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Błąd eksportu Excel: {ex}", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_RED,
            )
            pg.snack_bar.open = True
            pg.update()

    def show_taxpayer_data_dialog(result, pg):
        """Show dialog to collect taxpayer data for official PIT-38."""
        # Input fields for taxpayer data
        nip_input = ft.TextField(
            label="NIP (10 cyfr)",
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=10,
            width=400
        )
        pesel_input = ft.TextField(
            label="PESEL (11 cyfr)",
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=11,
            width=400
        )
        street_input = ft.TextField(label="Ulica", width=400)
        building_input = ft.TextField(label="Nr budynku", width=200)
        apartment_input = ft.TextField(label="Nr lokalu", width=200)
        city_input = ft.TextField(label="Miejscowość", width=400)
        postal_input = ft.TextField(label="Kod pocztowy (XX-XXX)", width=200)
        phone_input = ft.TextField(label="Telefon", width=400)
        email_input = ft.TextField(label="Email", width=400)
        iban_input = ft.TextField(label="NR rachunku bankowego (IBAN)", width=400)
        
        # 1.5% OPP section
        opp_krs_input = ft.TextField(label="KRS Organizacji Pożytku Publicznego", width=400)
        opp_amount_input = ft.TextField(label="Kwota 1.5%", keyboard_type=ft.KeyboardType.NUMBER, width=200)
        opp_cele_input = ft.TextField(label="Cel szczegółowy (opcjonalnie)", width=400)
        
        def submit_data(e):
            """Export official XML + PDF with provided data."""
            taxpayer_data = {
                'nip': nip_input.value,
                'pesel': pesel_input.value,
                'address': {
                    'street': street_input.value,
                    'building': building_input.value,
                    'apartment': apartment_input.value,
                    'city': city_input.value,
                    'postal_code': postal_input.value,
                },
                'phone': phone_input.value,
                'email': email_input.value,
                'bank_account': iban_input.value,
                'opp_krs': opp_krs_input.value,
                'opp_amount': float(opp_amount_input.value) if opp_amount_input.value else None,
                'opp_cele': opp_cele_input.value,
            }
            
            try:
                year = result.timestamp.year - 1 if result.timestamp else APP_YEAR
                
                # Generate OFFICIAL XML (for e-submission)
                xml_path = Path(export_to_official_pit38_xml(
                    result,
                    taxpayer_data,
                    f"PIT-38_{year}_oficjalny.xml"
                )).resolve()
                
                # Generate INSTRUCTIONS HTML (easy-to-follow guide)
                instr_path = Path(generate_pit38_instructions(result, year, taxpayer_data, f"PIT-38_{year}_instrukcja.html")).resolve()
                
                dialog.open = False
                
                # Show success message with both files
                pg.snack_bar = ft.SnackBar(
                    content=ft.Column([
                        ft.Text("✅ Wygenerowano PIT-38!", color=AppColors.TEXT_PRIMARY, weight=ft.FontWeight.BOLD),
                        ft.Divider(height=8, color=AppColors.BORDER),
                        ft.Text(f"📄 XML: {xml_path}", size=12, color=AppColors.TEXT_SECONDARY),
                        ft.Text("   → Do wysłania elektronicznie (e-Urząd Skarbowy)", size=11),
                        ft.Text(f"📄 Instrukcja: {instr_path}", size=12, color=AppColors.TEXT_SECONDARY),
                        ft.Text("   → Wydrukuj i użyj jako pomoc przy wypełnianiu", size=11),
                    ], spacing=4),
                    bgcolor=AppColors.ACCENT_GREEN,
                    duration=8000,
                    behavior=ft.SnackBarBehavior.FLOATING,
                )
                pg.snack_bar.open = True
                pg.update()
                
                # Open both files in browser
                import pathlib
                webbrowser.open(pathlib.Path(xml_path).as_uri())
                webbrowser.open(pathlib.Path(instr_path).as_uri())
                
            except Exception as ex:
                print(f"[EXPORT ERROR] {ex}")
                import traceback
                traceback.print_exc()
                pg.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Błąd generowania: {ex}", color=AppColors.TEXT_PRIMARY),
                    bgcolor=AppColors.ACCENT_RED,
                )
                pg.snack_bar.open = True
                pg.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Dane do PIT-38", size=20, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Wprowadź dane do formularza PIT-38(18)", size=13, color=AppColors.TEXT_SECONDARY),
                    ft.Text("Wygenerujemy XML (do e-Urzędu) + PDF (do druku)", size=12, color=AppColors.ACCENT_GOLD, italic=True),
                    ft.Divider(height=16),
                    ft.Text("DANE PODATNIKA", size=14, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    nip_input,
                    pesel_input,
                    ft.Divider(height=12),
                    ft.Text("ADRES ZAMIESZKANIA", size=14, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    street_input,
                    ft.Row([building_input, apartment_input], spacing=16),
                    ft.Row([city_input, postal_input], spacing=16),
                    ft.Divider(height=12),
                    ft.Text("DANE KONTAKTOWE", size=14, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    phone_input,
                    email_input,
                    ft.Divider(height=12),
                    ft.Text("ZWROT PODATKU", size=14, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    iban_input,
                    ft.Text("Nr rachunku do zwrotu (opcjonalne)", size=11, color=AppColors.TEXT_MUTED),
                    ft.Divider(height=12),
                    ft.Text("1.5% DLA OPP", size=14, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_GOLD),
                    opp_krs_input,
                    ft.Row([opp_amount_input, opp_cele_input], spacing=16),
                    ft.Text("Przekaż 1.5% na OPP (opcjonalne)", size=11, color=AppColors.TEXT_MUTED),
                ], spacing=8, scroll=ft.ScrollMode.AUTO),
                width=500,
                height=500,
            ),
            actions=[
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dialog, 'open', False)),
                ft.Button(
                    "Generuj XML + Instrukcję",
                    bgcolor=AppColors.ACCENT_GREEN,
                    color=AppColors.TEXT_PRIMARY,
                    on_click=submit_data,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        
        pg.overlay.append(dialog)
        dialog.open = True
        pg.update()

    def export_pit38_and_open(result, pg):
        """Generate official PIT-38 XML + PDF."""
        show_taxpayer_data_dialog(result, pg)
    
    def export_and_notify_json(result, pg):
        """Export calculation result to JSON backup."""
        try:
            from dataclasses import asdict
            backup_data = {
                'timestamp': datetime.datetime.now().isoformat(),
                'year': 2024,
                't212': {
                    'stock_income': result.t212.stock_income,
                    'stock_cost': result.t212.stock_cost,
                    'dividend_gross': result.t212.dividend_gross,
                    'dividend_tax_foreign': result.t212.dividend_tax_foreign,
                },
                'ibkr': {
                    'stock_income': result.ibkr.stock_income,
                    'stock_cost': result.ibkr.stock_cost,
                    'dividend_gross': result.ibkr.dividend_gross,
                    'dividend_tax_foreign': result.ibkr.dividend_tax_foreign,
                },
                'total': {
                    'stock_income': result.total.stock_income,
                    'stock_cost': result.total.stock_cost,
                    'stock_profit': result.total.stock_profit,
                    'dividend_gross': result.total.dividend_gross,
                    'dividend_tax_due': result.total.dividend_tax_due,
                    'interest_gross': result.total.interest_gross,
                    'interest_tax_due': result.total.interest_tax_due,
                },
                'transactions_count': len(result.transactions),
            }
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = Path(f"backup_podatki_{timestamp}.json").resolve()
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ Backup JSON zapisany: {output_path}", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_GREEN,
            )
            pg.snack_bar.open = True
            pg.update()
        except Exception as ex:
            pg.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Błąd backup JSON: {ex}", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_RED,
            )
            pg.snack_bar.open = True
            pg.update()
    
    def on_calculate(e):
        nonlocal current_result
        
        if not t212_path and not ibkr_path and not generic_files:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("⚠️ Wybierz przynajmniej jeden plik CSV!", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_RED,
            )
            page.snack_bar.open = True
            page.update()
            return
        
        calculate_btn.disabled = True
        progress_ring.visible = True
        progress_text.visible = True
        progress_text.value = t("calc.initializing")
        results_container.controls.clear()
        page.update()
        
        total_start_time = time.time()

        def run_calculation():
            nonlocal current_result
            try:
                engine.set_progress_callback(on_progress)

                # Combine all CSV paths (generic files are added to existing paths)
                all_generic_paths = [gf['path'] for gf in generic_files] if generic_files else []

                # Calculate with T212, IBKR, and generic files
                # Read current country from settings
                _calc_settings = SettingsManager.load()
                _country_code = _calc_settings.get("country", "PL")

                result = engine.calculate(
                    t212_path, ibkr_path,
                    xtb_path=str(xtb_path) if xtb_path else None,
                    bossa_path=str(bossa_path) if bossa_path else None,
                    mbank_path=str(mbank_path) if mbank_path else None,
                    generic_paths=all_generic_paths,
                    country_code=_country_code,
                )
                current_result = result

                db.save_calculation(result)

                calc_time = time.time() - total_start_time
                logger.info(f"[TIMING] Total user-perceived time: {calc_time:.2f}s")

                # Build UI components
                broker_cards = []
                has_t212 = t212_path is not None
                has_ibkr = ibkr_path is not None
                has_generic = len(generic_files) > 0

                _cc = result.country_code
                if has_t212:
                    broker_cards.append(create_result_card("Trading 212", result.t212, country_code=_cc))
                if has_ibkr:
                    broker_cards.append(create_result_card("Interactive Brokers", result.ibkr, country_code=_cc))

                if has_generic and hasattr(result, 'generic_brokers') and result.generic_brokers:
                    for broker_name, broker_result in result.generic_brokers.items():
                        broker_cards.append(create_result_card(broker_name, broker_result, country_code=_cc))

                if has_t212 or has_ibkr or has_generic:
                    broker_cards.append(create_result_card(t("calc.total"), result.total, is_total=True, country_code=_cc))

                results_container.controls = [
                    ft.Row(broker_cards, spacing=16, expand=True),
                    create_tax_summary_card(result),
                    create_tax_loss_harvesting_section(result),
                    create_transaction_details_panel(result),
                    ft.Container(
                        content=ft.Row([
                            # XML export only for Poland (KAS-compliant PIT-38)
                            *(
                                [ft.Button(t("export.xml"), icon=ft.Icons.DESCRIPTION,
                                    bgcolor=AppColors.ACCENT_GREEN, color=AppColors.TEXT_PRIMARY,
                                    on_click=lambda e: show_taxpayer_data_dialog(result, page))]
                                if result.country_code == "PL" else []
                            ),
                            ft.Button(t("export.pdf"), icon=ft.Icons.PICTURE_AS_PDF,
                                bgcolor=AppColors.PRIMARY, color=AppColors.TEXT_PRIMARY,
                                on_click=lambda e: export_pdf_and_open(result, page)),
                            ft.Button(t("export.excel"), icon=ft.Icons.TABLE_CHART,
                                bgcolor="#217346", color=AppColors.TEXT_PRIMARY,
                                on_click=lambda e: export_excel_and_open(result, page)),
                            ft.Button(t("export.json"), icon=ft.Icons.SAVE,
                                bgcolor=AppColors.SECONDARY, color=AppColors.TEXT_PRIMARY,
                                on_click=lambda e: export_and_notify_json(result, page)),
                        ], spacing=12, alignment=ft.MainAxisAlignment.CENTER, wrap=True),
                        padding=ft.Padding.symmetric(vertical=16),
                    ),
                ]

                calculate_btn.disabled = False
                progress_ring.visible = False
                progress_text.visible = False
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(t("calc.success"), color=AppColors.TEXT_PRIMARY),
                    bgcolor=AppColors.ACCENT_GREEN,
                )
                page.snack_bar.open = True
                # Force UI repaint (needed on Wayland/Linux where Flutter
                # doesn't repaint until user interaction without explicit push)
                page.update()
                refresh_history()
                import time as _time
                _time.sleep(0.05)
                page.update()

            except Exception as e:
                error_message = str(e)
                logger.error(f"[ERROR] Calculation failed: {error_message}", exc_info=True)
                
                # Check if it's an NBP API error
                is_nbp_error = "NBP" in str(e).upper() or "API" in str(e).upper()
                
                if is_nbp_error:
                    error_message = t("calc.error_nbp_help")
                
                calculate_btn.disabled = False
                progress_ring.visible = False
                progress_text.visible = False

                page.snack_bar = ft.SnackBar(
                    content=ft.Text(error_message, color=AppColors.TEXT_PRIMARY),
                    bgcolor=AppColors.ACCENT_RED,
                    duration=8000,
                )
                page.snack_bar.open = True
                page.update()

        # Run calculation in background thread
        executor.submit(run_calculation)

    def refresh_history():
        calculations = db.get_all_calculations()
        
        if not calculations:
            history_table_container.controls = [
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.HISTORY, size=48, color=AppColors.TEXT_MUTED),
                        ft.Text(t("history.no_records"), color=AppColors.TEXT_MUTED, size=16),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    alignment=ft.Alignment(0, 0),
                    expand=True,
                    padding=40,
                )
            ]
        else:
            history_cards = []
            for calc in calculations:
                dt = datetime.datetime.fromisoformat(calc['timestamp'])
                stock_profit = calc.get('stock_income', 0) - calc.get('stock_cost', 0)
                total_tax = calc.get('total_tax', 0)
                
                # Expanded details panel with highlighted sections
                details_panel = ft.Container(
                    content=ft.Column([
                        ft.Divider(height=16, color=AppColors.BORDER),
                        ft.Text(t("history.calc_details"), size=14, weight=ft.FontWeight.BOLD, color=AppColors.SECONDARY),
                        ft.Row([
                            # AKCJE section - highlighted
                            ft.Container(
                                content=ft.Column([
                                    ft.Container(
                                        content=ft.Text(t("history.stocks_label"), size=12, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                                        bgcolor=AppColors.PRIMARY,
                                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                        border_radius=4,
                                    ),
                                    ft.Row([ft.Text(t("history.income_label"), size=12, color=AppColors.TEXT_SECONDARY),
                                           ft.Text(format_pln(calc.get('stock_income', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                    ft.Row([ft.Text(t("history.cost_label"), size=12, color=AppColors.TEXT_SECONDARY),
                                           ft.Text(format_pln(calc.get('stock_cost', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                    ft.Row([ft.Text(t("history.profit_loss_lbl"), size=12, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.BOLD),
                                           ft.Text(format_pln(stock_profit), size=13,
                                                  color=AppColors.ACCENT_GREEN if stock_profit >= 0 else AppColors.ACCENT_RED,
                                                  weight=ft.FontWeight.BOLD)]),
                                ], spacing=4),
                                bgcolor=AppColors.SURFACE_VARIANT,
                                border=ft.Border.all(1, AppColors.PRIMARY),
                                border_radius=8,
                                padding=10,
                                expand=True,
                            ),
                            # DYWIDENDY section - highlighted
                            ft.Container(
                                content=ft.Column([
                                    ft.Container(
                                        content=ft.Text(t("history.dividends_label"), size=12, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                                        bgcolor=AppColors.SECONDARY,
                                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                        border_radius=4,
                                    ),
                                    ft.Row([ft.Text(t("history.gross_label"), size=12, color=AppColors.TEXT_SECONDARY),
                                           ft.Text(format_pln(calc.get('dividend_gross', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                    ft.Row([ft.Text(t("history.foreign_tax_lbl"), size=12, color=AppColors.TEXT_SECONDARY),
                                           ft.Text(format_pln(calc.get('dividend_tax_foreign', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                ], spacing=4),
                                bgcolor=AppColors.SURFACE_VARIANT,
                                border=ft.Border.all(1, AppColors.SECONDARY),
                                border_radius=8,
                                padding=10,
                                expand=True,
                            ),
                            # ODSETKI section
                            ft.Container(
                                content=ft.Column([
                                    ft.Container(
                                        content=ft.Text(t("history.interest_label"), size=12, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                                        bgcolor=AppColors.ACCENT_GOLD,
                                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                        border_radius=4,
                                    ),
                                    ft.Row([ft.Text(t("history.gross_label"), size=12, color=AppColors.TEXT_SECONDARY),
                                           ft.Text(format_pln(calc.get('interest_gross', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                ], spacing=4),
                                bgcolor=AppColors.SURFACE_VARIANT,
                                border=ft.Border.all(1, AppColors.ACCENT_GOLD),
                                border_radius=8,
                                padding=10,
                                expand=True,
                            ),
                            # BONUSY section
                            ft.Container(
                                content=ft.Column([
                                    ft.Container(
                                        content=ft.Text(t("history.bonuses_label"), size=12, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                                        bgcolor=AppColors.ACCENT_GREEN,
                                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                        border_radius=4,
                                    ),
                                    ft.Row([ft.Text("T212:", size=12, color=AppColors.TEXT_SECONDARY), 
                                           ft.Text(format_pln(calc.get('bonuses', 0)), size=12, color=AppColors.TEXT_PRIMARY)]),
                                ], spacing=4),
                                bgcolor=AppColors.SURFACE_VARIANT,
                                border=ft.Border.all(1, AppColors.ACCENT_GREEN),
                                border_radius=8,
                                padding=10,
                                expand=True,
                            ),
                        ], spacing=12),
                        ft.Divider(height=16, color=AppColors.BORDER),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=18, color=AppColors.ACCENT_GOLD),
                                ft.Text(t("history.total_tax_due"), size=14, color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.BOLD),
                                ft.Text(format_pln(total_tax), size=18, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_GOLD),
                            ], spacing=8),
                            bgcolor=AppColors.SURFACE_VARIANT,
                            border_radius=8,
                            padding=12,
                        ),
                    ], spacing=8),
                    padding=ft.Padding.only(top=12),
                    visible=False,
                )
                
                def toggle_details(e, panel=details_panel):
                    panel.visible = not panel.visible
                    page.update()
                
                # History card with expandable details
                card = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color=AppColors.PRIMARY),
                                    ft.Text(dt.strftime("%Y-%m-%d %H:%M"), size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                ], spacing=8),
                                ft.Text(t("history.profit_and_tax", profit=format_pln(stock_profit), tax=format_pln(total_tax)), size=12, color=AppColors.TEXT_SECONDARY),
                            ], expand=True),
                            ft.Row([
                                ft.IconButton(
                                    icon=ft.Icons.EXPAND_MORE,
                                    icon_color=AppColors.PRIMARY,
                                    icon_size=20,
                                    tooltip=t("history.show_details"),
                                    on_click=toggle_details,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    icon_color=AppColors.ACCENT_RED,
                                    icon_size=18,
                                    tooltip=t("history.delete_tip"),
                                    on_click=lambda e, cid=calc['id']: delete_calc(cid),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        details_panel,
                    ]),
                    bgcolor=AppColors.CARD,
                    border=ft.Border.all(1, AppColors.BORDER),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=16,
                )
                history_cards.append(card)
            
            history_table_container.controls = history_cards
        page.update()
    
    # Undo stack for deleted calculations
    deleted_history_stack = []
    
    def delete_calc(calc_id: int):
        # Save to undo stack before deleting
        calc_data = db.get_calculation(calc_id)
        if calc_data:
            deleted_history_stack.append(calc_data)
        db.delete_calculation(calc_id)
        refresh_history()
        page.snack_bar = ft.SnackBar(
            content=ft.Row([
                ft.Text("Usunięto z historii", color=AppColors.TEXT_PRIMARY),
                ft.TextButton("COFNIJ", on_click=lambda e: undo_delete(),
                             style=ft.ButtonStyle(color=AppColors.PRIMARY)),
            ], spacing=16),
            bgcolor=AppColors.SURFACE_VARIANT,
            duration=5000,
        )
        page.snack_bar.open = True
        page.update()
    
    def undo_delete():
        if deleted_history_stack:
            calc_data = deleted_history_stack.pop()
            db.restore_calculation(calc_data)
            refresh_history()
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Przywrocono obliczenie", color=AppColors.TEXT_PRIMARY),
                bgcolor=AppColors.ACCENT_GREEN,
            )
            page.snack_bar.open = True
            page.update()
        page.snack_bar.open = True
        page.update()
    
    def create_calculator_view() -> ft.Container:
        nonlocal calculate_btn
        
        calculate_btn = ft.Button(
            content=ft.Row([
                ft.Icon(ft.Icons.CALCULATE, size=24),
                ft.Text(t("calc.calculate_button"), size=16, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            on_click=on_calculate,
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY,
                color=AppColors.TEXT_PRIMARY,
                padding=20,
                shape=ft.RoundedRectangleBorder(radius=10),
                shadow_color=AppColors.PRIMARY,
                elevation=8,
            ),
            height=60,
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CALCULATE, size=32, color=AppColors.PRIMARY),
                        ft.Column([
                            ft.Text(t("calc.title"), size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                            ft.Text(t("calc.tax_subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                        ], spacing=2),
                    ], spacing=16),
                    padding=ft.Padding.only(bottom=8),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.HELP_OUTLINE, size=14, color=AppColors.TEXT_MUTED),
                        ft.Text(t("calc.csv_faq_hint"), size=12, color=AppColors.TEXT_MUTED, italic=True),
                    ], spacing=6),
                    padding=ft.Padding.only(bottom=16),
                ),
                ft.Container(
                    content=ft.Column([
                        # Trading 212
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Container(
                                        content=ft.Text("T212", size=16, weight=ft.FontWeight.BOLD, color="white"),
                                        bgcolor="#00A86B",  # T212 green
                                        padding=ft.Padding.all(8),
                                        border_radius=8,
                                        width=70,
                                        alignment=ft.alignment.Alignment.CENTER,
                                    ),
                                    ft.Column([
                                        ft.Text("Trading 212", size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        t212_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                t212_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16), ft.Text(t("calc.select_file"))], spacing=8),
                                    on_click=pick_t212_file,
                                    style=ft.ButtonStyle(bgcolor=AppColors.SURFACE_VARIANT, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=20, color=AppColors.BORDER),
                        # Interactive Brokers
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Container(
                                        content=ft.Text("IBKR", size=14, weight=ft.FontWeight.BOLD, color="white"),
                                        bgcolor="#003366",  # IBKR blue
                                        padding=ft.Padding.all(8),
                                        border_radius=8,
                                        width=70,
                                        alignment=ft.alignment.Alignment.CENTER,
                                    ),
                                    ft.Column([
                                        ft.Text("Interactive Brokers", size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        ibkr_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                ibkr_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16), ft.Text(t("calc.select_file"))], spacing=8),
                                    on_click=pick_ibkr_file,
                                    style=ft.ButtonStyle(bgcolor=AppColors.SURFACE_VARIANT, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=20, color=AppColors.BORDER),
                        # XTB
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Container(
                                        content=ft.Text("XTB", size=16, weight=ft.FontWeight.BOLD, color="white"),
                                        bgcolor="#FF6600",  # XTB orange
                                        padding=ft.Padding.all(8),
                                        border_radius=8,
                                        width=70,
                                        alignment=ft.alignment.Alignment.CENTER,
                                    ),
                                    ft.Column([
                                        ft.Text("XTB xStation", size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        xtb_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                xtb_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16), ft.Text(t("calc.select_file"))], spacing=8),
                                    on_click=pick_xtb_file,
                                    style=ft.ButtonStyle(bgcolor=AppColors.SURFACE_VARIANT, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=20, color=AppColors.BORDER),
                        # BOŚ Bossa
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Container(
                                        content=ft.Text("BOŚ", size=14, weight=ft.FontWeight.BOLD, color="white"),
                                        bgcolor="#8B4513",  # Brown/bronze
                                        padding=ft.Padding.all(8),
                                        border_radius=8,
                                        width=70,
                                        alignment=ft.alignment.Alignment.CENTER,
                                    ),
                                    ft.Column([
                                        ft.Text("BOŚ Bossa", size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        bossa_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                bossa_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16), ft.Text(t("calc.select_file"))], spacing=8),
                                    on_click=pick_bossa_file,
                                    style=ft.ButtonStyle(bgcolor=AppColors.SURFACE_VARIANT, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=20, color=AppColors.BORDER),
                        # mBank mTrader
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Container(
                                        content=ft.Text("MBANK", size=14, weight=ft.FontWeight.BOLD, color="white"),
                                        bgcolor="#E3000F",  # mBank red
                                        padding=ft.Padding.all(8),
                                        border_radius=8,
                                        width=70,
                                        alignment=ft.alignment.Alignment.CENTER,
                                    ),
                                    ft.Column([
                                        ft.Text("mBank mTrader", size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        mbank_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                mbank_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16), ft.Text(t("calc.select_file"))], spacing=8),
                                    on_click=pick_mbank_file,
                                    style=ft.ButtonStyle(bgcolor=AppColors.SURFACE_VARIANT, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=20, color=AppColors.BORDER),
                        # Inne Brokerzy (multi-file)
                        ft.Row([
                            ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.FOLDER_COPY, color=AppColors.ACCENT_GREEN, size=20),
                                    ft.Column([
                                        ft.Text(t("calc.other_brokers_multi"), size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                                        generic_text,
                                    ], spacing=2, expand=True),
                                ], spacing=12),
                                expand=True,
                            ),
                            ft.Row([
                                generic_clear_btn,
                                ft.Button(
                                    content=ft.Row([ft.Icon(ft.Icons.ADD_CIRCLE, size=16), ft.Text(t("calc.add_files"))], spacing=8),
                                    on_click=pick_generic_files,
                                    style=ft.ButtonStyle(bgcolor=AppColors.ACCENT_GREEN, color=AppColors.TEXT_PRIMARY),
                                ),
                            ], spacing=4),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ]),
                    bgcolor=AppColors.CARD,
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=AppTheme.CARD_PADDING,
                ),
                ft.Container(
                    content=ft.Row([progress_ring, progress_text, calculate_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=16),
                    padding=ft.Padding.symmetric(vertical=24),
                ),
                ft.Container(content=results_container, expand=True),
            ], scroll=ft.ScrollMode.AUTO, expand=True),
            padding=32,
            expand=True,
        )
    
    def create_history_view() -> ft.Container:
        refresh_history()
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.HISTORY, size=32, color=AppColors.PRIMARY),
                        ft.Column([
                            ft.Text(t("history.title"), size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                            ft.Text(t("history.subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                        ], spacing=2),
                    ], spacing=16),
                    padding=ft.Padding.only(bottom=24),
                ),
                history_table_container,
            ], scroll=ft.ScrollMode.AUTO, expand=True),
            padding=32,
            expand=True,
        )
    
    def create_help_view() -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.HELP_OUTLINE, size=32, color=AppColors.PRIMARY),
                        ft.Column([
                            ft.Text("Pomoc", size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                            ft.Text("Instrukcje i informacje", size=14, color=AppColors.TEXT_SECONDARY),
                        ], spacing=2),
                    ], spacing=16),
                    padding=ft.Padding.only(bottom=24),
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Jak używać kalkulatora?", size=18, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        ft.Text(
                            "1. Eksportuj raport CSV z Trading 212 (Historię transakcji)\n"
                            "2. Eksportuj raport aktywności z IBKR (Activity Statement CSV)\n"
                            "3. Wybierz pliki w kalkulatorze\n"
                            "4. Kliknij 'OBLICZ PODATEK'\n"
                            "5. Wyniki zostaną automatycznie zapisane w historii",
                            size=14, color=AppColors.TEXT_SECONDARY,
                        ),
                        ft.Divider(height=30, color=AppColors.BORDER),
                        ft.Text("Informacje techniczne", size=18, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        ft.Text(
                            "• Kursy walut pobierane są z API NBP\n"
                            "• Zastosowana jest metoda FIFO do obliczania kosztów\n"
                            "• Obliczenia są zgodne z wymogami PIT-38\n"
                            "• Wyniki zawierają podział na akcje, dywidendy i odsetki",
                            size=14, color=AppColors.TEXT_SECONDARY,
                        ),
                        ft.Divider(height=30, color=AppColors.BORDER),
                        ft.Text("O aplikacji", size=18, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        ft.Text(
                            "Tax Calculator 2025 v1.0.0\nPython 3.12+ | Flet Framework\n© 2025",
                            size=14, color=AppColors.TEXT_MUTED,
                        ),
                    ], spacing=12),
                    bgcolor=AppColors.CARD,
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=AppTheme.CARD_PADDING,
                ),
            ], scroll=ft.ScrollMode.AUTO, expand=True),
            padding=32,
            expand=True,
        )
    
    def create_statistics_view() -> ft.Container:
        """Create statistics view with charts based on calculation history."""
        calculations = db.get_all_calculations()
        
        if not calculations:
            return ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BAR_CHART, size=32, color=AppColors.SECONDARY),
                            ft.Column([
                                ft.Text(t("stats.title"), size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                                ft.Text(t("stats.full_subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                            ], spacing=2),
                        ], spacing=16),
                        padding=ft.Padding.only(bottom=24),
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=48, color=AppColors.TEXT_MUTED),
                            ft.Text(t("stats.no_data"), size=16, color=AppColors.TEXT_SECONDARY),
                            ft.Text(t("stats.no_data_hint"), size=14, color=AppColors.TEXT_MUTED),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                        padding=50,
                    ),
                ]),
                padding=32,
                expand=True,
            )
        
        # Use LATEST calculation only (not sum of all history)
        latest = calculations[-1] if calculations else {}
        total_stock_profit = latest.get('stock_income', 0) - latest.get('stock_cost', 0)
        total_dividends = latest.get('dividend_gross', 0)
        total_interest = latest.get('interest_gross', 0)
        total_tax = latest.get('total_tax', 0)
        total_bonuses = latest.get('bonuses', 0)
        
        # Interactive Bar Chart
        # Interactive Bar Chart (Custom Implementation)
        stock_color = AppColors.ACCENT_RED if total_stock_profit < 0 else AppColors.ACCENT_GREEN
        max_val = max(abs(total_stock_profit), total_dividends, total_interest, total_tax, 1)
        bar_max_height = 200
        
        # Simple linear progress bars instead of custom charts
        def create_stat_row(label, value, color, icon):
            percentage = min(abs(value) / max(max_val, 1), 1.0)
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=16, color=color),
                        ft.Text(label, size=14, color=AppColors.TEXT_SECONDARY, expand=True),
                        ft.Text(format_pln(value), size=14, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                    ]),
                    ft.ProgressBar(value=percentage, color=color, bgcolor=ft.Colors.TRANSPARENT, height=8, border_radius=ft.BorderRadius.all(4)),
                ], spacing=4),
                padding=ft.Padding.symmetric(vertical=8),
            )

        visual_chart = ft.Container(
            content=ft.Column([
                create_stat_row(t("stats.stock_profit"), total_stock_profit, stock_color, ft.Icons.TRENDING_UP if total_stock_profit >= 0 else ft.Icons.TRENDING_DOWN),
                create_stat_row(t("results.dividends"), total_dividends, AppColors.PRIMARY, ft.Icons.ATTACH_MONEY),
                create_stat_row(t("results.interest"), total_interest, AppColors.SECONDARY, ft.Icons.SAVINGS),
                create_stat_row(t("stats.total_tax_label"), total_tax, AppColors.ACCENT_GOLD, ft.Icons.ACCOUNT_BALANCE_WALLET),
            ], spacing=10),
            padding=20,
            bgcolor=AppColors.SURFACE_VARIANT,
            border_radius=AppTheme.BORDER_RADIUS,
        )
        
        # Summary cards
        def stat_card(title: str, value: float, icon: str, color: str) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=24, color=color),
                        ft.Text(title, size=14, color=AppColors.TEXT_SECONDARY),
                    ], spacing=8),
                    ft.Text(format_pln(value), size=24, weight=ft.FontWeight.BOLD, color=color),
                ], spacing=8),
                bgcolor=AppColors.CARD,
                border_radius=AppTheme.BORDER_RADIUS,
                padding=20,
                expand=True,
            )
        
        # Dynamic colors for profit/loss stat card
        stock_profit_color = AppColors.ACCENT_RED if total_stock_profit < 0 else AppColors.ACCENT_GREEN
        stock_profit_icon = ft.Icons.TRENDING_DOWN if total_stock_profit < 0 else ft.Icons.TRENDING_UP
        
        # Enhanced statistics calculations
        total_income = total_stock_profit + total_dividends + total_interest + total_bonuses
        net_profit = total_income - total_tax
        total_cost = latest.get('stock_cost', 0)
        return_rate = (total_stock_profit / total_cost * 100) if total_cost > 0 else 0
        daily_earnings = net_profit / 365
        monthly_earnings = net_profit / 12
        
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.BAR_CHART, size=32, color=AppColors.SECONDARY),
                        ft.Column([
                            ft.Text(t("stats.title"), size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                            ft.Text(t("stats.summary_subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                        ], spacing=2),
                    ], spacing=16),
                    padding=ft.Padding.only(bottom=24),
                ),
                # Summary row - dynamic colors for profit/loss
                ft.Row([
                    stat_card(t("stats.stock_profit"), total_stock_profit, stock_profit_icon, stock_profit_color),
                    stat_card(t("results.dividends"), total_dividends, ft.Icons.PAYMENTS, AppColors.PRIMARY),
                    stat_card(t("results.interest"), total_interest, ft.Icons.SAVINGS, AppColors.SECONDARY),
                    stat_card(t("stats.total_tax_label"), total_tax, ft.Icons.ACCOUNT_BALANCE_WALLET, AppColors.ACCENT_GOLD),
                ], spacing=16),
                # Visual bar chart
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("stats.income_sources"), size=16, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        visual_chart,
                    ], spacing=12),
                    bgcolor=AppColors.CARD,
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                # Earnings & return rate
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("stats.returns_section"), size=16, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        ft.Divider(height=16, color=AppColors.BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.PERCENT, size=18, color=AppColors.PRIMARY),
                            ft.Text(t("stats.return_rate"), color=AppColors.TEXT_SECONDARY),
                            ft.Text(f"{return_rate:+.2f}%", 
                                   color=AppColors.ACCENT_GREEN if return_rate >= 0 else AppColors.ACCENT_RED, 
                                   weight=ft.FontWeight.BOLD, size=16),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=8, color=AppColors.BORDER),
                        # Monthly earnings
                        ft.Row([
                            ft.Icon(ft.Icons.CALENDAR_MONTH, size=18, color=AppColors.SECONDARY),
                            ft.Text(t("stats.monthly"), color=AppColors.TEXT_SECONDARY),
                            ft.Text(format_pln(monthly_earnings), 
                                   color=AppColors.ACCENT_GREEN if monthly_earnings >= 0 else AppColors.ACCENT_RED, 
                                   weight=ft.FontWeight.W_500),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        # Daily earnings
                        ft.Row([
                            ft.Icon(ft.Icons.TODAY, size=18, color=AppColors.SECONDARY),
                            ft.Text(t("stats.daily"), color=AppColors.TEXT_SECONDARY),
                            ft.Text(format_pln(daily_earnings), 
                                   color=AppColors.ACCENT_GREEN if daily_earnings >= 0 else AppColors.ACCENT_RED, 
                                   weight=ft.FontWeight.W_500),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=8, color=AppColors.BORDER),
                        # Summary
                        ft.Row([
                            ft.Text(t("stats.total_gross"), color=AppColors.TEXT_SECONDARY),
                            ft.Text(format_pln(total_income), 
                                   color=AppColors.ACCENT_GREEN if total_income >= 0 else AppColors.ACCENT_RED, 
                                   weight=ft.FontWeight.W_500),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([
                            ft.Text(t("stats.tax_due"), color=AppColors.TEXT_SECONDARY),
                            ft.Text(format_pln(total_tax), color=AppColors.ACCENT_GOLD, weight=ft.FontWeight.BOLD),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([
                            ft.Text(t("stats.net_profit"), color=AppColors.TEXT_SECONDARY, weight=ft.FontWeight.BOLD),
                            ft.Text(format_pln(net_profit), 
                                   color=AppColors.ACCENT_GREEN if net_profit >= 0 else AppColors.ACCENT_RED, 
                                   weight=ft.FontWeight.BOLD, size=18),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ], spacing=8),
                    bgcolor=AppColors.CARD,
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
            ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=20),
            padding=32,
            expand=True,
        )
    
    def create_help_view() -> ft.Container:
        """Create comprehensive Help view with instructions, FAQ, and legal info."""
        
        def create_faq_item(question: str, answer: str) -> ft.Container:
            return ft.ExpansionTile(
                title=ft.Text(question, size=14, weight=ft.FontWeight.W_500, color=AppColors.TEXT_PRIMARY),
                controls=[
                    ft.Container(
                        content=ft.Text(answer, size=13, color=AppColors.TEXT_SECONDARY),
                        padding=ft.Padding.only(left=16, right=16, bottom=12),
                    )
                ],
                tile_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                bgcolor=AppColors.SURFACE,
            )
        
        return ft.Container(
            content=ft.Column([
                # Header
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.HELP, size=32, color=AppColors.SECONDARY),
                        ft.Column([
                            ft.Text(t("faq.title"), size=24, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                            ft.Text(t("faq.subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                        ], spacing=4),
                    ], spacing=16),
                    padding=ft.Padding.only(bottom=24),
                ),
                
                # Quick Start Guide
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("faq.quickstart_title"), size=18, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                        ft.Divider(height=12, color=AppColors.BORDER),
                        ft.Text(t("faq.quickstart_text"), size=13, color=AppColors.TEXT_SECONDARY),
                    ], spacing=8),
                    bgcolor=AppColors.CARD,
                    border=ft.Border.all(1, AppColors.BORDER),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                
                # Supported Brokers
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("faq.platforms_title"), size=18, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                        ft.Divider(height=12, color=AppColors.BORDER),
                        ft.Row([
                            ft.Chip(label=ft.Text("Trading 212")),
                            ft.Chip(label=ft.Text("Interactive Brokers")),
                            ft.Chip(label=ft.Text("XTB")),
                            ft.Chip(label=ft.Text("Revolut")),
                            ft.Chip(label=ft.Text("eToro")),
                        ], wrap=True, spacing=8),
                        ft.Row([
                            ft.Chip(label=ft.Text("Degiro")),
                            ft.Chip(label=ft.Text("mBank")),
                            ft.Chip(label=ft.Text("Saxo Bank")),
                            ft.Chip(label=ft.Text("Freedom24")),
                        ], wrap=True, spacing=8),
                        ft.ExpansionTile(
                            title=ft.Text(t("faq.more_brokers"), size=12, color=AppColors.TEXT_SECONDARY),
                            controls=[
                                ft.Container(
                                    content=ft.Row([
                                        ft.Chip(label=ft.Text("Plus500")),
                                        ft.Chip(label=ft.Text("Exante")),
                                        ft.Chip(label=ft.Text("Santander")),
                                        ft.Chip(label=ft.Text("PKO BP")),
                                        ft.Chip(label=ft.Text("BM BNP Paribas")),
                                        ft.Chip(label=ft.Text("DM BOŚ")),
                                        ft.Chip(label=ft.Text("Erste")),
                                        ft.Chip(label=ft.Text("BM mBank")),
                                        ft.Chip(label=ft.Text("Lynx")),
                                        ft.Chip(label=ft.Text("Tastyworks")),
                                        ft.Chip(label=ft.Text("Webull")),
                                        ft.Chip(label=ft.Text("Charles Schwab")),
                                        ft.Chip(label=ft.Text("Fidelity")),
                                        ft.Chip(label=ft.Text("Finax")),
                                        ft.Chip(label=ft.Text("BOSSA")),
                                    ], wrap=True, spacing=8),
                                    padding=ft.Padding.only(left=8, top=8, bottom=8),
                                )
                            ],
                        ),
                        ft.Text(t("faq.auto_detect"), size=12, color=AppColors.TEXT_MUTED, italic=True),
                    ], spacing=8),
                    bgcolor=AppColors.CARD,
                    border=ft.Border.all(1, AppColors.BORDER),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                
                # FAQ Section
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("faq.section_title"), size=18, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                        ft.Divider(height=12, color=AppColors.BORDER),
                        create_faq_item(t("faq.q1"), t("faq.a1")),
                        create_faq_item(t("faq.q2"), t("faq.a2")),
                        create_faq_item(t("faq.q3"), t("faq.a3")),
                        create_faq_item(t("faq.q4"), t("faq.a4")),
                        create_faq_item(t("faq.q5"), t("faq.a5")),
                    ], spacing=4),
                    bgcolor=AppColors.CARD,
                    border=ft.Border.all(1, AppColors.BORDER),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                
                # Legal Disclaimer
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.WARNING, size=24, color=AppColors.ACCENT_RED),
                            ft.Text(t("faq.legal_title"), size=16, weight=ft.FontWeight.BOLD, color=AppColors.ACCENT_RED),
                        ], spacing=8),
                        ft.Divider(height=12, color=AppColors.BORDER),
                        ft.Text(t("faq.legal_text"), size=13, color=AppColors.TEXT_SECONDARY),
                    ], spacing=8),
                    bgcolor=AppColors.SURFACE_VARIANT,
                    border=ft.Border.all(2, AppColors.ACCENT_RED),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                
                # Contact/Support
                ft.Container(
                    content=ft.Column([
                        ft.Text(t("faq.contact_title"), size=18, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                        ft.Divider(height=12, color=AppColors.BORDER),
                        ft.Text(t("faq.contact_text"), size=13, color=AppColors.TEXT_SECONDARY),
                    ], spacing=8),
                    bgcolor=AppColors.CARD,
                    border=ft.Border.all(1, AppColors.BORDER),
                    border_radius=AppTheme.BORDER_RADIUS,
                    padding=20,
                ),
                
            ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=16),
            padding=32,
            expand=True,
        )
    
    # Create views once at startup to avoid re-rendering lag
    # Main content container
    content_area = ft.Container(expand=True, padding=32)

    def on_nav_change(e):
        idx = e.control.selected_index
        content_area.content = None

        if idx == 0:
            content_area.content = create_calculator_view()
        elif idx == 1:
            content_area.content = create_history_view()
        elif idx == 2:
            content_area.content = create_statistics_view()
        elif idx == 3:
            content_area.content = create_settings_view()
        elif idx == 4:
            content_area.content = create_help_view()

        page.update()

    def refresh_ui():
        """Rebuild nav rail labels and current view after language change."""
        nav_rail.destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.CALCULATE_OUTLINED, selected_icon=ft.Icons.CALCULATE, label=t("nav.calculator")),
            ft.NavigationRailDestination(icon=ft.Icons.HISTORY_OUTLINED, selected_icon=ft.Icons.HISTORY, label=t("nav.history")),
            ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label=t("nav.statistics")),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label=t("nav.settings")),
            ft.NavigationRailDestination(icon=ft.Icons.HELP_OUTLINE, selected_icon=ft.Icons.HELP, label=t("nav.faq")),
        ]
        nav_rail.update()
        # Update persistent file-text placeholders
        if not t212_path:
            t212_text.value = t("calc.no_file")
        if not ibkr_path:
            ibkr_text.value = t("calc.no_file")
        if not xtb_path:
            xtb_text.value = t("calc.no_file")
        if not bossa_path:
            bossa_text.value = t("calc.no_file")
        if not mbank_path:
            mbank_text.value = t("calc.no_file")
        if not generic_files:
            generic_text.value = t("calc.no_files_plural")
        # Re-render the current view (skip settings to avoid recursion)
        idx = nav_rail.selected_index
        if idx == 0:
            content_area.content = create_calculator_view()
        elif idx == 1:
            content_area.content = create_history_view()
        elif idx == 2:
            content_area.content = create_statistics_view()
        elif idx == 4:
            content_area.content = create_help_view()
        page.update()

    def create_settings_view() -> ft.Container:
        from src.ui.settings import create_settings_view as _new_settings_view
        return _new_settings_view(page, on_language_change=refresh_ui)

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        min_extended_width=200,
        bgcolor=AppColors.SURFACE,
        indicator_color=AppColors.PRIMARY,
        on_change=on_nav_change,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.CALCULATE_OUTLINED, selected_icon=ft.Icons.CALCULATE, label=t("nav.calculator")),
            ft.NavigationRailDestination(icon=ft.Icons.HISTORY_OUTLINED, selected_icon=ft.Icons.HISTORY, label=t("nav.history")),
            ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label=t("nav.statistics")),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label=t("nav.settings")),
            ft.NavigationRailDestination(icon=ft.Icons.HELP_OUTLINE, selected_icon=ft.Icons.HELP, label=t("nav.faq")),
        ],
        leading=ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=36, color=AppColors.PRIMARY),
                ft.Text("TAX", size=12, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                ft.Text("2025", size=10, color=AppColors.TEXT_MUTED),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            padding=ft.Padding.symmetric(vertical=20),
        ),
    )
    
    # Initial View
    content_area.content = create_calculator_view()
    
    page.add(ft.Row([nav_rail, ft.VerticalDivider(width=1, color=AppColors.BORDER), content_area], expand=True, spacing=0))

# =============================================================================
# ENTRY POINT (Flet 0.80+)
# =============================================================================

if __name__ == "__main__":
    ft.run(main)

# =============================================================================
# PACKAGING INSTRUCTIONS (PyInstaller 2026)
# =============================================================================
"""
HOW TO PACKAGE AS .EXE (Windows):

1. Install required packages:
   pip install flet httpx pandas pyinstaller

2. Run with Flet's packager:
   flet pack main.py --name "TaxCalculator2025" --icon icon.ico

3. The executable will be in: dist/TaxCalculator2025.exe

4. For Android (.apk):
   flet build apk main.py
"""
