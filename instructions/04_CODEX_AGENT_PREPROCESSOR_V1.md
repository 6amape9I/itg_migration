# 04. Инструкция для Codex-агента: S01/v1 предобработчик реальных документов

## Роль

Ты работаешь как инженер-исполнитель в проекте `itg-kb-rebuild`. Твоя задача — не переписывать проект заново, а аккуратно развить текущий bootstrap до устойчивого предобработчика S01/v1.

## Текущий статус

Bootstrap уже принят условно:

- S00 ingest реализован.
- S01 normalize реализован минимально.
- Пути данных перенесены в `/mnt/storage/datasets/itg_datasets`.
- `ProjectPaths` умеет выводить stage-директории из `data_dir`.
- `validate-stage` уже проверяет часть артефактов.
- HTML block extractor уже не является пустой заглушкой, но требует усиления на реальных документах.

Твоя работа — довести S01 до версии, после которой можно безопасно переходить к S02/tagging.

## Главное ограничение

Не скачивай тяжёлые модели. Не подключай LLM. Не вызывай внешние API. Не добавляй обязательные тяжёлые зависимости. Не реализовывай S02.

Docling, OCR, LLM и медицинские модели оставить только как будущие optional adapters/placeholders, если они уже есть в проекте.

## Целевой результат

После твоей работы должны работать команды:

```bash
make test
make lint

python -m itg_kb.cli init-dirs
python -m itg_kb.cli ingest --input /mnt/storage/datasets/itg_datasets/00_raw/documents.csv
python -m itg_kb.cli validate-stage S00
python -m itg_kb.cli normalize
python -m itg_kb.cli validate-stage S01
python -m itg_kb.cli audit-normalized --sample-size 100
```

Если на текущем компьютере нет реального `documents.csv`, не падай в тестах из-за его отсутствия. Реальный прогон должен быть ручной командой, а не обязательной частью unit/integration tests.

## Задача 1. Актуализировать отчёт исполнителя

Создай новый отчёт в:

```text
docs/reports/<YYYY-MM-DD>_preprocessor_v1.md
```

В отчёте должно быть:

- что именно изменено;
- какие команды проверены;
- какие тесты прошли;
- какие риски остались;
- можно ли переходить к S02 или нужно ещё ревью sample-документов.

Важно: не оставляй устаревшее состояние как актуальное. Финальный `data_dir` сейчас:

```text
/mnt/storage/datasets/itg_datasets
```

## Задача 2. Улучшить schema-контракты S01

Проверь Pydantic-схемы:

```text
src/itg_kb/schemas/blocks.py
src/itg_kb/schemas/documents.py
```

Расширь `DocumentBlock`, если полей ещё нет:

```text
heading_path: list[str]
dom_path: str | None
text_hash: str
```

Расширь `NormalizedDocument`, если полей ещё нет:

```text
raw_length: int
plain_text_length: int
markdown_length: int
text_preservation_ratio: float | None
heading_count: int
paragraph_count: int
list_item_count: int
table_count: int
unknown_count: int
has_tables: bool
has_headings: bool
has_warnings: bool
```

Не ломай обратную совместимость существующих тестов. Если нужно — добавь default values.

Обнови JSON Schema в `schemas/`, если проект поддерживает их вручную.

## Задача 3. Усилить HTML block extractor

Рабочие файлы:

```text
src/itg_kb/preprocess/html_cleaner.py
src/itg_kb/preprocess/block_extractor.py
src/itg_kb/preprocess/table_extractor.py
src/itg_kb/preprocess/markdown_renderer.py
```

Требования:

1. Не терять текстовые узлы внутри `div`, `section`, `span`, `font`, `strong`, `em`, если рядом нет `<p>`.
2. Сохранять порядок блоков так, как они идут в документе.
3. Поддерживать кривой HTML без падения всего normalize.
4. Для каждого блока сохранять `heading_path`.
5. Для каждого блока по возможности сохранять `dom_path`.
6. Для каждого блока считать `text_hash`.
7. Для таблиц сохранять rows, row_count, column_count, has_header, markdown в metadata.
8. Для списков сохранять list_type и list_level в metadata, если можно определить.
9. Для ссылок и inline marks сохранять metadata, если это можно сделать простым способом без тяжелой логики.

Не нужно делать идеальный HTML parser. Нужно сделать устойчивый практичный parser для медицинских HTML-like документов.

## Задача 4. Улучшить table extractor

Таблицы должны сохраняться структурно.

Минимальный API:

```python
def extract_table_rows(table: Tag) -> list[list[str]]: ...
def table_to_text(rows: list[list[str]]) -> str: ...
def table_to_markdown(rows: list[list[str]]) -> str: ...
def infer_has_header(rows: list[list[str]]) -> bool: ...
```

Требования:

- не падать на пустых строках;
- не падать на разном числе колонок;
- корректно считать `row_count`;
- корректно считать `column_count` как максимум длины строки;
- если есть `<th>`, считать `has_header=true`;
- если `<th>` нет, можно эвристически считать первую строку заголовком, но это должно быть metadata, а не факт медицинского содержания.

## Задача 5. Улучшить markdown renderer

`by_doc/<doc_id>.md` нужен для ручного ревью и будущего LLM-контекста.

Требования:

- heading отображать как Markdown heading;
- list_item отображать как список;
- table отображать как Markdown table, если есть `metadata.markdown`;
- blockquote отображать как quote;
- unknown/raw_text отображать как обычный текст;
- не создавать нечитаемую кашу без пустых строк.

## Задача 6. Добавить audit-normalized

Добавь CLI-команду:

```bash
python -m itg_kb.cli audit-normalized --sample-size 100
```

Команда должна читать:

```text
/mnt/storage/datasets/itg_datasets/01_ingested/documents.parquet
/mnt/storage/datasets/itg_datasets/02_normalized/documents_normalized.parquet
/mnt/storage/datasets/itg_datasets/02_normalized/blocks.parquet
```

И писать:

```text
/mnt/storage/datasets/itg_datasets/90_reports/S01_quality_report.json
/mnt/storage/datasets/itg_datasets/90_reports/S01_quality_report.md
/mnt/storage/datasets/itg_datasets/90_reports/S01_sample_index.md
/mnt/storage/datasets/itg_datasets/90_reports/samples/<doc_id>.md
/mnt/storage/datasets/itg_datasets/90_reports/samples/<doc_id>.json
```

HTML preview можно добавить, если это делается просто:

```text
/mnt/storage/datasets/itg_datasets/90_reports/samples/<doc_id>.html
```

## Задача 7. Sampling logic

Выборка должна быть полезной для архитектурного ревью.

Сформируй sample из групп:

```text
random
largest_by_raw_length
with_tables
many_blocks
suspicious
```

`suspicious` — это документы:

- без блоков;
- с низким `text_preservation_ratio`;
- с большим числом `unknown`;
- с ошибками normalization;
- с пустым markdown при непустом raw_content.

В `S01_sample_index.md` для каждого документа укажи:

```text
doc_id
name/source_row
reason
block_count
table_count
text_preservation_ratio
пути к sample-файлам
```

## Задача 8. Улучшить validate-stage S01

`validate-stage S01` должен дополнительно проверять:

1. `documents_normalized.parquet` содержит обязательные колонки.
2. `blocks.parquet` содержит обязательные колонки.
3. Если в S00 есть непустые документы, `blocks.parquet` не пустой.
4. `documents_normalized.doc_id` покрывает все `documents.doc_id`.
5. `block_count` по каждому `doc_id` не конфликтует с фактическими строками в `blocks.parquet`.
6. `S01_normalization_report.json` читается.
7. Если `S01_quality_report.json` существует, он читается.

Если optional quality report отсутствует, это предупреждение, а не обязательно ошибка для базовой S01-валидации. Но после запуска `audit-normalized` он должен существовать.

## Задача 9. Добавить параметры normalize

Добавь параметры, которые помогут безопасно работать с реальной базой:

```bash
python -m itg_kb.cli normalize --limit 200
python -m itg_kb.cli normalize --doc-id doc_...
python -m itg_kb.cli normalize --force
```

Ожидаемое поведение:

- `--limit` обрабатывает первые N документов из `documents.parquet`.
- `--doc-id` обрабатывает один документ.
- `--force` разрешает перезаписать S01-артефакты.

Если реализуешь не всё, явно напиши в отчёте, что отложено и почему.

## Задача 10. Тесты

Добавь или обнови тесты:

```text
tests/unit/test_block_extractor.py
tests/unit/test_table_extractor.py
tests/unit/test_markdown_renderer.py
tests/integration/test_normalize.py
tests/integration/test_validate_stage.py
tests/integration/test_audit_normalized.py
```

Минимальные cases:

1. HTML с `div` без `<p>` не теряет текст.
2. Кривой HTML не ломает normalize.
3. Таблица с `<th>` получает `has_header=true`.
4. Таблица с разным числом колонок не ломает markdown renderer.
5. `heading_path` корректно появляется у блока после heading.
6. `validate-stage S01` ловит пустой `blocks.parquet` при непустых документах.
7. `audit-normalized` создаёт JSON/MD report и sample index.
8. `normalize --limit` не обрабатывает все документы.
9. `normalize --doc-id` обрабатывает только выбранный документ.
10. Пустой `content` не ломает pipeline.

Тесты должны использовать synthetic fixtures. Не требуй наличия реального `/mnt/storage/datasets/itg_datasets/00_raw/documents.csv` для прохождения тестов.

## Задача 11. Реальный smoke на корпусе

Если реальный CSV доступен в среде, выполни:

```bash
python -m itg_kb.cli init-dirs
python -m itg_kb.cli ingest --input /mnt/storage/datasets/itg_datasets/00_raw/documents.csv
python -m itg_kb.cli validate-stage S00
python -m itg_kb.cli normalize --limit 200 --force
python -m itg_kb.cli validate-stage S01
python -m itg_kb.cli audit-normalized --sample-size 50
```

После этого, если `--limit 200` успешен, можно выполнить полный normalize вручную:

```bash
python -m itg_kb.cli normalize --force
python -m itg_kb.cli validate-stage S01
python -m itg_kb.cli audit-normalized --sample-size 100
```

Если реального CSV нет, не создавай фиктивный большой файл. Просто укажи в отчёте, что real-corpus run не выполнен из-за отсутствия файла.

## Задача 12. Не трогать

Не трогай без необходимости:

- S02–S10 бизнес-логику;
- LLM adapters;
- STEOS export;
- graph modules;
- prompts для тегирования;
- curation-файлы, кроме документации.

Не добавляй новые большие зависимости ради красивого парсинга. Если нужна новая маленькая зависимость, обоснуй её в отчёте.

## Definition of Done

Работа считается готовой, если:

```text
- make test проходит.
- make lint проходит.
- docs/reports/<date>_preprocessor_v1.md создан и актуален.
- Project paths продолжают работать через /mnt/storage/datasets/itg_datasets.
- normalize создаёт расширенные S01-артефакты.
- audit-normalized создаёт quality report и sample index.
- validate-stage S01 стал строже.
- tables сохраняются структурно.
- heading_path/dom_path/text_hash добавлены или явно отложены с причиной.
- Реальный корпус можно прогнать хотя бы в режиме --limit 200, если CSV доступен.
- Никакие generated data artifacts не попали в git.
- Не скачаны модели и не вызваны API.
```

## Что написать архитектору в конце

В финальном отчёте коротко ответь:

```text
1. Какие файлы изменены?
2. Какие команды прошли?
3. Сколько тестов прошло?
4. Был ли прогон на реальном documents.csv?
5. Сколько документов обработано в тестовом/реальном прогоне?
6. Есть ли документы с потерей текста или no_blocks?
7. Где лежит S01_quality_report.md?
8. Можно ли переходить к S02/tagging или ещё требуется правка S01?
```
