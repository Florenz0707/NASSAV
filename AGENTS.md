# Repository Guidelines

## Project Structure & Module Organization

This repository is organized around two active applications plus one legacy reference:

- `django_backend/`: Django 5 backend, Celery tasks, WebSocket support, scripts, and pytest suite. Core app code lives in `django_backend/nassav/`; project settings are in `django_backend/django_project/`; operational docs live in `django_backend/doc/`.
- `vue_frontend/`: Vue 3 + Vite SPA. Views are in `src/views/`, shared UI in `src/components/`, state in `src/stores/`, and API wrappers in `src/api/`.
- `origin_project/`: preserved original implementation. Treat it as reference-only unless a task explicitly targets it.

## Build, Test, and Development Commands

- Backend setup: `cd django_backend && uv sync`
- Backend dev server: `uv run uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --reload`
- Backend tests: `uv run pytest tests/ -v`
- Backend lint/type checks: `uv run ruff check .` and `uv run pyright`
- Frontend setup: `cd vue_frontend && pnpm install`
- Frontend dev server: `pnpm dev`
- Frontend build: `pnpm build`
- Frontend lint: `pnpm lint` or `pnpm lint:fix`

Redis is required for Celery and WebSocket flows. Copy `django_backend/config/template-config.yaml` to `config/config.yaml` before running backend services.

## Coding Style & Naming Conventions

Python uses 4-space indentation, snake_case functions/modules, and Django-style model/service naming. Keep backend responsibilities narrow and prefer extending existing abstractions in `source/`, `scraper/`, and `translator/`.

Frontend code follows Prettier and ESLint: 2-space formatting, single quotes, no semicolons, and `printWidth: 100`. Use PascalCase for Vue components such as `ResourceCard.vue`, and keep store/API modules in lowercase filenames such as `resource.js`.

## Testing Guidelines

Add backend tests under `django_backend/tests/` using `test_*.py` naming. Prefer pytest fixtures from `conftest.py`; use targeted runs like `uv run pytest tests/test_resources_list.py -v` while iterating. Shell-based integration checks also exist in `django_backend/tests/*.sh` for API and WebSocket flows.

## Commit & Pull Request Guidelines

Recent history uses bracketed prefixes such as `[Feat]`, `[Fix]`, `[Chore]`, `[Enhancement]`, and `[Doc]`. Keep commits focused and descriptive, for example: `[Fix] Handle missing actor avatar fallback`.

PRs should summarize backend/frontend impact, note config or migration changes, link the related issue, and include screenshots for UI changes. Include the commands you ran to validate the change.
