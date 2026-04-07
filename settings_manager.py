"""
Settings Manager - GUI for Podatkomierz
Allows users to configure app settings without editing JSON manually.
"""

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"

DEFAULT_SETTINGS = {
    "t212_path": "",
    "ibkr_path": "",
    "xtb_path": "",
    "bossa_path": "",
    "mbank_path": "",
    "auto_prefetch_nbp": True,
    "cache_crypto_prices": True,
    "default_year": None,
    "opp_krs": "",
    "language": "pl",
    "country": "PL",
    "kirchensteuer": None,       # None, 0.08, or 0.09 (Germany only)
    "joint_filing": False,       # Germany: double Sparerpauschbetrag
}

def load_settings() -> dict:
    """Load settings from file."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict) -> bool:
    """Save settings to file."""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def reset_settings() -> bool:
    """Reset to default settings."""
    try:
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        return True
    except:
        return False
