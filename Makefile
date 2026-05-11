.PHONY: run run-api test ingest ingest-rules debug backup docs-sync

# Usa uv run — sem ativar venv manualmente
PYTHON := uv run python
PYTEST := uv run pytest

run: run-api

run-api:
	$(PYTHON) -m uvicorn api.main:app --reload --reload-dir api --reload-dir engine --host 0.0.0.0 --port 8000

test:
	$(PYTEST) tests/ -v

ingest:
	$(PYTHON) main.py

ingest-rules:
	$(PYTHON) ingest_rules.py

debug:
	$(PYTHON) dashboard.py

backup:
	@echo "Backup de .env e modulo_teste..."
	@cp .env .env.backup
	@cp -r modulo_teste modulo_teste.backup
	@echo "Backup concluído."

docs-sync:
	@echo "Sincronizando .md para Google Drive..."
	$(PYTHON) -c "\
import shutil, os; from pathlib import Path; \
dst = Path(os.environ['USERPROFILE']) / 'Google Drive' / 'voxdm-docs'; \
dst.mkdir(parents=True, exist_ok=True); \
[shutil.copy(f, dst / f.name) for f in Path('.').rglob('*.md') \
 if '.venv' not in f.parts and '.pytest_cache' not in f.parts]; \
print('Docs sincronizados.')"
