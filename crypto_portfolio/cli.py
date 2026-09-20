from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .models import Portfolio, normalize_symbol
from .pricing import PriceProvider, SamplePriceProvider, StaticPriceProvider
from .service import PortfolioService

DEFAULT_PORTFOLIO_PATH = "portfolio.json"


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


def _load_price_provider(path: Optional[str]) -> PriceProvider:
    if path:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            if isinstance(data, list):
                data = dict(data)

            return StaticPriceProvider(data)

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


def _cmd_init(args: argparse.Namespace) -> int:
    portfolio = Portfolio()
    _save_portfolio(args.portfolio, portfolio)
    print(f"Initialized portfolio at {args.portfolio}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)

    if args.avg_price is not None:
        asset = portfolio.add_holding(
            args.symbol,
            args.quantity,
            avg_price=args.avg_price,
        )
    else:
        asset = portfolio.add_asset(
            symbol=args.symbol,
            quantity=args.quantity,
            cost_basis=args.cost_basis,
            name=args.name,
        )

    _save_portfolio(args.portfolio, portfolio)

    print(
        f"Updated {asset.symbol}: "
        f"quantity={asset.quantity:.6f}, "
        f"cost_basis={asset.cost_basis:.2f}"
    )

    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)

    if args.quantity is not None:
        removed = portfolio.remove_holding(args.symbol, args.quantity)
    else:
        removed = portfolio.remove_asset(args.symbol)

    _save_portfolio(args.portfolio, portfolio)

    symbol = normalize_symbol(args.symbol)
    if removed:
        print(f"Removed {symbol}")
    else:
        print(f"No holding found for {symbol}")

    return 0


def _cmd_set_price(args: argparse.Namespace) -> int:
    provider = _load_price_provider(args.prices)
    provider.set_price(args.symbol, args.price)

    if args.prices:
        _save_price_provider(provider, args.prices)

    symbol = normalize_symbol(args.symbol)
    print(f"Set {symbol} price to {args.price:.2f}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)
    provider = _load_price_provider(args.prices)
    _print_summary(portfolio, provider)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file",
    )
    common.add_argument(
        "--prices",
        default=None,
        help="Path to a price JSON file",
    )

    parser = argparse.ArgumentParser(
        prog="crypto-portfolio",
        description="Track a crypto portfolio with cost basis, valuation, and allocation.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "init",
        parents=[common],
        help="Create an empty portfolio file",
    )

    add_parser = subparsers.add_parser(
        "add",
        parents=[common],
        help="Add or update a holding",
    )
    add_parser.add_argument("--symbol", required=True, help="Asset symbol, e.g. BTC")
    add_parser.add_argument("--quantity", type=float, required=True, help="Quantity to add")
    add_parser.add_argument(
        "--cost-basis",
        type=float,
        default=0.0,
        help="Total cost basis to add",
    )
    add_parser.add_argument(
        "--avg-price",
        type=float,
        default=None,
        help="Average price for the added quantity",
    )
    add_parser.add_argument("--name", default=None, help="Optional display name")

    remove_parser = subparsers.add_parser(
        "remove",
        parents=[common],
        help="Remove a holding or reduce its quantity",
    )
    remove_parser.add_argument("--symbol", required=True, help="Asset symbol")
    remove_parser.add_argument(
        "--quantity",
        type=float,
        default=None,
        help="Quantity to remove; omit to remove the entire holding",
    )

    set_price_parser = subparsers.add_parser(
        "set-price",
        parents=[common],
        help="Set a price in a price file",
    )
    set_price_parser.add_argument("--symbol", required=True, help="Asset symbol")
    set_price_parser.add_argument("--price", type=float, required=True, help="Price to set")

    subparsers.add_parser(
        "summary",
        parents=[common],
        help="Print a portfolio summary",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "add":
            return _cmd_add(args)
        if args.command == "remove":
            return _cmd_remove(args)
        if args.command == "set-price":
            return _cmd_set_price(args)
        if args.command == "summary":
            return _cmd_summary(args)

        parser.print_help()
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
