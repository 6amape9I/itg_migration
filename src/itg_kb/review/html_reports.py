"""HTML report placeholder."""

from __future__ import annotations


def render_html_report(title: str, body: str) -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>"
