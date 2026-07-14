# tests/test_csv_tool.py
import pytest
import tempfile
import csv
import asyncio
from agents.tools import CSVTool


@pytest.fixture
def sample_csv(tmp_path):
    """Create sample CSV file."""
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "age", "score"])
        writer.writerow(["Alice", "25", "85.5"])
        writer.writerow(["Bob", "30", "90.0"])
        writer.writerow(["Charlie", "35", "78.5"])
    return csv_file


@pytest.mark.asyncio
async def test_csv_read(sample_csv):
    """Test reading CSV file."""
    tool = CSVTool()
    result = await tool.execute(action="read", path=str(sample_csv))
    assert "Alice" in result
    assert "Bob" in result
    assert "85.5" in result


@pytest.mark.asyncio
async def test_csv_filter_age(sample_csv):
    """Test filtering CSV by age."""
    tool = CSVTool()
    result = await tool.execute(action="filter", path=str(sample_csv), query="age > 28")
    assert "Bob" in result
    assert "Charlie" in result
    assert "Alice" not in result


@pytest.mark.asyncio
async def test_csv_filter_complex(sample_csv):
    """Test complex filter expression."""
    tool = CSVTool()
    result = await tool.execute(action="filter", path=str(sample_csv), query="age >= 30 and score > 80")
    assert "Bob" in result
    assert "Charlie" not in result  # score 78.5 < 80


@pytest.mark.asyncio
async def test_csv_filter_security_blocked(sample_csv):
    """Test that dangerous expressions are blocked."""
    tool = CSVTool()
    result = await tool.execute(
        action="filter",
        path=str(sample_csv),
        query='__import__("os").system("ls")'
    )
    assert "Error" in result or "Unsupported" in result or "Invalid" in result


@pytest.mark.asyncio
async def test_csv_columns(sample_csv):
    """Test listing columns."""
    tool = CSVTool()
    result = await tool.execute(action="columns", path=str(sample_csv))
    assert "name" in result
    assert "age" in result
    assert "score" in result


@pytest.mark.asyncio
async def test_csv_stats(sample_csv):
    """Test CSV statistics."""
    tool = CSVTool()
    result = await tool.execute(action="stats", path=str(sample_csv))
    assert "age" in result
    assert "score" in result
    assert "count=3" in result or "count = 3" in result