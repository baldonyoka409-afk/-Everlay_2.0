# tests/test_rag.py
import pytest
import asyncio
from core.rag import EmbeddingProvider, RAGDatabase
from agents.tools import RAGTool


@pytest.mark.asyncio
async def test_rag_database_add_and_list(tmp_path):
    """Test adding and listing documents."""
    db_path = tmp_path / "test_rag.db"
    db = RAGDatabase(str(db_path))

    doc_id = db.add_document(
        title="Test Doc",
        content="Test content about Python",
        source="test",
        tags=["python", "test"],
        embedding=[0.1] * 384
    )

    assert doc_id is not None

    docs = db.list_documents(limit=10)
    assert len(docs) >= 1
    assert any(d["title"] == "Test Doc" for d in docs)


@pytest.mark.asyncio
async def test_rag_database_search(tmp_path):
    """Test semantic search (with known embeddings)."""
    db_path = tmp_path / "test_rag.db"
    db = RAGDatabase(str(db_path))

    # Add two docs with different embeddings
    db.add_document(
        title="Python Guide",
        content="Learn Python programming",
        source="test",
        tags=["python"],
        embedding=[1.0] + [0.0] * 383  # Vector pointing to dim 0
    )
    db.add_document(
        title="Java Guide",
        content="Learn Java programming",
        source="test",
        tags=["java"],
        embedding=[0.0, 1.0] + [0.0] * 382  # Vector pointing to dim 1
    )

    # Search with vector similar to Python doc
    results = db.search_similar([1.0] + [0.0] * 383, top_k=1)
    assert len(results) == 1
    assert results[0]["title"] == "Python Guide"
    assert results[0]["score"] > 0.9


@pytest.mark.asyncio
async def test_rag_tool_add_and_search(tmp_path):
    """Test RAGTool integration."""
    # Override DB path
    import core.rag
    original_init = core.rag.RAGDatabase.__init__

    def new_init(self, db_path=None):
        return original_init(self, db_path=str(tmp_path / "test_tool.db"))

    core.rag.RAGDatabase.__init__ = new_init

    try:
        tool = RAGTool()

        # Add document
        result = await tool.execute(
            action="add",
            title="Integration Test",
            content="This is an integration test document",
            source="pytest",
            tags=["integration", "test"]
        )
        assert "Документ добавлен" in result or "added" in result.lower()

        # List documents
        result = await tool.execute(action="list")
        assert "Integration Test" in result

    finally:
        core.rag.RAGDatabase.__init__ = original_init


@pytest.mark.asyncio
async def test_embedding_provider_hash_fallback():
    """Test hash-based embedding fallback."""
    provider = EmbeddingProvider()
    embedding = await provider.get_embedding("test text")

    assert isinstance(embedding, list)
    assert len(embedding) == 384
    # Should be normalized
    import numpy as np
    norm = np.linalg.norm(embedding)
    assert abs(norm - 1.0) < 0.01