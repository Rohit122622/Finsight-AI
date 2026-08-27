"""
FinSentry AI — Phase 3A Retrieval Service.

Implements the retrieval foundation for the Research Agent:
  - Vector (semantic) search
  - Keyword (lexical) search
  - Hybrid retrieval with deterministic score combination
  - Session-scoped, user-isolated retrieval
  - Metadata filtering at the database layer
  - Top-K retrieval with validation
  - Redis query caching with tenant-safe keys

Architecture:
    Query → RetrievalService → Vector + Keyword → Hybrid Ranking → Top-K → Results
"""

import hashlib
import json
import logging
import math
import re
from collections import Counter
import time
from typing import Any, Dict, List, Optional, Tuple

from core.config import get_settings
from database.connection import mongodb
from database.redis_client import redis_manager
from schemas.query_understanding import QueryUnderstandingRequest, QueryUnderstandingResult
from schemas.retrieval import (
    MetadataFilter,
    RetrievalMetadata,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
)
from services.embedding_service import embedding_service
from services.query_understanding_service import query_understanding_service

logger = logging.getLogger(__name__)

                                                                       

                                                    
MAX_TOP_K = 100

                                  
DEFAULT_TOP_K = 5

                                        
CACHE_TTL_SECONDS = 300

                                        
CACHE_KEY_PREFIX = "finsentry:retrieval:v1"

                                                                 
CACHE_VERSION = 1


class RetrievalService:
    """
    Phase 3A Retrieval Service.

    Provides vector, keyword, and hybrid retrieval across session-scoped
    document chunks with Redis caching and metadata filtering.
    """

    def __init__(self) -> None:
        self._cache_ttl = CACHE_TTL_SECONDS
        self._cache_version = CACHE_VERSION
        self._memory_cache: Dict[str, Tuple[float, str]] = {}
        self._session_versions: Dict[str, int] = {}                                   

                                                                       

    async def retrieve(
        self,
        session_id: str,
        user_id: str,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        """
        Execute a retrieval operation with caching, filtering, and hybrid ranking.

        This is the main entry point for the retrieval pipeline.

        Args:
            session_id: Owning research session ID (enforced at DB layer).
            user_id: Owning user ID (enforced at DB layer).
            request: Validated retrieval request with query, mode, filters, etc.

        Returns:
            RetrievalResponse with ranked results and operational metadata.
        """
                               
        top_k = self._validate_top_k(request.top_k)

                           
        cache_key = self._build_cache_key(session_id, user_id, request)
        cached_result = self._cache_get(cache_key)
        if cached_result is not None:
            logger.info(
                "Cache HIT for retrieval query (session=%s, query_hash=%s)",
                session_id,
                cache_key[-16:],
            )
            cached_result.retrieval_metadata.cache_hit = True
            cached_result.retrieval_metadata.cache_key = cache_key[-16:]
            return cached_result

        logger.info(
            "Cache MISS for retrieval query (session=%s, mode=%s, top_k=%d)",
            session_id,
            request.mode.value,
            top_k,
        )

                                                     
        qu_result: Optional[QueryUnderstandingResult] = None
        if request.enable_query_understanding:
            try:
                qu_result = query_understanding_service.understand_query(
                    QueryUnderstandingRequest(
                        query=request.query,
                        session_id=session_id,
                    )
                )
            except Exception as exc:
                logger.warning("Query understanding non-fatal error: %s", exc)

                                                                          
        mongo_filter = self._build_mongo_filter(session_id, user_id, request.filters)

                                                                      
        candidates = await self._fetch_candidates(mongo_filter, session_id, user_id)

        if not candidates:
            response = RetrievalResponse(
                query=request.query,
                session_id=session_id,
                results=[],
                total=0,
                retrieval_metadata=RetrievalMetadata(
                    mode=request.mode,
                    vector_weight=request.vector_weight,
                    keyword_weight=1.0 - request.vector_weight,
                    score_threshold=request.score_threshold,
                    total_candidates=0,
                    cache_hit=False,
                    filters_applied=request.filters,
                    query_understanding=qu_result,
                ),
            )
            self._cache_set(cache_key, response)
            return response

                                                  
        scored_results: List[RetrievalResult]
        if request.mode == RetrievalMode.VECTOR:
            scored_results = self._score_vector(
                request.query, candidates, session_id, user_id
            )
        elif request.mode == RetrievalMode.KEYWORD:
            scored_results = self._score_keyword(
                request.query, candidates, session_id, user_id
            )
        else:
            scored_results = self._score_hybrid(
                request.query,
                candidates,
                session_id,
                user_id,
                vector_weight=request.vector_weight,
            )

                               
        if request.score_threshold > 0.0:
            scored_results = [
                r for r in scored_results if r.score >= request.score_threshold
            ]

        total_candidates = len(scored_results)

                                                    
        scored_results.sort(key=lambda r: r.score, reverse=True)
        top_k_results = scored_results[:top_k]

                                                                     
                                                                              
        top_k_results = self._apply_chunk_filters(top_k_results, request.filters)

        response = RetrievalResponse(
            query=request.query,
            session_id=session_id,
            results=top_k_results,
            total=len(top_k_results),
            retrieval_metadata=RetrievalMetadata(
                mode=request.mode,
                vector_weight=request.vector_weight,
                keyword_weight=1.0 - request.vector_weight,
                score_threshold=request.score_threshold,
                total_candidates=total_candidates,
                cache_hit=False,
                filters_applied=request.filters,
                query_understanding=qu_result,
            ),
        )

                          
        self._cache_set(cache_key, response)

        return response



                                                                       

    @staticmethod
    def _validate_top_k(top_k: int) -> int:
        """Validate and clamp top_k to safe bounds."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if top_k > MAX_TOP_K:
            raise ValueError(f"top_k must not exceed {MAX_TOP_K}")
        return top_k

                                                                       

    @staticmethod
    def _build_mongo_filter(
        session_id: str,
        user_id: str,
        filters: Optional[MetadataFilter] = None,
    ) -> Dict[str, Any]:
        """
        Build the MongoDB document query with mandatory session/user isolation.

        Metadata filters are applied at the query layer, NOT post-fetch.
        """
        query: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "status": {"$in": ["PROCESSED", "INDEXED"]},
        }

        if filters:
            if filters.document_id:
                query["document_id"] = filters.document_id
            elif filters.document_ids:
                query["document_id"] = {"$in": filters.document_ids}

            if filters.status:
                query["status"] = filters.status

        return query

                                                                       

    async def _fetch_candidates(
        self,
        mongo_filter: Dict[str, Any],
        session_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all document chunks matching the filter from MongoDB.

        Returns a flat list of chunk dicts with parent document metadata attached.
        """
        db = mongodb.get_db()
        cursor = db.documents.find(
            mongo_filter,
            {
                "document_id": 1,
                "filename": 1,
                "chunks": 1,
                "metadata": 1,
                "session_id": 1,
                "user_id": 1,
            },
        )
        docs = await cursor.to_list(length=200)

        candidates: List[Dict[str, Any]] = []
        for doc in docs:
            doc_id = doc.get("document_id", "")
            filename = doc.get("filename", "")
            doc_session_id = doc.get("session_id", "")
            doc_user_id = doc.get("user_id", "")

                                                                      
            if doc_session_id != session_id or doc_user_id != user_id:
                logger.warning(
                    "Session/user mismatch in candidate fetch — skipping doc %s",
                    doc_id,
                )
                continue

            for ch in doc.get("chunks", []):
                candidates.append({
                    "chunk_id": ch.get("chunk_id", ""),
                    "document_id": doc_id,
                    "document_filename": filename,
                    "session_id": doc_session_id,
                    "user_id": doc_user_id,
                    "text": ch.get("text", ""),
                    "source_text": ch.get("source_text") or ch.get("text", ""),
                    "embedding": ch.get("embedding"),
                    "page_number": ch.get("page_number"),
                    "section": ch.get("section"),
                    "chunk_index": ch.get("chunk_index", 0),
                    "token_estimate": ch.get("token_estimate", 0),
                    "metadata": ch.get("metadata", {}),
                })

        return candidates

                                                                       

    def _score_vector(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        session_id: str,
        user_id: str,
    ) -> List[RetrievalResult]:
        """Score candidates using semantic vector cosine similarity."""
        query_vec = embedding_service.generate_embedding(query)
        results: List[RetrievalResult] = []

        for ch in candidates:
            ch_embedding = ch.get("embedding")
            if not ch_embedding or len(ch_embedding) != embedding_service.dimension:
                ch_embedding = embedding_service.generate_embedding(ch["text"])

            vector_score = max(0.0, min(1.0, embedding_service.cosine_similarity(query_vec, ch_embedding)))

            results.append(RetrievalResult(
                document_id=ch["document_id"],
                chunk_id=ch["chunk_id"],
                session_id=session_id,
                user_id=user_id,
                source_text=ch["source_text"],
                page_number=ch.get("page_number"),
                section=ch.get("section"),
                chunk_index=ch.get("chunk_index", 0),
                score=round(vector_score, 4),
                vector_score=round(vector_score, 4),
                keyword_score=None,
                retrieval_method=RetrievalMode.VECTOR,
                document_filename=ch.get("document_filename"),
                token_estimate=ch.get("token_estimate", 0),
                metadata=ch.get("metadata", {}),
            ))

        return results

                                                                       

    def _score_keyword(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        session_id: str,
        user_id: str,
    ) -> List[RetrievalResult]:
        """
        Score candidates using lexical keyword matching with BM25-like scoring.

        Handles exact financial terminology and number matching.
        """
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

                                              
        n_docs = max(len(candidates), 1)
        doc_freq: Counter = Counter()
        for ch in candidates:
            ch_terms = set(self._tokenize(ch["text"]))
            for qt in query_terms:
                if qt in ch_terms:
                    doc_freq[qt] += 1

        results: List[RetrievalResult] = []

        for ch in candidates:
            ch_text = ch["text"]
            ch_terms_list = self._tokenize(ch_text)
            ch_terms_counter = Counter(ch_terms_list)
            ch_len = len(ch_terms_list) if ch_terms_list else 1

            score = 0.0
            for qt in query_terms:
                tf = ch_terms_counter.get(qt, 0)
                df = doc_freq.get(qt, 0)
                idf = math.log((n_docs + 1) / (1 + df)) if df >= 0 else 0.0

                                                                              
                k1 = 1.2
                b = 0.75
                avg_dl = 100.0
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (ch_len / avg_dl)))
                score += tf_norm * idf

                                                                              
            query_lower = query.lower().strip()
            ch_text_lower = ch_text.lower()
            if query_lower in ch_text_lower:
                score += 2.0

                                                                
            query_numbers = re.findall(r'\$?[\d,]+\.?\d*[BMK]?', query)
            for num in query_numbers:
                if num in ch_text:
                    score += 1.5

                                    
            keyword_score = max(0.0, min(1.0, score / max(len(query_terms) * 3.0, 1.0)))

            results.append(RetrievalResult(
                document_id=ch["document_id"],
                chunk_id=ch["chunk_id"],
                session_id=session_id,
                user_id=user_id,
                source_text=ch["source_text"],
                page_number=ch.get("page_number"),
                section=ch.get("section"),
                chunk_index=ch.get("chunk_index", 0),
                score=round(keyword_score, 4),
                vector_score=None,
                keyword_score=round(keyword_score, 4),
                retrieval_method=RetrievalMode.KEYWORD,
                document_filename=ch.get("document_filename"),
                token_estimate=ch.get("token_estimate", 0),
                metadata=ch.get("metadata", {}),
            ))

        return results

                                                                       

    def _score_hybrid(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        session_id: str,
        user_id: str,
        vector_weight: float = 0.7,
    ) -> List[RetrievalResult]:
        """
        Combine vector and keyword scores using explicit deterministic weighted fusion.

        hybrid_score = vector_weight * vector_score + (1 - vector_weight) * keyword_score

        This is NOT simple concatenation — it produces a single fused ranking.
        """
        keyword_weight = 1.0 - vector_weight

                             
        vector_results = self._score_vector(query, candidates, session_id, user_id)
        keyword_results = self._score_keyword(query, candidates, session_id, user_id)

                                                     
        keyword_scores: Dict[str, float] = {}
        for kr in keyword_results:
            keyword_scores[kr.chunk_id] = kr.keyword_score or 0.0

        results: List[RetrievalResult] = []
        for vr in vector_results:
            v_score = vr.vector_score or 0.0
            k_score = keyword_scores.get(vr.chunk_id, 0.0)

            hybrid_score = (vector_weight * v_score) + (keyword_weight * k_score)
            hybrid_score = round(min(1.0, max(0.0, hybrid_score)), 4)

            results.append(RetrievalResult(
                document_id=vr.document_id,
                chunk_id=vr.chunk_id,
                session_id=vr.session_id,
                user_id=vr.user_id,
                source_text=vr.source_text,
                page_number=vr.page_number,
                section=vr.section,
                chunk_index=vr.chunk_index,
                score=hybrid_score,
                vector_score=round(v_score, 4),
                keyword_score=round(k_score, 4),
                retrieval_method=RetrievalMode.HYBRID,
                document_filename=vr.document_filename,
                token_estimate=vr.token_estimate,
                metadata=vr.metadata,
            ))

        return results

                                                                       

    @staticmethod
    def _apply_chunk_filters(
        results: List[RetrievalResult],
        filters: Optional[MetadataFilter],
    ) -> List[RetrievalResult]:
        """Apply chunk-level metadata filters (page_number, section, etc.)."""
        if not filters:
            return results

        filtered = results

        if filters.page_number is not None:
            filtered = [r for r in filtered if r.page_number == filters.page_number]

        if filters.page_range is not None:
            start, end = filters.page_range
            filtered = [
                r for r in filtered
                if r.page_number is not None and start <= r.page_number <= end
            ]

        if filters.section is not None:
            section_lower = filters.section.lower()
            filtered = [
                r for r in filtered
                if r.section is not None and r.section.lower() == section_lower
            ]

        if filters.extra:
            for key, value in filters.extra.items():
                filtered = [
                    r for r in filtered
                    if r.metadata.get(key) == value
                ]

        return filtered

                                                                       

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text for keyword matching, preserving financial terms."""
        if not text:
            return []
        clean = text.lower().strip()
        tokens = re.findall(r'\b[a-z0-9_$%.\-]+\b', clean)
        return [t for t in tokens if len(t) > 1]

                                                                       

    def _build_cache_key(
        self,
        session_id: str,
        user_id: str,
        request: RetrievalRequest,
    ) -> str:
        """
        Build a tenant-safe, parameter-aware cache key.

        The key includes user_id, session_id, query hash, top_k, mode,
        filters hash, and cache version to ensure:
        - No cross-user leakage
        - No cross-session leakage
        - Different parameters produce different keys
        - Version bumps invalidate stale caches
        """
                                         
        filter_str = ""
        if request.filters:
            filter_dict = request.filters.model_dump(exclude_none=True)
            filter_str = json.dumps(filter_dict, sort_keys=True)

                                                                                
        session_version = self._get_session_version(session_id)

        key_material = (
            f"{user_id}|{session_id}|{request.query}|"
            f"{request.top_k}|{request.mode.value}|"
            f"{request.score_threshold}|{request.vector_weight}|"
            f"{filter_str}|v{self._cache_version}|sv{session_version}"
        )

        key_hash = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:32]
        return f"{CACHE_KEY_PREFIX}:{user_id}:{session_id}:{key_hash}"



                                                                       

    def _cache_get(self, cache_key: str) -> Optional[RetrievalResponse]:
        """Attempt to retrieve cached retrieval results from Redis or memory fallback."""
        try:
            client = redis_manager.get_client()
            raw = client.get(cache_key)
            if raw is not None:
                data = json.loads(raw)
                return RetrievalResponse(**data)
        except Exception as exc:
            logger.debug("Redis cache GET failed: %s", exc)

                            
        if cache_key in self._memory_cache:
            exp, raw = self._memory_cache[cache_key]
            if time.time() < exp:
                try:
                    data = json.loads(raw)
                    return RetrievalResponse(**data)
                except Exception:
                    pass
            else:
                self._memory_cache.pop(cache_key, None)
        return None

    def _cache_set(self, cache_key: str, response: RetrievalResponse) -> None:
        """Store retrieval results in Redis with TTL and memory fallback."""
        raw = response.model_dump_json()
        self._memory_cache[cache_key] = (time.time() + self._cache_ttl, raw)
        try:
            client = redis_manager.get_client()
            client.setex(cache_key, self._cache_ttl, raw)
        except Exception as exc:
            logger.debug("Redis cache SET failed: %s", exc)

    def _cache_delete(self, cache_key: str) -> bool:
        """Delete a specific cache entry."""
        self._memory_cache.pop(cache_key, None)
        try:
            client = redis_manager.get_client()
            return bool(client.delete(cache_key))
        except Exception as exc:
            logger.debug("Redis cache DELETE failed: %s", exc)
            return True

    def _get_session_version(self, session_id: str) -> int:
        """Get the current retrieval version for a session."""
        if session_id in self._session_versions:
            return self._session_versions[session_id]

                                                 
        redis_key = f"{CACHE_KEY_PREFIX}:session_version:{session_id}"
        try:
            client = redis_manager.get_client()
            val = client.get(redis_key)
            if val is not None:
                version = int(val)
                self._session_versions[session_id] = version
                return version
        except Exception:
            pass

        self._session_versions[session_id] = 0
        return 0

    def bump_cache_version(self) -> int:
        """Bump global cache version, invalidating all old version keys."""
        self._cache_version += 1
        logger.info("Bumped global retrieval cache version to %d", self._cache_version)
        return self._cache_version

    def invalidate_session_cache(self, session_id: str, user_id: str) -> int:
        """
        Invalidate all cached retrieval queries for a session.

        Bumps the per-session retrieval version so all subsequent cache key
        computations produce different hashes, making old entries automatically
        stale without requiring key scanning.

        Also performs explicit cleanup of in-memory and Redis entries.
        """
                                                                   
        new_version = self._session_versions.get(session_id, 0) + 1
        self._session_versions[session_id] = new_version

        redis_version_key = f"{CACHE_KEY_PREFIX}:session_version:{session_id}"
        try:
            client = redis_manager.get_client()
            client.set(redis_version_key, new_version)
        except Exception as exc:
            logger.debug("Redis session version bump failed: %s", exc)

                                                           
        keys_to_del = [k for k in self._memory_cache if f":{user_id}:{session_id}:" in k]
        for k in keys_to_del:
            self._memory_cache.pop(k, None)

                                                 
        count = len(keys_to_del)
        try:
            client = redis_manager.get_client()
            pattern = f"{CACHE_KEY_PREFIX}:{user_id}:{session_id}:*"
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                count += client.delete(*keys)
        except Exception as exc:
            logger.debug("Redis invalidate session cache failed: %s", exc)

        logger.info(
            "Invalidated retrieval cache for session=%s (new version=%d, cleaned %d entries)",
            session_id, new_version, count,
        )
        return count


                                                                       

retrieval_service = RetrievalService()
