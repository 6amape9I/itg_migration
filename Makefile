PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff

.PHONY: setup test lint format init-dirs smoke

setup:
	@if command -v uv >/dev/null 2>&1; then uv sync --extra dev; else if [ ! -x "$(PYTHON)" ]; then python3 -m venv .venv; fi; $(PYTHON) -m pip install -e ".[dev]"; fi

test:
	$(PYTEST)

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

init-dirs:
	$(PYTHON) -m itg_kb.cli init-dirs

smoke:
	$(PYTHON) scripts/smoke_run.py
