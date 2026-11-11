# Customer Segmentation and Campaign Recommendations

## Stack

- **Language / Runtime**: Python 3.13.5, SQL (SQLite 3.49.1 local engine)
- **BI / Reporting**: Power BI (two page `.pbix` report and exported screenshots)
- **Key dependencies**: `pandas`, `openpyxl`, `scikit-learn`, `sqlite3`
- **Package manager**: `pip` (planned tooling: `ruff`, `sqlfluff`, `pytest`)

## Build approach

<TBD, set by /scope>

## Commands

```bash
python scripts/load_to_sql.py          # Load raw Excel sheets into SQLite
ruff check . && ruff format --check .  # Lint and format Python
sqlfluff lint sql/ --dialect sqlite    # Lint SQL scripts
pytest                                 # Run tests and SQL checks
```

## Git

- integration: on
- branch prefix: analysis/
- commit: per-milestone

## Tooling

- **Lint and format**: `ruff` (Python) and `sqlfluff` (SQL), installed by `/develop tooling`
- **Checks before commit**: `pre-commit` running lint, format, and Python type checks
- **Testing and CI**: `pytest` plus SQL reconciliation checks; GitHub Actions on push

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- **Functional pipeline**: write pure, stateless transform functions; keep file and DB I/O at script edges; never mutate inputs in place.
- **Explicit failures**: validate input file paths, sheet names, and columns at startup; raise explicit errors instead of silent fallbacks.
- **Folder layout**: keep raw input untouched in `dataset/`, Python in `scripts/`, SQL in `sql/`, `notebooks/`, `powerbi/`, `images/`, and `docs/`.
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
MCP servers: `mcp-server-sqlite` (recommended), `@microsoft/powerbi-modeling-mcp` (recommended)

## Context files

<!-- Nested AGENTS.md files are listed here as they are created -->

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._

