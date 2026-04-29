# itg-kb-rebuild

Проект пересобирает базу знаний ИТГ для STEOS: из исходной CSV-выгрузки документов формируются воспроизводимые промежуточные артефакты, чистые структурированные документы, блоки, отчеты и каркас будущих стадий тегов, статей, цитат, и графа знаний.

На первом проходе реализованы только две стадии:

- `S00 ingest CSV` - импорт `documents.csv`, стабильные `doc_id`, хэши, Parquet/JSONL и отчет.
- `S01 normalize documents and extract blocks` - HTML-aware нормализация, Markdown, plain text, блоки, таблицы и отчет.

ML/LLM-часть пока является каркасом: интерфейсы и конфиги есть, тяжелые модели, внешние API и пользовательские секреты не подключаются.

## Установка

Требуется Python 3.12.

Если установлен `uv`:

```bash
uv sync --extra dev
```

Если `uv` недоступен:

```bash
python -m pip install -e ".[dev]"
```

Makefile сначала пробует `uv`, затем использует `pip`:

```bash
make setup
```

## Структура

- `configs/` - пути, стадии, модели-заглушки, thresholds, STEOS и logging.
- `prompts/` - шаблоны будущих LLM-стадий.
- `curation/` - воспроизводимые ручные правки поверх машинных результатов.
- `src/itg_kb/` - пакет pipeline, схемы, IO, preprocessing, orchestration и CLI.
- `schemas/` - JSON Schema для основных Pydantic-моделей.
- `tests/` - synthetic fixtures и тесты S00/S01.
- `docs/` - отчёты исполнителя, чек-листы и обратная связь для архитектурного ревью.

## Данные

Данные и generated artifacts больше не хранятся в папке `data/` внутри проекта. Stage-директории лежат по глобальному storage path:

```text
/mnt/storage/datasets/itg_datasets
```

Положите исходную выгрузку в:

```text
/mnt/storage/datasets/itg_datasets/00_raw/documents.csv
```

Полезные поля: `name`, `content`, опционально `description`. Дополнительные поля сохраняются в `metadata`.

Ожидаемый объём выгрузки - около 16 000 документов. Для крупных документов CSV loader увеличивает лимит размера одного поля до 256 MiB, чтобы длинный `content` не ломал ingest на стандартном лимите Python `csv`.

Папки `00_raw/`, `01_ingested/`, `02_normalized/`, `03_tagging/`, `04_tag_normalization/`, `05_topic_corpora/`, `06_articles/`, `07_quotes/`, `08_hierarchy/`, `09_steos_export/`, `10_graph/`, `90_reports/`, `99_cache/`, `99_logs/` игнорируются Git, потому что содержат пользовательские данные и производные артефакты.

## Запуск

Создать директории:

```bash
python -m itg_kb.cli init-dirs
```

Импортировать CSV:

```bash
python -m itg_kb.cli ingest
```

Или явно:

```bash
python -m itg_kb.cli ingest --input /mnt/storage/datasets/itg_datasets/00_raw/documents.csv
```

Нормализовать документы после ingest:

```bash
`python -m itg_kb.cli normalize`
```

Проверить состояние:

```bash
python -m itg_kb.cli status
python -m itg_kb.cli validate-stage S00
python -m itg_kb.cli validate-stage S01
```

Если виртуальное окружение не активировано и команды `python` нет в `PATH`, используйте `.venv/bin/python` вместо `python`.

Smoke-run на синтетическом fixture:

```bash
python scripts/smoke_run.py
```

Smoke-run использует временную директорию и после успешного запуска не оставляет stage artifacts в рабочем дереве.

## Результаты

S00 пишет:

- `/mnt/storage/datasets/itg_datasets/01_ingested/documents.parquet`
- `/mnt/storage/datasets/itg_datasets/01_ingested/documents.jsonl`
- `/mnt/storage/datasets/itg_datasets/01_ingested/manifest.jsonl`
- `/mnt/storage/datasets/itg_datasets/90_reports/S00_ingest_report.json`

S01 пишет:

- `/mnt/storage/datasets/itg_datasets/02_normalized/documents_normalized.parquet`
- `/mnt/storage/datasets/itg_datasets/02_normalized/blocks.parquet`
- `/mnt/storage/datasets/itg_datasets/02_normalized/by_doc/<doc_id>.normalized.json`
- `/mnt/storage/datasets/itg_datasets/02_normalized/by_doc/<doc_id>.md`
- `/mnt/storage/datasets/itg_datasets/90_reports/S01_normalization_report.json`

## Исполнительская отчётность

После каждого набора правок исполнитель пишет отчёт в `docs/reports/`: что изменено, какой чек-лист выполнен, какие проверки прошли, какие риски или вопросы остаются для архитектора.

## Проверки

```bash
make test
make lint
```
