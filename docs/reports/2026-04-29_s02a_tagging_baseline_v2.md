# S02A tagging baseline v2 work report

## Instruction reread checkpoints

- 2026-04-29 phase 0: reread `instructions/07_CODEX_AGENT_S02A_TAGGING_BASELINE_V2.md` before implementation. Key constraints captured: deterministic S02A only, process `normalization_status=ok`, write full topic unit/candidate/evidence/doc summary artifacts, write skipped no-blocks report, preserve all candidates above threshold without a persisted top-k cap, and use top-k only for review/report display.
- 2026-04-29 phase 1: reread the instruction before schema/path work. Focus sections: outputs, Pydantic schemas, role enum, and validation quality gates.
- 2026-04-29 phase 2: reread the instruction before config/constants work. Focus sections: role values, facet/generic rules, required tagging config files, and warning thresholds.
- 2026-04-29 phase 3: reread the instruction before topic-unit implementation. Focus sections: topic unit definition, required unit types, heading/table/list/paragraph-window construction, and block ID preservation.
- 2026-04-29 phase 4: used the same reread covering sections 10.2-10.6 before parser/classifier/candidate/scoring/role work. Focus sections: facet/entity split patterns, deterministic YAML classification, candidate sources, score components, and role rules.
- 2026-04-29 phase 5: reread writer, CLI, review outputs, quality gates, tests, and DoD sections before stage writer and orchestration work.
- 2026-04-29 phase 6: final verification reread before smoke/full runs. Focus sections: required commands, full S02A run, report outputs, and final feedback checklist.

## Work log

- Initial repository inspection found existing S00/S01 orchestration, schema export, CLI, and placeholder tagging modules.
- Runtime S01 artifacts are configured under `/mnt/storage/datasets/itg_datasets` via `configs/paths.yaml`.
- Existing S01 artifact sample confirms `documents_normalized.parquet`, `blocks.parquet`, and `block_metrics.parquet` are present; list/dict parquet columns are JSON strings and need decoding in S02A readers.
- Exported JSON Schemas into `schemas/*.schema.json`.
- Full test suite and lint pass after implementation.

## Commands

- `sed -n '1,260p' instructions/07_CODEX_AGENT_S02A_TAGGING_BASELINE_V2.md`
- `sed -n '261,620p' instructions/07_CODEX_AGENT_S02A_TAGGING_BASELINE_V2.md`
- `sed -n '621,1100p' instructions/07_CODEX_AGENT_S02A_TAGGING_BASELINE_V2.md`
- `.venv/bin/python - <<'PY' ... inspect S01 parquet shapes and columns ... PY`
- `.venv/bin/python -m compileall src/itg_kb/tagging src/itg_kb/orchestration/stages.py src/itg_kb/cli.py src/itg_kb/schemas`
- `.venv/bin/python - <<'PY' ... write_json_schemas('schemas') ... PY`
- `.venv/bin/pytest tests/unit/test_topic_units.py tests/unit/test_entity_facet_parser.py tests/unit/test_entity_classifier.py tests/unit/test_candidate_roles.py tests/integration/test_s02a_tag_candidates.py`
- `make test`
- `make lint`
- `.venv/bin/python -m itg_kb.cli tag-candidates --stage S02A --limit 100 --force`
- `.venv/bin/python -m itg_kb.cli validate-stage S02A`
- `.venv/bin/python -m itg_kb.cli audit-tag-candidates --sample-size 50`
- `.venv/bin/python -m itg_kb.cli tag-candidates --stage S02A --force`
- `.venv/bin/python -m itg_kb.cli validate-stage S02A`
- `.venv/bin/python -m itg_kb.cli audit-tag-candidates --sample-size 300`

## Implementation notes

- Started schema/path phase: add S02A Pydantic models, S02A output path contracts, and schema export entries.
- Started config/constants phase: add required `configs/tagging/*.yaml` and shared deterministic enums/constants.
- Started topic-unit phase: implement S01 block decoding and structured topic unit construction.
- Implemented deterministic entity/facet parsing, YAML-pattern entity classification, candidate generation with evidence, score components, confidence buckets, and role assignment.
- Started stage writer/orchestration phase: write all S02A artifacts, reports, audit CSVs, and validation hooks.
- Started test phase: add required S02A unit and integration tests for topic units, parser, classifier, roles, no top-k cap, CLI-stage behavior, validation, and audit outputs.

## Files and modules added or updated

- Added configs: `configs/tagging/facet_patterns.yaml`, `generic_blocklist.yaml`, `entity_patterns.yaml`, `drug_forms.yaml`, `scoring.yaml`, `review.yaml`.
- Added tagging modules: `topic_units.py`, `entity_facet_parser.py`, `entity_classifier.py`, `candidate_generator.py`, `role_classifier.py`, `stage_s02a.py`, `constants.py`, `text.py`.
- Updated schemas: `TopicUnit`, expanded `TagCandidate`, `CandidateEvidence`, `DocTopicSummary`; exported `topic_unit.schema.json`, `candidate_evidence.schema.json`, `doc_topic_summary.schema.json`, and updated `tag_candidate.schema.json`.
- Updated orchestration/CLI/path wiring: `ProjectPaths.tagging_dir`, `s02a_outputs`, `tag-candidates`, `audit-tag-candidates`, and `validate-stage S02A`.
- Added tests: `tests/unit/test_topic_units.py`, `test_entity_facet_parser.py`, `test_entity_classifier.py`, `test_candidate_roles.py`, and `tests/integration/test_s02a_tag_candidates.py`.

## Verification

- `make test`: passed, 56 tests.
- `make lint`: passed.
- Smoke S02A limit 100: passed; `processed_documents=99`, `skipped_no_blocks=1`, `total_topic_units=1564`, `total_candidates=2393`, `documents_with_many_candidates=5`.
- Smoke validate S02A: passed; only expected partial-output warning.
- Smoke audit sample 50: passed; `sample_size_actual=50`, `distribution_rows=99`.
- Full S02A: passed; `processed_documents=16161`, `skipped_no_blocks=20`, `total_topic_units=231220`, `total_candidates=505837`, `documents_with_many_candidates=2030`, `documents_without_candidates=0`.
- Full validate S02A: passed with no errors or warnings.
- Full audit sample 300: passed; `sample_size_actual=300`, `distribution_rows=16161`.
- Full by-doc JSON count: `16161`.
- Final outputs are under `/mnt/storage/datasets/itg_datasets/03_tagging` and `/mnt/storage/datasets/itg_datasets/90_reports`.

## Limitations and S02B recommendations

- Deterministic entity classification is intentionally broad and pattern-based; many candidates remain `unknown` or `needs_review`.
- Russian morphology is handled only by selected regex/keyword variants, not a full lemmatizer.
- Generic/facet separation is conservative; S02B should review high-frequency rejected/generic phrases and tune facets.
- S02B recommendations: add curated alias/entity dictionaries from review output, improve morphology-aware matching, introduce per-entity-type precision audits, tune thresholds by role, and use S02A evidence to prepare normalization/merge candidates for S03 without collapsing surfaces in S02A.
