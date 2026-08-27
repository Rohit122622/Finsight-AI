"""
FinSentry AI — Vector Store Abstraction (Phase 2F).

Provides an abstract interface and decoupled implementations for vector embeddings storage
and similarity search, preventing tight coupling to any single database engine.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from models.document import DocumentChunk
from services.embedding_service import embedding_service


class BaseVectorStore(ABC):
    """
    Abstract Vector Store contract decoupled from storage backend.
    """

    @abstractmethod
    async def insert(
        self,
        session_id: str,
        user_id: str,
        document_id: str,
        chunks: List[DocumentChunk],
    ) -> int:
        """Insert and persist vector embeddings for chunks."""
        pass

    @abstractmethod
    async def search(
        self,
        session_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Search vector store and return ranked chunks."""
        pass

    @abstractmethod
    async def delete(
        self,
        session_id: str,
        user_id: str,
        document_id: Optional[str] = None,
    ) -> int:
        """Delete vectors for a document or entire session."""
        pass


class MongoVectorStore(BaseVectorStore):
    """
    MongoDB-backed vector store implementation.
    """

    async def insert(
        self,
        session_id: str,
        user_id: str,
        document_id: str,
        chunks: List[DocumentChunk],
    ) -> int:
        """Generate and attach embeddings to chunks stored in MongoDB."""
        from database.connection import mongodb
        db = mongodb.get_db()

        chunk_dicts = []
        for ch in chunks:
            if not ch.embedding:
                ch.embedding = embedding_service.generate_embedding(ch.text)
            ch.document_id = document_id
            ch.user_id = user_id
            chunk_dicts.append(ch.model_dump())

        result = await db.documents.update_one(
            {"document_id": document_id, "session_id": session_id, "user_id": user_id},
            {"$set": {"chunks": chunk_dicts, "status": "PROCESSED"}},
        )
        return len(chunk_dicts) if result.modified_count > 0 else 0

    async def search(
        self,
        session_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Search session chunks using vector cosine similarity."""
        results = await embedding_service.search_session_chunks(
            session_id=session_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        return [
            {
                "chunk_id": r.get("chunk_id"),
                "document_id": r.get("document_id"),
                "text": r.get("text"),
                "score": r.get("score"),
                "page_number": r.get("page_number"),
                "chunk_index": r.get("chunk_index"),
            }
            for r in results
        ]

    async def delete(
        self,
        session_id: str,
        user_id: str,
        document_id: Optional[str] = None,
    ) -> int:
        """Remove document vectors from the store."""
        from database.connection import mongodb
        db = mongodb.get_db()

        filter_q: Dict[str, Any] = {"session_id": session_id, "user_id": user_id}
        if document_id:
            filter_q["document_id"] = document_id

        res = await db.documents.update_many(
            filter_q,
            {"$set": {"chunks": []}},
        )
        return res.modified_count


                           
vector_store: BaseVectorStore = MongoVectorStore()
