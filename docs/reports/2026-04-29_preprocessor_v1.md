# S01/v1 preprocessor report

Date: 2026-04-29

## Scope

- S01 schema contract expanded for `DocumentBlock` and `NormalizedDocument`.
- S01 artifacts are treated as a new contract. Old S01 artifacts are not migrated and are overwritten only with `normalize --force`.
- S00 corpus in `/mnt/storage/datasets/itg_datasets` is the current reference: `16 181` ingested documents.
- S02/tagging is still blocked until full S01 normalize, quality report generation, and architect review of the sample index.

## Changes

- Added block fields: `heading_path`, `dom_path`, `text_hash`.
- Added normalized document metrics: raw/plain/markdown lengths, text preservation ratio, block type counts, table/heading/warning flags.
- Added structural table extraction metadata: `rows`, `row_count`, `column_count`, `has_header`, `markdown`.
- Added list metadata: `list_type`, `list_level`.
- Improved HTML traversal for text in `div`, `section`, `span`, `font`, `strong`, `em` and other containers without explicit `<p>`.
- Improved Markdown rendering for headings, lists, tables, blockquotes and raw text.
- Added `block_metrics.parquet` and by-doc `<doc_id>.structure.json`.
- Added `normalize --limit`, `normalize --doc-id`, `normalize --force`.
- Added `audit-normalized --sample-size`.
- Strengthened `validate-stage S01` for required columns, partial marker, full coverage, block count consistency, no-blocks on nonempty docs, and optional quality report readability.
- Updated JSON schemas in `schemas/`, including `normalized_document.schema.json`.

## Verification

- `make test` equivalent: `.venv/bin/python -m pytest` passed with `37` tests.
- `make lint` equivalent: `.venv/bin/ruff check .` passed.
- Real corpus smoke:
  - `python -m itg_kb.cli init-dirs` passed.
  - `python -m itg_kb.cli ingest --input /mnt/storage/datasets/itg_datasets/00_raw/documents.csv` passed: `16 181` rows, `16 181` ok, `0` empty, `0` failed.
  - `python -m itg_kb.cli validate-stage S00` passed.
  - `python -m itg_kb.cli normalize --limit 200 --force` passed as partial: `200` processed from `16 181`, `13 249` blocks, `0` failed.
  - `python -m itg_kb.cli validate-stage S01` passed for explicit partial S01.
  - `python -m itg_kb.cli audit-normalized --sample-size 50` passed: `50` sample documents, `150` sample files.
  - Final `python -m itg_kb.cli validate-stage S01` passed with no warnings after audit report creation.

## Smoke Results

- Current real S01 artifacts are partial, not full: `200 / 16 181` documents.
- `S01_quality_report.md`: `/mnt/storage/datasets/itg_datasets/90_reports/S01_quality_report.md`.
- `S01_sample_index.md`: `/mnt/storage/datasets/itg_datasets/90_reports/S01_sample_index.md`.
- In the 200-document smoke: `documents_without_blocks=0`, `low_text_preservation_documents=[]`, `errors_sample=[]`.
- The first 200 real documents produced only `paragraph` blocks; no table or heading blocks were present in this limited slice.

## Remaining Risks

- Full `normalize --force` over all `16 181` documents was not run in this pass.
- S02/tagging must not start from the current partial S01 artifacts.
- Architect should review `S01_sample_index.md` and samples before accepting the block structure.
- Full readiness requires:
  - `python -m itg_kb.cli normalize --force`
  - `python -m itg_kb.cli validate-stage S01`
  - `python -m itg_kb.cli audit-normalized --sample-size 100`
  - review of quality report and samples.
