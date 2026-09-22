from pathlib import Path

from backend.services.document_chunking import split_text
from backend.services.document_extraction import extract_document


for path in sorted(
    Path("benchmark-data").glob("*.docx")
):
    content = path.read_bytes()

    extracted_document = extract_document(
        filename=path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=content,
    )

    chunks = split_text(extracted_document.text)

    print("=" * 80)
    print("Document:", path.name)
    print("Characters:", extracted_document.character_count)
    print("Chunks:", len(chunks))

    for index, chunk in enumerate(chunks):
        print(
            f"  Chunk {index}: {len(chunk)} characters"
        )
