# 03. Требования к этапу S01/v1: предобработка и структурная нормализация документов ИТГ

## 1. Решение архитектора

Bootstrap проекта принимается как достаточный для перехода к следующей инженерной задаче. Мы не переходим сразу к S02/tagging, потому что качество тегов будет напрямую зависеть от того, насколько корректно S01 выделяет структуру документа: заголовки, абзацы, списки, таблицы, вложенность и полезные текстовые блоки.

Следующий этап — не ML/LLM и не выделение тегов. Следующий этап — довести предобработчик до версии S01/v1, прогнать его на реальной выгрузке `documents.csv`, получить отчёты качества и подготовить стабильный слой данных для тегирования.

## 2. Контекст текущего состояния

Текущий проект уже содержит:

- CLI-команды `init-dirs`, `ingest`, `normalize`, `status`, `validate-stage`.
- S00 ingest: импорт CSV, стабильные `doc_id`, `content_hash`, Parquet/JSONL/manifest/report.
- S01 normalize: HTML-aware очистка, извлечение блоков, Markdown, by-doc JSON/MD, отчёт.
- External storage path: `/mnt/storage/datasets/itg_datasets`.
- Каркасы будущих стадий S02–S10.
- Тесты на ingest, normalize, paths и validate-stage.

Но S01 сейчас является минимальной рабочей реализацией. Она ещё не должна считаться финальным предобработчиком для медицинской базы. Требуется укрепить её на реальных HTML-like документах.

## 3. Цель S01/v1

Сделать предобработчик, который:

1. Корректно читает результат S00 из external storage.
2. Сохраняет максимум полезной структуры из `content`, включая кривую HTML-разметку.
3. Не теряет текст, который находится внутри `div`, `section`, `span`, `font`, `strong`, `em` и других контейнеров без явного `<p>`.
4. Корректно извлекает таблицы и сохраняет их как структурированные данные, а не только как плоский текст.
5. Создаёт отчёт качества, по которому можно понять, готов ли корпус к S02/tagging.
6. Позволяет вручную посмотреть выборку документов до запуска тегирования.
7. Не скачивает модели, не вызывает API, не требует тяжёлых зависимостей.

## 4. Важное ограничение

На этом этапе запрещено:

- скачивать тяжёлые модели;
- подключать LLM;
- вызывать внешние API;
- реализовывать S02/tagging;
- коммитить данные из `/mnt/storage/datasets/itg_datasets`;
- смешивать ручные исправления с машинными результатами;
- удалять исходный `raw_content` из S00-артефактов.

Допускается улучшать парсинг HTML, Markdown rendering, отчёты, CLI, тесты и схемы.

## 5. External storage contract

Единственный рабочий storage path для данных:

```text
/mnt/storage/datasets/itg_datasets
```

Ожидаемая структура:

```text
/mnt/storage/datasets/itg_datasets/
  00_raw/
    documents.csv
  01_ingested/
    documents.parquet
    documents.jsonl
    manifest.jsonl
  02_normalized/
    documents_normalized.parquet
    blocks.parquet
    block_metrics.parquet
    by_doc/
      <doc_id>.normalized.json
      <doc_id>.md
      <doc_id>.structure.json
  90_reports/
    S00_ingest_report.json
    S01_normalization_report.json
    S01_quality_report.json
    S01_quality_report.md
    S01_sample_index.md
    samples/
      <doc_id>.md
      <doc_id>.html
      <doc_id>.json
```

`block_metrics.parquet`, `structure.json`, `S01_quality_report.*` и `samples/` являются новыми желательными артефактами S01/v1.

## 6. Требования к входу

Вход S01/v1:

```text
/mnt/storage/datasets/itg_datasets/01_ingested/documents.parquet
```

Обязательные колонки:

```text
doc_id
source_row
name
raw_content
content_hash
raw_length
has_html
ingest_status
metadata
```

Документы со статусом `empty_content` не должны ломать normalize. Для них создаётся запись в `documents_normalized.parquet` со статусом `empty_content`, но блоки не создаются.

## 7. Требования к разбору HTML-like content

Предобработчик должен считать `content` semi-structured документом, а не просто HTML-строкой.

### 7.1. Очистка

Удалять из анализа:

- `script`
- `style`
- `noscript`
- невидимый мусор, если он явно определяется как технический

Сохранять как текст или metadata:

- заголовки;
- абзацы;
- списки;
- таблицы;
- inline-выделение, если оно помогает понять смысл;
- ссылки, если они присутствуют;
- текстовые узлы внутри контейнеров без `<p>`.

### 7.2. Block taxonomy

Минимальные типы блоков:

```text
title
heading
paragraph
list_item
table
table_caption
blockquote
note
warning
raw_text
unknown
```

Если `note/warning/title/table_caption` пока трудно определить надёжно, допускается сохранять их как `paragraph` или `unknown`, но структура должна позволять добавить эти типы позже без миграции всех данных.

### 7.3. Заголовки и вложенность

Для каждого блока нужно сохранять:

- `parent_path` — технический путь вложенности;
- `heading_path` — человекочитаемый путь по заголовкам;
- `level` для heading;
- `order` — глобальный порядок блока в документе.

Пример `heading_path`:

```json
["Гастрит", "Лечение", "Диета"]
```

### 7.4. Таблицы

Таблицу нельзя сохранять только строкой `cell | cell`.

Для блока `table` в `metadata` должны быть:

```json
{
  "rows": [["Параметр", "Значение"], ["Температура", "37"]],
  "row_count": 2,
  "column_count": 2,
  "has_header": true,
  "markdown": "| Параметр | Значение |\n|---|---|\n| Температура | 37 |"
}
```

Если таблица кривая, нужно сохранить хотя бы `rows` и `text`, а ошибку/аномалию записать в metadata или report.

### 7.5. Списки

Для `list_item` нужно сохранять:

- текст пункта;
- уровень вложенности, если можно определить;
- тип списка: ordered/unordered/unknown;
- `parent_path` и `heading_path`.

### 7.6. Inline-разметка

Не нужно превращать inline-разметку в отдельные блоки. Но полезные признаки должны сохраняться в metadata, если это не усложняет реализацию:

```json
{
  "inline_marks": ["strong", "em"],
  "links": [{"text": "...", "href": "..."}]
}
```

## 8. Требования к DocumentBlock

Текущую схему `DocumentBlock` нужно расширить осторожно, без поломки существующих тестов.

Желательные поля:

```text
block_id: str
doc_id: str
order: int
type: str
text: str
html: str | null
level: int | null
parent_path: list[str]
heading_path: list[str]
dom_path: str | null
char_start: int | null
char_end: int | null
text_hash: str
metadata: dict
```

Если часть полей невозможно заполнить надёжно, они должны быть `null` или пустым списком, но колонка должна присутствовать в `blocks.parquet`.

## 9. Требования к NormalizedDocument

`documents_normalized.parquet` должен позволять быстро понять состояние каждого документа.

Желательные поля:

```text
doc_id
title
content_hash
plain_text
markdown
block_count
normalization_status
error
plain_text_length
markdown_length
raw_length
text_preservation_ratio
heading_count
paragraph_count
list_item_count
table_count
unknown_count
has_tables
has_headings
has_warnings
```

`text_preservation_ratio` считать как отношение длины нормализованного `plain_text` к длине plain text, извлечённого напрямую из HTML/soup. Это не идеальная метрика, но она полезна для поиска документов, где парсер потерял большой кусок текста.

## 10. Требования к отчётам

### 10.1. JSON report

Файл:

```text
/mnt/storage/datasets/itg_datasets/90_reports/S01_quality_report.json
```

Минимальные поля:

```json
{
  "stage": "S01",
  "total_documents": 16000,
  "empty_documents": 0,
  "ok_documents": 15900,
  "failed_documents": 0,
  "documents_without_blocks": 0,
  "total_blocks": 123456,
  "blocks_by_type": {},
  "documents_with_tables": 1000,
  "documents_with_headings": 12000,
  "low_text_preservation_documents": [],
  "top_largest_documents": [],
  "top_documents_by_block_count": [],
  "errors_sample": []
}
```

### 10.2. Markdown report

Файл:

```text
/mnt/storage/datasets/itg_datasets/90_reports/S01_quality_report.md
```

Отчёт должен быть удобен для чтения человеком и содержать:

- общую статистику;
- распределение типов блоков;
- список документов с подозрительно низкой сохранностью текста;
- список документов без блоков;
- список документов с большим числом `unknown`;
- список самых крупных документов;
- рекомендации: можно ли идти в S02 или надо чинить parser.

### 10.3. Sample index

Файл:

```text
/mnt/storage/datasets/itg_datasets/90_reports/S01_sample_index.md
```

Должен содержать ссылки на sample-файлы и краткую причину попадания документа в выборку.

## 11. Sampling для ручного ревью

Нужно добавить команду или режим, который формирует выборку документов для ручного ревью.

Минимальный принцип выборки:

```text
20 случайных документов
20 крупнейших по raw_length
20 с таблицами
20 с большим числом блоков
20 подозрительных: no_blocks / low_text_preservation / много unknown
```

Если пересечения большие, итоговая выборка может быть меньше 100, но должна покрывать разные типы документов.

Для каждого sample-документа сохранять:

```text
90_reports/samples/<doc_id>.md
90_reports/samples/<doc_id>.json
```

HTML-preview опционален, но желателен:

```text
90_reports/samples/<doc_id>.html
```

## 12. CLI requirements

Нужно сохранить существующие команды и добавить полезные параметры.

### 12.1. normalize

```bash
python -m itg_kb.cli normalize
python -m itg_kb.cli normalize --limit 200
python -m itg_kb.cli normalize --doc-id doc_...
python -m itg_kb.cli normalize --force
```

Если `--limit` или `--doc-id` не реализованы сразу, они должны быть явно отложены в отчёте. Но для разработки на реальной базе `--limit` очень желателен.

### 12.2. audit-normalized

Новая команда:

```bash
python -m itg_kb.cli audit-normalized --sample-size 100
```

Команда строит `S01_quality_report.json`, `S01_quality_report.md`, `S01_sample_index.md` и sample-файлы.

### 12.3. validate-stage

`validate-stage S01` должен проверять не только наличие файлов, но и качество минимального уровня.

Минимум:

- Parquet читается;
- обязательные колонки есть;
- `documents_normalized.parquet` покрывает все `doc_id` из S00;
- если в S00 есть непустые документы, `blocks.parquet` не должен быть пустым;
- `block_count` в documents_normalized согласован с фактическими блоками;
- `S01_normalization_report.json` читается.

## 13. Производительность

Для 16 000 документов S01/v1 должен работать как обычный CPU/I/O этап. Он не должен занимать сутки.

Требования:

- не держать одновременно в памяти гигантские by-doc JSON для всех документов;
- писать Parquet пакетно или аккуратно собирать records, если память позволяет;
- не делать сетевых запросов;
- логировать прогресс каждые N документов;
- отдельный плохой документ не должен ломать весь прогон;
- ошибки должны попадать в report.

## 14. Quality gates перед S02

Переход к S02/tagging разрешён, если выполнены условия:

```text
1. make test проходит.
2. make lint проходит.
3. init-dirs работает с /mnt/storage/datasets/itg_datasets.
4. ingest прошёл на реальном documents.csv.
5. validate-stage S00 проходит.
6. normalize прошёл на реальном documents.csv.
7. validate-stage S01 проходит.
8. S01_quality_report.md создан.
9. В отчёте нет массовой потери текста.
10. У непустых документов почти всегда есть хотя бы один блок.
11. Таблицы не теряются полностью.
12. Архитектор просмотрел sample index и принял структуру блоков.
```

Если хотя бы один пункт 4–8 не выполнен, S02 начинать нельзя.

## 15. Что не входит в S01/v1

Не входит:

- выделение тегов;
- нормализация синонимов;
- медицинский NER;
- LLM extraction;
- генерация статей;
- генерация цитат;
- граф знаний;
- загрузка в STEOS;
- подключение Docling как обязательной зависимости;
- OCR.

Docling/OCR можно оставить как будущий optional adapter, но не нужно включать его в обязательный runtime S01/v1.

## 16. Definition of Done

S01/v1 считается готовым, если:

```text
- Код не скачивает модели и не вызывает API.
- Все тесты проходят.
- Линтер проходит.
- Реальный documents.csv можно импортировать из /mnt/storage/datasets/itg_datasets/00_raw/documents.csv.
- Реальный корпус можно нормализовать в /mnt/storage/datasets/itg_datasets/02_normalized.
- validate-stage S00 и S01 проходят.
- Созданы S01_quality_report.json и S01_quality_report.md.
- Создан sample index для ручного ревью.
- by_doc JSON/MD создаются для документов.
- tables сохраняются структурно в metadata.
- Документы с ошибками не ломают весь pipeline.
- Отчёт исполнителя в docs/reports актуален и соответствует текущему коду.
```
