"""Stage report schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StageReport(BaseModel):
    stage: str
    status: str
    started_at: str
    finished_at: str
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors_sample: list[dict[str, Any]] = Field(default_factory=list)
