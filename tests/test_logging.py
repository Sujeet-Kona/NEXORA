import logging

import pytest
from pydantic import ValidationError

from backend.core.config import Settings, settings
from backend.core.logging import LOGGER_NAME, configure_logging


def make_settings(**overrides):
    return Settings(
        database_url="sqlite://",
        jwt_secret_key="test-secret",
        **overrides,
    )


def test_log_level_is_normalized():
    assert make_settings(log_level="debug").log_level == "DEBUG"


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(log_level="TRACE")


def test_configure_logging_uses_settings_log_level(monkeypatch):
    logger = logging.getLogger(LOGGER_NAME)
    original_level = settings.log_level

    monkeypatch.setattr(settings, "log_level", "DEBUG")
    configure_logging()
    assert logger.level == logging.DEBUG

    monkeypatch.setattr(settings, "log_level", "INFO")
    configure_logging()
    assert logger.level == logging.INFO

    monkeypatch.setattr(settings, "log_level", original_level)
    configure_logging()
