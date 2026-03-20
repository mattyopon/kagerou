.PHONY: install dev test lint typecheck quality clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	python3 -m pytest tests/ -q --tb=short

lint:
	python3 -m ruff check src/ tests/

typecheck:
	python3 -m mypy src/kagerou/ --strict

quality: lint typecheck test

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
