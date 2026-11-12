# Verify: Stack and architecture (spec 0001)

## Commands

- [x] `git check-ignore dataset/online_retail_II.xlsx retail.db retail.db-wal retail.db-shm exports/customers.parquet exports/customers.csv .venv/ ~report.pbix` (verifies all eight raw, local database, export, and temporary paths stay excluded from version control)
- [x] `uv run python -c "import os, glob; dirs = ['dataset', 'exports', 'images', 'notebooks', 'powerbi', 'scripts', 'sql', 'tests', 'docs']; ..."` (verifies clean skeleton existence across all nine project folders plus seven gitkeep tracking files)
- [x] `uv run python -c "import scripts; import tests; import sqlite3; import pandas; import pyarrow; import sklearn"` (verifies clean Python boot and dependency resolution across core libraries)
- [x] `uv run python -c "from pathlib import Path; ..."` (verifies ai_log baseline tracking for dataset caveats and initial architecture entry)
- [x] `uv run pytest tests/test_tooling.py` (verifies all fourteen automated tooling and stack tests pass cleanly)

## Surfaces

- [x] Version control ignore file (`.gitignore`) covering raw data, database files, exports, and tool caches
- [x] Directory skeleton (`dataset`, `exports`, `images`, `notebooks`, `powerbi`, `scripts`, `sql`, `tests`, `docs`)
- [x] Tracking baseline file (`docs/ai_log.md`) with three dataset caveats and verification standards
- [x] Package initialization files (`scripts/__init__.py`, `tests/__init__.py`)
- [x] Spec record (`docs/specs/0001-stack-and-architecture.md`)

## Acceptance criteria coverage

- AC 1: The architecture decision and chosen stack are recorded in Spec 0001 (met)
- AC 2: Raw workbook files in dataset/ and local SQLite binaries are ignored by git (met)
- AC 3: Export directories and temporary Power BI artifacts are ignored by git while keeping folder structure tracked (met)
- AC 4: Directory skeleton and Python packages boot cleanly without missing paths (met)
- AC 5: AI workflow log baseline is established in docs/ai_log.md with three core dataset caveats (met)
