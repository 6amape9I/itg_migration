"""Structured output validation helpers."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_payload(model: type[ModelT], payload: dict[str, object]) -> ModelT:
    return model.model_validate(payload)


def schema_for(model: type[BaseModel]) -> dict[str, object]:
    return model.model_json_schema()
