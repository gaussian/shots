# Agents

`shots` — LLM-assisted high-res marketing screenshots via Playwright. Pure-Python,
published to PyPI.

## Repo shape

- Source: `shots/` · Tests: `tests/` (`uv run --all-extras pytest`)
- Lint + format: `uv run --all-extras ruff check .` and `ruff format --check .`
- Types: `uv run --all-extras mypy shots --ignore-missing-imports`
- Default working branch: `develop`. Releases flow `develop` → `main`.
- Dependency cooldown: 7 days, via `exclude-newer` under `[tool.uv]` in `pyproject.toml`. Urgent fix: add `<pkg> = false` under `exclude-newer-package`, run `uv lock --upgrade-package <pkg>`, and remove the exemption once the release is over 7 days old.

## Git

- Always stage and commit in a single command: `git add file1 file2 && git commit -m "message"`
- Run git commands from the working directory directly — no `cd` or `-C` flags

## Opening PRs & versioning

`main` is protected: PRs only, and checks (`lint`, `test`) must pass to merge.
The version is a static string in `pyproject.toml` + `uv.lock` and is **not**
bumped automatically on merge — it must be bumped deliberately, or no release is
cut. Publishing to PyPI is automatic once a `develop` → `main` PR merges.

**Follow the `create-merge-pr` skill** (`.agents/skills/create-merge-pr/`) for the
full PR workflow, including when and how to bump the version.
