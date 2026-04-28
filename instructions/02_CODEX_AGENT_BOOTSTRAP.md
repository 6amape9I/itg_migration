# Первичная инструкция для Codex-агента

## 0. Роль агента

Ты работаешь над репозиторием `itg-kb-rebuild`.

Твоя задача в первом проходе — не реализовать весь ML/LLM pipeline, а привести проект в инженерно правильное стартовое состояние: структура, CLI, схемы, ingestion CSV, HTML-aware normalization, block extraction, отчёты и тесты.

Нельзя скачивать тяжёлые модели, большие датасеты, PDF-корпуса или другие тяжёлые файлы. Пользователь сам подготовит модели и внешние артефакты позже.

## 1. Контекст проекта

Нужно построить воспроизводимый pipeline пересборки медицинской базы знаний ИТГ для STEOS.

Исходный файл:

```text
data/00_raw/documents.csv
```

В CSV полезны поля:

- `name`;
- `content`.

Поле `description` можно импортировать как metadata, но по умолчанию не использовать для анализа.

`content` может содержать HTML-подобную разметку: заголовки, выделенный текст, таблицы, списки, абзацы, иногда некорректный HTML.

## 2. Общая архитектура, которую нужно заложить

Проект должен быть stage-based data pipeline.

Стадии:

```text
S00 ingest CSV
S01 normalize documents and extract blocks
S02 primary tag candidates
S03 tag normalization
S04 per-tag evidence extraction
S05 article compilation
S06 quote generation
S07 folder hierarchy
S08 STEOS export package
S09 graph extraction
S10 QA reports
```

В первом проходе реализуются только S00 и S01. Остальные стадии создаются как каркас модулей, схем, конфигов и промптов-заглушек.

Каждый этап должен:

- читать входы с диска;
- писать выходы на диск;
- создавать report;
- не падать из-за одного плохого документа;
- иметь возможность повторного запуска.

## 3. Жёсткие ограничения

Нельзя:

- скачивать тяжёлые модели;
- скачивать большие внешние файлы;
- вызывать внешние API;
- добавлять реальные секреты;
- хардкодить абсолютные пути пользователя;
- помещать `documents.csv` или производные data-файлы в Git;
- реализовывать бизнес-логику прямо в CLI-командах;
- делать один монолитный скрипт вместо модульной структуры.

Можно:

- добавлять лёгкие Python-зависимости;
- создавать синтетические тестовые fixtures;
- создавать интерфейсы и заглушки под будущие ML/LLM-компоненты;
- создавать конфиги и промпты-заглушки.

## 4. Требуемая структура проекта

Создай следующую структуру:

```text
itg-kb-rebuild/
  README.md
  pyproject.toml
  .env.example
  .gitignore
  Makefile

  configs/
    pipeline.yaml
    paths.yaml
    models.yaml
    entity_types.yaml
    thresholds.yaml
    steos.yaml
    logging.yaml

  prompts/
    tagging/
      system.md
      document_tagging.jinja2
      tag_arbitration.jinja2
    normalization/
      synonym_cluster_review.jinja2
      canonical_tag_name.jinja2
    extraction/
      extract_tag_evidence.jinja2
    article/
      compile_article.jinja2
      editorjs_formatting.jinja2
    quotes/
      generate_questions.jinja2
      extract_quotes.jinja2
    hierarchy/
      build_folder_tree.jinja2
    graph/
      extract_entities_relations.jinja2

  schemas/
    document.schema.json
    block.schema.json
    tag_candidate.schema.json
    tag_catalog.schema.json
    topic_snippet.schema.json
    article.schema.json
    quote.schema.json
    graph.schema.json

  curation/
    README.md
    tag_aliases.yaml
    tag_blocklist.yaml
    forced_doc_tags.yaml
    forced_tag_merges.yaml
    entity_type_overrides.yaml
    folder_overrides.yaml
    graph_relation_overrides.yaml

  src/
    itg_kb/
      __init__.py
      cli.py

      core/
        ids.py
        hashing.py
        paths.py
        run_context.py
        errors.py
        logging.py

      schemas/
        documents.py
        blocks.py
        tags.py
        articles.py
        quotes.py
        graph.py
        reports.py

      io/
        csv_loader.py
        jsonl.py
        parquet.py
        duckdb.py
        file_lock.py

      preprocess/
        html_cleaner.py
        block_extractor.py
        table_extractor.py
        markdown_renderer.py
        docling_adapter.py

      tagging/
        candidate_rules.py
        russian_ner.py
        llm_tagger.py
        scoring.py
        aggregator.py

      normalization/
        embeddings.py
        clustering.py
        canonicalizer.py
        alias_resolver.py

      extraction/
        tag_document_selector.py
        evidence_extractor.py
        snippet_store.py

      article/
        compiler.py
        editorjs.py
        article_validator.py

      quotes/
        question_generator.py
        quote_extractor.py
        quote_validator.py

      hierarchy/
        folder_tree_builder.py
        placement_validator.py

      graph/
        entity_extractor.py
        relation_extractor.py
        graph_exporter.py

      llm/
        base.py
        openai_compatible.py
        vllm.py
        sglang.py
        structured_output.py
        retry.py

      orchestration/
        stages.py
        reports.py
        checkpoints.py

      review/
        sampling.py
        html_reports.py
        csv_reports.py

  scripts/
    smoke_run.py
    benchmark_llm.py
    benchmark_tagging.py
    export_for_review.py

  tests/
    unit/
    integration/
    fixtures/
      documents_sample.csv
      html_document_1.html
      html_document_2.html

  notebooks/
    README.md

  data/
    .gitkeep
    00_raw/
    01_ingested/
    02_normalized/
    03_tagging/
    04_tag_normalization/
    05_topic_corpora/
    06_articles/
    07_quotes/
    08_hierarchy/
    09_steos_export/
    10_graph/
    90_reports/
    99_cache/
    99_logs/
```

`data/` должна быть в `.gitignore`, кроме `data/.gitkeep`.

## 5. Зависимости

Настрой `pyproject.toml` для Python 3.12.

Минимальные зависимости:

```text
pydantic
typer
rich
pandas
pyarrow
duckdb
beautifulsoup4
lxml
markdownify
pyyaml
pytest
ruff
```

Не добавляй в зависимости тяжёлые ML/LLM-библиотеки в первом проходе. Для `vLLM`, `SGLang`, `Docling`, embedding-моделей и медицинских NER-моделей создай интерфейсы/заглушки/конфиги, но не устанавливай и не скачивай их.

## 6. CLI-команды

Реализуй CLI в `src/itg_kb/cli.py`.

Команды, которые должны работать:

```bash
python -m itg_kb.cli init-dirs
python -m itg_kb.cli ingest --input data/00_raw/documents.csv
python -m itg_kb.cli normalize
python -m itg_kb.cli status
python -m itg_kb.cli validate-stage S00
python -m itg_kb.cli validate-stage S01
```

CLI не должен содержать основную бизнес-логику. Он должен вызывать функции из соответствующих модулей.

## 7. S00 ingest: требования

### 7.1. Вход

```text
data/00_raw/documents.csv
```

### 7.2. Логика

Нужно:

1. прочитать CSV;
2. проверить наличие `name` и `content`;
3. импортировать `description`, если есть;
4. сохранить неизвестные дополнительные поля как metadata или не потерять их;
5. создать `doc_id`;
6. посчитать `content_hash`;
7. определить `raw_length`;
8. определить `has_html`;
9. обработать пустой `content` без падения;
10. записать результаты.

### 7.3. Правила ID

Если есть исходный ID:

```text
doc_id = doc_<hash(source_id + content_hash)>
```

Если исходного ID нет:

```text
doc_id = doc_<hash(name + content_hash)>
```

Hash должен быть стабильным между запусками.

### 7.4. Выход

```text
data/01_ingested/documents.parquet
data/01_ingested/documents.jsonl
data/01_ingested/manifest.jsonl
data/90_reports/S00_ingest_report.json
```

### 7.5. Минимальная Pydantic-схема `DocumentRecord`

```python
class DocumentRecord(BaseModel):
    doc_id: str
    source_id: str | None = None
    source_row: int
    name: str
    description: str | None = None
    raw_content: str
    content_hash: str
    raw_length: int
    has_html: bool
    ingest_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 7.6. Отчёт S00

`S00_ingest_report.json` должен содержать:

- `stage`;
- `status`;
- `started_at`;
- `finished_at`;
- `input_path`;
- `total_rows`;
- `ok_rows`;
- `empty_content_rows`;
- `failed_rows`;
- `errors_sample`;
- `outputs`.

## 8. S01 normalize: требования

### 8.1. Вход

```text
data/01_ingested/documents.parquet
```

### 8.2. Логика

Нужно:

1. прочитать документы из S00;
2. для каждого документа распарсить `raw_content` как HTML-aware текст;
3. извлечь структурные блоки;
4. сохранить plain text;
5. сохранить markdown;
6. сохранить block-level representation;
7. не потерять таблицы;
8. не потерять заголовки;
9. обработать некорректный HTML без падения;
10. записать результаты.

### 8.3. Типы блоков

Минимальные типы:

```text
heading
paragraph
list_item
table
blockquote
unknown
```

Для `heading` нужно сохранять `level`, если возможно.

Для `table` нужно сохранять:

- текстовое представление;
- HTML-фрагмент, если доступен;
- желательно rows/cells в metadata.

### 8.4. Выход

```text
data/02_normalized/documents_normalized.parquet
data/02_normalized/blocks.parquet
data/02_normalized/by_doc/<doc_id>.normalized.json
data/02_normalized/by_doc/<doc_id>.md
data/90_reports/S01_normalization_report.json
```

### 8.5. Минимальная Pydantic-схема `DocumentBlock`

```python
class DocumentBlock(BaseModel):
    block_id: str
    doc_id: str
    order: int
    type: str
    text: str
    html: str | None = None
    level: int | None = None
    parent_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 8.6. Отчёт S01

`S01_normalization_report.json` должен содержать:

- `stage`;
- `status`;
- `started_at`;
- `finished_at`;
- `input_path`;
- `total_documents`;
- `ok_documents`;
- `empty_documents`;
- `failed_documents`;
- `total_blocks`;
- `blocks_by_type`;
- `errors_sample`;
- `outputs`.

## 9. Схемы, которые нужно создать в первом проходе

Создай Pydantic-модели:

```text
DocumentRecord
DocumentBlock
StageReport
TagCandidate
TagRecord
TagDocLink
TopicSnippet
ArticleArtifact
QuoteRecord
GraphNode
GraphEdge
```

Для будущих моделей можно сделать минимальные поля и TODO-комментарии, но они должны импортироваться без ошибок.

Также создай экспорт JSON Schema в папку `schemas/`. Можно сделать команду или функцию, которая генерирует `.schema.json` из Pydantic-моделей.

## 10. Конфиги

### 10.1. `configs/paths.yaml`

Должен содержать базовые пути:

```yaml
data_dir: data
raw_dir: data/00_raw
ingested_dir: data/01_ingested
normalized_dir: data/02_normalized
reports_dir: data/90_reports
cache_dir: data/99_cache
logs_dir: data/99_logs
```

### 10.2. `configs/entity_types.yaml`

Добавь минимальный набор типов:

```yaml
entity_types:
  disease:
    ru: "Заболевание / диагноз / состояние"
  symptom:
    ru: "Симптом / признак / жалоба"
  drug:
    ru: "Лекарство / действующее вещество / торговое название"
  treatment:
    ru: "Лечение / терапевтический подход"
  procedure:
    ru: "Процедура / манипуляция / инструкция"
  diagnostic_test:
    ru: "Диагностика / анализ / исследование"
  medical_device:
    ru: "Медицинское изделие / расходник"
  anatomy:
    ru: "Орган / анатомическая структура"
  contraindication:
    ru: "Противопоказание / ограничение"
  adverse_effect:
    ru: "Побочный эффект / осложнение"
  document_type:
    ru: "Документ / форма / справка / регламент"
  organization_process:
    ru: "Организационный процесс"
  lifestyle:
    ru: "Питание / образ жизни / профилактика"
  other_core_topic:
    ru: "Другая ключевая тема"
```

### 10.3. `configs/models.yaml`

Не указывай реальные локальные пути к моделям пользователя. Сделай шаблон:

```yaml
llm_profiles:
  local_default:
    backend: openai_compatible
    base_url: http://localhost:8000/v1
    model: PLACEHOLDER_LOCAL_MODEL
    temperature: 0.0
  external_default:
    backend: openai_compatible
    base_url: PLACEHOLDER_EXTERNAL_BASE_URL
    model: PLACEHOLDER_EXTERNAL_MODEL
    temperature: 0.0
```

## 11. LLM-заглушки

Создай интерфейсы:

```text
src/itg_kb/llm/base.py
src/itg_kb/llm/openai_compatible.py
src/itg_kb/llm/vllm.py
src/itg_kb/llm/sglang.py
src/itg_kb/llm/structured_output.py
src/itg_kb/llm/retry.py
```

Требование: эти модули должны импортироваться, но не должны требовать установленного `vllm`, `sglang` или тяжёлых ML-библиотек.

Если нужен OpenAI-compatible клиент, сделай его ленивым и опциональным. При отсутствии зависимости он должен выдавать понятную ошибку только при реальном вызове, а не при импорте проекта.

## 12. Тестовые fixtures

Создай `tests/fixtures/documents_sample.csv` с 3–5 синтетическими документами.

Минимальные случаи:

1. HTML-документ с `<h1>`, `<h2>`, `<p>`.
2. Документ с таблицей `<table>`.
3. Обычный plain text без HTML.
4. Документ с пустым `content`.
5. Документ с кривым HTML.

Не использовать реальные медицинские данные пользователя в tests.

## 13. Тесты

Добавь тесты:

```text
tests/unit/test_hashing.py
tests/unit/test_html_cleaner.py
tests/unit/test_block_extractor.py
tests/integration/test_ingest.py
tests/integration/test_normalize.py
```

Проверить:

- ingest создаёт ожидаемые файлы;
- ingest стабильно создаёт одинаковый `doc_id` на одинаковом входе;
- пустой `content` не ломает pipeline;
- normalize создаёт блоки;
- HTML heading сохраняется как `heading`;
- HTML table сохраняется как `table`;
- кривой HTML не роняет весь pipeline.

## 14. Makefile

Создай команды:

```makefile
setup:
	uv sync

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

init-dirs:
	python -m itg_kb.cli init-dirs

smoke:
	python scripts/smoke_run.py
```

Если используешь не `uv`, адаптируй `setup`, но README должен объяснять выбранный способ.

## 15. README.md

README должен объяснять:

1. цель проекта;
2. структуру папок;
3. как установить зависимости;
4. как положить `documents.csv`;
5. как запустить `init-dirs`;
6. как запустить `ingest`;
7. как запустить `normalize`;
8. где смотреть результаты;
9. где смотреть отчёты;
10. почему `data/` не коммитится;
11. что ML/LLM-часть пока является каркасом.

## 16. Definition of Done

Первый проход считается готовым, если:

```text
make test проходит
make lint проходит или явно описаны допустимые предупреждения
python -m itg_kb.cli init-dirs создаёт нужные папки
python -m itg_kb.cli ingest --input tests/fixtures/documents_sample.csv работает
python -m itg_kb.cli normalize работает после ingest
python -m itg_kb.cli status показывает наличие/отсутствие артефактов стадий
python -m itg_kb.cli validate-stage S00 работает
python -m itg_kb.cli validate-stage S01 работает
README описывает запуск первых двух стадий
в репозитории нет больших данных и секретов
```

## 17. Что не нужно делать в первом проходе

Не реализовывать сейчас:

- полноценное выделение медицинских тегов;
- скачивание и запуск медицинских NER-моделей;
- скачивание и запуск LLM;
- построение embedding-кластеров;
- компиляцию статей;
- генерацию цитат;
- загрузку в STEOS;
- построение графа знаний.

Для этих частей нужно создать только структуру, схемы, конфиги и интерфейсы, чтобы следующий этап разработки был безопасным и понятным.

## 18. Приоритет качества кода

Важнее всего:

1. воспроизводимость;
2. явные контракты файлов;
3. устойчивость к плохим документам;
4. сохранение структуры HTML/таблиц;
5. отсутствие тяжёлых зависимостей на старте;
6. удобство последующего ревью.
