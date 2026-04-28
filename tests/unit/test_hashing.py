from itg_kb.core.hashing import content_hash, stable_hash
from itg_kb.core.ids import make_doc_id


def test_stable_hash_is_deterministic() -> None:
    assert stable_hash("abc") == stable_hash("abc")
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_doc_id_is_stable_for_same_input() -> None:
    hash_value = content_hash("same content")
    first = make_doc_id(source_id=None, name="Document", content_hash_value=hash_value)
    second = make_doc_id(source_id=None, name="Document", content_hash_value=hash_value)
    assert first == second
    assert first.startswith("doc_")
