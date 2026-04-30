# S02A. Первичное выделение кандидатов тегов: deterministic baseline v2

## 0. Контекст

Проект уже прошёл S00/S01.

S01 теперь корректно распознаёт исходные документы как Editor.js JSON и сохраняет структурированные артефакты:

```text
/mnt/storage/datasets/itg_datasets/02_normalized/documents_normalized.parquet
/mnt/storage/datasets/itg_datasets/02_normalized/blocks.parquet
/mnt/storage/datasets/itg_datasets/02_normalized/block_metrics.parquet
```

Полный прогон S01 дал:

```text
docs: 16181
source_format: editorjs = 16181
blocks: 524236
paragraph: 210001
heading: 176284
list_item: 132308
table: 5641
unknown: 2
docs_with_json_markers: 0
normalization_status: ok = 16161, no_blocks = 20
```

S02A должен работать поверх этой структуры. Нельзя мыслить документ как плоский текст. Основные сигналы теперь: `title`, `heading`, `heading_path`, `block.type`, `block.order`, `table/list/paragraph` и связи блоков внутри Editor.js-документа.

## 1. Главная правка к предыдущей версии требований

В предыдущем черновике могло сложиться впечатление, что из одного документа нужно сохранять только ограниченное число кандидатов, например top-6. Это неверно.

**Жёсткого максимума кандидатов на документ быть не должно.**

Один документ может быть короткой карточкой и дать 1–3 кандидата. Другой документ может быть большой главой, методичкой, фрагментом книги или смешанным документом и дать 20, 50, 100+ кандидатов. Это нормально, если каждый кандидат имеет evidence и прошёл минимальный quality threshold.

Любые `top_k` допустимы только для:

```text
review CSV
короткого doc-level summary
компактного LLM-промпта в будущих этапах
отображения в отчётах
```

`top_k` не должен ограничивать сохранение кандидатов в `tag_candidates.parquet`.

Если документ даёт аномально много кандидатов, система должна не обрезать их молча, а ставить warning:

```text
many_candidates_in_document
long_document_many_topic_units
candidate_explosion_risk
```

## 2. Новая формулировка S02A

S02A — это не “один документ → несколько тегов”.

S02A — это:

```text
структурное выделение topic units
+ извлечение кандидатов ключевых сущностей внутри topic units
+ отделение сущностей от facets/aspects
+ классификация роли кандидата
+ сохранение evidence и score
```

Причина: документы ИТГ переплетены. В одном документе может обсуждаться грипп, перчатки, симптом, лекарство, условие лечения и организационная инструкция. Нельзя насильно сводить такой документ к одному тегу.

S02A должен сохранять несколько типов результатов:

```text
1. topic units — смысловые зоны документа;
2. tag candidates — все кандидаты ключевых сущностей;
3. candidate evidence — откуда взялся каждый кандидат;
4. doc topics summary — краткое summary по документу для review;
5. ambiguity queue — документы/units, где автоматике не хватило уверенности.
```

## 3. Что такое topic unit

`topic_unit` — это локальный смысловой контейнер внутри документа.

Примеры:

```text
раздел под heading
подраздел под heading_path
таблица с собственным heading_path
группа list_item под heading
окно paragraphs в документе без заголовков
```

S02A должен извлекать кандидатов не только на уровне документа, но и на уровне `topic_unit`.

### 3.1. Пример маленького документа

```text
Зиннат таблетки, покрытые пленочной оболочкой 125 мг: Способы и дозировка

Режим дозирования и схемы приема
...
```

Ожидаемая логика:

```text
topic_unit: весь документ или section под heading
candidate: Зиннат таблетки, покрытые пленочной оболочкой 125 мг
core_surface: Зиннат
entity_type: drug_product
facet_type: dosage / administration
role: document_primary_candidate или section_topic_candidate
```

`Способы и дозировка` не должен становиться самостоятельным тегом. Это facet.

### 3.2. Пример переплетённого документа

```text
Грипп можно лечить в условиях использования медицинских перчаток только если отсутствует симптом X.
```

Ожидаемая логика:

```text
Грипп                  disease          section_topic_candidate / document_primary_candidate
Медицинские перчатки   medical_device   cross_topic_reference или section_topic_candidate
Симптом X              symptom          conditional_context
Лечение                facet_only       treatment
```

## 4. Входы S02A

```text
data/02_normalized/documents_normalized.parquet
data/02_normalized/blocks.parquet
data/02_normalized/block_metrics.parquet
```

S02A должен обрабатывать только документы с `normalization_status = ok`.

Документы `no_blocks` должны попадать в отдельный отчёт и не должны ломать stage.

## 5. Выходы S02A

Добавить/обновить выходы:

```text
data/03_tagging/topic_units.parquet
data/03_tagging/tag_candidates.parquet
data/03_tagging/candidate_evidence.parquet
data/03_tagging/doc_topics.parquet
data/03_tagging/doc_tag_candidates.jsonl
data/03_tagging/ambiguity_queue.jsonl
data/03_tagging/by_doc/<doc_id>.tag_candidates.json
data/90_reports/S02A_tagging_report.json
data/90_reports/S02A_tagging_report.md
data/90_reports/S02A_review_sample.csv
data/90_reports/S02A_candidate_distribution.csv
data/90_reports/S02A_no_blocks_skipped.csv
```

## 6. Схемы данных

Все структуры должны быть Pydantic-моделями. Схемы должны экспортироваться в `schemas/*.schema.json`.

### 6.1. TopicUnit

```python
class TopicUnit(BaseModel):
    topic_unit_id: str
    doc_id: str
    unit_index: int
    unit_type: str
    title: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    text: str
    text_length: int
    char_start: int | None = None
    char_end: int | None = None
    source_block_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
```

`unit_type` values:

```text
document_title
heading_section
table_unit
list_unit
paragraph_window
fallback_document
```

### 6.2. TagCandidate

```python
class TagCandidate(BaseModel):
    candidate_id: str
    doc_id: str
    topic_unit_id: str | None = None

    role: str
    surface: str
    normalized_surface: str
    core_surface: str | None = None
    normalized_core_surface: str | None = None

    entity_type: str
    entity_subtype: str | None = None
    facet_type: str | None = None
    facets: list[str] = Field(default_factory=list)
    qualifiers: dict[str, str] = Field(default_factory=dict)

    sources: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str] = Field(default_factory=list)
    evidence_texts: list[str] = Field(default_factory=list)
    heading_paths: list[list[str]] = Field(default_factory=list)

    score: float
    score_components: dict[str, float] = Field(default_factory=dict)
    confidence_bucket: str

    needs_review: bool = False
    review_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 6.3. CandidateEvidence

```python
class CandidateEvidence(BaseModel):
    evidence_id: str
    candidate_id: str
    doc_id: str
    topic_unit_id: str | None = None
    block_id: str
    evidence_type: str
    text: str
    heading_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    weight: float
```

`evidence_type` values:

```text
title
heading
heading_path
paragraph
list_item
table
pattern_match
```

### 6.4. DocTopicSummary

```python
class DocTopicSummary(BaseModel):
    doc_id: str
    title: str
    normalization_status: str
    topic_unit_count: int
    candidate_count_total: int
    primary_candidate_ids: list[str] = Field(default_factory=list)
    top_candidate_ids_for_review: list[str] = Field(default_factory=list)
    facet_only_count: int = 0
    cross_topic_reference_count: int = 0
    needs_review: bool = False
    review_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
```

## 7. Роли кандидатов

Добавить строгий enum/константы ролей:

```text
document_primary_candidate
section_topic_candidate
secondary_topic_candidate
cross_topic_reference
conditional_context
facet_only
rejected_generic
needs_review
```

Объяснение:

`document_primary_candidate` — главный кандидат уровня всего документа.

`section_topic_candidate` — главная тема отдельного section/topic_unit. Для большой главы таких кандидатов может быть много.

`secondary_topic_candidate` — важная сущность, которая не является главной в данном unit, но может стать тегом на следующих этапах.

`cross_topic_reference` — связанная сущность, важная для графа и S04, но не обязательно самостоятельная тема данного section.

`conditional_context` — симптом/условие/ограничение, которое влияет на смысл медицинского утверждения.

`facet_only` — аспект вроде “лечение”, “дозировка”, “противопоказания”, “симптомы”, если рядом нет самостоятельной сущности.

`rejected_generic` — мусорная общая формулировка.

`needs_review` — автоматике не хватило уверенности.

## 8. Facet vs entity

Главный принцип:

```text
Tag candidate = сущность/тема, вокруг которой можно собрать итоговую статью.
Facet = аспект описания этой сущности.
```

Запрещено продвигать generic facet в primary candidate без entity.

Примеры facet-only/generic phrases:

```text
способы и дозировка
режим дозирования
особенности приема
показания
противопоказания
побочные действия
симптомы
лечение
диагностика
профилактика
подготовка
инструкция по применению
описание
общие сведения
```

Если заголовок выглядит как:

```text
<entity>: <facet>
```

то candidate = `<entity>`, facet = `<facet>`.

Примеры:

```text
Гастрит: симптомы и лечение
candidate = Гастрит
entity_type = disease
facets = symptoms, treatment

Зиннат таблетки 125 мг: Способы и дозировка
candidate = Зиннат таблетки 125 мг
entity_type = drug_product
facet = dosage

Общий анализ крови: подготовка
candidate = Общий анализ крови
entity_type = diagnostic_test
facet = preparation
```

## 9. Конфиги S02A

Создать папку:

```text
configs/tagging/
```

Создать файлы:

```text
configs/tagging/facet_patterns.yaml
configs/tagging/generic_blocklist.yaml
configs/tagging/entity_patterns.yaml
configs/tagging/drug_forms.yaml
configs/tagging/scoring.yaml
configs/tagging/review.yaml
```

### 9.1. facet_patterns.yaml

```yaml
facets:
  dosage:
    - дозировка
    - режим дозирования
    - способ применения
    - способы и дозировка
    - как принимать
  administration:
    - особенности приема
    - способ приема
    - внутрь
  contraindications:
    - противопоказания
    - нельзя применять
  side_effects:
    - побочные действия
    - нежелательные реакции
  symptoms:
    - симптомы
    - признаки
  treatment:
    - лечение
    - терапия
  diagnosis:
    - диагностика
    - анализ
    - обследование
  preparation:
    - подготовка
  instruction:
    - инструкция
    - как использовать
    - как надевать
```

### 9.2. generic_blocklist.yaml

```yaml
generic_phrases:
  - способы и дозировка
  - режим дозирования
  - особенности приема
  - инструкция по применению
  - показания
  - противопоказания
  - побочные действия
  - симптомы
  - лечение
  - диагностика
  - профилактика
  - подготовка
  - описание
  - общие сведения
  - введение
```

### 9.3. drug_forms.yaml

```yaml
forms:
  - таблетки
  - капсулы
  - раствор
  - суспензия
  - мазь
  - крем
  - капли
  - спрей
  - сироп
  - порошок
  - гель
strength_units:
  - мг
  - мкг
  - г
  - мл
  - '%'
  - ме
```

### 9.4. review.yaml

```yaml
review_top_k_per_doc: 10
review_sample_size: 300
large_doc_topic_unit_warning_threshold: 50
many_candidates_warning_threshold: 50
candidate_explosion_warning_threshold: 200
```

Важное правило: эти threshold могут создавать warnings, но не должны молча удалять кандидатов.

## 10. Алгоритм S02A

### 10.1. Step 1 — build topic units

Реализовать модуль:

```text
src/itg_kb/tagging/topic_units.py
```

Алгоритм:

1. Загрузить документы и blocks.
2. Для каждого документа с `normalization_status = ok` сгруппировать блоки по `heading_path`.
3. Каждая значимая группа под heading_path становится `heading_section`.
4. Таблицы могут становиться отдельными `table_unit`, если таблица достаточно содержательная.
5. Последовательности list_item под одним heading_path могут становиться `list_unit`.
6. Если heading нет, создать `paragraph_window` по окнам блоков.
7. Если документ маленький, можно создать один `fallback_document` unit.
8. Не терять block_ids.

Topic unit должен сохранять связь с исходными блоками.

### 10.2. Step 2 — parse title/heading into entity + facet

Реализовать модуль:

```text
src/itg_kb/tagging/entity_facet_parser.py
```

Поддержать паттерны:

```text
<entity>: <facet>
<entity> — <facet>
<entity> - <facet>
<entity>. <facet>
<facet> <entity>
как <action> <entity>
инструкция по <entity>
```

Если правая часть является facet phrase, candidate строится из левой части.

Если левая часть является generic phrase, а справа есть сущность, candidate строится из правой части.

### 10.3. Step 3 — classify entity type

Реализовать модуль:

```text
src/itg_kb/tagging/entity_classifier.py
```

Первый deterministic classifier должен работать по паттернам.

Entity types:

```text
disease
symptom
drug_brand
drug_substance
drug_product
medical_device
procedure
treatment
diagnostic_test
anatomy
contraindication
adverse_effect
document_type
medical_instruction
healthcare_process
lifestyle_prevention
organization_process
other_core_topic
unknown
```

Примеры:

```text
таблетки + мг -> drug_product
капсулы + мг -> drug_product
раствор + мл -> drug_product
общий анализ крови -> diagnostic_test
медицинские перчатки -> medical_device
как надевать ... -> medical_instruction + entity if extractable
```

### 10.4. Step 4 — generate candidates

Реализовать модуль:

```text
src/itg_kb/tagging/candidate_generator.py
```

Источники candidates:

```text
document title
first heading
all heading blocks
topic unit title / heading_path
table headers
strong list headings
strong repeated surface forms in topic unit
```

Не нужно извлекать кандидаты из каждого слова paragraph. Paragraph используется как supporting evidence и для cross-topic references только при сильных паттернах.

### 10.5. Step 5 — score candidates

Реализовать модуль:

```text
src/itg_kb/tagging/scoring.py
```

Примерные score components:

```text
title_entity_match
heading_entity_match
heading_path_match
topic_unit_position
entity_pattern_match
facet_split_confidence
frequency_in_headings
frequency_in_unit_text
cross_reference_signal
generic_penalty
dosage_only_penalty
too_short_penalty
```

Суммарный score нормализовать в 0..1.

`confidence_bucket`:

```text
high      score >= 0.80
medium    0.55 <= score < 0.80
low       score < 0.55
```

### 10.6. Step 6 — assign candidate roles

Реализовать модуль:

```text
src/itg_kb/tagging/role_classifier.py
```

Правила:

1. Лучший кандидат документа может стать `document_primary_candidate`, если score высокий и он не generic.
2. Лучший кандидат topic_unit может стать `section_topic_candidate`.
3. Важные дополнительные сущности внутри unit — `secondary_topic_candidate`.
4. Сущности в условных конструкциях — `conditional_context`.
5. Generic phrase без entity — `facet_only` или `rejected_generic`.
6. Неуверенные случаи — `needs_review`.

### 10.7. Step 7 — write artifacts and reports

Реализовать writer:

```text
src/itg_kb/tagging/stage_s02a.py
```

Он должен писать все выходные Parquet/JSONL/JSON/CSV/MD.

## 11. CLI

Добавить команды:

```bash
python -m itg_kb.cli tag-candidates --stage S02A
python -m itg_kb.cli tag-candidates --stage S02A --limit 100
python -m itg_kb.cli tag-candidates --stage S02A --doc-id <doc_id>
python -m itg_kb.cli tag-candidates --stage S02A --force
python -m itg_kb.cli validate-stage S02A
python -m itg_kb.cli audit-tag-candidates --sample-size 300
```

`--limit` ограничивает количество документов для отладки, но не количество candidates на документ.

`--doc-id` должен позволять быстро проверить один документ.

`--force` перезаписывает S02A outputs.

## 12. Review outputs

`S02A_review_sample.csv` должен содержать минимум:

```text
doc_id
title
topic_unit_id
heading_path
candidate_id
surface
core_surface
entity_type
role
facet_type
facets
score
confidence_bucket
evidence_text
warnings
needs_review
review_reason
```

`S02A_candidate_distribution.csv` должен содержать:

```text
doc_id
title
topic_unit_count
candidate_count_total
primary_candidate_count
section_candidate_count
cross_reference_count
facet_only_count
needs_review_count
warnings
```

`S02A_tagging_report.json/md` должен содержать:

```text
total_documents
processed_documents
skipped_no_blocks
total_topic_units
total_candidates
candidates_by_role
candidates_by_entity_type
candidates_by_confidence_bucket
documents_without_candidates
documents_needing_review
documents_with_many_candidates
top_generic_rejected_phrases
top_facets
outputs
```

## 13. Quality gates

S02A считается успешным, если:

```text
1. Stage не падает на 16181 документах.
2. Все candidates имеют evidence_block_ids или осознанный reason, почему evidence нет. В норме evidence обязателен.
3. tag_candidates.parquet сохраняет все candidates выше минимального threshold, без hard top_k cap.
4. topic_units.parquet создан и не пустой.
5. doc_topics.parquet создан для всех ok-документов S01.
6. facet-only phrases не становятся document_primary_candidate.
7. documents_without_candidates попадают в ambiguity_queue или needs_review.
8. no_blocks документы попадают в skipped report.
9. validate-stage S02A проверяет читаемость и обязательные колонки всех ключевых artifacts.
10. audit-tag-candidates создаёт review sample.
```

Дополнительный quality gate:

```text
Если candidate_count_total > many_candidates_warning_threshold, документ получает warning, но candidates сохраняются.
```

## 14. Тесты

Добавить tests:

```text
tests/unit/test_topic_units.py
tests/unit/test_entity_facet_parser.py
tests/unit/test_entity_classifier.py
tests/unit/test_candidate_roles.py
tests/integration/test_s02a_tag_candidates.py
```

Обязательные кейсы:

### 14.1. Drug dosage title

Input:

```text
Зиннат таблетки, покрытые пленочной оболочкой 125 мг: Способы и дозировка
```

Expected:

```text
candidate surface contains Зиннат
entity_type = drug_product
facet_type = dosage or facets include dosage
Способы и дозировка is not document_primary_candidate
```

### 14.2. Disease with facets

Input:

```text
Гастрит: симптомы и лечение
```

Expected:

```text
candidate = Гастрит
entity_type = disease or unknown with high review priority
facets include symptoms/treatment
```

### 14.3. Medical device instruction

Input:

```text
Как правильно надевать медицинские перчатки
```

Expected:

```text
candidate = медицинские перчатки
entity_type = medical_device
facet_type = instruction
```

### 14.4. Large chapter with many headings

Synthetic document with 20 headings.

Expected:

```text
topic_unit_count >= 20
candidate_count_total >= 20
no hard cap at 6 or 10
review_top_k may be 10, but tag_candidates contains all candidates
```

### 14.5. Tangled document

Input contains disease, device, symptom and treatment condition.

Expected:

```text
multiple candidates with different roles
conditional symptom is not dropped
cross-topic reference is preserved
```

## 15. Что не делать в S02A

Не использовать LLM.

Не скачивать модели.

Не вызывать внешние API.

Не делать финальную нормализацию синонимов — это S03.

Не схлопывать `Зиннат`, `Зиннат таблетки`, `Зиннат 125 мг`, `цефуроксим` в один canonical tag — это S03.

Не удалять candidates только потому, что их много.

Не считать все NER-сущности тегами.

Не превращать generic facets в primary tags.

## 16. Definition of Done

Готово, если:

```bash
make test
make lint
python -m itg_kb.cli tag-candidates --stage S02A --limit 100 --force
python -m itg_kb.cli validate-stage S02A
python -m itg_kb.cli audit-tag-candidates --sample-size 50
```

проходят успешно.

После этого нужно прогнать полный S02A:

```bash
python -m itg_kb.cli tag-candidates --stage S02A --force
python -m itg_kb.cli validate-stage S02A
python -m itg_kb.cli audit-tag-candidates --sample-size 300
```

И предоставить отчёт:

```text
S02A_tagging_report.json
S02A_tagging_report.md
S02A_review_sample.csv
S02A_candidate_distribution.csv
```

## 17. Ожидаемая обратная связь от агента

В конце работы агент должен написать:

```text
1. Какие файлы и модули добавлены.
2. Какие CLI-команды добавлены.
3. Какие тесты добавлены.
4. Результаты make test / make lint.
5. Результаты smoke run --limit 100.
6. Сколько topic_units и candidates получилось на smoke run.
7. Есть ли документы с many_candidates warning.
8. Какие ограничения текущего deterministic baseline.
9. Что предлагается делать в S02B.
```
