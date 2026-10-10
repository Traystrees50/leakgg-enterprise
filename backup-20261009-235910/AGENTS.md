# Project Guidelines

## Overview

- This is a Python Discord monitoring bot for bonus-code drops across Telegram, web sources, StakeStats, and CodeStats.
- Read [README.md](README.md) for the supported platforms, Discord commands, and CLI usage; keep this file focused on agent-critical conventions.

## Architecture

- `main.py` is the CLI entry point and selects daemon, bot, polling, diagnostics, source-management, and test actions.
- `scrapers/` contains source-specific collectors; `scrapers/engine.py` coordinates scans and deduplication.
- `models.py`, `filters.py`, and `tracker.py` define the shared event model, validation rules, and persisted seen-code state.
- `discord_notifier.py` owns outbound notifications; `discord_bot.py` owns Discord commands and dashboard interactions.
- `dashboard_manager.py` persists route/source/subscriber settings in `routes_config.json`; `config.py` loads environment variables and runtime defaults.

## Development Commands

- Install dependencies with `python -m pip install -r requirements.txt`.
- Run the full test suite with `python test_bot.py`.
- Run a single diagnostic scan with `python main.py check-once`; add `--notify` only when outbound Discord notifications are intended.
- Run the CLI health report with `python main.py health`.
- Do not use the workspace MSBuild task for this Python project.

## Conventions

- Preserve bonus-code, URL, and state-key casing. Do not normalize codes to lowercase; redeem links depend on exact casing.
- Extend `BonusCodeItem` and `Platform` in `models.py` when adding platform/event data, then update scraper parsing and focused tests together.
- Keep source collection, event filtering, persistence, and notification responsibilities in their existing modules rather than adding cross-layer logic to `main.py`.
- Use temporary files or injected paths in tests for JSON persistence. Do not mutate the tracked `seen_codes.json` or `routes_config.json` during tests.
- Configuration is environment-driven through `.env`/`python-dotenv`; never commit tokens, webhook URLs, Telegram credentials, or other secrets. Use `.env.example` as the template.
- Treat network scraping as failure-prone: preserve existing timeouts, retry/rate-limit behavior, and graceful error handling when changing collectors.