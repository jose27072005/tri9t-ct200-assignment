# Tri9T AI internship assignment: engineering approach

## Scope and evidence

The assignment PDF specifies a CT-200 document ingestion and QA traceability backend. The two supplied source manuals were processed locally as v1 (`ct200_manual.pdf`) and v2 (`ct200_manual_v2.pdf`). The files live in `data/` for the local workflow and are ignored by Git so they are not copied into the public project repository. The assignment refers to irregularities listed above but does not enumerate a separate irregularity list; this document records the irregularities observed directly in the manuals.

Validation performed against the actual manuals: both versions ingest successfully; extraction yields 28 nodes for v1 and 29 for v2; the numbered clinical result thresholds remain in the body of section 3.3; a v1 selection snapshots 300 cycles and a 15% low-battery threshold; v2 reports 250 cycles and 10%; the same logical node is matched, flagged changed, and prior generated output becomes stale. Generation in this workflow used a local deterministic stub because no live LLM key is configured. The 13 automated tests passed locally, including OCR of a synthetic image-only page. No claim is made that a live model was called or that generated cases are clinically validated.

## Architecture and data model

FastAPI exposes ingestion, hierarchical browsing, search, diffs, selections, generation, and impact retrieval. Pydantic validates request and generated-case schemas. SQLAlchemy with SQLite stores document versions, parsed nodes, parent-child links, source hashes, logical node IDs, change flags, and version-pinned selections. Each selection item stores its exact subtree text and hash snapshot. Generated cases use an atomic-write JSON store, which the assignment permits, with model/provider, timestamp, retry count, source node and logical IDs, hashes, and exact source text. This avoids requiring a MongoDB service for local setup; a multi-process deployment should use MongoDB or a transactional database for generation records.

## Extraction and tree reconstruction

Text extraction uses pypdf. For PDFs with a text layer, PyMuPDF font metadata supplies a second signal: numeric or list-like lines are recognized as headings only when they appear in bold spans. This prevents the manual’s numbered result rows (`1. Normal` through `5. Hypertensive Crisis`) from being promoted to section headings. If font metadata cannot be read, extraction falls back to the parser’s structural heuristics. Image-only pages fail explicitly unless OCR is requested; OCR uses PyMuPDF, Pillow, pytesseract, and a local Tesseract executable. Empty OCR output and OCR failures surface as ingestion errors.

Heading reconstruction recognizes numeric sections and preserves skipped depth (including `2.1.1.1`), plus uppercase and lettered/Roman subheadings. It retains source reading order even where numbering is out of sequence: section 3.4 Auto Shutoff precedes 3.3 Result Display and Classification in the supplied manuals. Page numbers and short repeated CardioTrack running headers are discarded. Ligatures and nonbreaking hyphens in extracted text are retained, so equivalent words can differ at the code-point level. Table text is retained in node bodies but row/column geometry is not reconstructed; this remains a known limitation.

The parser regression tests explicitly cover skipped numeric depth, out-of-order section labels, and the numbered clinical threshold list. Additional tests cover repeated page headers/page numbers, duplicate headings under different parents, and OCR. Actual manual parsing is separately validated through the ingestion API. This is a CT-200-focused heuristic, not a general PDF layout engine; columns, tables, captions, and image semantics still require visual review.

## Version matching and change flags

Matching first uses exact normalized sibling paths. If the path changes, a parent-scoped similarity score combines normalized heading similarity (65%) with body similarity (35%). A candidate must score at least 0.58 and beat the next candidate by 0.04; ambiguous candidates are treated as new rather than silently linked. Restricting matching to a previously matched parent preserves context and avoids merging duplicate titles from unrelated sections. Matched nodes reuse logical IDs; differences in heading or body hashes are flagged as content changes. New nodes receive deterministic IDs based on their path. This method is deterministic and explainable but remains a heuristic: a major rewrite or sibling reorder may produce a delete/add or a questionable match. Review low-confidence changes before relying on them.

The supplied v1/v2 match for Battery Life Under Typical Use is stable. Its body changes from approximately 300 cycles and a 15% low-battery threshold to 250 cycles and 10%. The v2 manual also adds Bluetooth error code E6 and a Data Export section, and changes the cuff inflation step and E3 recovery timing. The API flags changed/new content and diffs matched-node text; it does not interpret clinical significance.

## LLM prompt, validation, retry, and provenance

The provider uses an OpenAI-compatible chat-completions endpoint configured by environment variables. It requests 3–5 concrete cases grounded only in selected text, source IDs, and no invented thresholds. Pydantic validates the returned object, case count, fields, risk values, and citations against the selected subtree. A malformed or invalid primary response receives one bounded correction retry, then one optional fallback-provider call. With no provider configured, generation returns an error and stores no partial output. The API workflow tests use a stub to exercise this path without claiming live model behavior.

Every successful output is an immutable JSON record with selection/version, source snapshots and hashes, source node IDs/logical IDs, model/provider, attempt count, cases, and timestamp. Repeated generation requests create separate records so model changes and provenance remain auditable.

## Staleness and impact

A selection snapshots the chosen node and all descendants. On generation retrieval, every source logical ID is resolved against the latest document version and its full subtree hash is recomputed. A changed or missing subtree marks output stale and reports impacted nodes. The snapshot remains pinned to v1 after v2 ingestion. This is intentionally conservative: any text change can mark a case stale, even punctuation. It does not trigger automatic regeneration; reviewers inspect the diff and rerun QA generation when appropriate.

## Failure modes and tradeoffs

- Malformed, encrypted, text-empty, or image-only (without OCR) PDFs fail ingestion rather than creating an empty version.
- Duplicate version labels return a conflict; each manual version remains immutable.
- LLM timeout, absent credentials, malformed JSON, invalid schema, or out-of-selection citations produce a bounded retry/fallback and then an error without persisting unvalidated output.
- Atomic JSON replacement protects a single local writer; concurrent processes can race. MongoDB or a transactional store is the next step for concurrent deployment.
- SQLite and the local JSON store need backups, access controls, and deployment hardening before handling real regulated content. This assignment is not a validated medical-device process.
- The manuals’ tables are represented as extracted text, not structured rows. Verify table-dependent requirements against page images before generating tests that depend on table relationships.

## Required decision log

1. **Most likely silent wrong result:** a numbered clinical list item being treated as a section heading. The manuals exposed this directly. Font-weight evidence is now used for real PDFs, and a regression test asserts the five result thresholds remain within section body text. Rendering and reviewing every page remains appropriate for production sign-off.
2. **Simplicity versus matching accuracy:** parent-scoped fuzzy matching is more resilient than path-only matching while remaining inspectable. The threshold and margin avoid forced ambiguous matches, but substantial rewrites may still lose identity; review those as new/deleted nodes.
3. **Unhandled input:** table geometry and image meaning are not reconstructed. OCR supplies text for image-only pages but may misread columns or diagrams. Keep the source PDF available and verify such content visually.

## What I would improve next

Add visual page-to-tree review tooling and OCR confidence reporting, layout-aware table extraction, a human review queue for ambiguous semantic matches, and concurrency-safe generation storage. Add a real-provider evaluation dataset with medically reviewed expected results before assessing case quality.
