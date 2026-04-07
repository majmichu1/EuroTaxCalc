"""
Tests for SettingsManager — migrated from test_podatkomierz.py.
"""

import pytest
from pathlib import Path

from src.models import DataValidator


class TestSettingsManager:
    """Test settings persistence — uses main.py's SettingsManager via import."""

    def test_save_and_load(self, tmp_path):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from main import SettingsManager

        original_path = SettingsManager.FILE_PATH
        SettingsManager.FILE_PATH = tmp_path / "test_settings.json"

        try:
            test_settings = {"test_key": "test_value", "number": 42}
            SettingsManager.save(test_settings)
            loaded = SettingsManager.load()
            assert loaded["test_key"] == "test_value"
            assert loaded["number"] == 42
        finally:
            SettingsManager.FILE_PATH = original_path

    def test_load_nonexistent(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from main import SettingsManager

        original_path = SettingsManager.FILE_PATH
        SettingsManager.FILE_PATH = Path("nonexistent_settings_xyz123.json")

        try:
            loaded = SettingsManager.load()
            assert loaded == {}
        finally:
            SettingsManager.FILE_PATH = original_path
