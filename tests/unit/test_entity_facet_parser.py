from pathlib import Path

from itg_kb.tagging.entity_facet_parser import EntityFacetParser

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "tagging"


def test_drug_dosage_title_splits_entity_and_facet() -> None:
    parser = EntityFacetParser.from_config_dir(CONFIG_DIR)

    parsed = parser.parse(
        "Зиннат таблетки, покрытые пленочной оболочкой 125 мг: Способы и дозировка"
    )

    assert "Зиннат" in parsed.surface
    assert parsed.core_surface == "Зиннат"
    assert parsed.facet_type == "dosage"
    assert "dosage" in parsed.facets


def test_disease_title_splits_multiple_facets() -> None:
    parser = EntityFacetParser.from_config_dir(CONFIG_DIR)

    parsed = parser.parse("Гастрит: симптомы и лечение")

    assert parsed.surface == "Гастрит"
    assert {"symptoms", "treatment"} <= set(parsed.facets)


def test_medical_device_instruction_extracts_entity() -> None:
    parser = EntityFacetParser.from_config_dir(CONFIG_DIR)

    parsed = parser.parse("Как правильно надевать медицинские перчатки")

    assert parsed.surface == "медицинские перчатки"
    assert parsed.facet_type == "instruction"
