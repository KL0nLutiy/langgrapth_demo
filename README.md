# Crypto Portfolio

A small Python project for tracking a crypto portfolio, calculating total value, P/L, and allocation, and exposing a minimal web UI plus JSON API.

## Technology stack

- Python 3.10+
- Standard library only:
  - `http.server` for the web UI/API
  - `argparse` for the CLI
  - `json` for persistence
- `pytest` for tests

## Project layout

- `crypto_portfolio/`
  - `__init__.py`: core domain model and service
  - `cli.py`: command-line interface
  - `web.py`: HTTP server, JSON API, and UI
  - `models.py`, `pricing.py`, `service.py`: compatibility re-exports
- `tests/`
  - `test_portfolio.py`
  - `test_web.py`

## CLI usage

