from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from .models import Portfolio, _validate_amount, normalize_symbol
from .pricing import PriceProvider, SamplePriceProvider, StaticPriceProvider
from .service import PortfolioService

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
    if not os.path.exists(path):
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
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(portfolio.to_dict(), handle, indent=2)
        handle.write("\n")


def _normalize_prices(data: object) -> object:
    if isinstance(data, Mapping):
        if "prices" in data and isinstance(data.get("prices"), (Mapping, list, tuple)):
            return _normalize_prices(data.get("prices"))

        prices: Dict[str, float] = {}
        for symbol, price in data.items():
            try:
                prices[normalize_symbol(symbol)] = _validate_amount(price, "price")
            except ValueError:
                continue

        return prices

    if isinstance(data, list):
        prices = {}

        for item in data:
            if isinstance(item, Mapping):
                symbol = item.get("symbol")
                price = item.get("price")
                if symbol is not None and price is not None:
                    try:
                        prices[normalize_symbol(symbol)] = _validate_amount(price, "price")
                    except ValueError:
                        continue
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    prices[normalize_symbol(item[0])] = _validate_amount(item[1], "price")
                except ValueError:
                    continue

        return prices

    return {}


def _load_price_provider(path: Optional[str]) -> PriceProvider:
    if not path:
        return SamplePriceProvider()

    if not os.path.exists(path):
        return StaticPriceProvider()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        if not content.strip():
            return StaticPriceProvider()

        data = json.loads(content)
        return StaticPriceProvider(_normalize_prices(data))
    except Exception:
        return StaticPriceProvider()


def _save_price_provider(provider: PriceProvider, path: Optional[str]) -> None:
    if not path:
        return

    prices = {symbol: provider.get_price(symbol) for symbol in provider.symbols()}

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(prices, handle, indent=2)
        handle.write("\n")


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _command_init(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)

    _save_portfolio(portfolio_path, Portfolio())

    if prices_path:
        _save_price_provider(SamplePriceProvider(), prices_path)

    print(f"Initialized portfolio at {portfolio_path}")
    return 0


def _command_add(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)

    quantity = _first_not_none(
        getattr(args, "quantity", None),
        getattr(args, "quantity_pos", None),
    )
    if quantity is None:
        quantity = 0.0

    cost_basis = _first_not_none(
        getattr(args, "cost_basis", None),
        getattr(args, "cost_basis_pos", None),
    )
    avg_price = getattr(args, "avg_price", None)

    asset = service.add_asset(
        args.symbol,
        quantity=quantity,
        cost_basis=cost_basis,
        avg_price=avg_price,
    )

    _save_portfolio(portfolio_path, portfolio)

    if float(quantity) == 0 or asset is None:
        print("No assets added.")
    else:
        print(f"Added {asset.quantity:.6f} {asset.symbol} at {asset.avg_price:.2f}")

    return 0


def _command_set(args: argparse.Namespace) -> int:
    portfolio_path, _ = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(None)
    service = PortfolioService(portfolio, provider)

    quantity = _first_not_none(
        getattr(args, "quantity", None),
        getattr(args, "quantity_pos", None),
    )

    if quantity is None:
        raise _CliError("quantity is required")

    asset = service.set_quantity(args.symbol, quantity)
    _save_portfolio(portfolio_path, portfolio)

    if asset is None:
        print(f"Removed {normalize_symbol(args.symbol)}")
    else:
        print(f"Set {asset.symbol} quantity to {asset.quantity:.6f}")

    return 0


def _command_remove(args: argparse.Namespace) -> int:
    portfolio_path, _ = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(None)
    service = PortfolioService(portfolio, provider)

    symbol = normalize_symbol(args.symbol)

    if portfolio.get_asset(symbol) is None:
        raise _CliError(f"Asset {symbol} not found")

    quantity = _first_not_none(
        getattr(args, "quantity", None),
        getattr(args, "quantity_pos", None),
    )

    removed = service.remove_asset(symbol, quantity)
    _save_portfolio(portfolio_path, portfolio)

    if removed:
        print(f"Removed {symbol}")
    else:
        print(f"No change for {symbol}")

    return 0


def _command_price(args: argparse.Namespace) -> int:
    _, prices_path = _resolve_paths(args)
    provider = _load_price_provider(prices_path)

    price = _first_not_none(
        getattr(args, "price", None),
        getattr(args, "price_pos", None),
    )

    if price is None:
        raise _CliError("price is required")

    symbol = normalize_symbol(args.symbol)
    provider.set_price(symbol, price)

    if prices_path:
        _save_price_provider(provider, prices_path)

    print(f"Set price for {symbol} to {float(price):.2f}")
    return 0


def _command_summary(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)

    summary = service.get_summary()

    print(f"Portfolio value: {summary.total_value:.2f} {summary.currency}")
    print(f"Total cost: {summary.total_cost:.2f} {summary.currency}")
    print(
        f"Profit/Loss: {summary.total_profit_loss:.2f} {summary.currency} "
        f"({summary.profit_loss_pct:.2f}%)"
    )

    if summary.holdings:
        print("Holdings:")
        for holding in summary.holdings:
            print(
                f"{holding.symbol} {holding.quantity:.6f} "
                f"@ {holding.avg_price:.2f} = {holding.value:.2f}"
            )
    else:
        print("No holdings.")

    return 0


def _command_portfolio(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)

    holdings = service.get_holdings()

    print("Portfolio:")

    if holdings:
        for holding in holdings:
            print(
                f"{holding.symbol} {holding.quantity:.6f} "
                f"@ {holding.avg_price:.2f} = {holding.value:.2f}"
            )

        total_value = sum(holding.value for holding in holdings)
        print(f"Portfolio value: {total_value:.2f} {portfolio.currency}")
    else:
        print("No assets.")
        print(f"Portfolio value: 0.00 {portfolio.currency}")

    return 0


def _command_prices(args: argparse.Namespace) -> int:
    _, prices_path = _resolve_paths(args)
    provider = _load_price_provider(prices_path)

    print("Portfolio prices:")

    symbols = provider.symbols()
    if symbols:
        for symbol in symbols:
            print(f"{symbol} {provider.get_price(symbol):.2f}")
    else:
        print("No prices.")

    return 0


def _command_export(args: argparse.Namespace) -> int:
    portfolio_path, _ = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)

    print(json.dumps(portfolio.to_dict(), indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--portfolio",
        default=argparse.SUPPRESS,
        metavar="PATH",
        help="Portfolio file path",
    )
    common.add_argument(
        "--prices",
        default=argparse.SUPPRESS,
        metavar="PATH",
        help="Prices file path",
    )

    parser = _ArgumentParser(
        prog="crypto-portfolio",
        description="Crypto Portfolio",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="command", parser_class=_ArgumentParser)

    init_parser = subparsers.add_parser(
        "init",
        parents=[common],
        help="Initialize an empty portfolio",
    )
    init_parser.set_defaults(func=_command_init)

    add_parser = subparsers.add_parser(
        "add",
        parents=[common],
        help="Add an asset",
    )
    add_parser.add_argument("symbol", help="Asset symbol")
    add_parser.add_argument(
        "quantity_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="QUANTITY",
    )
    add_parser.add_argument(
        "cost_basis_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="COST_BASIS",
    )
    add_parser.add_argument("--quantity", type=float, default=None, dest="quantity")
    add_parser.add_argument("--cost-basis", type=float, default=None, dest="cost_basis")
    add_parser.add_argument("--avg-price", type=float, default=None, dest="avg_price")
    add_parser.set_defaults(func=_command_add)

    set_parser = subparsers.add_parser(
        "set",
        parents=[common],
        help="Set asset quantity",
    )
    set_parser.add_argument("symbol", help="Asset symbol")
    set_parser.add_argument(
        "quantity_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="QUANTITY",
    )
    set_parser.add_argument("--quantity", type=float, default=None, dest="quantity")
    set_parser.set_defaults(func=_command_set)

    remove_parser = subparsers.add_parser(
        "remove",
        parents=[common],
        help="Remove an asset or a partial quantity",
    )
    remove_parser.add_argument("symbol", help="Asset symbol")
    remove_parser.add_argument(
        "quantity_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="QUANTITY",
    )
    remove_parser.add_argument("--quantity", type=float, default=None, dest="quantity")
    remove_parser.set_defaults(func=_command_remove)

    price_parser = subparsers.add_parser(
        "price",
        parents=[common],
        help="Set a price",
    )
    price_parser.add_argument("symbol", help="Asset symbol")
    price_parser.add_argument(
        "price_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="PRICE",
    )
    price_parser.add_argument("--price", type=float, default=None, dest="price")
    price_parser.set_defaults(func=_command_price)

    summary_parser = subparsers.add_parser(
        "summary",
        parents=[common],
        help="Show portfolio summary",
    )
    summary_parser.set_defaults(func=_command_summary)

    portfolio_parser = subparsers.add_parser(
        "portfolio",
        aliases=["list"],
        parents=[common],
        help="List portfolio assets",
    )
    portfolio_parser.set_defaults(func=_command_portfolio)

    prices_parser = subparsers.add_parser(
        "prices",
        aliases=["price-list"],
        parents=[common],
        help="List known prices",
    )
    prices_parser.set_defaults(func=_command_prices)

    export_parser = subparsers.add_parser(
        "export",
        parents=[common],
        help="Export portfolio as JSON",
    )
    export_parser.set_defaults(func=_command_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()

    try:
        args = parser.parse_args(argv)
    except _CliError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    func = getattr(args, "func", None)

    if func is None:
        parser.print_help()
        return 0

    try:
        return int(func(args))
    except _CliError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
