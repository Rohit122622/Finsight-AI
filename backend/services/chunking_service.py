"""
Section-Aware Token Chunking Service for FinSentry AI.

Segments document text into 300-500 token chunks while preserving
section boundaries, atomic table structures, page provenance, and financial facts.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from agents.document.schemas import ExtractedTable, ParsedChunk
from services.section_classifier_service import section_classifier_service

logger = logging.getLogger(__name__)

                             
DEFAULT_MIN_TOKENS = 250
DEFAULT_TARGET_TOKENS = 400
DEFAULT_MAX_TOKENS = 550
DEFAULT_OVERLAP_TOKENS = 50


class ChunkingService:
    """
    Service for token-based, section-aware document chunking.
    """

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Accurate token counting compatible with subword and BGE-large-en tokenizers.
        Splits on word boundaries, numbers, currency symbols, and punctuation.
        """
        if not text or not text.strip():
            return 0
                                                                                                
        tokens = re.findall(r"\b[A-Za-z0-9_$%.-]+\b|[^\w\s]", text)
        return max(1, len(tokens))

    def chunk_document_content(
        self,
        document_id: str,
        session_id: str,
        user_id: str,
        page_segments: List[Dict[str, Any]],
        extracted_tables: Optional[List[ExtractedTable]] = None,
        target_token_size: int = DEFAULT_TARGET_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        filename: str = "document.pdf",
    ) -> List[ParsedChunk]:
        """
        Generate semantic, section-classified chunks from page text segments and structured tables.
        """
        chunks: List[ParsedChunk] = []
        chunk_index = 0
        active_section = "other"
        active_section_label = "Other"

        tables_by_page: Dict[int, List[ExtractedTable]] = {}
        for tbl in (extracted_tables or []):
            tables_by_page.setdefault(tbl.page_number, []).append(tbl)

        for seg in page_segments:
            page_num = seg.get("page", 1)
            page_text = seg.get("text", "").strip()

                                                                       
            detected_sec = section_classifier_service.detect_section_header(page_text[:500])
            if detected_sec:
                active_section, active_section_label = detected_sec

                                                                                  
            page_tables = tables_by_page.get(page_num, [])
            for table in page_tables:
                table_section, table_sec_label = section_classifier_service.classify_text(
                    table.markdown, active_section=active_section
                )
                table.section = table_section
                table_tokens = self.count_tokens(table.markdown)

                table_chunk = ParsedChunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index}",
                    document_id=document_id,
                    session_id=session_id,
                    user_id=user_id,
                    chunk_index=chunk_index,
                    text=f"[Table from Page {page_num} - {table_sec_label}]\n{table.markdown}",
                    source_text=table.markdown,
                    content_type="table",
                    section=table_section,
                    page_number=page_num,
                    page_start=page_num,
                    page_end=page_num,
                    source_pages=[page_num],
                    table_id=table.table_id,
                    token_estimate=table_tokens,
                    character_count=len(table.markdown),
                    extraction_method=table.extraction_method,
                    metadata={
                        "table_id": table.table_id,
                        "row_count": len(table.rows),
                        "headers": table.headers,
                        "document_filename": filename,
                        "section_type": table_sec_label,
                    },
                )
                chunks.append(table_chunk)
                chunk_index += 1

                                                                    
            if page_text:
                page_text_chunks = self._chunk_page_text(
                    text=page_text,
                    page_num=page_num,
                    document_id=document_id,
                    session_id=session_id,
                    user_id=user_id,
                    start_chunk_index=chunk_index,
                    active_section=active_section,
                    active_section_label=active_section_label,
                    target_token_size=target_token_size,
                    overlap_tokens=overlap_tokens,
                    filename=filename,
                )
                chunks.extend(page_text_chunks)
                chunk_index += len(page_text_chunks)

        logger.info(
            "Chunked document %s: generated %d total chunks (target %d tokens)",
            document_id,
            len(chunks),
            target_token_size,
        )
        return chunks

    def _chunk_page_text(
        self,
        text: str,
        page_num: int,
        document_id: str,
        session_id: str,
        user_id: str,
        start_chunk_index: int,
        active_section: str,
        active_section_label: str,
        target_token_size: int,
        overlap_tokens: int,
        filename: str,
    ) -> List[ParsedChunk]:
        """
        Break a single page's text into paragraphs and pack into target token bounds (300-500 tokens).
        """
        page_chunks: List[ParsedChunk] = []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
                          
            paragraphs = [text]

        current_paras: List[str] = []
        current_tokens = 0
        current_section = active_section
        current_section_label = active_section_label
        local_index = start_chunk_index

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

                                                          
            detected_sec = section_classifier_service.detect_section_header(para)
            if detected_sec and current_paras:
                                                                       
                chunk_text = "\n\n".join(current_paras).strip()
                if chunk_text:
                    c_tokens = self.count_tokens(chunk_text)
                    page_chunks.append(
                        self._create_parsed_chunk(
                            chunk_id=f"{document_id}_chunk_{local_index}",
                            document_id=document_id,
                            session_id=session_id,
                            user_id=user_id,
                            chunk_index=local_index,
                            text=chunk_text,
                            section=current_section,
                            section_label=current_section_label,
                            page_num=page_num,
                            token_count=c_tokens,
                            filename=filename,
                        )
                    )
                    local_index += 1
                current_paras = []
                current_tokens = 0
                current_section, current_section_label = detected_sec

                                                                          
            if current_tokens + para_tokens > DEFAULT_MAX_TOKENS and current_paras:
                chunk_text = "\n\n".join(current_paras).strip()
                c_tokens = self.count_tokens(chunk_text)
                page_chunks.append(
                    self._create_parsed_chunk(
                        chunk_id=f"{document_id}_chunk_{local_index}",
                        document_id=document_id,
                        session_id=session_id,
                        user_id=user_id,
                        chunk_index=local_index,
                        text=chunk_text,
                        section=current_section,
                        section_label=current_section_label,
                        page_num=page_num,
                        token_count=c_tokens,
                        filename=filename,
                    )
                )
                local_index += 1

                                                                           
                if current_paras and self.count_tokens(current_paras[-1]) <= overlap_tokens * 1.5:
                    current_paras = [current_paras[-1], para]
                    current_tokens = self.count_tokens(current_paras[-1]) + para_tokens
                else:
                    current_paras = [para]
                    current_tokens = para_tokens
            else:
                current_paras.append(para)
                current_tokens += para_tokens

                                        
        if current_paras:
            chunk_text = "\n\n".join(current_paras).strip()
            if chunk_text:
                c_tokens = self.count_tokens(chunk_text)
                page_chunks.append(
                    self._create_parsed_chunk(
                        chunk_id=f"{document_id}_chunk_{local_index}",
                        document_id=document_id,
                        session_id=session_id,
                        user_id=user_id,
                        chunk_index=local_index,
                        text=chunk_text,
                        section=current_section,
                        section_label=current_section_label,
                        page_num=page_num,
                        token_count=c_tokens,
                        filename=filename,
                    )
                )

        return page_chunks

    @staticmethod
    def _create_parsed_chunk(
        chunk_id: str,
        document_id: str,
        session_id: str,
        user_id: str,
        chunk_index: int,
        text: str,
        section: str,
        section_label: str,
        page_num: int,
        token_count: int,
        filename: str,
    ) -> ParsedChunk:
        return ParsedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            session_id=session_id,
            user_id=user_id,
            chunk_index=chunk_index,
            text=text,
            source_text=text,
            content_type="text",
            section=section,
            page_number=page_num,
            page_start=page_num,
            page_end=page_num,
            source_pages=[page_num],
            table_id=None,
            token_estimate=token_count,
            character_count=len(text),
            extraction_method="native",
            metadata={
                "document_filename": filename,
                "section_type": section_label,
            },
        )


chunking_service = ChunkingService()
