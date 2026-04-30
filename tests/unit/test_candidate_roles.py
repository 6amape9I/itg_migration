from pathlib import Path

from itg_kb.tagging.candidate_generator import generate_candidates_for_document
from itg_kb.tagging.entity_classifier import EntityClassifier
from itg_kb.tagging.entity_facet_parser import EntityFacetParser
from itg_kb.tagging.scoring import load_scoring_config
from itg_kb.tagging.topic_units import build_topic_units_for_document

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "tagging"


def test_drug_dosage_title_candidate_is_entity_not_facet_primary() -> None:
    candidates = _candidates_for(
        title="Зиннат таблетки, покрытые пленочной оболочкой 125 мг: Способы и дозировка",
        blocks=[],
    )

    drug = next(candidate for candidate in candidates if "Зиннат" in candidate.surface)
    assert drug.entity_type == "drug_product"
    assert "dosage" in drug.facets
    assert drug.role == "document_primary_candidate"
    assert not any(
        candidate.surface == "Способы и дозировка"
        and candidate.role == "document_primary_candidate"
        for candidate in candidates
    )


def test_large_heading_document_has_no_persisted_candidate_cap() -> None:
    blocks = []
    for index in range(20):
        blocks.append(
            _block(
                f"h{index}",
                index * 2 + 1,
                "heading",
                f"Гастрит {index}",
                [f"Гастрит {index}"],
            )
        )
        blocks.append(
            _block(
                f"p{index}",
                index * 2 + 2,
                "paragraph",
                "Описание раздела про гастрит.",
                [f"Гастрит {index}"],
            )
        )

    document = {"doc_id": "doc_test", "title": "Большая глава"}
    units = build_topic_units_for_document(document, blocks)
    candidates = _candidates_for(title=document["title"], blocks=blocks)

    assert len(units) >= 20
    assert len(candidates) >= 20


def test_tangled_document_preserves_multiple_roles() -> None:
    candidates = _candidates_for(
        title="Смешанный документ",
        blocks=[
            _block(
                "p1",
                1,
                "paragraph",
                (
                    "Грипп можно лечить в условиях использования медицинских перчаток "
                    "только если отсутствует симптом X."
                ),
                [],
            )
        ],
    )

    by_type = {candidate.entity_type: candidate for candidate in candidates}
    roles = {candidate.role for candidate in candidates}
    assert "disease" in by_type
    assert "medical_device" in by_type
    assert "symptom" in by_type
    assert "conditional_context" in roles
    assert "cross_topic_reference" in roles or "section_topic_candidate" in roles
    assert any(candidate.role == "facet_only" for candidate in candidates)


def _candidates_for(title: str, blocks: list[dict[str, object]]):
    document = {"doc_id": "doc_test", "title": title, "normalization_status": "ok"}
    units = build_topic_units_for_document(document, blocks)
    parser = EntityFacetParser.from_config_dir(CONFIG_DIR)
    classifier = EntityClassifier.from_config_dir(CONFIG_DIR)
    scoring_config = load_scoring_config(CONFIG_DIR)
    candidates, _ = generate_candidates_for_document(
        document,
        blocks,
        units,
        parser=parser,
        classifier=classifier,
        scoring_config=scoring_config,
    )
    return candidates


def _block(
    block_id: str, order: int, block_type: str, text: str, heading_path: list[str]
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "doc_id": "doc_test",
        "order": order,
        "type": block_type,
        "text": text,
        "heading_path": heading_path,
        "char_start": order * 10,
        "char_end": order * 10 + len(text),
        "metadata": {},
    }
