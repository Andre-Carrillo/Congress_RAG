.PHONY: install install-all ingest chunks index app test lint clean

install:
	uv sync

install-all:
	uv sync --extra all

ingest:
	uv run python scripts/ingest.py

chunks:
	uv run python scripts/ingest.py --skip-db

index:
	uv run python scripts/build_index.py

app:
	uv run streamlit run src/congress_rag/ui/app.py

test:
	uv run pytest

test-integration:
	uv run pytest -m integration

lint:
	uv run ruff check src scripts tests

clean:
	rm -rf data/processed/*.db data/processed/*.jsonl data/processed/*.csv data/chroma
