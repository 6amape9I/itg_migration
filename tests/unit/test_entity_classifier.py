from pathlib import Path

from itg_kb.tagging.entity_classifier import EntityClassifier

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "tagging"


def test_classifier_detects_required_examples() -> None:
    classifier = EntityClassifier.from_config_dir(CONFIG_DIR)

    assert classifier.classify("Зиннат таблетки 125 мг").entity_type == "drug_product"
    assert classifier.classify("Общий анализ крови").entity_type == "diagnostic_test"
    assert classifier.classify("медицинские перчатки").entity_type == "medical_device"
    assert classifier.classify("Гастрит").entity_type == "disease"
