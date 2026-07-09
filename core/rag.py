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
from agents.base import Tool
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingProvider:
    """Провайдер эмбеддингов - OpenRouter или локальный (Ollama)."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._local_available = False

    async def get_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг для текста."""
        # Сначала пробуем локальный (быстрее и бесплатно)
        if await self._check_local():
            return await self._get_local_embedding(text)
        # Фолбэк на OpenRouter
        return await self._get_openrouter_embedding(text)

    async def _check_local(self) -> bool:
        """Проверить доступность локального Ollama."""
        if self._local_available:
            return True
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    self._local_available = resp.status == 200
        except Exception:
            self._local_available = False
        return self._local_available

    async def _get_local_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг через локальный Ollama (nomic-embed-text)."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text}
            ) as resp:
                data = await resp.json()
                return data.get("embedding", [])

    async def _get_openrouter_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг через OpenRouter."""
        from core.openrouter_client import get_client
        client = get_client()
        # Используем text-embedding-3-small или доступную модель
        response = await client.chat_completion(
            messages=[{"role": "user", "content": text}],
            model="text-embedding-3-small",
            max_tokens=1
        )
        # OpenRouter не даёт эмбеддинги напрямую через chat_completion
        # Используем fallback - простой hash-based вектор
        return self._hash_embedding(text)

    def _hash_embedding(self, text: str, dim: int = 384) -> List[float]:
        """Простой детерминированный эмбеддинг на основе хеша (fallback)."""
        # Создаём псевдо-эмбеддинг из хешей частей текста
        chunks = [text[i:i+100] for i in range(0, len(text), 100)]
        vec = np.zeros(dim)
        for i, chunk in enumerate(chunks[:dim]):
            h = int(hashlib.md5(chunk.encode()).hexdigest(), 16)
            vec[i % dim] = (h % 10000) / 10000.0 - 0.5
        # Нормализуем
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


class RAGDatabase:
    """SQLite база для хранения документов и эмбеддингов."""

    def __init__(self, db_path: str = "everlay_brain.db"):
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


class RAGTool(Tool):
    """Инструмент для работы с RAG системой."""

    def __init__(self):
        self.db = RAGDatabase()
        self.embedder = EmbeddingProvider()

    @property
    def name(self) -> str:
        return "rag"

    @property
    def description(self) -> str:
        return "Работа с базой знаний: добавление документов, семантический поиск, теги."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "search", "get", "list", "delete", "tags"],
                    "description": "Действие"
                },
                "title": {"type": "string", "description": "Заголовок документа (для add)"},
                "content": {"type": "string", "description": "Содержимое документа (для add)"},
                "source": {"type": "string", "description": "Источник (файл, URL, заметка)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Теги"},
                "query": {"type": "string", "description": "Поисковый запрос (для search)"},
                "top_k": {"type": "integer", "description": "Количество результатов", "default": 5},
                "doc_id": {"type": "string", "description": "ID документа (для get/delete)"},
                "tag_name": {"type": "string", "description": "Имя тега (для tags)"},
                "tag_color": {"type": "string", "description": "Цвет тега (hex)", "default": "#4ec9b0"}
            },
            "required": ["action"]
        }

    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action")

        try:
            if action == "add":
                title = kwargs.get("title", "Без названия")
                content = kwargs.get("content", "")
                source = kwargs.get("source", "")
                tags = kwargs.get("tags", [])

                # Получаем эмбеддинг
                embedding = await self.embedder.get_embedding(content)

                doc_id = self.db.add_document(
                    title=title,
                    content=content,
                    source=source,
                    tags=tags,
                    embedding=embedding
                )
                return f"✅ Документ добавлен (ID: {doc_id[:8]}...)\nТеги: {', '.join(tags) if tags else 'нет'}"

            elif action == "search":
                query = kwargs.get("query", "")
                top_k = kwargs.get("top_k", 5)
                if not query:
                    return "❌ Пустой запрос"

                embedding = await self.embedder.get_embedding(query)
                results = self.db.search_similar(embedding, top_k=top_k)

                if not results:
                    return "🔍 Ничего не найдено"

                out = [f"🔍 Найдено {len(results)} результатов:\n"]
                for i, r in enumerate(results, 1):
                    tags_str = f" [{', '.join(r['tags'])}]" if r['tags'] else ""
                    out.append(f"{i}. **{r['title']}** (score: {r['score']:.3f}){tags_str}")
                    out.append(f"   {r['content'][:200]}...")
                    out.append(f"   Источник: {r['source'] or 'не указан'}")
                    out.append("")
                return "\n".join(out)

            elif action == "get":
                doc_id = kwargs.get("doc_id", "")
                doc = self.db.get_document(doc_id)
                if not doc:
                    return f"❌ Документ не найден: {doc_id}"
                tags_str = f"\nТеги: {', '.join(doc['tags'])}" if doc['tags'] else ""
                return f"📄 **{doc['title']}**\nID: {doc['id']}\nИсточник: {doc['source'] or 'не указан'}{tags_str}\n\n{doc['content']}"

            elif action == "list":
                docs = self.db.list_documents(limit=20)
                if not docs:
                    return "📭 База пуста"
                out = ["📚 Документы в базе:\n"]
                for d in docs:
                    tags_str = f" [{', '.join(json.loads(d['tags']))}]" if d['tags'] else ""
                    out.append(f"• {d['title']} (ID: {d['id'][:8]}...){tags_str} — {d['source'] or 'нет источника'}")
                return "\n".join(out)

            elif action == "delete":
                doc_id = kwargs.get("doc_id", "")
                if self.db.delete_document(doc_id):
                    return f"🗑️ Документ удалён: {doc_id}"
                return f"❌ Не найден: {doc_id}"

            elif action == "tags":
                tag_name = kwargs.get("tag_name", "")
                tag_color = kwargs.get("tag_color", "#4ec9b0")
                if tag_name:
                    self.db.add_tag(tag_name, tag_color)
                    return f"🏷️ Тег добавлен: {tag_name}"
                tags = self.db.get_tags()
                if not tags:
                    return "🏷️ Тегов нет"
                return "🏷️ Теги:\n" + "\n".join(f"• {t['name']} ({t['color']})" for t in tags)

            else:
                return f"❌ Неизвестное действие: {action}"

        except Exception as e:
            logger.error(f"RAG error: {e}")
            return f"❌ Ошибка RAG: {e}"


# Глобальный экземпляр
_rag_tool: Optional[RAGTool] = None


def get_rag_tool() -> RAGTool:
    """Получить глобальный RAG инструмент."""
    global _rag_tool
    if _rag_tool is None:
        _rag_tool = RAGTool()
    return _rag_tool