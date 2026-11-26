PYTHON ?= python3
SCRIPTS := scripts/ci_sdk.py scripts/sdk_inputs.py ci/verify_apps.py

.PHONY: check

check:
	$(PYTHON) -m ruff format --check $(SCRIPTS)
	$(PYTHON) -m ruff check $(SCRIPTS)
	$(PYTHON) -m mypy --strict --scripts-are-modules $(SCRIPTS)
