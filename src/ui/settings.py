"""
Settings view — country selection, language, file paths, tax options.
Auto-saves on every change.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.ui.theme import AppColors, AppTheme
from src.i18n import t, set_language, get_language
from src.countries import get_all_countries


def create_settings_view(page: ft.Page, on_language_change: Callable | None = None) -> ft.Container:
    """Create the full settings view. Auto-saves on every control change."""
    from settings_manager import load_settings, save_settings, reset_settings

    settings = load_settings()
    countries = get_all_countries()

    # -----------------------------------------------------------------
    # Country dropdown
    # -----------------------------------------------------------------
    country_options = [
        ft.dropdown.Option(
            key=code,
            text=f"{country.flag}  {country.name_local} ({country.name_en})"
        )
        for code, country in sorted(countries.items(), key=lambda x: x[1].name_en)
    ]

    country_dropdown = ft.Dropdown(
        label=t("settings.country"),
        value=settings.get("country", "PL"),
        options=country_options,
        width=400,
        bgcolor=AppColors.SURFACE_VARIANT,
        color=AppColors.TEXT_PRIMARY,
        border_color=AppColors.BORDER,
        focused_border_color=AppColors.PRIMARY,
    )

    # -----------------------------------------------------------------
    # Language dropdown
    # -----------------------------------------------------------------
    lang_dropdown = ft.Dropdown(
        label=t("settings.language"),
        value=settings.get("language", "pl"),
        options=[
            ft.dropdown.Option(key="pl", text="🇵🇱  " + t("settings.language_pl")),
            ft.dropdown.Option(key="en", text="🇬🇧  " + t("settings.language_en")),
        ],
        width=250,
        bgcolor=AppColors.SURFACE_VARIANT,
        color=AppColors.TEXT_PRIMARY,
        border_color=AppColors.BORDER,
        focused_border_color=AppColors.PRIMARY,
    )

    # -----------------------------------------------------------------
    # File path inputs
    # -----------------------------------------------------------------
    t212_path_input = ft.TextField(
        label=t("settings.t212_path"),
        value=settings.get("t212_path", ""),
        width=600,
        hint_text="/path/to/trading212.csv",
        bgcolor=AppColors.SURFACE_VARIANT,
        color=AppColors.TEXT_PRIMARY,
        border_color=AppColors.BORDER,
        focused_border_color=AppColors.PRIMARY,
    )
    ibkr_path_input = ft.TextField(
        label=t("settings.ibkr_path"),
        value=settings.get("ibkr_path", ""),
        width=600,
        hint_text="/path/to/ibkr.csv",
        bgcolor=AppColors.SURFACE_VARIANT,
        color=AppColors.TEXT_PRIMARY,
        border_color=AppColors.BORDER,
        focused_border_color=AppColors.PRIMARY,
    )

    # -----------------------------------------------------------------
    # Calculation options
    # -----------------------------------------------------------------
    auto_prefetch = ft.Checkbox(
        label=t("settings.auto_prefetch"),
        value=settings.get("auto_prefetch_nbp", True),
        fill_color=AppColors.PRIMARY,
    )
    cache_crypto = ft.Checkbox(
        label=t("settings.cache_crypto"),
        value=settings.get("cache_crypto_prices", True),
        fill_color=AppColors.PRIMARY,
    )

    # -----------------------------------------------------------------
    # Germany-specific: Kirchensteuer + joint filing
    # -----------------------------------------------------------------
    kirchensteuer_dropdown = ft.Dropdown(
        label=t("settings.kirchensteuer"),
        value=str(settings.get("kirchensteuer", "None")),
        options=[
            ft.dropdown.Option(key="None", text=t("settings.kist_none")),
            ft.dropdown.Option(key="0.08", text=t("settings.kist_8")),
            ft.dropdown.Option(key="0.09", text=t("settings.kist_9")),
        ],
        width=400,
        bgcolor=AppColors.SURFACE_VARIANT,
        color=AppColors.TEXT_PRIMARY,
        border_color=AppColors.BORDER,
        focused_border_color=AppColors.PRIMARY,
    )

    joint_filing_cb = ft.Checkbox(
        label=t("settings.joint_filing"),
        value=settings.get("joint_filing", False),
        fill_color=AppColors.PRIMARY,
    )

    # -----------------------------------------------------------------
    # Country info card
    # -----------------------------------------------------------------
    def build_country_info(code: str) -> ft.Container:
        try:
            country = countries[code]
        except KeyError:
            return ft.Container()

        rows = [
            (t("country.tax_rate"), country.effective_cgt_rate_display),
            (t("country.method"), country.cost_method),
            (t("country.allowance"),
             country.format_currency(country.tax_free_allowance) if country.tax_free_allowance > 0
             else t("country.none")),
            (t("country.form"), country.tax_form_name),
            (t("country.deadline"), country.filing_deadline),
            (t("country.rate_source"), country.rate_service),
        ]

        row_widgets = []
        for label, value in rows:
            row_widgets.append(
                ft.Row([
                    ft.Text(label, size=12, color=AppColors.TEXT_MUTED, width=160),
                    ft.Text(value, size=12, color=AppColors.TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                ])
            )

        notes = []
        if code == "BE":
            notes.append(ft.Text(t("be.cgt_note"), size=11, color=AppColors.ACCENT_GOLD, italic=True))
            notes.append(ft.Text(t("be.tob_info"), size=11, color=AppColors.TEXT_MUTED, italic=True))
        if code == "IT":
            notes.append(ft.Text(t("it.regime_note"), size=11, color=AppColors.TEXT_MUTED, italic=True))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(country.flag, size=24),
                    ft.Text(f"{country.name_local} — {country.name_en}",
                            size=15, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                ], spacing=8),
                ft.Divider(height=8, color=AppColors.BORDER),
                *row_widgets,
                *notes,
            ], spacing=6),
            bgcolor=AppColors.SURFACE_VARIANT,
            border_radius=AppTheme.BORDER_RADIUS,
            padding=16,
            border=ft.border.all(1, AppColors.PRIMARY),
        )

    country_info_container = ft.Container(content=build_country_info(settings.get("country", "PL")))

    de_options_container = ft.Container(
        content=ft.Column([
            ft.Text(t("settings.tax_options"), size=16,
                    weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
            ft.Divider(height=8, color=AppColors.BORDER),
            kirchensteuer_dropdown,
            joint_filing_cb,
        ], spacing=10),
        bgcolor=AppColors.CARD,
        border_radius=AppTheme.BORDER_RADIUS,
        padding=20,
        visible=settings.get("country", "PL") == "DE",
    )

    # -----------------------------------------------------------------
    # Auto-save helpers
    # -----------------------------------------------------------------
    def _kist_val():
        raw = kirchensteuer_dropdown.value
        if not raw or raw == "None":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _apply_de_config():
        try:
            from src.countries import get_country
            de = get_country("DE")
            de.extra["kirchensteuer"] = _kist_val()
            if joint_filing_cb.value:
                de.tax_free_allowance = de.extra.get("sparerpauschbetrag_joint", 2000)
            else:
                de.tax_free_allowance = 1000.0
        except Exception:
            pass

    def _save_all():
        try:
            settings["country"] = country_dropdown.value or "PL"
            settings["language"] = lang_dropdown.value or "pl"
            settings["t212_path"] = t212_path_input.value or ""
            settings["ibkr_path"] = ibkr_path_input.value or ""
            settings["auto_prefetch_nbp"] = bool(auto_prefetch.value)
            settings["cache_crypto_prices"] = bool(cache_crypto.value)
            settings["kirchensteuer"] = _kist_val()
            settings["joint_filing"] = bool(joint_filing_cb.value)
            save_settings(settings)
        except Exception as ex:
            print(f"[settings] _save_all error: {ex}")

    # -----------------------------------------------------------------
    # Event handlers — auto-save on every change
    # -----------------------------------------------------------------
    def on_country_change(e):
        code = country_dropdown.value
        country_info_container.content = build_country_info(code)
        de_options_container.visible = (code == "DE")
        if code == "PL":
            lang_dropdown.value = "pl"
        else:
            if lang_dropdown.value == "pl":
                lang_dropdown.value = "en"
        # Apply language immediately
        set_language(lang_dropdown.value)
        _save_all()
        if on_language_change:
            on_language_change()
        page.update()

    country_dropdown.on_select = on_country_change

    def on_lang_change(e):
        set_language(lang_dropdown.value)
        _save_all()
        if on_language_change:
            on_language_change()
        page.update()

    lang_dropdown.on_select = on_lang_change

    def on_de_option_change(e):
        _apply_de_config()
        _save_all()

    kirchensteuer_dropdown.on_select = on_de_option_change
    joint_filing_cb.on_change = on_de_option_change

    def on_checkbox_change(e):
        _save_all()

    auto_prefetch.on_change = on_checkbox_change
    cache_crypto.on_change = on_checkbox_change

    def on_path_blur(e):
        _save_all()

    t212_path_input.on_blur = on_path_blur
    ibkr_path_input.on_blur = on_path_blur

    # -----------------------------------------------------------------
    # Reset handler
    # -----------------------------------------------------------------
    def reset_settings_handler(e):
        if reset_settings():
            t212_path_input.value = ""
            ibkr_path_input.value = ""
            auto_prefetch.value = True
            cache_crypto.value = True
            country_dropdown.value = "PL"
            lang_dropdown.value = "pl"
            kirchensteuer_dropdown.value = "None"
            joint_filing_cb.value = False
            de_options_container.visible = False
            country_info_container.content = build_country_info("PL")
            set_language("pl")
            if on_language_change:
                on_language_change()
            page.update()

    return ft.Container(
        content=ft.Column([
            # Header
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SETTINGS, size=32, color=AppColors.PRIMARY),
                    ft.Column([
                        ft.Text(t("settings.title"), size=24,
                                weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                        ft.Text(t("settings.subtitle"), size=14, color=AppColors.TEXT_SECONDARY),
                    ], spacing=2),
                ], spacing=16),
                padding=ft.padding.only(bottom=24),
            ),

            # Country + Language
            ft.Container(
                content=ft.Column([
                    ft.Text(f"🌍 {t('settings.country')} & {t('settings.language')}",
                            size=16, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    ft.Divider(height=8, color=AppColors.BORDER),
                    ft.Row([country_dropdown, lang_dropdown], spacing=16, wrap=True),
                    country_info_container,
                ], spacing=12),
                bgcolor=AppColors.CARD,
                border_radius=AppTheme.BORDER_RADIUS,
                padding=20,
            ),

            # Germany-specific tax options
            de_options_container,

            # File paths
            ft.Container(
                content=ft.Column([
                    ft.Text(f"📁 {t('settings.file_paths')}",
                            size=16, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    ft.Text(t("settings.file_paths_hint"), size=12, color=AppColors.TEXT_MUTED),
                    ft.Divider(height=8, color=AppColors.BORDER),
                    t212_path_input,
                    ibkr_path_input,
                ], spacing=10),
                bgcolor=AppColors.CARD,
                border_radius=AppTheme.BORDER_RADIUS,
                padding=20,
            ),

            # Calculation options
            ft.Container(
                content=ft.Column([
                    ft.Text(f"⚙️ {t('settings.calc_options')}",
                            size=16, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY),
                    ft.Divider(height=8, color=AppColors.BORDER),
                    auto_prefetch,
                    cache_crypto,
                ], spacing=10),
                bgcolor=AppColors.CARD,
                border_radius=AppTheme.BORDER_RADIUS,
                padding=20,
            ),

            # Reset button only
            ft.OutlinedButton(
                t("settings.reset"),
                icon=ft.Icons.REFRESH,
                on_click=reset_settings_handler,
            ),

        ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=20),
        padding=32,
        expand=True,
    )
