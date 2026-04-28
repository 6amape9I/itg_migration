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
- `data/` - локальные входы и generated artifacts.

## Данные

Положите исходную выгрузку в:

```text
data/00_raw/documents.csv
```

Полезные поля: `name`, `content`, опционально `description`. Дополнительные поля сохраняются в `metadata`.

`data/` не коммитится, кроме `data/.gitkeep`: в этой папке лежат пользовательские данные и производные артефакты pipeline.

## Запуск

Создать директории:

```bash
python -m itg_kb.cli init-dirs
```

Импортировать CSV:

```bash
python -m itg_kb.cli ingest --input data/00_raw/documents.csv
```

Нормализовать документы после ingest:

```bash
python -m itg_kb.cli normalize
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

## Результаты

S00 пишет:

- `data/01_ingested/documents.parquet`
- `data/01_ingested/documents.jsonl`
- `data/01_ingested/manifest.jsonl`
- `data/90_reports/S00_ingest_report.json`

S01 пишет:

- `data/02_normalized/documents_normalized.parquet`
- `data/02_normalized/blocks.parquet`
- `data/02_normalized/by_doc/<doc_id>.normalized.json`
- `data/02_normalized/by_doc/<doc_id>.md`
- `data/90_reports/S01_normalization_report.json`

## Проверки

```bash
make test
make lint
```
