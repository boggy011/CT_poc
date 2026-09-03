.PHONY: install lint format typecheck test test-cov contract-delta contract-lakebase run-mock run-sqlite migrate-sqlite migrate-delta users security check

install:
	uv sync --all-extras

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy

test:
	uv run pytest

test-cov:
	uv run pytest --cov --cov-report=term-missing

contract-delta:
	RETPACK_TEST_DELTA=1 uv run pytest tests/contract -k delta

contract-lakebase:
	RETPACK_TEST_LAKEBASE=1 uv run pytest tests/contract -k lakebase

run-sqlite:
	RETPACK_SUBMISSION_BACKEND=sqlite RETPACK_MOCK_SEED=1 uv run streamlit run src/retpack_ui/app.py

migrate-sqlite:
	uv run python -m retpack_adapters.migrate_cli sqlite

migrate-delta:
	uv run python -m retpack_adapters.migrate_cli delta

# Provision portal users in the workspace dev tables, e.g. make users ARGS="add-internal someone@abi.example"
users:
	uv run python -m retpack_adapters.users_cli $(ARGS)

run-mock:
	RETPACK_SUBMISSION_BACKEND=mock RETPACK_MOCK_SEED=1 uv run streamlit run src/retpack_ui/app.py

security:
	uv run bandit -q -r src -c pyproject.toml
	uv run pip-audit --skip-editable

check: lint typecheck test-cov security
