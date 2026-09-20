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
        return

    print()
    print(
        f"{'Symbol':<8}{'Quantity':>12}{'Price':>12}{'Value':>12}"
        f"{'Avg':>12}{'P&L':>12}{'Alloc':>10}"
    )

    for holding in summary.holdings:
        print(
            f"{holding.symbol:<8}"
            f"{holding.quantity:>12.6f}"
            f"{holding.price:>12.2f}"
            f"{holding.value:>12.2f}"
            f"{holding.avg_price:>12.2f}"
            f"{holding.profit_loss:>12.2f}"
            f"{holding.allocation_pct:>9.2f}%"
        )


def _error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)


def _add_global_options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--portfolio", default=default, help="Path to the portfolio JSON file.")
    parser.add_argument("--prices", default=default, help="Path to a static prices JSON file.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-portfolio",
        description="Track a crypto portfolio and calculate P&L.",
    )
    _add_global_options(parser, suppress=False)
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    init_parser = subparsers.add_parser("init", aliases=["new", "create"], help="Create or reset a portfolio file.")
    _add_global_options(init_parser, suppress=True)

    add_parser = subparsers.add_parser("add", aliases=["buy"], help="Add or increase a holding.")
    _add_global_options(add_parser, suppress=True)
    add_parser.add_argument("symbol")
    add_parser.add_argument("quantity_positional", nargs="?", type=float, default=None, metavar="quantity")
    add_parser.add_argument("cost_basis_positional", nargs="?", type=float, default=None, metavar="cost_basis")
    add_parser.add_argument("--quantity", type=float, default=None)
    add_parser.add_argument("--cost-basis", type=float, default=None)
    add_parser.add_argument("--price", type=float, default=None, help="Average price per unit; used when cost basis is omitted.")
    add_parser.add_argument("--name", default=None)

    remove_parser = subparsers.add_parser("remove", aliases=["sell"], help="Remove or decrease a holding.")
    _add_global_options(remove_parser, suppress=True)
    remove_parser.add_argument("symbol")
    remove_parser.add_argument("quantity_positional", nargs="?", type=float, default=None, metavar="quantity")
    remove_parser.add_argument("--quantity", type=float, default=None)
    remove_parser.add_argument("--all", action="store_true", help="Remove the entire holding.")

    set_parser = subparsers.add_parser("set", aliases=["update"], help="Set the quantity for a holding.")
    _add_global_options(set_parser, suppress=True)
    set_parser.add_argument("symbol")
    set_parser.add_argument("quantity_positional", nargs="?", type=float, default=None, metavar="quantity")
    set_parser.add_argument("--quantity", type=float, default=None)
    set_parser.add_argument("--cost-basis", type=float, default=None)

    summary_parser = subparsers.add_parser("summary", aliases=["show", "report", "status"], help="Print a portfolio summary.")
    _add_global_options(summary_parser, suppress=True)

    price_parser = subparsers.add_parser(
        "price",
        aliases=["set-price", "set_price", "price-set", "update-price", "update_price"],
        help="Set a static price for a symbol.",
    )
    _add_global_options(price_parser, suppress=True)
    price_parser.add_argument("symbol")
    price_parser.add_argument("price_positional", nargs="?", type=float, default=None, metavar="price")
    price_parser.add_argument("--price", type=float, default=None)

    prices_parser = subparsers.add_parser(
        "prices",
        aliases=["list-prices", "list_prices", "list"],
        help="List available static prices.",
    )
    _add_global_options(prices_parser, suppress=True)

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = Portfolio()
    _save_portfolio(path, portfolio)
    print(f"Initialized portfolio at {path}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)

    quantity = args.quantity if args.quantity is not None else args.quantity_positional
    if quantity is None:
        print("Error: quantity is required", file=sys.stderr)
        return 2

    cost_basis = args.cost_basis if args.cost_basis is not None else args.cost_basis_positional
    if cost_basis is None:
        if args.price is not None:
            cost_basis = float(quantity) * float(args.price)
        else:
            cost_basis = 0.0

    portfolio = _load_portfolio(path)
    asset = portfolio.add_asset(args.symbol, quantity=quantity, cost_basis=cost_basis, name=args.name)
    _save_portfolio(path, portfolio)
    print(f"Added {asset.quantity:.6f} {asset.symbol} (cost basis {asset.cost_basis:.2f})")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    symbol = args.symbol
    quantity = args.quantity if args.quantity is not None else args.quantity_positional

    portfolio = _load_portfolio(path)
    asset = portfolio.get_asset(symbol)
    display_symbol = str(symbol).strip().upper() or "UNKNOWN"

    if asset is None:
        print(f"No holdings found for {display_symbol}", file=sys.stderr)
        return 1

    if getattr(args, "all", False) or quantity is None:
        removed = asset.quantity
        portfolio.remove_asset(symbol)
    else:
        quantity = float(quantity)
        if quantity < 0:
            raise ValueError("quantity must be a non-negative finite number")
        if quantity > asset.quantity + 1e-12:
            raise ValueError(f"Cannot remove {quantity:.6f} {asset.symbol}; only {asset.quantity:.6f} held")
        removed = quantity
        portfolio.remove_quantity(symbol, quantity)

    _save_portfolio(path, portfolio)
    print(f"Removed {removed:.6f} {display_symbol}")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    symbol = args.symbol
    quantity = args.quantity if args.quantity is not None else args.quantity_positional

    if quantity is None:
        print("Error: quantity is required", file=sys.stderr)
        return 2

    portfolio = _load_portfolio(path)
    asset = portfolio.set_quantity(symbol, quantity)

    cost_basis = getattr(args, "cost_basis", None)
    if cost_basis is not None:
        asset = portfolio.set_cost_basis(symbol, cost_basis)

    _save_portfolio(path, portfolio)
    display_symbol = str(symbol).strip().upper() or "UNKNOWN"

    if asset is None:
        print(f"Removed {display_symbol}")
    else:
        print(f"Set {asset.symbol} quantity to {asset.quantity:.6f}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    path = _portfolio_path(args)
    portfolio = _load_portfolio(path)
    provider = _load_price_provider(_prices_path(args))
    _print_summary(portfolio, provider)
    return 0


def _cmd_price(args: argparse.Namespace) -> int:
    path = _prices_path(args) or DEFAULT_PRICES_PATH
    price = args.price if args.price is not None else args.price_positional

    if price is None:
        print("Error: price is required", file=sys.stderr)
        return 2

    provider = _load_price_provider(path)
    if not isinstance(provider, StaticPriceProvider):
        provider = StaticPriceProvider()

    provider.set_price(args.symbol, price)
    _save_price_provider(provider, path)
    print(f"Set {normalize_symbol(args.symbol)} price to {float(price):.2f}")
    return 0


def _cmd_prices(args: argparse.Namespace) -> int:
    provider = _load_price_provider(_prices_path(args))
    symbols = provider.symbols()

    if not symbols:
        print("No prices available.")
        return 0

    for symbol in symbols:
        print(f"{symbol} {provider.get_price(symbol):.2f}")
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    command = getattr(args, "command", None)

    if command in {"init", "new", "create"}:
        return _cmd_init(args)
    if command in {"add", "buy"}:
        return _cmd_add(args)
    if command in {"remove", "sell"}:
        return _cmd_remove(args)
    if command in {"set", "update"}:
        return _cmd_set(args)
    if command in {"summary", "show", "report", "status"}:
        return _cmd_summary(args)
    if command in {"price", "set-price", "set_price", "price-set", "update-price", "update_price"}:
        return _cmd_price(args)
    if command in {"prices", "list-prices", "list_prices", "list"}:
        return _cmd_prices(args)

    _error(f"Unknown command: {command}")
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 2

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return _dispatch(args)
    except ValueError as exc:
        _error(str(exc))
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        _error(str(exc))
        return 1
