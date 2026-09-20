from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Mapping, Optional

from .models import Portfolio, normalize_symbol
from .pricing import PriceProvider, SamplePriceProvider, StaticPriceProvider
from .service import PortfolioService

DEFAULT_PORTFOLIO_PATH = "portfolio.json"
DEFAULT_PRICES_PATH = "prices.json"


def _portfolio_path(args: argparse.Namespace) -> str:
    path = getattr(args, "portfolio", None)
    if not path:
        return DEFAULT_PORTFOLIO_PATH
    return str(path)


def _prices_path(args: argparse.Namespace) -> Optional[str]:
    path = getattr(args, "prices", None)
    return str(path) if path else None


def _load_portfolio(path: str) -> Portfolio:
    if not os.path.exists(path):
        return Portfolio()

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    return Portfolio.from_dict(data)


def _save_portfolio(path: str, portfolio: Portfolio) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(portfolio.to_dict(), handle, indent=2)
        handle.write("\n")


def _normalize_prices(data: object) -> object:
    if isinstance(data, Mapping):
        return dict(data)

    if isinstance(data, list):
        prices = {}
        for item in data:
            if isinstance(item, Mapping):
                symbol = item.get("symbol")
                price = item.get("price")
                if symbol is not None and price is not None:
                    prices[str(symbol)] = price
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                prices[str(item[0])] = item[1]
        return prices

    return data


def _load_price_provider(path: Optional[str]) -> PriceProvider:
    if path:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return StaticPriceProvider(_normalize_prices(data))
        return StaticPriceProvider()

    return SamplePriceProvider()


def _save_price_provider(provider: PriceProvider, path: str) -> None:
    if not isinstance(provider, StaticPriceProvider):
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(provider.to_dict(), handle, indent=2)
        handle.write("\n")


def _print_summary(portfolio: Portfolio, provider: PriceProvider) -> None:
    service = PortfolioService(portfolio, provider)
    summary = service.get_summary()
    currency = summary.currency

    print(f"Portfolio value: {summary.total_value:.2f} {currency}")
    print(f"Total cost basis: {summary.total_cost:.2f} {currency}")
    print(
        f"Unrealized P&L: {summary.total_profit_loss:.2f} {currency} "
        f"({summary.profit_loss_pct:.2f}%)"
    )

    if not summary.holdings:
        print("No holdings.")
        return

    print()
    print(f"{'Symbol':<8} {'Quantity':>12} {'Price':>12} {'Value':>12} {'P&L':>12} {'P&L%':>8} {'Alloc%':>8}")
    for holding in summary.holdings:
        print(
            f"{holding.symbol:<8} "
            f"{holding.quantity:>12.8f} "
            f"{holding.price:>12.2f} "
            f"{holding.value:>12.2f} "
            f"{holding.profit_loss:>12.2f} "
            f"{holding.profit_loss_pct:>8.2f} "
            f"{holding.allocation_pct:>8.2f}"
        )


def _print_holdings(portfolio: Portfolio, provider: PriceProvider) -> None:
    service = PortfolioService(portfolio, provider)
    holdings = service.get_holdings()

    if not holdings:
        print("No holdings.")
        return

    print(f"{'Symbol':<8} {'Quantity':>12} {'Avg Price':>12} {'Price':>12} {'Value':>12}")
    for holding in holdings:
        print(
            f"{holding.symbol:<8} "
            f"{holding.quantity:>12.8f} "
            f"{holding.avg_price:>12.2f} "
            f"{holding.price:>12.2f} "
            f"{holding.value:>12.2f}"
        )


def _print_prices(provider: PriceProvider, symbols: Optional[List[str]] = None) -> None:
    prices = provider.get_prices(symbols)

    if not prices:
        print("No prices.")
        return

    print(f"{'Symbol':<8} {'Price':>12}")
    for symbol in sorted(prices):
        print(f"{symbol:<8} {prices[symbol]:>12.2f}")


def _cmd_init(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    if os.path.exists(path):
        print(f"Portfolio already exists: {path}", file=sys.stderr)
        return 1

    _save_portfolio(path, Portfolio())
    print(f"Initialized portfolio at {path}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)

    try:
        symbol = normalize_symbol(args.symbol)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        quantity = float(args.quantity)
        cost_basis = float(args.cost_basis)
    except ValueError:
        print("quantity and cost_basis must be numbers", file=sys.stderr)
        return 1

    portfolio.add_asset(symbol, quantity=quantity, cost_basis=cost_basis)
    _save_portfolio(path, portfolio)
    print(f"Added {symbol}")
    return 0


def _cmd_set_quantity(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)

    try:
        symbol = normalize_symbol(args.symbol)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        quantity = float(args.quantity)
    except ValueError:
        print("quantity must be a number", file=sys.stderr)
        return 1

    if portfolio.get_asset(symbol) is None:
        print(f"Holding not found: {symbol}", file=sys.stderr)
        return 1

    portfolio.set_quantity(symbol, quantity)
    _save_portfolio(path, portfolio)
    print(f"Updated {symbol} quantity to {quantity:.8f}")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)

    try:
        symbol = normalize_symbol(args.symbol)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not portfolio.remove_asset(symbol):
        print(f"Holding not found: {symbol}", file=sys.stderr)
        return 1

    _save_portfolio(path, portfolio)
    print(f"Removed {symbol}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)
    provider = _load_price_provider(_prices_path(args))

    _print_summary(portfolio, provider)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)
    provider = _load_price_provider(_prices_path(args))

    _print_holdings(portfolio, provider)
    return 0


def _cmd_prices(args: argparse.Namespace) -> int:
    provider = _load_price_provider(_prices_path(args))
    symbols = [normalize_symbol(symbol) for symbol in args.symbols] if args.symbols else None

    _print_prices(provider, symbols)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(portfolio.to_dict(), handle, indent=2)
            handle.write("\n")
        print(f"Exported portfolio to {args.output}")
    else:
        print(json.dumps(portfolio.to_dict(), indent=2))

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto-portfolio", description="Crypto portfolio tracker")
    parser.add_argument("--portfolio", default=None, help="Path to portfolio JSON file")
    parser.add_argument("--prices", default=None, help="Path to prices JSON file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a new portfolio file")
    init_parser.set_defaults(func=_cmd_init)

    add_parser = subparsers.add_parser("add", help="Add or increase a holding")
    add_parser.add_argument("symbol")
    add_parser.add_argument("quantity")
    add_parser.add_argument("cost_basis")
    add_parser.set_defaults(func=_cmd_add)

    set_parser = subparsers.add_parser("set", help="Manage holding quantities")
    set_subparsers = set_parser.add_subparsers(dest="set_command", required=True)

    set_quantity_parser = set_subparsers.add_parser("quantity", help="Set a holding quantity")
    set_quantity_parser.add_argument("symbol")
    set_quantity_parser.add_argument("quantity")
    set_quantity_parser.set_defaults(func=_cmd_set_quantity)

    remove_parser = subparsers.add_parser("remove", help="Remove a holding")
    remove_parser.add_argument("symbol")
    remove_parser.set_defaults(func=_cmd_remove)

    summary_parser = subparsers.add_parser("summary", help="Print portfolio summary")
    summary_parser.set_defaults(func=_cmd_summary)

    list_parser = subparsers.add_parser("list", help="List holdings")
    list_parser.set_defaults(func=_cmd_list)

    prices_parser = subparsers.add_parser("prices", help="Print prices")
    prices_parser.add_argument("symbols", nargs="*")
    prices_parser.set_defaults(func=_cmd_prices)

    export_parser = subparsers.add_parser("export", help="Export portfolio JSON")
    export_parser.add_argument("--output", default=None)
    export_parser.set_defaults(func=_cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
