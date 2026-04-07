"""
PIT-38 XML export — official KAS-compliant format for Poland only.

Compliant with XSD schema from crd.gov.pl/wzor/2025/10/09/13914/schemat.xsd
"""

from __future__ import annotations

import logging
import xml.dom.minidom
import xml.etree.ElementTree as ET

from src.models import CalculationResult

logger = logging.getLogger('TaxCalculator')


def export_to_official_pit38_xml(
    result: CalculationResult,
    taxpayer_data: dict,
    output_path: str = "PIT-38.xml",
) -> str:
    """
    Export to OFFICIAL PIT-38(18) XML format for direct submission to KAS.

    taxpayer_data keys:
        nip, pesel, first_name, surname, fathers_name, mothers_name,
        birth_date, address (dict: street, building, apartment, city, postal_code),
        phone, email, bank_account, bank_swift,
        opp_krs, opp_amount, opp_cele, opp_consent,
        previous_losses
    """
    NS = {
        'etd': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/20/12/01/00128/',
        'zzu': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/20/12/01/00130/',
        'kpp': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/20/12/01/00131/',
    }

    root = ET.Element('{http://crd.gov.pl/wzor/2025/10/09/13914/}PIT-38')
    root.set('xmlns:etd', NS['etd'])
    root.set('xmlns:zzu', NS['zzu'])
    root.set('xmlns:kpp', NS['kpp'])
    root.set('generacja', '1')
    root.set('wersjaSchemy', '18/eD/PITZGZ38/')

    t = result.total

    stock_income = int(round(t.stock_income))
    stock_cost = int(round(t.stock_cost))
    stock_profit = int(round(max(0, t.stock_profit)))
    stock_loss = int(round(abs(min(0, t.stock_profit))))

    div_gross = int(round(t.dividend_gross))
    div_tax_foreign = int(round(t.dividend_tax_foreign))
    div_tax_due = int(round(max(0, t.dividend_gross * 0.19 - t.dividend_tax_foreign)))

    int_gross = int(round(t.interest_gross))
    int_tax = int(round(t.interest_gross * 0.19))

    previous_losses = taxpayer_data.get('previous_losses', 0)
    tax_base = max(0, stock_profit - previous_losses)
    stock_tax = int(round(tax_base * 0.19))
    total_tax = stock_tax + div_tax_due + int_tax

    def make_elem(parent, name, value, namespace='etd'):
        if value is None:
            return None
        elem = ET.SubElement(parent, f'{{{NS[namespace]}}}{name}')
        elem.text = str(value)
        return elem

    # NAGLOWEK
    naglowek = ET.SubElement(root, f'{{{NS["etd"]}}}Naglowek')
    make_elem(naglowek, 'SymbolWzoruFormularza', 'PIT-38')
    make_elem(naglowek, 'KodFormularza', 'PIT')
    make_elem(naglowek, 'Wariant', '18')

    # DANE IDENTYFIKACYJNE
    dane_id = ET.SubElement(root, f'{{{NS["etd"]}}}DaneIdentyfikacyjneIAdres')

    if taxpayer_data.get('nip'):
        make_elem(dane_id, 'NIP', taxpayer_data['nip'].replace('-', ''))
    if taxpayer_data.get('pesel'):
        make_elem(dane_id, 'PESEL', taxpayer_data['pesel'])
    if taxpayer_data.get('first_name'):
        make_elem(dane_id, 'ImiePierwsze', taxpayer_data['first_name'].upper())
    if taxpayer_data.get('surname'):
        make_elem(dane_id, 'Nazwisko', taxpayer_data['surname'].upper())
    if taxpayer_data.get('fathers_name'):
        make_elem(dane_id, 'ImieOjca', taxpayer_data['fathers_name'].upper())
    if taxpayer_data.get('mothers_name'):
        make_elem(dane_id, 'ImieMatki', taxpayer_data['mothers_name'].upper())
    if taxpayer_data.get('birth_date'):
        make_elem(dane_id, 'DataUrodzenia', taxpayer_data['birth_date'])

    # ADRES
    adres = ET.SubElement(dane_id, f'{{{NS["etd"]}}}AdresZamieszkania')
    adres_polski = ET.SubElement(adres, f'{{{NS["etd"]}}}AdresPolski')
    addr = taxpayer_data.get('address', {})
    if addr.get('street'):
        make_elem(adres_polski, 'Ulica', addr['street'].upper())
    if addr.get('building'):
        make_elem(adres_polski, 'NrBudynku', addr['building'])
    if addr.get('apartment'):
        make_elem(adres_polski, 'NrLokalu', addr['apartment'])
    if addr.get('city'):
        make_elem(adres_polski, 'Miejscowosc', addr['city'].upper())
    if addr.get('postal_code'):
        make_elem(adres_polski, 'KodPocztowy', addr['postal_code'])

    # ZEZNANIE
    zeznanie = ET.SubElement(root, f'{{{NS["etd"]}}}Zeznanie')
    make_elem(zeznanie, 'RodzajKorekty', '1')
    make_elem(zeznanie, 'Przychody', stock_income)
    make_elem(zeznanie, 'Koszty', stock_cost)
    make_elem(zeznanie, 'RazemPrzychody', stock_income)
    make_elem(zeznanie, 'RazemKoszty', stock_cost)

    if stock_profit > 0:
        make_elem(zeznanie, 'RazemDochod', stock_profit)
    elif stock_loss > 0:
        make_elem(zeznanie, 'RazemStrata', stock_loss)

    if previous_losses:
        make_elem(zeznanie, 'StratyZlatUbieglych', int(round(previous_losses)))

    make_elem(zeznanie, 'PodstawaObliczeniaPodatku', tax_base)
    make_elem(zeznanie, 'StawkaPodatku', '19')
    make_elem(zeznanie, 'PodatekOdDochodow', stock_tax)

    if div_tax_foreign > 0:
        make_elem(zeznanie, 'PodatekZaplaconyZaGranica', div_tax_foreign)
    make_elem(zeznanie, 'PodatekNalezny', total_tax)

    # DANE KONTAKTOWE
    if taxpayer_data.get('phone') or taxpayer_data.get('email'):
        kontakt = ET.SubElement(root, f'{{{NS["etd"]}}}DaneKontaktowe')
        if taxpayer_data.get('phone'):
            make_elem(kontakt, 'Telefon', taxpayer_data['phone'])
        if taxpayer_data.get('email'):
            make_elem(kontakt, 'Email', taxpayer_data['email'])

    # RACHUNEK BANKOWY
    if taxpayer_data.get('bank_account'):
        rachunek = ET.SubElement(root, f'{{{NS["etd"]}}}RachunekBankowy')
        make_elem(rachunek, 'KodKrajuBanku', 'PL')
        if taxpayer_data.get('bank_swift'):
            make_elem(rachunek, 'KodSWIFT', taxpayer_data['bank_swift'])
        make_elem(rachunek, 'WalutaRachunku', 'PLN')
        make_elem(rachunek, 'NumerIBAN', taxpayer_data['bank_account'].replace(' ', ''))

    # 1.5% OPP
    if taxpayer_data.get('opp_krs'):
        opp = ET.SubElement(root, f'{{{NS["etd"]}}}NaRzeczOrganizacjiPoszytkuPublicznego')
        make_elem(opp, 'NumerKRS', taxpayer_data['opp_krs'])
        if taxpayer_data.get('opp_amount'):
            make_elem(opp, 'WnioskowanaKwota', int(round(taxpayer_data['opp_amount'])))
        if taxpayer_data.get('opp_cele'):
            make_elem(opp, 'CelSzczegolowy', taxpayer_data['opp_cele'])
        if taxpayer_data.get('opp_consent'):
            make_elem(opp, 'ZgodaNaDane', 'true')

    # Write XML with pretty-printing
    tree = ET.ElementTree(root)
    with open(output_path, 'wb') as f:
        tree.write(f, encoding='UTF-8', xml_declaration=True, method='xml')

    dom = xml.dom.minidom.parse(output_path)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='UTF-8')
    with open(output_path, 'wb') as f:
        f.write(pretty_xml)

    logger.info(f"[XML Export] Generated official PIT-38(18) XML: {output_path}")
    return output_path
