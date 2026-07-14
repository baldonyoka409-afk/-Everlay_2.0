"""
RAG System - Retrieval-Augmented Generation для Everlay.
SQLite + эмбеддинги для семантического поиска.
"""
import asyncio
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingProvider:
    """Провайдер эмбеддингов - Ollama (локально), OpenRouter или hash-based фоллбэк."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._local_available = False
        self._provider = self.settings.embedding_provider.lower()

    async def get_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг для текста согласно настроенному провайдеру."""
        # Если задан конкретный провайдер (не auto)
        if self._provider == "ollama":
            if await self._check_local():
                return await self._get_local_embedding(text)
            return self._hash_embedding(text)
        elif self._provider == "openrouter":
            return await self._get_openrouter_embedding(text)
        elif self._provider == "hash":
            return self._hash_embedding(text)

        # auto: Ollama -> OpenRouter -> hash
        if await self._check_local():
            return await self._get_local_embedding(text)

        return await self._get_openrouter_embedding(text)

    async def _check_local(self) -> bool:
        """Проверить доступность локального Ollama."""
        if self._local_available:
            return True
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.settings.ollama_timeout_seconds)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.settings.ollama_base_url}/api/tags",
                    timeout=timeout
                ) as resp:
                    self._local_available = resp.status == 200
        except Exception:
            self._local_available = False
        return self._local_available

    async def _get_local_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг через локальный Ollama."""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=self.settings.ollama_timeout_seconds)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.settings.ollama_base_url}/api/embeddings",
                json={"model": self.settings.ollama_embedding_model, "prompt": text},
                timeout=timeout
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("embedding", [])
                # Если ошибка - фоллбэк
                return self._hash_embedding(text)

    async def _get_openrouter_embedding(self, text: str) -> List[float]:
        """OpenRouter не поддерживает эмбеддинги через chat/completions.
        Возвращаем hash-based как фоллбэк."""
        # OpenRouter не имеет отдельного /embeddings эндпоинта
        # Если появится - раскомментировать и реализовать
        return self._hash_embedding(text)

    def _hash_embedding(self, text: str, dim: int = 384) -> List[float]:
        """Простой детерминированный эмбеддинг на основе хеша (fallback).
        НЕ подходит для семантического поиска - только для совместимости."""
        chunks = [text[i:i+100] for i in range(0, len(text), 100)]
        vec = np.zeros(dim)
        for i, chunk in enumerate(chunks[:dim]):
            h = int(hashlib.md5(chunk.encode()).hexdigest(), 16)
            vec[i % dim] = (h % 10000) / 10000.0 - 0.5
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


class RAGDatabase:
    """SQLite база для хранения документов и эмбеддингов."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            from core.config import get_settings
            db_path = get_settings().rag_db_path
        self.db_path = Path(db_path).resolve()
        self._init_db()

    def _init_db(self):
        """Инициализация таблиц."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    tags TEXT,  -- JSON array
                    metadata TEXT,  -- JSON
                    embedding TEXT,  -- JSON array of floats
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    messages TEXT,  -- JSON array
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_documents_tags ON documents(tags);
                CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at);
            """)

    def add_document(
        self,
        title: str,
        content: str,
        source: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ) -> str:
        """Добавить документ в базу."""
        doc_id = str(uuid.uuid4())
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        emb_json = json.dumps(embedding or [], ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO documents (id, title, content, source, tags, metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, title, content, source, tags_json, meta_json, emb_json))
        return doc_id

    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.3,
        tags_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Семантический поиск похожих документов."""
        if not query_embedding:
            return []

        query_vec = np.array(query_embedding)
        results = []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM documents WHERE embedding != '[]'"
            params = []

            if tags_filter:
                placeholders = ','.join(['?' for _ in tags_filter])
                sql += f" AND ("
                conditions = []
                for tag in tags_filter:
                    conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
                sql += " OR ".join(conditions) + ")"

            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                try:
                    emb = json.loads(row["embedding"])
                    if not emb:
                        continue
                    doc_vec = np.array(emb)
                    # Косинусное сходство
                    score = float(np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec)))
                    if score >= min_score:
                        results.append({
                            "id": row["id"],
                            "title": row["title"],
                            "content": row["content"],
                            "source": row["source"],
                            "tags": json.loads(row["tags"]),
                            "metadata": json.loads(row["metadata"]),
                            "score": score,
                            "created_at": row["created_at"]
                        })
                except Exception:
                    continue

        # Сортируем по убыванию score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def get_document(self, doc_id: str) -> Optional[Dict]:
        """Получить документ по ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "title": row["title"],
                    "content": row["content"],
                    "source": row["source"],
                    "tags": json.loads(row["tags"]),
                    "metadata": json.loads(row["metadata"]),
                    "embedding": json.loads(row["embedding"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
        return None

    def list_documents(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Список документов."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, title, source, tags, created_at FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_document(self, doc_id: str) -> bool:
        """Удалить документ."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cursor.rowcount > 0

    def add_tag(self, name: str, color: str = "#4ec9b0") -> bool:
        """Добавить тег."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color))
            return True
        except Exception:
            return False

    def get_tags(self) -> List[Dict]:
        """Список тегов."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tags ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]


# Глобальный экземпляр RAGTool (lazy import чтобы избежать циклических импортов)
_rag_tool: Optional["RAGTool"] = None


def get_rag_tool() -> "RAGTool":
    """Получить глобальный RAG инструмент (lazy import)."""
    global _rag_tool
    if _rag_tool is None:
        from agents.tools import RAGTool
        _rag_tool = RAGTool()
    return _rag_tool