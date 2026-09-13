# Retrieval Baseline

Document:
Elder_Emergency_Alert_System_Report.docx

Current chunking:
- RecursiveCharacterTextSplitter
- chunk_size = 3000
- chunk_overlap = 400

Corpus:
- 1 document
- 2 chunks

Metrics:
- Recall@1 = 1.0
- Recall@2 = 1.0
- MRR = 0.80

Observation:
The signal-flow section crosses the chunk boundary.
Chunk overlap preserves repeated context, but the logical
section is split between chunks.
