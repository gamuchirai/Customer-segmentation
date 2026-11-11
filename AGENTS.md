# Customer Segmentation and Campaign Recommendations

## Stack

- **Language / Runtime**: Python 3.13.5, SQL (SQLite 3.49.1 local engine at `retail.db`)
- **BI / Reporting**: Power BI (two page `.pbix` report in `powerbi/` reading flat `.parquet` and `.csv` tables from `exports/`, plus exported screenshots in `images/`)
- **Key dependencies**: `pandas`, `openpyxl`, `scikit-learn`, `pyarrow`, `sqlite3` (stdlib)
- **Package manager**: `uv` (`[tool.uv] package = false`, `pyproject.toml`, `uv.lock`; dev tools: `ruff`, `sqlfluff`, `ty` with `pandas-stubs`, `pytest`, `pytest-cov`, `pre-commit`, `nbstripout`)

## Build approach

<TBD, set by /scope>

## Commands

```bash
uv sync                                              # Install runtime and dev dependencies from uv.lock
uv run python scripts/load_to_sql.py                 # Load raw Excel sheets into retail.db (SQLite)
uv run ruff check . && uv run ruff format --check .  # Lint and format Python
uv run sqlfluff lint sql/ --dialect sqlite           # Lint SQL scripts
uv run ty check                                      # Type check Python with gradual ty
uv run pytest                                        # Run tests and SQL checks
uv run pre-commit install                            # Install pre-commit and pre-push git hooks
uv run pre-commit run --all-files                    # Run all commit-stage hooks manually
```

## Git

- integration: on
- branch prefix: analysis/
- commit: per-milestone

## Tooling

- **Lint and format**: `ruff` (Python), `sqlfluff` (SQLite dialect via `.sqlfluff`), and `nbstripout` (strip notebook cell outputs)
- **Type checking**: `ty` (gradual static type checks with `pandas-stubs`)
- **Checks before commit and push**: `pre-commit` running hygiene checks, `ruff`, `nbstripout`, `sqlfluff`, `validate-pyproject`, and `check-jsonschema` at commit, plus `ty` on `pre-push`
- **Testing and CI**: `pytest` (with `pytest-cov` and synthetic fixtures in `tests/fixtures/`) plus SQL reconciliation checks; GitHub Actions (`.github/workflows/ci.yml`) on push, pull request, and merge group

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- **Functional pipeline**: write pure, stateless transform functions; keep file and DB I/O at script edges; never mutate inputs in place.
- **Explicit failures**: validate input file paths, sheet names, and columns at startup; raise explicit errors instead of silent fallbacks.
- **Folder layout**: keep raw input untouched in `dataset/`, Python in `scripts/`, SQL in `sql/`, tests and synthetic fixtures in `tests/` (`tests/fixtures/`), `notebooks/`, `powerbi/`, `images/`, `docs/`, and gitignored `retail.db` and `exports/`.
- **Types and docs**: add gradual Python type hints, function docstrings, and SQL header comments explaining business rules.
- **Naming and SQL**: use `snake_case` across Python and SQL; write idempotent SQL (`DROP IF EXISTS` or `CREATE`) safe to rerun.
- **Commits**: use conventional commit messages (`feat:`, `fix:`, `docs:`); always confirm before pushing or opening PRs.

## Agent skills

- [modern-python](.agents/skills/modern-python/): `trailofbits/skills`, modern Python tooling and clean patterns
- [pytest-coverage](.agents/skills/pytest-coverage/): `github/awesome-copilot`, pytest test design and coverage checks
- [ruff-linting](.agents/skills/ruff-linting/): `laurigates/claude-plugins`, ruff Python linting and formatting
- [pandas-pro](.agents/skills/pandas-pro/): `jeffallan/claude-skills`, pandas DataFrame cleaning and aggregation
- [xlsx](.agents/skills/xlsx/): `anthropics/skills`, Excel spreadsheet reading and validation
- [scikit-learn](.agents/skills/scikit-learn/): `k-dense-ai/scientific-agent-skills`, scikit-learn scaling and clustering pipelines
- [sqlite-best-practices](.agents/skills/sqlite-best-practices/): `erayack/sqlite-best-practices`, SQLite schema design and query optimization
- [sqlfluff](.agents/skills/sqlfluff/): `ivanshamaev/de-agent-skills`, sqlfluff SQL linting and formatting
- [powerbi-modeling](.agents/skills/powerbi-modeling/): `github/awesome-copilot`, Power BI semantic models and DAX measures
- [semantic-model-authoring](.agents/skills/semantic-model-authoring/): `microsoft/skills-for-fabric`, Power BI tables, columns, and measures
- [python-precommit](.agents/skills/python-precommit/): `paldom/python-skills`, pre-commit hook setup and CI sync
- [python-ci](.agents/skills/python-ci/): `paldom/python-skills`, GitHub Actions quality-gate workflows and SHA pinning
- [jupyter-notebook](.agents/skills/jupyter-notebook/): `openai/skills`, clean Jupyter notebook scaffolding
- Global `pdf` skill: optional Markdown memo PDF export (not installed locally in `.agents/skills/`)
- Skipped skills: `optimizing-parquet-storage` (skipped for now; BI exports are small flat mart tables)
MCP servers: `mcp-server-sqlite` (recommended), `@microsoft/powerbi-modeling-mcp` (recommended)

## Context files

<!-- Nested AGENTS.md files are listed here as they are created -->

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
