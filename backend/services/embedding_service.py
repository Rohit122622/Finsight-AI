"""
Embedding and semantic vector retrieval service for FinSentry AI (Phase 2B/2C).

Provides dense vector generation, cosine similarity calculation, and multi-tenant
session-scoped semantic search across extracted document chunks.
"""

import hashlib
import logging
import math
import re
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database

from core.config import get_settings
from database.connection import get_sync_db, mongodb

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating embeddings and performing semantic vector retrieval.
    """

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    def _get_db(self) -> AsyncIOMotorDatabase:
        return mongodb.get_db()

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate a normalized dense vector embedding for the given text.

        Uses sublinear term-frequency feature projection with signed hashing
        and L2 normalization over 1024 dimensions.
        """
        if not text or not text.strip() or len(text.strip()) < 5:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        clean_text = text.lower().strip()
        tokens = [t for t in re.findall(r'\b[a-z0-9_$%.-]+\b', clean_text) if len(t) > 1]

        if not tokens:
            return [0.0] * self.dimension

        from collections import Counter
        counts = Counter(tokens)
        for i in range(len(tokens) - 1):
            counts[f"{tokens[i]}_{tokens[i+1]}"] += 2.0

        for term, count in counts.items():
            h_int = int(hashlib.sha256(term.encode("utf-8")).hexdigest(), 16)
            idx = h_int % self.dimension
            sign = 1.0 if ((h_int >> 8) & 1) else -1.0
            weight = (1.0 + math.log(count)) if count > 0 else 0.0
            vector[idx] += sign * weight

                          
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate normalized dense vector embeddings for a batch of text chunks.
        """
        return [self.generate_embedding(t) for t in texts]

    def validate_vector(self, vector: List[float]) -> bool:
        """
        Validate vector dimension and finite values.
        """
        if not vector or len(vector) != self.dimension:
            return False
        return all(math.isfinite(v) for v in vector)


    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Compute the cosine similarity between two float vectors.
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        sim = dot / (norm_a * norm_b)
        return max(0.0, min(1.0, float(sim)))

    async def search_session_chunks(
        self,
        user_id: str,
        session_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search across all processed document chunks in a session.

        Enforces strict multi-tenant boundary via user_id and session_id filtering.
        """
        query_vec = self.generate_embedding(query)
        db = self._get_db()

        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "status": "PROCESSED",
        }
        if document_ids:
            filter_query["document_id"] = {"$in": document_ids}

        cursor = db.documents.find(
            filter_query,
            {"document_id": 1, "filename": 1, "chunks": 1, "metadata": 1},
        )
        docs = await cursor.to_list(length=100)

        scored_chunks: List[Dict[str, Any]] = []

        for doc in docs:
            doc_id = doc.get("document_id")
            filename = doc.get("filename", "Unknown Document")
            chunks = doc.get("chunks", [])

            for ch in chunks:
                ch_text = ch.get("text", "")
                ch_embedding = ch.get("embedding")
                if not ch_embedding or len(ch_embedding) != self.dimension:
                    ch_embedding = self.generate_embedding(ch_text)

                score = self.cosine_similarity(query_vec, ch_embedding)
                if score >= score_threshold:
                    scored_chunks.append({
                        "chunk_id": ch.get("chunk_id"),
                        "chunk_index": ch.get("chunk_index", 0),
                        "document_id": doc_id,
                        "document_filename": filename,
                        "text": ch_text,
                        "score": round(score, 4),
                        "token_estimate": ch.get("token_estimate", 0),
                        "page_number": ch.get("page_number"),
                        "metadata": ch.get("metadata", {}),
                    })

                                             
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

    def search_session_chunks_sync(
        self,
        user_id: str,
        session_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous search helper for Celery workers.
        """
        query_vec = self.generate_embedding(query)
        db: Database = get_sync_db()

        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "status": "PROCESSED",
        }
        if document_ids:
            filter_query["document_id"] = {"$in": document_ids}

        docs = list(
            db.documents.find(
                filter_query,
                {"document_id": 1, "filename": 1, "chunks": 1, "metadata": 1},
            ).limit(100)
        )

        scored_chunks: List[Dict[str, Any]] = []

        for doc in docs:
            doc_id = doc.get("document_id")
            filename = doc.get("filename", "Unknown Document")
            chunks = doc.get("chunks", [])

            for ch in chunks:
                ch_text = ch.get("text", "")
                ch_embedding = ch.get("embedding")
                if not ch_embedding or len(ch_embedding) != self.dimension:
                    ch_embedding = self.generate_embedding(ch_text)

                score = self.cosine_similarity(query_vec, ch_embedding)
                if score >= score_threshold:
                    scored_chunks.append({
                        "chunk_id": ch.get("chunk_id"),
                        "chunk_index": ch.get("chunk_index", 0),
                        "document_id": doc_id,
                        "document_filename": filename,
                        "text": ch_text,
                        "score": round(score, 4),
                        "token_estimate": ch.get("token_estimate", 0),
                        "page_number": ch.get("page_number"),
                        "metadata": ch.get("metadata", {}),
                    })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]


embedding_service = EmbeddingService()
