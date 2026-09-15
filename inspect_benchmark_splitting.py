from pathlib import Path

from backend.services.document_chunking import split_text
from backend.services.document_extraction import extract_text


for path in sorted(
    Path("benchmark-data").glob("*.docx")
):
    content = path.read_bytes()

    text = extract_text(
        filename=path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=content,
    )

    chunks = split_text(text)

    print("=" * 80)
    print("Document:", path.name)
    print("Characters:", len(text))
    print("Chunks:", len(chunks))

    for index, chunk in enumerate(chunks):
        print(
            f"  Chunk {index}: {len(chunk)} characters"
        )
