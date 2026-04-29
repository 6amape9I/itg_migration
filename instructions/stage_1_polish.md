Задача: исправить S01/v1, потому что реальный content в documents.csv часто является Editor.js JSON, а текущий preprocessor воспринимает его как plain text.

Проблема:
В normalized plain_text и blocks попадает служебный JSON:
- blocks
- id
- type
- data
- api
- styles
- toolbar
- version
и т.д.
Это недопустимо. plain_text должен содержать только человеческий текст, а blocks должны соответствовать Editor.js blocks.

Что сделать:
1. Добавить модуль src/itg_kb/preprocess/editorjs_parser.py.
2. Добавить detector формата content:
   - editorjs_json, если raw_content валидный JSON и содержит top-level "blocks": list;
   - html, если есть HTML markup;
   - plain_text иначе.
3. Перед HTML/plain обработкой проверять Editor.js.
4. Реализовать extract_editorjs_blocks(doc_id, raw_content):
   - type="header" -> DocumentBlock type="heading", level=data.level, text=data.text;
   - type="paragraph" -> DocumentBlock type="paragraph", text=data.text;
   - type="list" -> list_item блоки из data.items;
   - type="table" -> table block из data.content / rows;
   - type="quote" -> blockquote;
   - type="delimiter" -> пропускать;
   - неизвестные типы -> unknown только если есть полезный текст.
5. Игнорировать служебные поля:
   - api
   - element
   - caret
   - events
   - i18n
   - inlineToolbar
   - listeners
   - notifier
   - readOnly
   - sanitizer
   - saver
   - selection
   - styles
   - toolbar
   - tooltip
   - ui
6. Для Editor.js paragraph:
   - если data.text содержит HTML inline-разметку, очистить её через BeautifulSoup/markdownify;
   - сохранить переносы строк;
   - не включать JSON-обвязку.
7. Обновить plain_text:
   - для Editor.js plain_text должен строиться из извлечённых block.text, а не из raw JSON.
8. Обновить markdown:
   - header -> ### ...
   - paragraph -> текст
   - list_item -> - текст
   - table -> markdown table, если возможно.
9. В metadata каждого block добавить:
   - source_format: editorjs
   - editorjs_block_id
   - editorjs_type
10. Добавить document-level metadata:
   - source_format: editorjs
   - raw_format_detected: editorjs_json
11. Исправить метрики:
   - text_preservation_ratio для Editor.js нельзя считать по raw JSON длине;
   - добавить useful_text_ratio = useful_text_length / raw_length;
   - warnings, если useful_text_ratio слишком низкий или если editorjs parse failed.
12. Добавить тесты:
   - fixture с примером как doc_0a0ad5b9a5b8d6e1243e;
   - header должен стать heading level 3;
   - paragraph должен содержать только "Режим дозирования..." и дозировку/приём;
   - plain_text не должен содержать '"blocks"', '"api"', '"styles"', '"toolbar"', '"version"';
   - markdown не должен содержать JSON;
   - structure.json не должен содержать JSON-хвосты.
13. Добавить audit:
   - количество документов по source_format;
   - количество editorjs документов;
   - топ документов, где plain_text содержит подозрительные JSON markers;
   - quality gate: если plain_text содержит '"blocks":' или '"api":' более чем в N документах, validate-stage S01 должен выдавать warning или error.
14. Не скачивать модели, не вызывать API.

После реализации:
- прогнать unit/integration tests;
- прогнать normalize --doc-id doc_0a0ad5b9a5b8d6e1243e --force;
- проверить, что sample больше не содержит JSON;
- затем прогнать полный normalize --force.