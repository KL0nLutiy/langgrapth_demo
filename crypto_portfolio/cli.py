from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import (
    Portfolio,
    PortfolioService,
    StaticPriceProvider,
    _validate_amount,
    normalize_symbol,
)

DEFAULT_PORTFOLIO_PATH = "portfolio.json"
DEFAULT_PRICES_PATH = "prices.json"


class _CliError(Exception):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliError(message)


def _resolve_paths(args: argparse.Namespace) -> tuple[str, Optional[str]]:
    portfolio = (
        getattr(args, "portfolio", None)
        or getattr(args, "global_portfolio", None)
        or os.environ.get("CRYPTO_PORTFOLIO_PATH")
        or DEFAULT_PORTFOLIO_PATH
    )

    prices = (
        getattr(args, "prices", None)
        or getattr(args, "global_prices", None)
        or os.environ.get("CRYPTO_PRICES_PATH")
    )

    return str(portfolio), (str(prices) if prices else None)


def _load_portfolio(path: str) -> Portfolio:
    if not path or not os.path.exists(path):
        return Portfolio()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        if not content.strip():
            return Portfolio()

        data = json.loads(content)
        return Portfolio.from_dict(data)
    except Exception:
        return Portfolio()


def _save_portfolio(path: str, portfolio: Portfolio) -> None:
    if not path:
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(portfolio.to_dict(), handle, indent=2)
        handle.write("\n")


def _load_prices(path: Optional[str]) -> StaticPriceProvider:
    candidate = path or os.environ.get("CRYPTO_PRICES_PATH") or DEFAULT_PRICES_PATH

    if not candidate or not os.path.exists(candidate):
        return StaticPriceProvider({})

    try:
        with open(candidate, "r", encoding="utf-8") as handle:
            content = handle.read()

        if not content.strip():
            return StaticPriceProvider({})

        data = json.loads(content)
        return StaticPriceProvider(data)
    except Exception:
        return StaticPriceProvider({})


def _save_prices(path: Optional[str], provider: StaticPriceProvider) -> None:
    if not path:
        path = DEFAULT_PRICES_PATH

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(provider.to_dict(), handle, indent=2)
        handle.write("\n")


def _json_output(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _error(message: str) -> None:
    print(json.dumps({"error": message}), file=sys.stderr)


def _add_path_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--portfolio", dest="portfolio", default=None)
    parser.add_argument("--prices", dest="prices", default=None)


def _add_symbol_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("symbol", nargs="?", default=None)
    parser.add_argument("--symbol", dest="symbol_option", default=None)


def _get_symbol(args: argparse.Namespace) -> str:
    symbol = getattr(args, "symbol_option", None) or getattr(args, "symbol", None)

    if symbol is None:
        raise _CliError("symbol is required")

    normalized = normalize_symbol(symbol)
    if not normalized:
        raise _CliError("symbol is required")

    return normalized


def _validate_required(args: argparse.Namespace, name: str) -> float:
    value = getattr(args, name, None)

    if value is None:
        raise _CliError(f"--{name.replace('_', '-')} is required")

    return _validate_amount(value, name)


def _mutation_payload(
    portfolio: Portfolio,
    prices_path: Optional[str],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    provider = _load_prices(prices_path)
    service = PortfolioService(portfolio, provider)
    summary = service.get_summary().to_dict()

    payload = dict(summary)
    payload.update(extra)
    payload["summary"] = summary

    return payload


def _cmd_init(args: argparse.Namespace) -> int:
    path, _ = _resolve_paths(args)
    portfolio = Portfolio()
    _save_portfolio(path, portfolio)
    _json_output(portfolio.to_dict())
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(path)

    symbol = _get_symbol(args)
    quantity = _validate_required(args, "quantity")

    cost_basis: Optional[float] = None
    for attr in ("cost_basis", "cost"):
        value = getattr(args, attr, None)
        if value is not None:
            cost_basis = _validate_amount(value, "cost_basis")
            break

    if cost_basis is None:
        for attr in ("avg_price", "price"):
            value = getattr(args, attr, None)
            if value is not None:
                cost_basis = quantity * _validate_amount(value, "avg_price")
                break

    if cost_basis is None:
        cost_basis = 0.0

    portfolio.add_asset(symbol, quantity, cost_basis)
    _save_portfolio(path, portfolio)

    asset = portfolio.get_asset(symbol)
    payload = _mutation_payload(
        portfolio,
        prices_path,
        {"asset": asset.to_dict() if asset else None},
    )

    _json_output(payload)
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(path)

    symbol = _get_symbol(args)
    quantity = _validate_required(args, "quantity")

    if portfolio.get_asset(symbol) is None:
        raise _CliError(f"asset {symbol} not found")

    asset = portfolio.set_quantity(symbol, quantity)
    _save_portfolio(path, portfolio)

    payload = _mutation_payload(
        portfolio,
        prices_path,
        {
            "asset": asset.to_dict() if asset else None,
            "removed": asset is None,
        },
    )

    _json_output(payload)
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(path)

    symbol = _get_symbol(args)
    quantity = getattr(args, "quantity", None)

    if quantity is None:
        removed = portfolio.remove_asset(symbol)
    else:
        removed = portfolio.remove_asset(symbol, _validate_amount(quantity, "quantity"))

    if not removed:
        raise _CliError(f"asset {symbol} not found")

    _save_portfolio(path, portfolio)
    payload = _mutation_payload(portfolio, prices_path, {"removed": True})
    _json_output(payload)
    return 0


def _cmd_price(args: argparse.Namespace) -> int:
    _, prices_path = _resolve_paths(args)
    if prices_path is None:
        prices_path = DEFAULT_PRICES_PATH

    provider = _load_prices(prices_path)
    symbol = _get_symbol(args)
    price = _validate_required(args, "price")

    provider.set_price(symbol, price)
    _save_prices(prices_path, provider)

    _json_output(
        {
            "symbol": symbol,
            "price": price,
            "prices": provider.to_dict()["prices"],
        }
    )
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(path)
    provider = _load_prices(prices_path)
    service = PortfolioService(portfolio, provider)

    _json_output(service.get_summary().to_dict())
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    path, _ = _resolve_paths(args)
    portfolio = _load_portfolio(path)

    _json_output(portfolio.to_dict())
    return 0


def _cmd_holdings(args: argparse.Namespace) -> int:
    path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(path)
    provider = _load_prices(prices_path)
    service = PortfolioService(portfolio, provider)

    _json_output([holding.to_dict() for holding in service.get_holdings()])
    return 0


def _build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="crypto-portfolio", description="Crypto Portfolio")
    parser.add_argument("--portfolio", dest="global_portfolio", default=None)
    parser.add_argument("--prices", dest="global_prices", default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize an empty portfolio")
    _add_path_args(init_parser)

    add_parser = subparsers.add_parser("add", help="Add or increase an asset")
    _add_path_args(add_parser)
    _add_symbol_args(add_parser)
    add_parser.add_argument("--quantity", "-q", default=None)
    add_parser.add_argument("--cost-basis", dest="cost_basis", default=None)
    add_parser.add_argument("--cost", dest="cost", default=None)
    add_parser.add_argument("--avg-price", dest="avg_price", default=None)
    add_parser.add_argument("--price", dest="price", default=None)

    set_parser = subparsers.add_parser("set", help="Set an asset quantity")
    _add_path_args(set_parser)
    _add_symbol_args(set_parser)
    set_parser.add_argument("--quantity", "-q", required=True)

    remove_parser = subparsers.add_parser("remove", help="Remove an asset or quantity")
    _add_path_args(remove_parser)
    _add_symbol_args(remove_parser)
    remove_parser.add_argument("--quantity", "-q", default=None)

    price_parser = subparsers.add_parser("price", help="Set a price")
    _add_path_args(price_parser)
    _add_symbol_args(price_parser)
    price_parser.add_argument("--price", "-p", required=True)

    summary_parser = subparsers.add_parser("summary", help="Print portfolio summary")
    _add_path_args(summary_parser)

    export_parser = subparsers.add_parser("export", help="Export portfolio JSON")
    _add_path_args(export_parser)

    holdings_parser = subparsers.add_parser("holdings", help="Print holdings")
    _add_path_args(holdings_parser)

    return parser


_HANDLERS = {
    "init": _cmd_init,
    "add": _cmd_add,
    "set": _cmd_set,
    "remove": _cmd_remove,
    "price": _cmd_price,
    "summary": _cmd_summary,
    "export": _cmd_export,
    "holdings": _cmd_holdings,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()

    try:
        args = parser.parse_args(argv)
        handler = _HANDLERS.get(args.command)

        if handler is None:
            raise _CliError(f"unknown command: {args.command}")

        return handler(args)
    except _CliError as exc:
        _error(str(exc))
        return 1
    except ValueError as exc:
        _error(str(exc))
        return 1
    except Exception as exc:
        _error(f"unexpected error: {exc}")
        return 1
