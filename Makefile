.PHONY: run test ingest debug backup

PYTHON := .venv/Scripts/python
PYTEST := .venv/Scripts/pytest

run:
	$(PYTHON) -m uvicorn api.main:app --reload

test:
	$(PYTEST) tests/ -v

ingest:
	$(PYTHON) main.py

debug:
	$(PYTHON) dashboard.py

backup:
	@echo "Backup de .env e modulo_teste..."
	@cp .env .env.backup
	@cp -r modulo_teste modulo_teste.backup
	@echo "Backup concluído."
