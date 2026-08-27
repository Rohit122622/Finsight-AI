"""
Structured Financial Table Extraction Service for FinSentry AI.

Extracts tables from PDF pages using pdfplumber, preserving row labels,
column headers, and exact numeric cell values as first-class structured data.
"""

import io
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from agents.document.schemas import ExtractedTable, ExtractedTableRow

logger = logging.getLogger(__name__)


class TableExtractionService:
    """
    Service for identifying, extracting, and normalizing structured tables in financial PDFs.
    """

    def extract_tables_from_pdf_bytes(
        self, content: bytes, max_pages: Optional[int] = None
    ) -> List[ExtractedTable]:
        """
        Extract all structured tables from PDF byte stream.

        Returns a list of ExtractedTable instances with full metadata.
        """
        tables: List[ExtractedTable] = []
        if not content:
            return tables

        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_to_process = pdf.pages if max_pages is None else pdf.pages[:max_pages]

                for page_idx, page in enumerate(pages_to_process, start=1):
                    extracted_raw = page.extract_tables()
                    if not extracted_raw:
                        continue

                    for t_idx, raw_table in enumerate(extracted_raw):
                        parsed_table = self._normalize_table(
                            raw_table=raw_table,
                            page_number=page_idx,
                            table_sequence=t_idx + 1,
                        )
                        if parsed_table:
                            tables.append(parsed_table)

            logger.info("Extracted %d structured tables across PDF pages", len(tables))
            return tables

        except Exception as exc:
            logger.warning("Structured table extraction encountered error: %s", exc)
            return tables

    def _normalize_table(
        self,
        raw_table: List[List[Optional[str]]],
        page_number: int,
        table_sequence: int,
    ) -> Optional[ExtractedTable]:
        """
        Convert raw 2D grid from pdfplumber into clean ExtractedTable schema.
        """
        if not raw_table or len(raw_table) < 2:
            return None

                     
        cleaned_grid: List[List[str]] = []
        for row in raw_table:
            cleaned_row = [(c.replace("\n", " ").strip() if c else "") for c in row]
                                        
            if any(cleaned_row):
                cleaned_grid.append(cleaned_row)

        if len(cleaned_grid) < 2:
            return None

                                                                                    
        headers_raw = cleaned_grid[0]
        data_rows = cleaned_grid[1:]

                             
        headers: List[str] = []
        for idx, h in enumerate(headers_raw):
            clean_h = h.strip() if h else f"Column_{idx+1}"
            headers.append(clean_h)

        structured_rows: List[ExtractedTableRow] = []
        for row in data_rows:
            if not any(row):
                continue

            label = row[0].strip() if len(row) > 0 else ""
                                                                     
            if not label and len(row) > 1:
                for cell in row:
                    if cell.strip():
                        label = cell.strip()
                        break

            values = [c.strip() for c in row[1:]] if len(row) > 1 else []
            structured_rows.append(ExtractedTableRow(label=label or "Item", values=values))

        if not structured_rows:
            return None

                                             
        markdown_lines = []
        markdown_lines.append("| " + " | ".join(headers) + " |")
        markdown_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in data_rows:
                                                      
            padded_row = list(row) + [""] * max(0, len(headers) - len(row))
            markdown_lines.append("| " + " | ".join(padded_row[:len(headers)]) + " |")

        table_markdown = "\n".join(markdown_lines)
        table_id = f"table_p{page_number}_{table_sequence}_{uuid.uuid4().hex[:6]}"

        return ExtractedTable(
            table_id=table_id,
            page_number=page_number,
            headers=headers,
            rows=structured_rows,
            markdown=table_markdown,
            extraction_method="pdfplumber",
            metadata={"row_count": len(structured_rows), "column_count": len(headers)},
        )

    def split_large_table_if_needed(
        self,
        table: ExtractedTable,
        max_rows_per_split: int = 15,
    ) -> List[ExtractedTable]:
        """
        Table boundary splitting rule:
        If a table is larger than max chunk size, split at logical row groups,
        preserving headers and table identity in every resulting chunk.
        """
        if len(table.rows) <= max_rows_per_split:
            return [table]

        split_tables: List[ExtractedTable] = []
        total_rows = len(table.rows)

        for start_idx in range(0, total_rows, max_rows_per_split):
            end_idx = min(start_idx + max_rows_per_split, total_rows)
            chunk_rows = table.rows[start_idx:end_idx]

                                                     
            md_lines = ["| " + " | ".join(table.headers) + " |", "| " + " | ".join(["---"] * len(table.headers)) + " |"]
            for r in chunk_rows:
                row_cells = [r.label] + r.values
                padded = row_cells + [""] * max(0, len(table.headers) - len(row_cells))
                md_lines.append("| " + " | ".join(padded[:len(table.headers)]) + " |")

            split_table = ExtractedTable(
                table_id=f"{table.table_id}_part{len(split_tables)+1}",
                page_number=table.page_number,
                section=table.section,
                headers=table.headers,
                rows=chunk_rows,
                markdown="\n".join(md_lines),
                extraction_method=table.extraction_method,
                metadata={
                    "parent_table_id": table.table_id,
                    "split_index": len(split_tables) + 1,
                    "total_rows": total_rows,
                },
            )
            split_tables.append(split_table)

        return split_tables


table_extraction_service = TableExtractionService()
