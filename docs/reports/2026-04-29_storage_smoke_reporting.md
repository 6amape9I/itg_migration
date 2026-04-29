# 2026-04-29 - Storage path, smoke cleanup, reporting

## Цель

Выполнить первичные замечания по структуре данных, smoke-run, отчётности исполнителя и крупным CSV `content`.

## Изменения

- Stage-директории были перенесены из `data/` в прежний project-root storage path. Позже это решение заменено инструкцией `polish_stage0`.
- Smoke-run переведён на временную директорию, поэтому после успешного запуска не оставляет S00/S01 artifacts в рабочем дереве.
- Добавлена папка `docs/` для отчётов, чек-листов и обратной связи архитектору.
- CSV loader увеличивает лимит размера одного поля до 256 MiB для длинных `content`.
- README обновлён: storage path, ожидаемые ~16 000 документов, smoke cleanup и правило отчётности.

## Чек-лист

- [x] Пути S00/S01 обновлены в `configs/paths.yaml` и `configs/pipeline.yaml`.
- [x] Git ignore покрывает stage-директории без `data/`.
- [x] Smoke-run не пишет generated artifacts в проект.
- [x] Документация для архитектора добавлена в `docs/`.
- [x] Лимит CSV поля увеличен сейчас, а не отложен.

## Проверки

- `make test` - passed, 12 tests.
- `make lint` - passed, `ruff check`.
- `make smoke` - passed, `S00: ok rows=5`, `S01: ok blocks=10`.
- После `make smoke` stage-директории `00_raw`, `01_ingested`, `02_normalized`, `90_reports` и legacy `data` в рабочем дереве не появились.

## Обратная связь архитектору

- Текущий storage path совпадает с корнем репозитория в этой среде, поэтому stage-директории добавлены в `.gitignore` явно.
- Если позднее код проекта будет физически перенесён в подпапку, `configs/paths.yaml` уже поддерживает абсолютный storage path без изменения кода.
- Если отдельные `content` окажутся больше 256 MiB, нужно отдельно согласовать streaming ingest и Parquet schema с `large_string`.
