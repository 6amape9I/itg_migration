"""Russian NER placeholder.

No NER model is downloaded or imported during bootstrap.
"""

from __future__ import annotations


class RussianNerExtractor:
    def extract(self, _text: str) -> list[dict[str, object]]:
        return []
