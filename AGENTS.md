# Repository Guidelines

This guide keeps contributors aligned on structure, tooling, and review expectations for the Mardi DoIP server codebase. Favor small, reviewable changes and keep instructions updated when workflows evolve.

## Project Structure & Module Organization
- Place runtime code under `src/` with the top-level package `mardi_doip_server/`; keep entrypoints and adapters grouped by protocol or feature.
- Add reusable scripts to `scripts/` and supporting docs or diagrams to `docs/`.
- Keep tests in `tests/` mirroring the `src/` layout (e.g., `src/mardi_doip_server/doip.py` pairs with `tests/test_doip.py`).
- Configuration samples belong in `config/` (e.g., `config/example.env`) so newcomers know which variables to set.

## Build, Test, and Development Commands
- Create a local environment: `python -m venv .venv && source .venv/bin/activate`.
- Install dependencies from the lockfile or constraints: `pip install -r requirements.txt` (add `-e .` for editable installs during development).
- Run tests with coverage: `pytest --maxfail=1 --disable-warnings -q`.
- Format and lint before pushing: `ruff check src tests` and `black src tests` if those tools are available; add them to `requirements-dev.txt` when first introduced.
- If the server exposes a CLI entrypoint, run it via `python -m mardi_doip_server` so relative imports resolve consistently.

## Coding Style & Naming Conventions
- Use 4-space indentation, type hints for public functions, and docstrings for modules that expose network behavior or protocols.
- Prefer explicit imports from `mardi_doip_server.*`; avoid wildcard imports.
- Name DoIP handlers and services by role (`DoipSession`, `DiagnosticRouter`, `UdpListener`), and tests by behavior (`test_session_times_out`).

## Testing Guidelines
- Write pytest tests alongside fixtures in `tests/conftest.py`; isolate network I/O behind fakes so tests run offline.
- Target at least smoke coverage for new endpoints and regression tests for bugs; add property-based tests when validating protocol edge cases.
- Run `pytest` before opening a PR and include failing-reproduction tests when fixing defects.

## Commit & Pull Request Guidelines
- Use concise, imperative commit subjects (`Add DoIP session timeout`, `Refine VIN lookup`) and keep bodies explaining motivation and key decisions.
- Reference related issues in the PR description, list major changes, and note any configuration or migration steps.
- Include screenshots or log snippets for observable changes (e.g., new diagnostics output) and call out known gaps or follow-ups.

## Security & Configuration Tips
- Never commit secrets; rely on environment variables and provide redacted examples in `config/example.env`.
- Keep dependencies pinned; when bumping protocol libraries, describe compatibility considerations in the PR.
- Avoid binding dev servers to public interfaces by default; prefer `127.0.0.1` and document any firewall or port expectations.
