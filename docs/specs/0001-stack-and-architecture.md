# 0001. Stack and Architecture for Customer Segmentation Pipeline

**Date**: 2026-11-11
**Status**: Proposed

## Summary

This decision sets the core tools and folder layout for the customer segmentation project. Python (`uv` for package management) loads the raw Excel workbook into a local SQLite database, SQL scripts transform the data into metrics and customer segments, and Python exports both typed Parquet files (columnar storage files that preserve exact data types) and CSV files for Power BI Desktop and manual checks. Using local files and exported tables removes external database setup and keeps every dashboard number directly traceable to SQL.

## Context

The repository holds a single `43.5 MB` raw workbook (`dataset/online_retail_II.xlsx`) covering two years of UK online retail transactions (about `1.07 million` rows across two sheets) with no existing application code (`0` source files). The project aims to produce a public GitHub portfolio case study where a hiring reviewer can grasp headline business insights within 60 seconds and trace every dashboard metric back to reproducible SQL queries.

Local inspection shows Python `3.13.5` (with `pandas`, `openpyxl`, `scikit-learn`, `pyarrow`, and `sqlite3`), `uv 0.9.2`, and Microsoft Power BI Desktop (`2.159.1231.0`) are already installed on Windows. However, no third party SQLite or DuckDB ODBC drivers (system connectors that let desktop apps query local database files directly) are installed on the machine. Root `AGENTS.md` already drafts a baseline built around Python, SQLite, Power BI, `ruff` (Python linter and formatter), `sqlfluff` (SQL linter), and `pytest` (test framework), while `docs/scope/scope.md` requires keeping raw workbooks and local database binaries out of Git.

Without an agreed stack and file boundary up front, the pipeline risks breaking Power BI imports on machines lacking ODBC drivers, drifting Python dependencies across environments, or bloating Git history with binary files. Every tool choice also needs to let automated tests and continuous integration run cleanly on GitHub even when the `43.5 MB` raw workbook is excluded from version control.

## Options considered

### Option 1: Local SQLite with `uv`, Dual Parquet and CSV BI Exports, and a Single `.pbix` Report

Python manages dependencies with `uv` (`pyproject.toml` and `uv.lock`), loads raw sheets via `openpyxl` and `pandas` into a local SQLite `3.49.1` database, runs idempotent (safe to rerun) SQL scripts in `sql/`, and exports analytical tables to both Parquet (for typed Power BI Desktop import) and CSV (for quick spreadsheet inspection) under an ignored `exports/` directory `(basis: AGENTS.md baseline, local environment check, Power BI built in Parquet connector)`. Quality gates use `ruff`, `sqlfluff` (`--dialect sqlite`), `ty` (fast Python type checker), and `pytest` backed by small synthetic fixtures in `tests/fixtures/` `(basis: modern-python skill, sqlfluff SQLite dialect support)`.

**Pros**:
- Zero database server or Windows ODBC driver installation required on any machine opening the project or `.pbix` report.
- Aligns directly with `AGENTS.md` (`scripts/`, `sql/`, `notebooks/`, `powerbi/`, `images/`, `docs/`) and tools already installed locally (`uv 0.9.2`, `sqlite3`, `pyarrow`, Power BI Desktop).
- Deterministic `uv.lock` environments plus synthetic fixtures keep GitHub Actions CI green without committing the `43.5 MB` workbook.

**Cons**:
- Requires rerunning the Python pipeline runner to refresh `exports/` before refreshing Power BI Desktop visuals.
- Writing both Parquet and CSV exports adds modest local disk use and two output files per mart table.
- A single `.pbix` binary does not produce readable text diffs in Git pull requests (unlike `.pbip` project folders).

### Option 2: DuckDB Analytical Engine with Parquet Pipeline and DuckDB Power Query Custom Connector

Replace SQLite with DuckDB (`duckdb` Python package) as an embedded analytical column store, query tables directly with DuckDB SQL, and connect Power BI Desktop to the `.duckdb` file via the DuckDB ODBC driver plus the unsigned DuckDB Power Query `.mez` custom connector `(basis: DuckDB Power Query connector documentation)`.

**Pros**:
- Faster analytical aggregations and native SQL `COPY ... TO ... (FORMAT PARQUET)` exports without Python serialization.
- Built in column pruning and rich analytical window functions.

**Cons**:
- Requires installing the DuckDB ODBC driver, copying a custom `.mez` extension, and lowering Power BI Desktop extension security settings on every Windows machine opening the report `(basis: DuckDB Power Query connector documentation)`.
- Conflicts with the existing `AGENTS.md` SQLite baseline and `sqlite-best-practices` skill already installed in the repo.

### Option 3: Local PostgreSQL Server with Native Power BI Connector and `pip`

Run a local PostgreSQL server instance, load and transform retail tables inside PostgreSQL schemas, connect Power BI Desktop using its native PostgreSQL connector, and manage Python libraries with `pip` and `requirements.txt` `(basis: Power BI native database connectors)`.

**Pros**:
- Live native Power BI Desktop connection without intermediate export files or third party ODBC drivers.
- Full server grade SQL features and multi user concurrency.

**Cons**:
- Forces every reviewer or contributor to install, start, and secure a PostgreSQL service locally for a single user static two year dataset.
- Plain `requirements.txt` lacks transitive hash locking unless paired with extra tools, weakening reproducibility compared to `uv.lock` `(basis: uv lockfile workflow)`.

## Decision

**Chosen option**: Option 1: Local SQLite with `uv`, Dual Parquet and CSV BI Exports, and a Single `.pbix` Report

Adopt a local batch analytics monolith anchored on Python `3.13.5` (`uv` in application mode `[tool.uv] package = false` with `pyproject.toml` and `uv.lock`), SQLite `3.49.1` (`retail.db` at repository root via Python `sqlite3`), ordered idempotent SQL scripts in `sql/`, flat `exports/<table_name>.parquet` and `exports/<table_name>.csv` outputs in an ignored `exports/` folder consumed via a `DataDirectory` parameter inside Power BI Desktop (`.pbix` plus PNG screenshots), an output stripped Jupyter notebook (`nbstripout`) paired with a pure Python clustering module, `ruff` + `sqlfluff` + gradual `ty` (with `pandas-stubs`) + `pytest` quality gates wired into `pre-commit` and GitHub Actions, and isolated Markdown tracking (`docs/ai_log.md` and `docs/campaign_recommendations_memo.md`).

**Implementation skills**: `modern-python` (`trailofbits/skills`, `.agents/skills/modern-python/`) · `pandas-pro` (`Jeffallan/claude-skills`, `.agents/skills/pandas-pro/`) · `xlsx` (`anthropics/skills`, `.agents/skills/xlsx/`) · `sqlite-best-practices` (`erayack/sqlite-best-practices`, `.agents/skills/sqlite-best-practices/`) · `sqlfluff` (`ivanshamaev/de-agent-skills`, `.agents/skills/sqlfluff/`) · `scikit-learn` (`K-Dense-AI/scientific-agent-skills`, `.agents/skills/scikit-learn/`) · `pytest-coverage` (`github/awesome-copilot`, `.agents/skills/pytest-coverage/`) · `ruff-linting` (`laurigates/claude-plugins`, `.agents/skills/ruff-linting/`) · `powerbi-modeling` (`github/awesome-copilot`, `.agents/skills/powerbi-modeling/`) · `semantic-model-authoring` (`microsoft/skills-for-fabric`, `.agents/skills/semantic-model-authoring/`) · `python-precommit` (`paldom/python-skills`, `.agents/skills/python-precommit/`) · `python-ci` (`paldom/python-skills`, `.agents/skills/python-ci/`) · `jupyter-notebook` (`openai/skills`, `.agents/skills/jupyter-notebook/`) · `pdf` (`anthropics/skills`, global skill for optional memo PDF export)

## Rationale

This stack matches the operational reality of a single analyst portfolio project: the dataset is a fixed `1.07 million` row historical snapshot (`dataset/online_retail_II.xlsx`), so a serverless embedded SQLite engine handles every query in seconds with zero background services to run or debug `(basis: AGENTS.md baseline, local monolith batch pattern)`. Because Windows has no SQLite or DuckDB ODBC driver installed and Power BI Desktop has no native SQLite connector, exporting clean mart tables via Python (`pyarrow` for Parquet and `pandas` for CSV) guarantees Power BI reads exact dates and numbers on any Windows machine with zero driver setup while letting reviewers inspect CSV files directly in Excel `(basis: local environment check, Power BI built in Parquet connector)`.

Standardizing on `uv` (`pyproject.toml` plus `uv.lock`) instead of plain `pip` uses the `uv 0.9.2` binary already installed locally and gives deterministic dependency resolution for both local runs and GitHub Actions `(basis: uv lockfile workflow, modern-python skill)`. Keeping pure transform code inside a `scripts/` package (`__init__.py`) and testing with small synthetic Excel and SQLite fixtures in `tests/fixtures/` honors the folder rules in `AGENTS.md` and keeps CI fast and self contained even though the `43.5 MB` workbook is gitignored `(basis: AGENTS.md folder layout, GitHub large file limits)`.

## Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Architecture pattern | Local batch analytics pipeline (monolith) | Simplest structure for a single analyst transforming a fixed two year snapshot into SQL views and BI tables. |
| Python runtime and packaging | Python `3.13.5` with `uv` (`[tool.uv] package = false`), `pyproject.toml`, and `uv.lock` | `uv 0.9.2` is already installed locally, application mode avoids wheel build errors, and `uv.lock` keeps environments deterministic. |
| Code layout | `scripts/` package (`__init__.py`), `sql/`, `tests/` (`pythonpath = ["."]`) | Preserves `AGENTS.md` folder layout while letting `pytest` import stateless transform functions cleanly. |
| Local SQL database | SQLite `3.49.1` at `retail.db` (repo root) via Python stdlib `sqlite3` | Zero install relational engine in Python stdlib that keeps `dataset/` untouched, fits `1.07M` rows, and pairs with `sqlfluff`. |
| Pipeline runner | Single idempotent Python runner in `scripts/` | Rebuilds `retail.db` from Excel, runs ordered `sql/` scripts, writes exports, and catches Windows file lock errors (`WinError 32`) cleanly. |
| BI data bridge | Flat `exports/<table_name>.parquet` (`pyarrow`) and `.csv` outputs | Parquet preserves exact column types in Power BI without ODBC drivers; CSV allows quick spreadsheet checks. |
| BI reporting | Single `.pbix` in `powerbi/` (with `DataDirectory` parameter) plus PNG exports in `images/` | Parameterized Power Query paths keep clones portable across machines while `.pbix` gives reviewers one click access. |
| Clustering validation | Pure Python module in `scripts/` + `.ipynb` in `notebooks/` with `nbstripout` | Keeps reusable `scikit-learn` logic testable while `nbstripout` automatically removes noisy cell outputs before commit. |
| Quality gates | `ruff`, `sqlfluff` (`sqlite` dialect), and gradual `ty` with `pandas-stubs` | Fast unified Python lint and format, SQLite linting, and gradual static type checks that avoid third party stub failures in CI. |
| Automation and testing | `pytest` with `tests/fixtures/`, `pre-commit` (`nbstripout`, hooks), and GitHub Actions | Synthetic fixtures keep CI fast and green without the `43.5 MB` Excel file while optional checks verify full data locally. |
| Version control exclusions | `.gitignore` for `dataset/*.xlsx`, `*.db*`, `*.sqlite*`, `exports/`, `.venv/`, caches, plus `.gitkeep` | Satisfies `scope.md` exclusion rule, covers SQLite WAL artifacts (`-wal`, `-shm`) and Power BI lock files, and keeps empty folders tracked. |
| Docs and Phase 2 isolation | `docs/ai_log.md`, Markdown memo (optional PDF), `phase2_ga4/` | Separates stakeholder prose from code and keeps any future BigQuery GA4 funnel isolated from core dependencies. |

## Consequences

**Positive**:
- Any reviewer or teammate can clone the repository, run `uv sync`, place the dataset in `dataset/`, and rebuild the entire database and BI exports with one command.
- Power BI Desktop imports typed Parquet tables cleanly on any Windows PC without installing third party ODBC drivers or lowering security settings.
- Synthetic fixtures in `tests/fixtures/` guarantee every commit is verified in GitHub Actions even when the raw `43.5 MB` workbook is absent.

**Negative / tradeoffs**:
- Updating a SQL script requires rerunning the pipeline runner before refreshing Power BI Desktop, and Power BI Desktop must be closed on Windows before rewriting `exports/` files due to OS file locks (`WinError 32`).
- Exporting both Parquet and CSV creates two files per mart table inside `exports/` and uses extra local disk space.
- Storing the dashboard as a `.pbix` binary means Power BI layout and DAX measure edits cannot be reviewed as line by line text diffs in Git.
- Switching from `pip` to `uv` and adding `ty`, `pyarrow`, `nbstripout`, and `pre-commit` means `AGENTS.md` and the build steps need updating before implementation starts.

**Neutral**:
- Raw data acquisition moves from repository storage to explicit download steps in `README.md` pointing to the UCI Online Retail II release.
- Future Phase 2 BigQuery GA4 exploration stays quarantined inside `phase2_ga4/` with no impact on core SQLite dependencies.

## Follow-up

- [ ] Update root `AGENTS.md`: replace `pip` with `uv`, document `retail.db`, `ty`, `pre-commit`, `nbstripout`, `pyarrow`, `pandas-stubs`, `exports/`, and `tests/`, add the newly installed skills (`python-precommit`, `python-ci`, `jupyter-notebook`), note the global `pdf` skill if used for memo export, and record `optimizing-parquet-storage` as skipped for now.
- [ ] Connect your two selected optional MCP servers in your user or workspace MCP settings: `mcp-server-sqlite` (via `uvx mcp-server-sqlite --db-path retail.db`) and `@microsoft/powerbi-modeling-mcp` (via `npx -y @microsoft/powerbi-modeling-mcp@latest --start`) so agents can inspect live SQLite tables and Power BI models later.
- [ ] Scaffold Feature 1 (`Stack and architecture`): create the clean directory skeleton (with `.gitkeep` in `dataset/` and `exports/`), write `.gitignore`, and initialize `docs/ai_log.md`.
- [ ] Configure Feature 2 (`Coding standards and tooling`): set up `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml` (including `nbstripout`, `ruff`, `sqlfluff`, and `ty`), and the GitHub Actions CI workflow.

## References

**Project sources**:
- `AGENTS.md` (initial `/audit` conventions, folder layout, SQLite `3.49.1`, and `sqlfluff`/`ruff`/`pytest` baseline)
- `docs/scope/scope.md` (Feature 1 scope and exclusion of raw datasets and local database binaries from version control)
- `Portfolio Project Brief Customer Segmentation and Campaign Recommendations.md` (UCI Online Retail II dataset rules, business questions, and deliverables)
- `10-Step Project Roadmap.md` (local environment profile and ordered SQL script plan)
- Installed skills in `.agents/skills/` (`modern-python`, `sqlite-best-practices`, `sqlfluff`, `python-precommit`, `python-ci`, `jupyter-notebook`, and companion project skills)

**Practices & standards**:
- Local batch analytics monolith pattern (`agent-modes/architecture.md`)
- Deterministic lockfiles (`uv.lock`) and PEP 735 dependency groups (`modern-python`)
- Idempotent SQL pipeline execution and synthetic CI test fixtures
- Power BI Desktop built in Parquet connector pattern (avoiding unconfigured local ODBC drivers)
- GitHub repository file size guidance (`50 MiB` warning, `100 MiB` block)

**Links**:
- UCI Machine Learning Repository Online Retail II dataset: https://archive.ics.uci.edu/dataset/502/online+retail+ii
- Model Context Protocol Reference Servers (`mcp-server-sqlite` source): https://github.com/modelcontextprotocol/servers
- `mcp-server-sqlite` package on PyPI: https://pypi.org/project/mcp-server-sqlite/
- Microsoft Power BI Modeling MCP Server: https://github.com/microsoft/powerbi-modeling-mcp
- SQLite ODBC Driver by Christian Werner (evaluated ODBC option): http://www.ch-werner.de/sqliteodbc/
- MotherDuck DuckDB Power Query Connector (evaluated DuckDB option): https://github.com/MotherDuck-Open-Source/duckdb-power-query-connector/releases/latest
- `paldom/python-skills` registry page (`python-precommit`, `python-ci`): https://skills.sh/Paldom/python-skills
- `openai/skills` registry page (`jupyter-notebook`): https://skills.sh/openai/skills

