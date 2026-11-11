import configparser
import importlib
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(_read_text("pyproject.toml"))


def _extract_precommit_rev(config_text: str, repo_url: str) -> str:
    pattern = rf"- repo:\s*{re.escape(repo_url)}\s*\n\s*rev:\s*([^\s#]+)"
    match = re.search(pattern, config_text)
    assert match is not None, f"Missing pre-commit rev for {repo_url}"
    return match.group(1)


# Covers: Spec 0001 (Proposed stack: Python runtime and packaging) & Scope Feature 2
def test_pyproject_declares_stack_and_uv_application_mode() -> None:
    pyproject = _load_pyproject()
    project = pyproject["project"]
    tool_uv = pyproject["tool"]["uv"]
    groups = pyproject["dependency-groups"]

    assert project["requires-python"] == ">=3.13"
    assert tool_uv["package"] is False
    assert tool_uv["default-groups"] == ["dev"]

    deps = {re.split(r"[<>=!~]", item, maxsplit=1)[0] for item in project["dependencies"]}
    assert {"openpyxl", "pandas", "pyarrow", "scikit-learn"} <= deps

    lint_pkgs = {re.split(r"[<>=!~]", item, maxsplit=1)[0] for item in groups["lint"]}
    test_pkgs = {re.split(r"[<>=!~]", item, maxsplit=1)[0] for item in groups["test"]}
    dev_pkgs = {
        re.split(r"[<>=!~]", item, maxsplit=1)[0] for item in groups["dev"] if isinstance(item, str)
    }

    assert {"pandas-stubs", "ruff", "sqlfluff", "ty"} <= lint_pkgs
    assert {"pytest", "pytest-cov"} <= test_pkgs
    assert {"nbstripout", "pre-commit"} <= dev_pkgs


# Covers: Spec 0001 (Quality gates & Code layout)
def test_pyproject_configures_ruff_ty_pytest_and_coverage() -> None:
    pyproject = _load_pyproject()
    tool = pyproject["tool"]

    ruff = tool["ruff"]
    assert ruff["line-length"] == 100
    assert ruff["target-version"] == "py313"
    assert ruff["src"] == ["scripts", "tests"]

    ty = tool["ty"]
    assert ty["environment"]["python-version"] == "3.13"
    assert ty["src"]["include"] == ["scripts", "tests"]

    pytest_cfg = tool["pytest"]["ini_options"]
    assert pytest_cfg["testpaths"] == ["tests"]
    assert pytest_cfg["pythonpath"] == ["."]

    coverage_run = tool["coverage"]["run"]
    coverage_report = tool["coverage"]["report"]
    assert coverage_run["source"] == ["scripts"]
    assert coverage_report["fail_under"] == 80


# Covers: Spec 0001 (Python runtime libraries & scripts/tests package layout)
@pytest.mark.parametrize(
    "module_name",
    ["sqlite3", "pandas", "openpyxl", "pyarrow", "sklearn", "scripts", "tests"],
)
def test_core_runtime_and_package_imports_succeed(module_name: str) -> None:
    imported = importlib.import_module(module_name)

    assert imported is not None


# Covers: Spec 0001 (SQLite SQL linting) & Scope Feature 2
def test_sqlfluff_config_targets_sqlite_and_ignores_generated_dirs() -> None:
    parser = configparser.ConfigParser()
    parser.read_string(_read_text(".sqlfluff"))

    core = parser["sqlfluff"]
    assert core["dialect"] == "sqlite"
    assert core["templater"] == "raw"
    assert core["max_line_length"] == "100"
    assert core["sql_file_exts"] == ".sql"

    ignored = {entry.strip() for entry in core["ignore"].split(",")}
    assert {".venv", "dataset", "exports"} <= ignored


# Covers: Spec 0001 (Follow-up 4: pre-commit hook sync with uv.lock) & Scope Feature 2
def test_precommit_tool_revisions_match_uv_lock() -> None:
    lock_data = tomllib.loads(_read_text("uv.lock"))
    locked_versions = {pkg["name"]: pkg["version"] for pkg in lock_data["package"]}
    precommit_text = _read_text(".pre-commit-config.yaml")

    assert "default_install_hook_types: [pre-commit, pre-push]" in precommit_text
    ruff_rev = _extract_precommit_rev(
        precommit_text, "https://github.com/astral-sh/ruff-pre-commit"
    )
    assert ruff_rev == f"v{locked_versions['ruff']}"
    nb_rev = _extract_precommit_rev(precommit_text, "https://github.com/kynan/nbstripout")
    assert nb_rev == locked_versions["nbstripout"]
    sql_rev = _extract_precommit_rev(precommit_text, "https://github.com/sqlfluff/sqlfluff")
    assert sql_rev == locked_versions["sqlfluff"]
    assert "entry: uv run ty check" in precommit_text
    assert "stages: [pre-push]" in precommit_text


# Covers: Spec 0001 (Follow-up 4: GitHub Actions CI workflow) & Scope Feature 2
def test_ci_workflow_runs_check_only_gates_and_always_aggregator() -> None:
    ci_text = _read_text(".github/workflows/ci.yml")

    for expected_snippet in [
        "lint:",
        "typecheck:",
        "test:",
        "pre-commit:",
        "all-checks-passed:",
        "uv sync --locked --group dev",
        "uv run ruff check --output-format=github .",
        "uv run ruff format --check .",
        "uv run sqlfluff lint sql/ --dialect sqlite",
        "uv run ty check",
        "uv run pytest",
        "uv run pre-commit run --all-files --show-diff-on-failure",
        "needs: [lint, typecheck, test, pre-commit]",
        "if: always()",
    ]:
        assert expected_snippet in ci_text


# Covers: Spec 0001 (Version control exclusions) & Commit 7e9df3c .gitignore updates
def test_gitignore_excludes_raw_data_databases_exports_and_caches() -> None:
    entries = {
        line.strip()
        for line in _read_text(".gitignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    expected_rules = {
        "dataset/*.xlsx",
        "*.db",
        "*.db-*",
        "exports/*",
        "!exports/.gitkeep",
        ".venv/",
        ".sqlfluff_cache/",
        ".coverage",
        ".coverage.*",
        "~*.pbix",
        "*.pbix.bak",
    }
    assert expected_rules <= entries


# Covers: Spec 0001 (Follow-up 1: AGENTS.md conventions) & Scope Feature 2
def test_agents_md_documents_uv_and_quality_gates() -> None:
    agents_text = _read_text("AGENTS.md")

    for expected_command in [
        "uv sync",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run sqlfluff lint sql/ --dialect sqlite",
        "uv run ty check",
        "uv run pytest",
        "uv run pre-commit install",
    ]:
        assert expected_command in agents_text

    assert "pip install" not in agents_text
