.PHONY: run test ingest debug backup docs-sync

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

docs-sync:
	@echo "Sincronizando .md para Google Drive..."
	$(PYTHON) -c "\
import shutil, os; from pathlib import Path; \
dst = Path(os.environ['USERPROFILE']) / 'Google Drive' / 'voxdm-docs'; \
dst.mkdir(parents=True, exist_ok=True); \
[shutil.copy(f, dst / f.name) for f in Path('.').rglob('*.md') \
 if '.venv' not in f.parts and '.pytest_cache' not in f.parts]; \
print('Docs sincronizados.')"
