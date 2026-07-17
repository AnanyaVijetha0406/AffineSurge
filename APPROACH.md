# Approach Document — CT-200 QA Traceability

## Goal

Turn the CT-200 PDF manuals into a browsable, versioned section tree; let users pin selections; generate QA test-case ideas with an LLM; and surface whether those generations are still valid after document re-ingestion.

## OCR / parsing approach

The provided PDFs are **text-extractable**, not image-only scans. I used **PyMuPDF (`fitz`)** to extract page text in reading order, then reconstructed hierarchy with regex heading detection (`1`, `1.1`, `2.1.1.1`, …).

Why not full OCR (Tesseract/cloud)? OCR adds latency and noise on clean digital PDFs. The assignment update allows “PDF parsing and/or OCR.” For this corpus, structure recovery from text is the right tool. If a page were image-only, the same pipeline would swap in OCR text before the heading pass — that adapter is the intended extension point, not a generic multi-format parser.

### Hierarchy strategy

1. Stream lines in **document order** (never sort by section number).
2. Detect numbered headings → create nodes with `level = dots + 1`.
3. Maintain a stack: pop while `stack.level >= new.level`, then attach as child.
4. Body text accumulates until the next heading.
5. Tables under `2.1` / `4.2` become `node_type=table` children.
6. Numbered classification bullets under `3.3` become `node_type=list`.
7. `content_hash = sha256(section|heading|body)`.
8. `node_key = sec:{number}` for sections (stable across versions); tables/lists use `parent/type:sort`.

### Structural irregularities handled

| Irregularity | Handling |
|--------------|----------|
| `3.4` appears before `3.3` | Document order / `sort_order`; no numeric sort |
| Deep `2.1.1.1` without `2.1.1` | Level from numbering; parent = nearest shallower ancestor (`2.1`) |
| Duplicate “Error Codes” (`4.2` vs `7.1`) | Distinct `node_key`s via section numbers; unit-tested |
| Tables | Captured as child table nodes with raw row text |
| Cross-refs / lists | Left in body or list nodes; not resolved as graph edges |

### What failed initially / how I fixed it

1. **Sorting children by section number** merged the 3.3/3.4 story incorrectly → switched to stable `sort_order` from parse sequence; added a unit test.
2. **Title-only keys** collided on “Error Codes” → switched to `sec:{n}`.
3. **Table rows swallowed as body** under 4.2 → added table-header heuristics + child table nodes.
4. Validation: unit tests + manual comparison of v1/v2 hashes for battery, inflate step, E3 timing, new `5.3` / `E6`.

## Version matching

Match nodes across versions by **`node_key`** (section-number based).

- Same key + same hash → unchanged  
- Same key + different hash → modified (`changed_from_previous=true`)  
- Key only in new version → new  
- Key only in old → not cloned into new tree (detectable via change API / staleness)

**Where it breaks:** renumbered sections (e.g. `5.2` → `5.3` with same title) look like delete+add; title renames with same number look like in-place edits (usually desired). Fuzzy title matching would help renumbers but risks false merges on duplicate titles — rejected for this corpus.

## Data model

**SQLite (SQLAlchemy)**

- `documents`, `document_versions`, `nodes` (tree + hashes)
- `selections`, `selection_items` — **version-pinned snapshots** of heading/body/hash so old selections survive re-ingest

**MongoDB**

- `generations` — LLM outputs linked to `selection_id`, `source_hashes`, and per-node snapshots

## LLM design

- Provider: Gemini (`gemini-3-flash-preview`)
- Prompt asks for 3–5 QA ideas as **strict JSON**
- `response_mime_type=application/json`
- Validate with Pydantic; on failure, retry up to 3× with repair hint
- **On persistent failure: HTTP 502**, do not store fake cases

**Duplicate submission policy:** return the existing successful generation for that selection unless `force=true`. Rationale: generations are expensive and should be reproducible for demo/review; force covers intentional regen.

## Staleness

At retrieval time, compare each generation’s `source_hashes` to the **latest** version’s nodes with the same `node_key`. Any mismatch or missing key → stale.

**Limit (honest):** a one-word wording change is treated the same as a changed mmHg threshold. No semantic severity model. No auto-regeneration (out of scope).

## Generation storage

MongoDB Atlas is preferred. If the Atlas connection fails (common first-time cause: Network Access IP allowlist / TLS), the app falls back to `data/generations.json`. This is explicitly allowed by the assignment (“or a well-justified JSON store”) and keeps generation + staleness queryable without blocking the rest of the pipeline.

## LLM fallback

When Gemini returns quota errors (`429`), the service tries alternate Flash models, then a rule-based generator marked `llm_status=fallback_rule_based`. Structured-output validation still applies when the LLM responds; fallback is only for provider unavailability — not for silently accepting malformed JSON as success.

## Decision log

1. **Most likely silent wrong result:** hierarchy mis-parenting (content present but under the wrong section), which still “looks fine” in a flat dump. **Catch it** with order/parent unit tests (3.4 before 3.3; 2.1.1.1 under 2.1; distinct Error Codes keys) and spot-check search hits against known manual pages.

2. **Simplicity over correctness:** hash-only staleness with no semantic diff severity; table extraction is heuristic, not a full grid model. **What breaks first in production:** tables with wrapped cells / multi-line error descriptions may fragment, and reviewers may be flooded with “stale” flags on trivial edits.

3. **Unhandled input:** scanned/image-only PDF pages (no text layer). **Behavior:** parser returns few/no headings and ingestion stores a sparse tree rather than crashing; operators should see anomalously low `node_count`. Encrypted PDFs raise from PyMuPDF and fail the ingest call.

## What I’d do with more time

- Add optional OCR fallback page-by-page when `page.get_text()` is empty  
- Semantic/clinical-aware staleness (threshold tokens)  
- Coverage matrix: requirements ↔ generated tests  
- Stronger table reconstruction (cell geometry via PyMuPDF blocks)
