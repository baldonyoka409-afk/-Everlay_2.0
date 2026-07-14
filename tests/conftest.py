# tests/conftest.py
import sys
from pathlib import Path
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import shutil
from core.config import Settings


@pytest.fixture(scope="session")
def test_settings():
    """Test settings with temp paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        settings = Settings(
            openrouter_api_key="test-key",
            rag_db_path=str(tmp_path / "test_rag.db"),
            database_url=f"sqlite:///{tmp_path}/test.db",
            log_file=str(tmp_path / "test.log"),
            app_env="testing",
            app_debug=True,
        )
        yield settings


@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)