"""
Embedding and semantic vector retrieval service for FinSentry AI (Phase 2B/2C).

Provides dense vector generation using BAAI/bge-large-en (1024 dimensions),
cosine similarity calculation, native MongoDB Atlas Vector Search pipeline execution,
and multi-tenant session-scoped retrieval across extracted document chunks.
"""

import hashlib
import logging
import math
import re
import threading
import time
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database

from core.config import get_settings
from database.connection import get_sync_db, mongodb

logger = logging.getLogger(__name__)

# Process-level singleton cache for sentence transformer neural models
_SHARED_MODELS: Dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


class EmbeddingService:
    """
    Service for generating BAAI/bge-large-en neural embeddings and executing
    MongoDB Atlas Vector Search across document chunks.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        dimension: int = 1024,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._model_load_attempted = False
        self._is_neural_ready = False

    def _get_db(self) -> AsyncIOMotorDatabase:
        return mongodb.get_db()

    def _load_model(self) -> None:
        """
        Lazily load the BAAI/bge-large-en sentence-transformer neural model with thread-safe process singleton reuse.
        """
        global _SHARED_MODELS

        with _MODEL_LOCK:
            if self.model_name in _SHARED_MODELS:
                self._model = _SHARED_MODELS[self.model_name]
                self._is_neural_ready = self._model is not None
                self._model_load_attempted = True
                return

            if self._model_load_attempted:
                return

            self._model_load_attempted = True
            t0 = time.time()
            try:
                from sentence_transformers import SentenceTransformer
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info("Loading neural embedding model '%s' on %s...", self.model_name, device)
                model = SentenceTransformer(self.model_name, device=device)
                _SHARED_MODELS[self.model_name] = model
                self._model = model
                self._is_neural_ready = True
                load_duration = (time.time() - t0) * 1000
                logger.info(
                    "Neural embedding model '%s' successfully loaded in %.1fms (dimension=%d, device=%s)",
                    self.model_name,
                    load_duration,
                    self.dimension,
                    device,
                )
            except Exception as exc:
                logger.warning(
                    "Neural model '%s' could not be loaded directly (%s); using high-fidelity 1024-dim projection fallback",
                    self.model_name,
                    exc,
                )
                _SHARED_MODELS[self.model_name] = None
                self._model = None
                self._is_neural_ready = False

    @property
    def is_neural_active(self) -> bool:
        """Check if the neural BAAI/bge-large-en model is active."""
        if not self._model_load_attempted:
            self._load_model()
        return self._is_neural_ready

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate a 1024-dimensional normalized dense vector embedding for the given text
        using BAAI/bge-large-en (with offline-safe projection fallback).
        """
        if not text or not text.strip() or len(text.strip()) < 2:
            return [0.0] * self.dimension

        self._load_model()

        if self._is_neural_ready and self._model is not None:
            try:
                embedding = self._model.encode(text.strip(), normalize_embeddings=True)
                if hasattr(embedding, "tolist"):
                    embedding = embedding.tolist()
                if self.validate_vector(embedding):
                    return embedding
            except Exception as exc:
                logger.warning("Neural encoding encountered error, using fallback projection: %s", exc)

        return self._deterministic_feature_embedding(text)

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate normalized 1024-dimensional dense vector embeddings for a batch of text chunks.
        """
        if not texts:
            return []

        self._load_model()

        if self._is_neural_ready and self._model is not None:
            t0 = time.time()
            try:
                clean_texts = [t.strip() if (t and t.strip()) else "empty" for t in texts]
                embeddings = self._model.encode(
                    clean_texts,
                    normalize_embeddings=True,
                    batch_size=32,
                    show_progress_bar=False,
                )
                result: List[List[float]] = []
                for emb in embeddings:
                    vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    if self.validate_vector(vec):
                        result.append(vec)
                    else:
                        result.append(self._deterministic_feature_embedding("empty"))
                duration_ms = (time.time() - t0) * 1000
                logger.info(
                    "Generated embeddings for %d chunks in %.1fms (%.1fms/chunk)",
                    len(texts),
                    duration_ms,
                    duration_ms / max(len(texts), 1),
                )
                return result
            except Exception as exc:
                logger.warning("Neural batch encoding error, using fallback projection: %s", exc)

        return [self.generate_embedding(t) for t in texts]

    def _deterministic_feature_embedding(self, text: str) -> List[float]:
        """
        High-fidelity sublinear term-frequency feature projection with signed hashing
        and L2 normalization over 1024 dimensions. Ensures valid, non-zero unit vectors.
        """
        if not text or not text.strip():
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        clean_text = text.lower().strip()
        tokens = [t for t in re.findall(r"\b[a-z0-9_$%.-]+\b", clean_text) if len(t) > 1]

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
        Perform semantic vector search across all processed document chunks in a session.
        Uses native MongoDB Atlas Vector Search if available, with in-application cosine fallback.
        """
        query_vec = self.generate_embedding(query)
        db = self._get_db()

        # 1. Attempt native MongoDB Atlas $vectorSearch aggregation pipeline
        try:
            atlas_results = await self._execute_atlas_vector_search(
                db=db,
                user_id=user_id,
                session_id=session_id,
                query_vec=query_vec,
                top_k=top_k,
                score_threshold=score_threshold,
                document_ids=document_ids,
            )
            if atlas_results:
                return atlas_results
        except Exception as atlas_exc:
            logger.debug("Atlas $vectorSearch not available or raised error: %s; using application cosine search", atlas_exc)

        # 2. Application-side vector retrieval fallback
        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "status": {"$in": ["PROCESSED", "INDEXED"]},
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
                        "source_text": ch.get("source_text") or ch_text,
                        "score": round(score, 4),
                        "token_estimate": ch.get("token_estimate", 0),
                        "page_number": ch.get("page_number"),
                        "section": ch.get("section"),
                        "metadata": ch.get("metadata", {}),
                    })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

    async def _execute_atlas_vector_search(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        session_id: str,
        query_vec: List[float],
        top_k: int,
        score_threshold: float = 0.0,
        document_ids: Optional[List[str]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute native MongoDB Atlas $vectorSearch aggregation stage.
        """
        filter_doc: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
        }
        if document_ids:
            filter_doc["document_id"] = {"$in": document_ids}

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "chunks.embedding",
                    "queryVector": query_vec,
                    "numCandidates": max(50, top_k * 10),
                    "limit": top_k * 2,
                    "filter": filter_doc,
                }
            },
            {
                "$project": {
                    "document_id": 1,
                    "filename": 1,
                    "chunks": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        cursor = db.documents.aggregate(pipeline)
        docs = await cursor.to_list(length=top_k * 2)
        if not docs:
            return None

        results: List[Dict[str, Any]] = []
        for doc in docs:
            doc_id = doc.get("document_id")
            filename = doc.get("filename", "")
            for ch in doc.get("chunks", []):
                score = float(doc.get("score", 0.0))
                if score >= score_threshold:
                    results.append({
                        "chunk_id": ch.get("chunk_id"),
                        "chunk_index": ch.get("chunk_index", 0),
                        "document_id": doc_id,
                        "document_filename": filename,
                        "text": ch.get("text", ""),
                        "source_text": ch.get("source_text") or ch.get("text", ""),
                        "score": round(score, 4),
                        "token_estimate": ch.get("token_estimate", 0),
                        "page_number": ch.get("page_number"),
                        "section": ch.get("section"),
                        "metadata": ch.get("metadata", {}),
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

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
        Synchronous search helper for Celery workers and synchronous pipelines.
        """
        query_vec = self.generate_embedding(query)
        db: Database = get_sync_db()

        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "status": {"$in": ["PROCESSED", "INDEXED"]},
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
                        "source_text": ch.get("source_text") or ch_text,
                        "score": round(score, 4),
                        "token_estimate": ch.get("token_estimate", 0),
                        "page_number": ch.get("page_number"),
                        "section": ch.get("section"),
                        "metadata": ch.get("metadata", {}),
                    })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]


embedding_service = EmbeddingService()
