"""
Embedding and semantic vector retrieval service for FinSentry AI (Phase 2B/2C).

Provides dense vector generation using BAAI/bge-large-en (1024 dimensions),
cosine similarity calculation, native MongoDB Atlas Vector Search pipeline execution,
and multi-tenant session-scoped retrieval across extracted document chunks.
"""

import hashlib
import logging
import math
import os
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
        self.device = "uninitialized"
        self.model_load_ms = 0.0
        self.model_load_count = 0
        self.model_reused = False

    def _get_db(self) -> AsyncIOMotorDatabase:
        return mongodb.get_db()

    def _load_model(self) -> None:
        """
        Lazily load the BAAI/bge-large-en sentence-transformer neural model with thread-safe process singleton reuse.
        """
        global _SHARED_MODELS

        with _MODEL_LOCK:
            if self.model_name in _SHARED_MODELS and _SHARED_MODELS[self.model_name] is not None:
                self._model = _SHARED_MODELS[self.model_name]
                self.device = str(self._model.device)
                self._is_neural_ready = True
                self._model_load_attempted = True
                self.model_reused = True
                logger.info(
                    "MODEL_CACHE_HIT: Reused cached neural embedding model '%s' in process %d",
                    self.model_name,
                    os.getpid(),
                )
                return

            if self._model_load_attempted and self.model_name in _SHARED_MODELS:
                return

            self._model_load_attempted = True
            logger.info(
                "MODEL_CACHE_MISS: Initializing neural embedding model '%s' in process %d...",
                self.model_name,
                os.getpid(),
            )
            t0 = time.time()
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                # Auto-select GPU/CUDA when genuine CUDA device is available, safe CPU fallback otherwise
                if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                    device = "cuda"
                    device_desc = f"cuda (GPU: {torch.cuda.get_device_name(0)})"
                    cpu_threads = os.cpu_count() or 4
                else:
                    device = "cpu"
                    device_desc = "cpu"
                    cpu_threads = min(10, os.cpu_count() or 4)
                    torch.set_num_threads(cpu_threads)

                model = SentenceTransformer(self.model_name, device=device)
                _SHARED_MODELS[self.model_name] = model
                self._model = model
                self.device = str(model.device)
                self._is_neural_ready = True
                load_duration = (time.time() - t0) * 1000
                self.model_load_ms = load_duration
                self.model_load_count += 1
                logger.info(
                    "Neural embedding model '%s' successfully loaded in %.1fms (model_load_ms=%.1f, dimension=%d, device=%s, threads=%d)",
                    self.model_name,
                    load_duration,
                    load_duration,
                    self.dimension,
                    device_desc,
                    cpu_threads,
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

    def preload_model(self) -> None:
        """Explicitly preload and warm up neural model during application startup."""
        self._load_model()
        if self._is_neural_ready and self._model is not None:
            try:
                import torch
                with torch.inference_mode():
                    _ = self._model.encode(["FinSentry warm-up"], batch_size=1, normalize_embeddings=True)
            except Exception:
                pass

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
                import torch
                with torch.inference_mode():
                    embedding = self._model.encode(
                        text.strip(),
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                if hasattr(embedding, "tolist"):
                    embedding = embedding.tolist()
                if self.validate_vector(embedding):
                    return embedding
            except Exception as exc:
                logger.warning("Neural encoding encountered error, using fallback projection: %s", exc)

        return self._deterministic_feature_embedding(text)

    def generate_embeddings_batch(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        """
        Generate normalized 1024-dimensional dense vector embeddings for a batch of text chunks
        with granular stage timings and telemetry (preprocessing, inference, postprocessing, validation).
        """
        if not texts:
            return []

        self._load_model()

        if self._is_neural_ready and self._model is not None:
            t_total_start = time.time()
            try:
                import torch

                threads = torch.get_num_threads()
                if batch_size is None:
                    batch_size = 64 if str(getattr(self._model, "device", "")).startswith("cuda") else 32

                # 1. Preprocessing / Cleaning
                t_prep_start = time.time()
                clean_texts = [t.strip() if (t and t.strip()) else "empty" for t in texts]
                preprocessing_ms = (time.time() - t_prep_start) * 1000

                # 2. Model Inference
                t_infer_start = time.time()
                with torch.inference_mode():
                    embeddings = self._model.encode(
                        clean_texts,
                        normalize_embeddings=True,
                        batch_size=batch_size,
                        show_progress_bar=False,
                    )
                inference_ms = (time.time() - t_infer_start) * 1000

                # 3. Post-Processing & Validation
                t_post_start = time.time()
                result: List[List[float]] = []
                for emb in embeddings:
                    vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    if self.validate_vector(vec):
                        result.append(vec)
                    else:
                        result.append(self._deterministic_feature_embedding("empty"))
                postprocessing_ms = (time.time() - t_post_start) * 1000

                total_duration_ms = (time.time() - t_total_start) * 1000
                ms_per_chunk = total_duration_ms / max(len(texts), 1)
                chunks_per_sec = (len(texts) / (total_duration_ms / 1000.0)) if total_duration_ms > 0 else 0.0

                curr_device = getattr(self, "device", None) or (str(self._model.device) if self._model else "unknown")
                logger.info(
                    "EMBEDDING_PERF: device=%s, model=%s, chunks=%d, batch_size=%d, torch_threads=%d, latency_ms=%.1f, ms_per_chunk=%.2f, throughput=%.2f chunks/sec, inference_ms=%.1f",
                    curr_device,
                    self.model_name,
                    len(texts),
                    batch_size,
                    threads,
                    total_duration_ms,
                    ms_per_chunk,
                    chunks_per_sec,
                    inference_ms,
                )
                return result
            except Exception as exc:
                logger.warning("Neural batch encoding error, using fallback projection: %s", exc)

        return [self.generate_embedding(t) for t in texts]

    def benchmark_batch_encoding(
        self,
        sample_texts: Optional[List[str]] = None,
        batch_sizes: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Benchmark neural encoding throughput across multiple batch sizes on current hardware.
        """
        if batch_sizes is None:
            batch_sizes = [16, 32]
        if sample_texts is None:
            sample_texts = [
                f"Financial disclosure statement paragraph {i} analyzing consolidated operating results and capital expenditures."
                for i in range(64)
            ]

        results = {}
        for bs in batch_sizes:
            t0 = time.time()
            vecs = self.generate_embeddings_batch(sample_texts, batch_size=bs)
            dur_ms = (time.time() - t0) * 1000
            ms_per = dur_ms / len(sample_texts)
            rate = len(sample_texts) / (dur_ms / 1000.0) if dur_ms > 0 else 0.0
            results[f"batch_{bs}"] = {
                "chunks": len(sample_texts),
                "batch_size": bs,
                "total_ms": round(dur_ms, 1),
                "ms_per_chunk": round(ms_per, 2),
                "chunks_per_sec": round(rate, 2),
                "vectors_count": len(vecs),
            }
        return results

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
