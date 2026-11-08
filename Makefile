VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_READY := $(VENV)/.ready

.DEFAULT_GOAL := help
.PHONY: help install run check test lint format build clean

help: ## Show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

$(VENV_READY): pyproject.toml uv.lock
	uv sync --locked
	$(VENV_PYTHON) -m pre_commit install
	@touch $(VENV_READY)

install: $(VENV_READY) ## Create .venv with uv and install the git hook

run: $(VENV_READY) ## Open the app from source
	$(VENV_PYTHON) main.py

check: $(VENV_READY) ## Print available updates
	$(VENV_PYTHON) main.py --check

test: $(VENV_READY) ## Run the test suite
	$(VENV_PYTHON) -B -m unittest discover -s tests

lint: $(VENV_READY) ## Check style and types
	$(VENV_PYTHON) -m ruff check .
	$(VENV_PYTHON) -m ruff format --check .
	$(VENV_PYTHON) -B scripts/space_blocks.py --check
	$(VENV_PYTHON) -m mypy
	$(VENV_PYTHON) -m pyright

format: $(VENV_READY) ## Fix style problems and format the code
	$(VENV_PYTHON) -m ruff check --fix .
	$(VENV_PYTHON) -B scripts/space_blocks.py
	$(VENV_PYTHON) -m ruff format .
	@# Formatting can split a bracket over lines, which COM812 then gives a trailing comma.
	$(VENV_PYTHON) -m ruff check --fix --select COM812 .
	$(VENV_PYTHON) -m ruff format .

build: $(VENV_READY) ## Build dist/NXDesk-<platform>-<arch>.zip
	$(VENV_PYTHON) -B scripts/build.py

clean: ## Remove build output, the build environment and caches
	rm -rf dist $(VENV)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
