"""HTML-aware text cleanup."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def has_html_markup(value: str | None) -> bool:
    return bool(value and HTML_TAG_RE.search(value))


def make_soup(raw_content: str) -> BeautifulSoup:
    return BeautifulSoup(raw_content or "", "lxml")


def clean_soup(raw_content: str) -> BeautifulSoup:
    soup = make_soup(raw_content)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup


def normalize_whitespace(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    compact: list[str] = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    return "\n".join(compact).strip()


def plain_text(raw_content: str) -> str:
    if not has_html_markup(raw_content):
        return normalize_whitespace(raw_content or "")
    soup = clean_soup(raw_content)
    return normalize_whitespace(soup.get_text("\n", strip=True))
