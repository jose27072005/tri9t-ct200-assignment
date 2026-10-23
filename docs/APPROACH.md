# Tri9T AI assignment approach

## Scope and evidence

The assignment PDF supplied here describes a CT-200 PDF parser, versioned tree, traceable QA generation, and stale impact retrieval. Its text says to handle “every irregularity listed above,” but the PDF contains no actual irregularity list. It names `ct200_manual_v1.pdf` and `ct200_manual_v2.pdf` in an external data package. That package was not present among the attachments or workspace files. The implementation therefore accepts the manuals as runtime inputs and does not claim manual-specific extraction or v1/v2 validation.

## Architecture and data model

FastAPI exposes ingestion, browse/search/diff, selection, generation, and retrieval endpoints. SQLAlchemy with SQLite stores document versions, parsed nodes, parent-child links, source hashes, logical node IDs, and version-pinned selection rows. Each selection item stores the node/version reference and an exact subtree text and hash snapshot, which remains retrievable by selection ID after newer versions arrive. Generated cases live in an atomic-write JSON store, allowed by the assignment, with provider/model, timestamps, retry count, source node/logical IDs, hashes, and source text. This avoids a MongoDB server dependency while retaining queryable provenance; a deployment with multiple writers should move this document to MongoDB or a transactional store.

## Extraction and tree reconstruction

The initial parser uses pypdf text extraction because the source may contain an embedded text layer. It recognizes numeric headings (including skipped levels), uppercase headings, and lettered/Roman subheads, and uses a heading-level stack to assign parent-child links. It normalizes line breaks and skips isolated page numbers and repeated short `CardioTrack` running headers. PDF pages with no embedded text fail explicitly; callers may opt into OCR, requiring PyMuPDF, Pillow, and local Tesseract. OCR errors are surfaced rather than returning an empty tree. Tables and figures are not reliably reconstructed; their extracted text remains in node bodies, and this is a known limitation pending inspection of the actual manuals.

The tests use synthetic examples for duplicate headings under different parents, skipped levels, repeated running headers/page numbers, lettered procedure items, OCR of image-only pages, invalid LLM citations, provider retry/fallback, and API-level v1 → pinned selection → generation → v2 → stale retrieval. Duplicate headings remain distinct nodes because node identity derives from a path including sibling ordinal and normalized heading, not heading text alone. A repeated same-title sibling is likewise disambiguated by ordinal.

This is an initial CT-200 heuristic, not a general PDF parser. It can mistake uppercase warnings for headings and cannot infer headings from typography, columns, table geometry, or image layout. Before finalizing parser rules, inspect all pages and compare extracted tree/body coverage with rendered pages; measure missing text and hierarchy errors. That required real-manual inspection remains outstanding because those PDFs were unavailable.

## Version matching and change flags

The parser's path is built from each node's sibling ordinal and normalized heading. Re-ingestion compares that path to the immediately preceding version: a match reuses the prior logical ID; a matching path with a different heading/body hash is flagged as changed, and a missing path is new. This is deterministic and handles repeated headings, but inserting/reordering siblings can shift ordinals and cause false new nodes; a rename also breaks path matching. A next iteration should use parent-scoped assignment (heading similarity plus body similarity) with confidence thresholds, and report ambiguous matches for review instead of silently linking them. Hashes are SHA-256 over heading and body with exact text, so even formatting whitespace can mark change. An API workflow regression test checks that a changed body preserves its logical node and returns a meaningful diff.

## LLM prompt, validation, and retry

The provider uses an OpenAI-compatible chat-completions endpoint, configurable through environment variables. It requests JSON with 3–5 executable cases and source node IDs, forbids unsupported thresholds, and requests explicit uncertainty when source text is insufficient. Pydantic validates case count, fields, minimum lengths, risk enum, and citations restricted to the submitted node IDs. There is one bounded correction retry with the primary provider, then one optional fallback-provider call. If all attempts fail or no provider is configured, the API returns an error and stores no partial generation. Repeating a generation request intentionally creates a new immutable record rather than deduplicating: the provider output can differ, and separate timestamps/model provenance preserve that fact. Each record retains exact source text and hashes independently of later versioning.

## Staleness and impact

Selections snapshot the selected node's entire descendant text, so selecting a section includes its requirements as well as its own body. At retrieval time, each generation source is resolved by logical ID against the latest version and the current subtree hash is recomputed. A missing logical node or a different subtree hash marks that source impacted; API results expose stale status, latest version, and affected source list. This is conservative: even a wording-only change triggers stale status, and exact text hashes do not distinguish a clinically meaningful threshold change from punctuation. No automatic regeneration occurs. Reviewers should inspect the node diff and re-approve generated cases.

## Failure modes and operations

- Invalid, encrypted, malformed, image-only (without OCR), or text-empty PDFs return an ingestion error; they never create a successful version with a silently empty tree.
- Duplicate document/version labels return conflict; use a new version label.
- LLM timeout, missing keys for both providers, malformed JSON, schema violation, or out-of-selection citation yields a bounded primary retry and optional single fallback call, then an HTTP error without persisting a generation.
- JSON file replacement is atomic for one local process; concurrent multi-process writers can race. Use MongoDB or a lock/transaction strategy for deployment.
- The SQLite and JSON defaults are local-development storage and need backups and access controls before real regulated use. This fictional exercise is not a validated medical-device process.

## Required decision log

1. **Most likely silent wrong result:** heuristic heading classification can assign a visually prominent paragraph or warning as a heading while still producing valid JSON. Catch it by rendering every manual page and comparing section coverage/parentage against an extracted tree review, with explicit low-confidence/ambiguous headings in a production parser.
2. **Simplicity over correctness:** path-plus-ordinal matching is simpler than fuzzy semantic matching and avoids silently matching identical headings across parents, but insertions and reordering can look like delete/add and lose continuity. A production matcher should score parent-local candidates and stop for review below a confidence threshold.
3. **Unhandled input:** multi-column/table/image content without a text layer is not structurally understood. Image-only pages fail unless optional OCR is enabled; even OCR output is plain text and tables/figures may be incomplete, so the result must be manually checked against page images.

## What I'd improve with another day

Obtain the missing package, inspect every page of v1 and v2 visually, list the actual irregularities, and add corresponding regression fixtures before claiming document fidelity. Then add layout-aware extraction for tables/captions, confidence-scored heading detection, semantic sibling matching, concurrency-safe output storage, and an integration script that ingests both supplied manuals and demonstrates a real changed requirement and stale generation.
