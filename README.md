# Tri9T AI internship assignment: CT-200 traceability backend

FastAPI backend for CT-200 PDF ingestion, hierarchical browsing, immutable document versions, pinned selections, QA generation, provenance, and stale-impact queries. The supplied CT-200 manuals are source materials and are intentionally excluded from Git. To reproduce ingestion after cloning, copy the assignment's v1 and v2 PDFs to `data/ct200_manual_v1.pdf` and `data/ct200_manual_v2.pdf`; alternatively upload them through `/ingest-upload`. The parser and table extractor have been exercised on both manuals; observed findings and limitations are in `docs/APPROACH.md`.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env  # create it only if you do not already have one
# Set LLM_API_KEY in .env to enable live Groq generation.
uvicorn --env-file .env app.main:app --reload
```

OCR also requires the Tesseract executable. On macOS install it with `brew install tesseract`; on Debian/Ubuntu use `sudo apt-get install tesseract-ocr`. The Python OCR libraries are installed from `requirements.txt`.

If you do not create a `.env` file, start with `uvicorn app.main:app --reload` and configure any needed environment variables in your shell. OCR of image-only pages also needs the Tesseract executable.

SQLite defaults to `./tri9t.db`; generated output defaults to `./generated_outputs.json`. Set `DATABASE_URL`, `OUTPUT_STORE`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` as needed. The default LLM endpoint is Groq's OpenAI-compatible chat completions endpoint and the default model is `openai/gpt-oss-120b` (JSON mode supported). The local `.env` is ignored by Git and must never be committed. Optional `LLM_FALLBACK_API_KEY`, `LLM_FALLBACK_BASE_URL`, and `LLM_FALLBACK_MODEL` configure one fallback-provider call after the primary retry. Generation needs at least one provider key; ingestion and browsing do not. Generated outputs are stored in an atomic JSON file per assignment allowance.

## API workflow

Open `/docs` for the interactive API. Example commands:

```sh
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"document_key":"ct-200","version":"v1","path":"data/ct200_manual_v1.pdf"}'
curl 'localhost:8000/documents/ct-200/nodes?version=v1'
curl 'localhost:8000/documents/ct-200/tables?version=v1'
```

Select node IDs returned for v1, create a pinned selection, then generate cases. The node tree includes extracted tables; `GET /documents/{key}/tables?version=...` returns cells, source page, heading context, bounding box, and hash. Table rows are included in node hashes and the text sent for QA generation.

```sh
curl -X POST localhost:8000/selections -H 'Content-Type: application/json' \
  -d '{"name":"Pressure safety","document_key":"ct-200","version":"v1","node_ids":[1]}'
curl -X POST localhost:8000/generations -H 'Content-Type: application/json' -d '{"selection_id":1}'
```

Retrieve the persisted snapshot with `GET /selections/{selection_id}`. It includes the pinned version, exact selected subtree text, and its hash; the snapshot remains v1 after v2 is ingested.

Re-ingest v2 without overwriting v1, then inspect `/nodes/{id}/diff`, or retrieve prior generations via `/generations?selection_id=1` or `/generations?node_id=1`. Responses include staleness and impacted source nodes relative to the latest ingested version. Selections retain exact text snapshots and version/node pairs.

```sh
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"document_key":"ct-200","version":"v2","path":"data/ct200_manual_v2.pdf"}'
curl localhost:8000/generations?selection_id=1
```

Image-only pages fail explicitly unless `ocr:true`; OCR uses PyMuPDF, Pillow, pytesseract, and the Tesseract executable. This prevents silently empty extraction.

## Tests

```sh
pytest -q
```

The suite covers duplicate headings and parents, skipped numeric levels, repeated headers and page numbers, lettered and numbered lists, out-of-order section numbering, OCR of image-only pages, vector-table extraction, semantic sibling matching, invalid citations, bounded retry/fallback, and synthetic versioned API behavior. The actual v1/v2 manuals were also ingested through the API in an isolated SQLite database; a local generation stub verified pinned source text, changed-node diff, and stale-impact retrieval. This validates ingestion and traceability, not clinical correctness or live-provider output.
