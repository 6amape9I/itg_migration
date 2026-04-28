# Глобальная инструкция по проекту `itg-kb-rebuild`

## 0. Контекст и цель

Проект предназначен для пересборки базы знаний ИТГ внутри STEOS: из исходной выгрузки документов нужно получить чистые тематические статьи, корректные цитаты, план папок и материал для построения графа знаний.

Исходная выгрузка на старте: `data/00_raw/documents.csv`.

Полезные поля исходной выгрузки:

- `name` — название документа;
- `content` — основной контент документа, часто с HTML-подобной разметкой;
- `description` — импортируется как метаданные, но по умолчанию не участвует в анализе, потому что в текущей выгрузке не содержит полезной информации.

Ожидаемый объём: около 16 000 документов.

Ключевое ограничение: проект должен быть воспроизводимым и перезапускаемым. Нельзя строить процесс как один длинный одноразовый скрипт, который при сбое заставляет начинать всё заново.

## 1. Основной архитектурный принцип

Проект строится как stage-based data pipeline.

Каждый этап:

1. читает входные артефакты с диска;
2. валидирует входные данные;
3. пишет выходные артефакты на диск;
4. пишет отчёт этапа;
5. сохраняет версию конфигурации, промпта и модели, если использовались ML/LLM-компоненты;
6. может быть перезапущен без порчи результатов других этапов.

Главная единица проекта — не вызов модели, а артефакт. Всё, что нужно последующим этапам, должно быть сохранено в стабильном формате.

## 2. Базовый стек

### 2.1. Основной язык и CLI

- Python 3.12.
- CLI: `typer`.
- Форматирование вывода CLI: `rich`.
- Тесты: `pytest`.
- Линтинг: `ruff`.
- Управление зависимостями: предпочтительно `uv`, допустимо `poetry`.

### 2.2. Данные и локальная аналитика

- Табличные промежуточные данные: `parquet`.
- Потоковые записи и логи артефактов: `jsonl`.
- Одиночные документы, отчёты, планы: `json`.
- Человекочитаемые версии статей и отчётов: `md`.
- Локальные запросы и аналитика: `duckdb`.

### 2.3. Валидация и схемы

- Все ключевые структуры данных описываются через Pydantic-модели.
- Для внешних LLM-ответов генерируются JSON Schema из Pydantic-схем.
- Любой LLM/ML-результат должен валидироваться до записи в финальные артефакты этапа.

### 2.4. Парсинг и нормализация документов

На старте `content` приходит как текст/HTML-подобная разметка, поэтому основной путь:

- `beautifulsoup4` + `lxml` для HTML-aware parsing;
- `markdownify` или аналог для человекочитаемого Markdown;
- собственный block extractor для заголовков, абзацев, списков и таблиц.

Позже можно добавить адаптер под Docling для PDF/DOCX/HTML/Markdown/images, но в первичной реализации тяжёлые конвертеры и модели не скачиваются автоматически.

### 2.5. LLM-инференс

LLM-слой должен быть абстрагирован от конкретного сервера или API.

Основная целевая идея:

- локальный inference server через OpenAI-compatible API;
- основной кандидат на локальный serving: `vLLM`;
- альтернативный backend для экспериментов: `SGLang`;
- внешний API должен подключаться через тот же интерфейс, если позже будет принято решение использовать облачный inference.

На этапе инициализации проекта тяжёлые модели не скачиваются. Репозиторий должен иметь только интерфейсы, конфиги и заглушки.

## 3. Рекомендуемая структура проекта

```text
itg-kb-rebuild/
  README.md
  pyproject.toml
  uv.lock
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
      documents.csv
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

Папка `data/` должна быть исключена из Git, кроме `.gitkeep`.

## 4. Правила идентификаторов

### 4.1. Документы

`doc_id` должен быть стабильным и не зависеть от порядка запуска pipeline.

Если в CSV есть исходный ID из базы:

```text
doc_id = doc_<hash(source_id + content_hash)>
```

Если исходного ID нет:

```text
doc_id = doc_<hash(name + content_hash)>
```

`content_hash` считается по исходному `content` после минимальной технической нормализации строк, но до смысловой очистки HTML. Это нужно, чтобы понимать, изменился ли документ в источнике.

### 4.2. Блоки

```text
block_id = blk_<hash(doc_id + order + block_text)>
```

Блок должен иметь:

- `doc_id`;
- `block_id`;
- `order`;
- `type`;
- `text`;
- `html`, если доступен;
- `parent_path`;
- `char_start` и `char_end`, если возможно.

### 4.3. Теги

До нормализации используется `candidate_id`.

После нормализации создаётся стабильный `tag_id`. Он не должен меняться при переименовании canonical name.

Финальные файлы статей:

```text
<slug_canonical_name>__<tag_id>.editorjs.json
<slug_canonical_name>__<tag_id>.md
<slug_canonical_name>__<tag_id>.metadata.json
```

## 5. Стадии pipeline

## S00. Ingest исходного CSV

### Вход

```text
data/00_raw/documents.csv
```

### Задача

Импортировать CSV, создать стабильные ID, посчитать хэши, сохранить данные в удобные форматы для дальнейшей обработки.

### Выход

```text
data/01_ingested/documents.parquet
data/01_ingested/documents.jsonl
data/01_ingested/manifest.jsonl
data/90_reports/S00_ingest_report.json
```

### Минимальная запись документа

```json
{
  "doc_id": "doc_...",
  "source_id": null,
  "source_row": 123,
  "name": "...",
  "description": "",
  "raw_content": "...",
  "content_hash": "...",
  "raw_length": 12034,
  "has_html": true,
  "ingest_status": "ok"
}
```

### Критерии приёмки

- Все строки CSV обработаны или явно отражены в отчёте ошибок.
- Пустой `content` не ломает pipeline.
- Битая строка CSV не должна ронять весь этап.
- Созданы Parquet, JSONL и отчёт.

## S01. Нормализация и разбор документа на блоки

### Вход

```text
data/01_ingested/documents.parquet
```

### Задача

Преобразовать `content` в чистое структурированное представление, сохранив важную разметку: заголовки, абзацы, списки, таблицы, выделенные блоки.

### Выход

```text
data/02_normalized/documents_normalized.parquet
data/02_normalized/blocks.parquet
data/02_normalized/by_doc/<doc_id>.normalized.json
data/02_normalized/by_doc/<doc_id>.md
data/90_reports/S01_normalization_report.json
```

### Пример `normalized.json`

```json
{
  "doc_id": "doc_...",
  "title": "Название из name",
  "content_hash": "...",
  "plain_text": "...",
  "markdown": "...",
  "blocks": [
    {
      "block_id": "blk_...",
      "doc_id": "doc_...",
      "order": 1,
      "type": "heading",
      "level": 2,
      "text": "Гастрит",
      "html": "<h2>Гастрит</h2>",
      "parent_path": ["root", "section_1"],
      "char_start": 0,
      "char_end": 7
    }
  ]
}
```

### Критерии приёмки

- Каждый непустой документ имеет хотя бы один блок.
- Таблицы не теряются.
- Заголовки сохраняются отдельно от обычных абзацев.
- Документы с кривым HTML не роняют весь этап.

## S02. Первичное выделение кандидатов тегов

### Вход

```text
data/02_normalized/documents_normalized.parquet
data/02_normalized/blocks.parquet
```

### Задача

Получить кандидаты тегов, а не финальные теги. Каждый кандидат должен иметь evidence: откуда он взялся и почему считается важным.

### Источники кандидатов

1. `name` документа.
2. Заголовки `h1/h2/h3`.
3. Первые строки таблиц.
4. Частотные медицинские сущности.
5. Правила для паттернов: `симптомы`, `лечение`, `инструкция`, `противопоказания`, `дозировка`, `показания`, `диагностика`.
6. Лёгкие русскоязычные NLP/NER-компоненты.
7. LLM только для арбитража сложных случаев.

### Выход

```text
data/03_tagging/tag_candidates.parquet
data/03_tagging/doc_tag_candidates.jsonl
data/03_tagging/by_doc/<doc_id>.tag_candidates.json
data/90_reports/S02_tagging_report.json
```

### Формат кандидата

```json
{
  "candidate_id": "cand_...",
  "doc_id": "doc_...",
  "surface": "гастрит",
  "normalized_surface": "гастрит",
  "entity_type": "disease",
  "sources": ["title", "heading", "medical_ner", "llm"],
  "evidence_block_ids": ["blk_..."],
  "evidence_texts": ["..."],
  "score": 0.91,
  "score_components": {
    "title": 0.30,
    "heading": 0.20,
    "frequency": 0.10,
    "ner": 0.15,
    "llm": 0.16
  }
}
```

### Критерии приёмки

- Кандидат без evidence запрещён.
- LLM-ответы валидируются схемой.
- Документы с ошибкой LLM получают статус retry/fallback, а не ломают весь этап.

## S03. Нормализация тегов и схлопывание синонимов

### Вход

```text
data/03_tagging/tag_candidates.parquet
```

### Задача

Превратить поверхностные формулировки в каталог самостоятельных тегов.

Пример: `болезнь альцгеймера`, `альцгеймер`, `деменция альцгеймеровского типа` могут попасть в один cluster, но финальное объединение должно быть осторожным.

### Выход

```text
data/04_tag_normalization/tag_catalog.parquet
data/04_tag_normalization/tag_aliases.parquet
data/04_tag_normalization/tag_doc_links.parquet
data/04_tag_normalization/clusters_for_review.csv
data/04_tag_normalization/by_tag/<tag_id>.json
data/90_reports/S03_tag_normalization_report.json
```

### Формат записи тега

```json
{
  "tag_id": "tag_...",
  "canonical_name": "Гастрит",
  "entity_type": "disease",
  "aliases": ["гастрит", "острый гастрит"],
  "status": "auto_accepted",
  "doc_count": 18,
  "confidence": 0.88,
  "created_from_candidates": ["cand_...", "cand_..."]
}
```

### Критерии приёмки

- Все объединения сохраняются.
- Нельзя удалять кандидатов бесследно.
- Спорные кластеры уходят в `clusters_for_review.csv`.
- Ручные правила из `curation/` имеют приоритет над автоматикой.

## S04. Извлечение сырья по каждому тегу

### Вход

```text
data/04_tag_normalization/tag_catalog.parquet
data/04_tag_normalization/tag_doc_links.parquet
data/02_normalized/blocks.parquet
```

### Задача

Для каждого финального тега собрать все связанные документы и извлечь релевантные фрагменты. Извлечение идёт документ за документом.

### Выход

```text
data/05_topic_corpora/<tag_id>/snippets.jsonl
data/05_topic_corpora/<tag_id>/source_docs.json
data/90_reports/S04_extraction_report.json
```

### Формат snippet

```json
{
  "tag_id": "tag_...",
  "doc_id": "doc_...",
  "block_id": "blk_...",
  "text": "...",
  "relevance": 0.94,
  "extraction_method": "llm",
  "quote_candidate": true
}
```

### Критерии приёмки

- Каждый snippet связан с исходным документом и блоком.
- Сырьё не должно быть пересказом без ссылки на источник.
- Нерелевантный мусор не должен попадать в corpus тега.

## S05. Компиляция итоговой статьи

### Вход

```text
data/05_topic_corpora/<tag_id>/snippets.jsonl
```

### Задача

Создать одну чистую статью по каждому тегу. Статья должна быть структурной, без дублей, без мусора и без самостоятельных домыслов модели.

### Выход

```text
data/06_articles/<tag_id>/<slug>__<tag_id>.editorjs.json
data/06_articles/<tag_id>/<slug>__<tag_id>.md
data/06_articles/<tag_id>/<slug>__<tag_id>.metadata.json
data/90_reports/S05_articles_report.json
```

### Критерии приёмки

- Article JSON соответствует Editor.js-like структуре.
- Markdown-версия создаётся для ревью.
- Metadata содержит список source snippets.
- Статья не должна содержать утверждений без источника.

## S06. Генерация вопросов и цитат

### Вход

```text
data/06_articles/<tag_id>/...
data/05_topic_corpora/<tag_id>/snippets.jsonl
data/02_normalized/blocks.parquet
```

### Задача

Создать JSON с вопросами и точными цитатами. Ответом на вопрос должна служить буквальная цитата из исходного документа.

### Выход

```text
data/07_quotes/<tag_id>/<slug>__<tag_id>.quotes.json
data/07_quotes/<tag_id>/<slug>__<tag_id>.quotes.jsonl
data/90_reports/S06_quotes_report.json
```

### Формат цитаты

```json
{
  "quote_id": "quote_...",
  "tag_id": "tag_...",
  "doc_id": "doc_...",
  "block_id": "blk_...",
  "question": "Какие симптомы характерны для гастрита?",
  "answer_quote": "буквальная цитата из документа",
  "char_start": 120,
  "char_end": 260,
  "confidence": 0.91
}
```

### Критерии приёмки

- `answer_quote` должна существовать в исходном тексте блока.
- Цитаты вида `Введение`, `Общие сведения`, `Заключение` должны отбрасываться валидатором как мусорные.
- На каждый документ должно генерироваться достаточное покрытие вопросов, но финальные цитаты проходят deduplication.

## S07. Построение иерархии папок

### Вход

```text
data/04_tag_normalization/tag_catalog.parquet
data/06_articles/
```

### Задача

Построить оптимальную иерархию папок для STEOS и определить placement каждого итогового файла.

### Выход

```text
data/08_hierarchy/folder_tree.json
data/08_hierarchy/file_placements.parquet
data/08_hierarchy/folder_tree_for_review.md
data/90_reports/S07_hierarchy_report.json
```

### Формат placement

```json
{
  "tag_id": "tag_...",
  "article_file": "...editorjs.json",
  "folder_path": ["Медицина", "Заболевания ЖКТ", "Гастрит"],
  "confidence": 0.87,
  "reason": "..."
}
```

### Критерии приёмки

- Каждый финальный тег имеет ровно одно placement-решение.
- Ручные overrides из `curation/folder_overrides.yaml` имеют приоритет.
- План можно просмотреть до загрузки в STEOS.

## S08. Экспорт и миграция в STEOS

### Вход

```text
data/06_articles/
data/07_quotes/
data/08_hierarchy/
```

### Задача

Подготовить пакет загрузки в STEOS. Фактическая запись в STEOS должна быть отделена от подготовки import package.

### Выход

```text
data/09_steos_export/import_plan.json
data/09_steos_export/articles/
data/09_steos_export/quotes/
data/09_steos_export/folders/
data/09_steos_export/migration_report.json
```

### Критерии приёмки

- Есть dry-run режим.
- Повторный запуск не создаёт дубли.
- Сохраняется mapping локальных ID к ID в STEOS.

## S09. Извлечение сущностей и связей для графа

### Вход

```text
data/06_articles/
data/05_topic_corpora/
data/07_quotes/
```

### Задача

Построить граф знаний: сущности, типы, связи, веса и evidence.

### Выход

```text
data/10_graph/nodes.parquet
data/10_graph/edges.parquet
data/10_graph/evidence.parquet
data/10_graph/graph_export.jsonl
data/90_reports/S09_graph_report.json
```

### Формат node

```json
{
  "node_id": "node_...",
  "name": "Гастрит",
  "type": "disease",
  "aliases": ["гастрит"],
  "source_tag_id": "tag_...",
  "confidence": 0.94
}
```

### Формат edge

```json
{
  "edge_id": "edge_...",
  "source_node_id": "node_...",
  "target_node_id": "node_...",
  "relation_type": "has_symptom",
  "weight": 0.78,
  "evidence_ids": ["quote_...", "snippet_..."]
}
```

### Критерии приёмки

- Связь без evidence запрещена.
- Веса должны быть объяснимыми.
- Ручные overrides из `curation/graph_relation_overrides.yaml` имеют приоритет.

## S10. QA, отчёты и ревью

### Обязательные отчёты

```text
data/90_reports/pipeline_status.json
data/90_reports/document_coverage.md
data/90_reports/tag_quality_report.md
data/90_reports/normalization_review.csv
data/90_reports/article_quality_report.md
data/90_reports/quote_validation_report.md
data/90_reports/graph_quality_report.md
```

### Минимальные метрики

- количество документов всего;
- количество пустых документов;
- количество успешно нормализованных документов;
- количество документов без тегов;
- среднее число кандидатов на документ;
- число финальных тегов;
- число тегов с низкой уверенностью;
- число статей;
- число цитат;
- число цитат, не прошедших exact-match проверку;
- число graph nodes;
- число graph edges.

## 6. Таксономия сущностей и тегов

Файл: `configs/entity_types.yaml`.

Минимальный набор типов:

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

Важно: тег — это не любая найденная сущность. Тегом становится только сущность, вокруг которой имеет смысл собрать отдельный итоговый документ.

Примеры:

- `Гастрит` — хороший тег.
- `Медицинские перчатки` — хороший тег, если документ описывает работу с ними.
- `Желудок` — может быть сущностью графа, но не обязательно тегом.
- `Введение` — не тег.
- `Общие сведения` — не тег.

## 7. Ручные правки и curation layer

Все ручные решения хранятся отдельно от машинных результатов.

Файлы:

```text
curation/tag_aliases.yaml
curation/tag_blocklist.yaml
curation/forced_doc_tags.yaml
curation/forced_tag_merges.yaml
curation/entity_type_overrides.yaml
curation/folder_overrides.yaml
curation/graph_relation_overrides.yaml
```

Правила:

- Нельзя руками редактировать generated Parquet/JSONL как основной способ исправления.
- Любая ручная правка должна быть воспроизводимой.
- Curation-файлы имеют приоритет над автоматикой.

## 8. LLM-слой

### 8.1. Общий интерфейс

```python
class LLMClient:
    def generate_json(
        self,
        *,
        messages: list[dict],
        schema: dict,
        model_profile: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_s: int = 120,
    ) -> dict:
        ...
```

### 8.2. Адаптеры

```text
llm/openai_compatible.py
llm/vllm.py
llm/sglang.py
llm/structured_output.py
llm/retry.py
```

### 8.3. Жёсткие требования

- Для извлечения фактов `temperature = 0` или близко к нулю.
- Каждый ответ валидируется Pydantic-схемой.
- Невалидный JSON идёт в retry.
- После N retry задача получает статус `llm_failed`.
- В результатах сохраняются `prompt_hash`, `model_name`, `model_profile`, `run_id`.
- Слой LLM не должен знать бизнес-логику этапа: он только отправляет запрос и возвращает валидированный ответ.

## 9. Производительность первого этапа

Нельзя прогонять все 16 000 документов через тяжёлую LLM целиком как основной путь.

Правильный порядок S02:

```text
HTML-aware parsing
быстрые правила и заголовки
лёгкий NER / кандидатогенерация
агрегация и scoring
LLM только для арбитража сложных случаев
```

Целевой режим:

```text
80–90% документов проходят без большой LLM или с коротким LLM-запросом по сжатому представлению
10–20% документов отправляются в расширенный LLM-arbitration
0% документов теряются из-за ошибки модели
```

## 10. Критерии инженерной готовности проекта

Проект считается инженерно готовым к масштабной обработке, если:

- все стадии имеют контракты входа/выхода;
- все ключевые структуры описаны Pydantic-схемами;
- отчёты создаются после каждого этапа;
- плохой документ не роняет весь pipeline;
- `data/` не попадает в Git;
- есть smoke-тесты на маленьком наборе документов;
- есть возможность перезапустить отдельный этап;
- LLM backend можно заменить без переписывания бизнес-логики;
- все ручные правки лежат в `curation/`.

## 11. Чеклист ревью

На ревью проверяется:

- нет ли монолитных скриптов вместо stage modules;
- не попадают ли data-файлы в Git;
- валидируются ли схемы;
- создаются ли отчёты по стадиям;
- не падает ли pipeline на одном плохом документе;
- сохраняется ли HTML/table структура;
- есть ли стабильные `doc_id` и `content_hash`;
- можно ли перезапустить `ingest` и `normalize`;
- нет ли захардкоженных путей и секретов;
- есть ли тесты на пустые, битые и HTML-документы.

## 12. Технические ориентиры

Эти источники используются как ориентиры при проектировании, но агент не должен скачивать тяжёлые модели или большие файлы в первичной инициализации:

- vLLM: OpenAI-compatible server и high-throughput LLM serving — https://docs.vllm.ai/
- SGLang: structured outputs через JSON Schema/regex/EBNF — https://docs.sglang.ai/advanced_features/structured_outputs.html
- Docling: structured document conversion — https://docling-project.github.io/docling/
- DuckDB: локальная аналитика по Parquet/JSON — https://duckdb.org/
- Pydantic: JSON Schema и сериализация моделей — https://docs.pydantic.dev/
- Editor.js: block-style JSON output — https://editorjs.io/
- Prefect: потенциальная будущая оркестрация, caching/retries — https://docs.prefect.io/
