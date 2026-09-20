"""Benchmark the exact batching function used by DocumentAgent ingestion."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.document.document_agent import DocumentAgent
from services.chunking_service import chunking_service
from services.embedding_service import embedding_service
from services.table_extraction_service import table_extraction_service

FIXTURES = (
    ("Apple", Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "apple_2025_annual_report.pdf"),
    ("BBBY", Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bbby_distress_10k.pdf"),
)


def _production_chunks(name: str, pdf_path: Path):
    """Use DocumentAgent's native extraction and production chunker."""
    data = pdf_path.read_bytes()
    agent = DocumentAgent()
    _, _, page_segments = agent._extract_pdf_text_native(data)
    tables = table_extraction_service.extract_tables_from_pdf_bytes(data)
    return chunking_service.chunk_document_content(
        document_id=f"benchmark-{name.lower()}", session_id="benchmark", user_id="benchmark",
        page_segments=page_segments, extracted_tables=tables, target_token_size=400,
        overlap_tokens=50, filename=pdf_path.name,
    )


def run_benchmark() -> None:
    print("FinSentry production-ingestion embedding benchmark")
    for name, path in FIXTURES:
        chunks = _production_chunks(name, path)
        texts = [chunk.text for chunk in chunks]
        load_before = embedding_service.model_load_count
        started = time.perf_counter()
        vectors = embedding_service.generate_embeddings_batch(texts)
        elapsed = time.perf_counter() - started
        valid = len(vectors) == len(texts) and all(embedding_service.validate_vector(v) for v in vectors)
        print({
            "workload": name,
            "source": str(path),
            "device": embedding_service.device,
            "model": embedding_service.model_name,
            "batch_size": 64 if embedding_service.device.startswith("cuda") else 32,
            "chunk_count": len(texts),
            "model_load_ms": round(embedding_service.model_load_ms, 1),
            "model_loads_this_run": embedding_service.model_load_count - load_before,
            "model_reused": embedding_service.model_reused,
            "embedding_elapsed_s": round(elapsed, 3),
            "chunks_per_second": round(len(texts) / elapsed, 3) if elapsed else 0.0,
            "vectors_valid": valid,
        })


if __name__ == "__main__":
    run_benchmark()
