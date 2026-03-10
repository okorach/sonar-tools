# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sonar-tools is a Python CLI application suite for SonarQube administration. It provides 17 CLI commands for auditing, exporting, syncing, and managing SonarQube instances (Server 9.9+, 2025.1+, 2026.1+, Community Build, and SonarQube Cloud). Published on PyPI as `sonar-tools`.

## Build & Development

**Build system:** Poetry (Python 3.9+)

```bash
# Install dependencies
poetry install

# Build package
poetry build

# Run all linters (ruff, pylint, flake8)
conf/run_linters.sh

# Run individual linters
ruff check .
pylint --rcfile conf/pylintrc sonar/ cli/ migration/
flake8 --config conf/.flake8 --exclude test/gen .

# Run tests with coverage
poetry run coverage run --branch --source=. -m pytest test/gen/latest/ test/gen/cb/ test/gen/99/ test/gen/cloud/ test/gen/common/ --junit-xml=build/xunit-results.xml
poetry run coverage xml -o build/coverage.xml

# Run a single test file
poetry run pytest test/gen/latest/test_projects.py

# Run a single test
poetry run pytest test/gen/latest/test_projects.py::test_function_name
```

Tests require running SonarQube instances with pre-provisioned test data. Test generation uses `test/build` to prepare test files in `test/gen/`. Unit tests are in `test/unit/`.

## Code Style

- Line length: 150 characters
- Ruff configured with `select = ["ALL"]` and specific ignores (see pyproject.toml)
- Double quotes for strings
- Target Python version: 3.9

## Architecture

### Package Structure

- **`sonar/`** - Core library: SonarQube object abstractions and API layer
- **`cli/`** - CLI entry points for most commands (findings-export, housekeeper, projects, measures, etc.)
- **`sonar/cli/`** - CLI entry points for audit, config, maturity, misra commands
- **`migration/`** - Separate migration tool for SonarQube Cloud migration
- **`conf/`** - Build scripts, linter configs, Dockerfiles
- **`test/`** - Tests: `unit/` for unit tests, `gen/` for generated integration tests per SQ version

### Core Class Hierarchy

`SqObject` (`sonar/sqobject.py`) is the base class for all SonarQube entities. It provides caching via `SqObject.CACHE` and common API operations.

Key classes inheriting from `SqObject`:
- `Platform` (`sonar/platform.py`) - Main entry point representing a SonarQube instance. Manages API communication via `ApiManager`, handles authentication, and provides access to all SQ entities.
- `Project` (`sonar/projects.py`) - Project management (branches, PRs, settings, permissions, measures)
- `Finding` (`sonar/findings.py`) - Base for `Issue` (`sonar/issues.py`) and `Hotspot` (`sonar/hotspots.py`)
- `QualityProfile` / `QualityGate` / `Rule` - Quality management
- `Portfolio` / `Application` - Enterprise edition aggregation objects
- `User` / `Group` / `Token` - Identity management

### API Layer

`sonar/api/manager.py` contains `ApiManager` and `ApiOperation` for all HTTP communication with SonarQube. Version-specific API specs are in `sonar/api/*.json` (9.9, 2025.1, cloud).

`sonar/config.json` defines API endpoint configurations.

### Audit System

`sonar/audit/` contains the audit framework:
- `rules.json` - 200+ audit rule definitions
- `rules.py` / `problem.py` - Rule loading, checking, and problem representation
- `severities.py` / `types.py` - Severity levels and audit type definitions

### CLI Framework

`cli/options.py` centralizes command-line argument parsing. Common arguments: `-u` (URL), `-t` (token), `-o` (org), `-v` (verbose), `-f` (file format).

### Permissions

`sonar/permissions/` is a sub-package handling global, project, quality gate/profile, portfolio, application, and template permissions.

### Entry Points

All CLI commands are defined in `pyproject.toml` under `[project.scripts]`. Each maps to a `main()` function (e.g., `sonar-audit` -> `sonar.cli.audit:main`, `sonar-findings-export` -> `cli.findings_export:main`).

### Test Structure

Tests use pytest with fixtures defined in `test/unit/conftest.py`. Test utilities are in `test/unit/utilities.py`. The `tutil.SQ` object is the shared Platform endpoint for tests. Credential files (`test/unit/credentials*.py`) configure connections to different SQ versions.

### Error Handling

Exit codes are defined in `sonar/errcodes.py` (0=success through 17=server error). Custom exceptions are in `sonar/exceptions.py`.
