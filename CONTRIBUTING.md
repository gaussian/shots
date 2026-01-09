# Contributing to shots

Thank you for your interest in contributing to **shots**! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)

## Code of Conduct

Please be respectful and constructive in all interactions. We welcome contributors of all experience levels.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/shots.git
   cd shots
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/shots.git
   ```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Installation

1. Install dependencies with uv:
   ```bash
   uv sync --all-extras
   ```

2. Install Playwright browsers:
   ```bash
   uv run playwright install chromium
   ```

3. (Optional) Install pre-commit hooks:
   ```bash
   uv run pre-commit install
   ```

## Running Tests

### Run all tests
```bash
uv run pytest tests/ -v
```

### Run tests with coverage
```bash
uv run pytest tests/ -v --cov=shots --cov-report=term-missing
```

### Run a specific test file
```bash
uv run pytest tests/unit/test_utils.py -v
```

### Run tests matching a pattern
```bash
uv run pytest tests/ -v -k "test_viewport"
```

## Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting.

### Check for linting issues
```bash
uv run ruff check .
```

### Auto-fix linting issues
```bash
uv run ruff check --fix .
```

### Check formatting
```bash
uv run ruff format --check .
```

### Auto-format code
```bash
uv run ruff format .
```

### Type checking with mypy
```bash
uv run mypy shots --ignore-missing-imports
```

### Run all checks (recommended before committing)
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy shots --ignore-missing-imports && uv run pytest tests/ -v
```

## Pull Request Process

### Branch Naming

Create a descriptive branch name:
- `feature/add-new-viewport-preset`
- `fix/crop-bounds-validation`
- `docs/update-readme-examples`

### Before Submitting

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/develop
   ```

2. **Ensure all checks pass**:
   - Tests: `uv run pytest tests/ -v`
   - Linting: `uv run ruff check .`
   - Formatting: `uv run ruff format --check .`
   - Type checking: `uv run mypy shots --ignore-missing-imports`

3. **Write clear commit messages** following conventional commits:
   - `feat: add tablet landscape viewport preset`
   - `fix: handle missing storage_state gracefully`
   - `docs: add CLI usage examples`
   - `refactor: simplify viewport resolution logic`

### Submitting a PR

1. Push your branch to your fork
2. Open a Pull Request against the `develop` branch
3. Fill out the PR template completely
4. Request review from maintainers

### PR Labels

Apply appropriate labels to your PR (maintainers may adjust):

| Label | Description |
|-------|-------------|
| `feature` / `enhancement` | New functionality |
| `bug` / `fix` | Bug fixes |
| `docs` / `documentation` | Documentation changes |
| `refactor` | Code refactoring |
| `test` / `testing` | Test additions or changes |
| `breaking` / `breaking-change` | Breaking API changes |
| `release:major` | Triggers major version bump |
| `release:minor` | Triggers minor version bump |
| (no release label) | Triggers patch version bump |

### Review Process

- PRs require at least one approving review
- CI checks must pass
- Address all review comments
- Keep PRs focused and reasonably sized

## Issue Guidelines

### Reporting Bugs

Use the **Bug Report** template and include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version)
- Screenshots if applicable

### Requesting Features

Use the **Feature Request** template and include:
- Clear description of the feature
- Use case / motivation
- Proposed implementation (if any)

### Questions

For questions about usage, please check the README first. If your question isn't answered there, open a discussion or issue.

---

Thank you for contributing to shots!
