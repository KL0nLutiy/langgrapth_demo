import argparse
import json
import os
from typing import List, Optional

from .portfolio import Portfolio
from .prices import PriceProvider, SamplePriceProvider, StaticPriceProvider

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
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, list):
            data = dict(data)

        return StaticPriceProvider(data)

    return SamplePriceProvider()


def _print_summary(portfolio: Portfolio, provider: PriceProvider) -> None:
    symbols = portfolio.symbols()
    prices = provider.get_prices(symbols)

    total_value = portfolio.total_value(prices)
    total_cost = portfolio.total_cost()
    pnl = total_value - total_cost
    currency = portfolio.currency or "USD"

    print(f"Portfolio value: {total_value:.2f} {currency}")
    print(f"Total cost basis: {total_cost:.2f} {currency}")
    print(f"Unrealized P&L: {pnl:.2f} {currency}")

    if not symbols:
        return

    print()
    print(f"{'Symbol':<8}{'Quantity':>12}{'Price':>12}{'Value':>12}{'Allocation':>12}")

    allocation = portfolio.allocation(prices)

    for symbol in symbols:
        asset = portfolio.get_asset(symbol)
        price = prices.get(symbol, 0.0)
        value = asset.quantity * price
        percent = allocation.get(symbol, 0.0) * 100

        print(
            f"{symbol:<8}"
            f"{asset.quantity:>12.6f}"
            f"{price:>12.2f}"
            f"{value:>12.2f}"
            f"{percent:>11.2f}%"
        )


def _cmd_init(args: argparse.Namespace) -> int:
    portfolio = Portfolio()
    _save_portfolio(args.portfolio, portfolio)
    print(f"Initialized portfolio at {args.portfolio}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)

    name = args.name
    if name is not None and not str(name).strip():
        name = None

    asset = portfolio.add_asset(
        symbol=args.symbol,
        quantity=args.quantity,
        cost_basis=args.cost_basis,
        name=name,
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
    symbol = args.symbol.strip().upper()

    if not portfolio.remove_asset(symbol):
        print(f"Asset {symbol} not found")
        return 1

    _save_portfolio(args.portfolio, portfolio)
    print(f"Removed {symbol}")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)
    updated = False

    if args.quantity is not None:
        portfolio.set_quantity(args.symbol, args.quantity)
        updated = True

    if args.cost_basis is not None:
        portfolio.set_cost_basis(args.symbol, args.cost_basis)
        updated = True

    if not updated:
        print("Nothing to update. Provide --quantity and/or --cost-basis.")
        return 1

    _save_portfolio(args.portfolio, portfolio)

    asset = portfolio.get_asset(args.symbol)
    print(
        f"Updated {asset.symbol}: "
        f"quantity={asset.quantity:.6f}, "
        f"cost_basis={asset.cost_basis:.2f}"
    )

    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    portfolio = _load_portfolio(args.portfolio)
    provider = _load_price_provider(args.prices)
    _print_summary(portfolio, provider)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-portfolio",
        description="Track a crypto portfolio and calculate value, cost basis, and P&L.",
    )

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create an empty portfolio file.")
    init_parser.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file.",
    )
    init_parser.set_defaults(func=_cmd_init)

    add_parser = subparsers.add_parser("add", help="Add or update an asset holding.")
    add_parser.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file.",
    )
    add_parser.add_argument("--symbol", required=True, help="Asset symbol, e.g. BTC.")
    add_parser.add_argument(
        "--quantity",
        required=True,
        type=float,
        help="Quantity to add.",
    )
    add_parser.add_argument(
        "--cost-basis",
        type=float,
        default=0.0,
        help="Total cost basis for the quantity being added.",
    )
    add_parser.add_argument(
        "--name",
        default=None,
        help="Optional human-readable asset name.",
    )
    add_parser.set_defaults(func=_cmd_add)

    remove_parser = subparsers.add_parser("remove", help="Remove an asset.")
    remove_parser.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file.",
    )
    remove_parser.add_argument("--symbol", required=True, help="Asset symbol to remove.")
    remove_parser.set_defaults(func=_cmd_remove)

    set_parser = subparsers.add_parser(
        "set", help="Set quantity and/or cost basis for an asset."
    )
    set_parser.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file.",
    )
    set_parser.add_argument("--symbol", required=True, help="Asset symbol to update.")
    set_parser.add_argument(
        "--quantity",
        type=float,
        default=None,
        help="New total quantity.",
    )
    set_parser.add_argument(
        "--cost-basis",
        type=float,
        default=None,
        help="New total cost basis.",
    )
    set_parser.set_defaults(func=_cmd_set)

    summary_parser = subparsers.add_parser("summary", help="Print portfolio summary.")
    summary_parser.add_argument(
        "--portfolio",
        default=DEFAULT_PORTFOLIO_PATH,
        help="Path to the portfolio JSON file.",
    )
    summary_parser.add_argument(
        "--prices",
        default=None,
        help="Optional JSON file containing symbol prices.",
    )
    summary_parser.set_defaults(func=_cmd_summary)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
