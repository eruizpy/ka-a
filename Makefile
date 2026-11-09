.PHONY: install test browser check demo
PYTHON ?= python3

install:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -c constraints.txt -e '.[dev,aws]'

test:
	.venv/bin/python -m pytest -q

browser:
	.venv/bin/python -m pytest qa/test_browser.py -q

check:
	.venv/bin/ruff check src tests qa
	.venv/bin/ruff format --check src tests qa

demo:
	.venv/bin/kaa demo
