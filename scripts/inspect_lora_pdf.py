from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.evaluation.dataset import (
    BENCHMARK_DATA_DIR,
    build_corpus_chunks,
    ground_truth_chunk_ids,
    load_cases,
)
from backend.services.document_extraction import extract_pdf_document


def main() -> None:
    pdf_path = BENCHMARK_DATA_DIR / "LORA.pdf"
    if not pdf_path.is_file():
        raise SystemExit(f"Required benchmark PDF missing: {pdf_path}")

    extracted = extract_pdf_document(pdf_path.read_bytes())
    print("PDF:", pdf_path.name)
    print("PDF metadata:", extracted.metadata)
    print("Physical pages:", extracted.page_count)
    print("Image-only pages:", extracted.image_only_pages)
    print("OCR recommended:", extracted.recommends_ocr)

    for page in extracted.pages[:3]:
        print(f"\\n--- EXTRACTED PAGE {page.page_number} ---")
        print(page.text[:3500])

    chunks = build_corpus_chunks()
    cases = [case for case in load_cases() if case.document == "LORA.pdf"]
    missing = []
    print("\\n--- LORA GROUND-TRUTH MATCHES ---")
    for case in cases:
        matched = ground_truth_chunk_ids(chunks, case)
        matches = [
            (chunk.id, chunk.page_start, chunk.page_end)
            for chunk in chunks
            if chunk.id in matched
        ]
        print(case.question, "=>", matches)
        if not matched:
            missing.append(case.question)

    print("Missing LoRA anchors:", missing)


if __name__ == "__main__":
    main()
