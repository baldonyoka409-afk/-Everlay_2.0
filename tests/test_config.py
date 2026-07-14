# tests/test_config.py
import pytest
from core.config import Settings, get_settings


def test_settings_defaults():
    """Test default settings values."""
    settings = Settings(
        openrouter_api_key="test",
    )

    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert settings.openrouter_default_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert len(settings.free_models) == 11
    assert len(settings.paid_models) == 5
    assert settings.rag_db_path == "everlay_brain.db"  # default
    assert settings.log_level == "INFO"


def test_settings_override_rag_db_path():
    """Test overriding rag_db_path."""
    import os
    # Save original
    old = os.environ.get("RAG_DB_PATH")
    os.environ["RAG_DB_PATH"] = "custom.db"
    try:
        settings = Settings(openrouter_api_key="test")
        assert settings.rag_db_path == "custom.db"
    finally:
        if old is not None:
            os.environ["RAG_DB_PATH"] = old
        else:
            os.environ.pop("RAG_DB_PATH", None)


def test_settings_free_models_not_empty():
    """Free models list should not be empty."""
    settings = Settings(openrouter_api_key="test")
    assert len(settings.free_models) > 0
    assert all(":free" in m for m in settings.free_models)


def test_settings_paid_models_not_empty():
    """Paid models list should not be empty."""
    settings = Settings(openrouter_api_key="test")
    assert len(settings.paid_models) > 0
    assert all(":free" not in m for m in settings.paid_models)


def test_get_settings_cached():
    """get_settings should return cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2