Исправить bootstrap перед переходом к S02.

Контекст:
Папка данных перенесена в /mnt/storage/datasets/itg_datasets.
Внутри неё должны быть stage-директории:
00_raw, 01_ingested, 02_normalized, 03_tagging, 04_tag_normalization,
05_topic_corpora, 06_articles, 07_quotes, 08_hierarchy, 09_steos_export,
10_graph, 90_reports, 99_cache, 99_logs.

Задачи:
1. Обновить configs/paths.yaml на /mnt/storage/datasets/itg_datasets.
2. Обновить README: все примеры путей и outputs должны указывать на /mnt/storage/datasets/itg_datasets, а не на /mnt/storage/projects/PycharmProjects/itg_migrat.
3. Убрать или не использовать storage_root, если он не нужен.
4. Доработать ProjectPaths:
   - если задан data_dir, а raw_dir/ingested_dir/etc не заданы, они должны вычисляться как data_dir / subdir;
   - absolute paths должны поддерживаться;
   - .gitkeep создаётся только для локальной repo data/, но не для external storage.
5. Усилить validate-stage:
   - S00: проверить существование и читаемость documents.parquet, documents.jsonl, manifest.jsonl, S00 report;
   - проверить обязательные колонки documents.parquet: doc_id, source_row, name, raw_content, content_hash, raw_length, has_html, ingest_status, metadata;
   - S01: проверить существование и читаемость documents_normalized.parquet, blocks.parquet, S01 report;
   - проверить обязательные колонки blocks.parquet: block_id, doc_id, order, type, text, html, level, parent_path, char_start, char_end, metadata;
   - проверить, что normalized doc_id покрывают ingested doc_id.
6. Добавить тесты на ProjectPaths с external data_dir.
7. Добавить тесты на validate-stage: успешный S00/S01 и случай битого/отсутствующего artifact.
8. Улучшить block_extractor:
   - не терять текстовые узлы вне p/h/table/li;
   - добавить fixture с HTML, где есть текст внутри div без p;
   - добавить fixture с реальным-ish кривым HTML.
9. Не скачивать модели, не вызывать API, не добавлять тяжёлые файлы.
10. После правок должны проходить:
   make test
   make lint
   python -m itg_kb.cli init-dirs
   python -m itg_kb.cli status