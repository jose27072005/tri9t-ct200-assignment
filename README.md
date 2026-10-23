# Tri9T AI internship assignment: CT-200 traceability backend

FastAPI backend for CT-200 PDF ingestion, hierarchical browsing, immutable document versions, pinned selections, QA generation, provenance, and stale-impact queries. The provided assignment PDF was available, but its referenced `AI Internship Assignment Files - CT-200` package (including `ct200_manual_v1.pdf` and `ct200_manual_v2.pdf`) was not attached or present in this workspace. No manual ingestion or v1-to-v2 results are claimed. Add both PDFs under `data/` before running the documented workflow.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional; add an LLM API key to generate tests
uvicorn --env-file .env app.main:app --reload
```

If you do not create a `.env` file, start with `uvicorn app.main:app --reload` and configure any needed environment variables in your shell.

SQLite defaults to `./tri9t.db`; generated output defaults to `./generated_outputs.json`. Set `DATABASE_URL`, `OUTPUT_STORE`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` as needed. The default LLM endpoint is Groq's OpenAI-compatible chat completions endpoint. No key is required for ingestion or browsing. Generated outputs are stored in an atomic JSON file per assignment allowance.

## API workflow

Open `/docs` for the interactive API. Example commands:

```sh
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"document_key":"ct-200","version":"v1","path":"data/ct200_manual_v1.pdf"}'
curl 'localhost:8000/documents/ct-200/nodes?version=v1'
```

Select node IDs returned for v1, create a pinned selection, then generate cases:

```sh
curl -X POST localhost:8000/selections -H 'Content-Type: application/json' \
  -d '{"name":"Pressure safety","document_key":"ct-200","version":"v1","node_ids":[1]}'
curl -X POST localhost:8000/generations -H 'Content-Type: application/json' -d '{"selection_id":1}'
```

Re-ingest v2 without overwriting v1, then inspect `/nodes/{id}/diff`, or retrieve prior generations via `/generations?selection_id=1` or `/generations?node_id=1`. Responses include staleness and impacted source nodes relative to the latest ingested version. Selections retain exact text snapshots and version/node pairs.

```sh
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"document_key":"ct-200","version":"v2","path":"data/ct200_manual_v2.pdf"}'
curl localhost:8000/generations?selection_id=1
```

Image-only pages fail explicitly unless `ocr:true`; optional OCR requires PyMuPDF, Pillow and Tesseract installed. This prevents silently empty extraction.

## Tests

```sh
pytest -q
```

Parser tests cover duplicate headings under separate parents, skipped numeric levels, repeated running headers/page numbers, and lettered lists. They test synthetic structures because the assignment PDF does not enumerate its “irregularities listed above” and the actual CT-200 data package is missing. These are not validation results on the manuals.
