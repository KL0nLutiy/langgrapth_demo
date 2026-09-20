# Crypto Portfolio

A small Python project for tracking a crypto portfolio with cost basis, valuation, profit/loss, and allocation.

## Technology Stack

- Python 3.8+
- Standard library only for runtime behavior
- `pytest` for tests
- `setuptools` / `pyproject.toml` for packaging and CLI entry point

## Architecture

- `crypto_portfolio/models.py`
  - Domain model: `Asset`, `Portfolio`, `AssetValue`, `PortfolioSummary`
  - Symbol normalization and amount validation
  - Portfolio persistence helpers via `to_dict` / `from_dict`

- `crypto_portfolio/pricing.py`
  - `PriceProvider` interface
  - `StaticPriceProvider` for JSON-backed or in-memory prices
  - `SamplePriceProvider` with deterministic sample prices

- `crypto_portfolio/service.py`
  - `PortfolioService` business logic
  - Valuation, P&L, allocation, and summary generation

- `crypto_portfolio/cli.py`
  - Command-line interface
  - Portfolio and price file persistence
  - Commands: `init`, `add`, `remove`, `set-price`, `summary`

- `tests/`
  - Initial unit and CLI tests

## Features

- Add holdings by symbol, quantity, and cost basis or average price
- Remove holdings fully or partially
- Track total cost basis and average price
- Calculate portfolio value, unrealized P&L, and allocation
- Persist portfolio and price data as JSON
- Use sample prices by default or provide a static price file

## Build and Run

