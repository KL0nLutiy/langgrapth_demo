from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Mapping, Optional

from .models import Asset, AssetValue, Portfolio, _validate_amount, normalize_symbol
from .pricing import PriceProvider, SamplePriceProvider, StaticPriceProvider
from .service import PortfolioService

DEFAULT_PORTFOLIO_PATH = "portfolio.json"
DEFAULT_PRICES_PATH = "prices.json"


def _resolve_paths(args: argparse.Namespace) -> tuple[str, Optional[str]]:
    portfolio = (
        getattr(args, "portfolio", None)
        or getattr(args, "global_portfolio", None)
        or DEFAULT_PORTFOLIO_PATH
    )
    prices = getattr(args, "prices", None) or getattr(args, "global_prices", None)

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
        return dict(data)

    if isinstance(data, list):
        prices: Dict[str, Any] = {}

        for item in data:
            if isinstance(item, Mapping):
                symbol = item.get("symbol")
                price = item.get("price")
                if symbol is not None and price is not None:
                    prices[str(symbol)] = price
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                prices[str(item[0])] = item[1]

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


def _save_price_provider(provider: PriceProvider, path: str) -> None:
    if not path or not isinstance(provider, StaticPriceProvider):
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(provider.to_dict(), handle, indent=2)
        handle.write("\n")


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _print_holdings_table(holdings: List[AssetValue]) -> None:
    if not holdings:
        print("No holdings.")
        return

    header = (
        f"{'Asset':<10} {'Quantity':>12} {'Price':>12} {'Value':>12} "
        f"{'Avg Price':>12} {'P/L':>12} {'P/L %':>10} {'Allocation %':>12}"
    )
    print(header)

    for holding in holdings:
        print(
            f"{holding.symbol:<10} "
            f"{holding.quantity:>12.6f} "
            f"{holding.price:>12.2f} "
            f"{holding.value:>12.2f} "
            f"{holding.avg_price:>12.2f} "
            f"{holding.profit_loss:>12.2f} "
            f"{holding.profit_loss_pct:>9.2f}% "
            f"{holding.allocation_pct:>11.2f}%"
        )


def _error(message: str) -> None:
    print(message, file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-portfolio",
        description="Track a crypto portfolio with CLI and web UI.",
    )

    parser.add_argument(
        "--portfolio",
        dest="global_portfolio",
        default=None,
        help="Path to the portfolio JSON file",
    )
    parser.add_argument(
        "--prices",
        dest="global_prices",
        default=None,
        help="Path to the prices JSON file",
    )

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize portfolio and price files")
    init_parser.add_argument("--portfolio", dest="portfolio", default=None)
    init_parser.add_argument("--prices", dest="prices", default=None)

    summary_parser = subparsers.add_parser("summary", help="Show portfolio summary")
    summary_parser.add_argument("--portfolio", dest="portfolio", default=None)
    summary_parser.add_argument("--prices", dest="prices", default=None)

    holdings_parser = subparsers.add_parser("holdings", help="List holdings")
    holdings_parser.add_argument("--portfolio", dest="portfolio", default=None)
    holdings_parser.add_argument("--prices", dest="prices", default=None)

    add_parser = subparsers.add_parser("add", help="Add or increase a holding")
    add_parser.add_argument("symbol")
    add_parser.add_argument("quantity")
    add_parser.add_argument("--cost-basis", dest="cost_basis", default=None)
    add_parser.add_argument("--avg-price", dest="avg_price", default=None)
    add_parser.add_argument("--portfolio", dest="portfolio", default=None)
    add_parser.add_argument("--prices", dest="prices", default=None)

    remove_parser = subparsers.add_parser("remove", help="Remove a holding")
    remove_parser.add_argument("symbol")
    remove_parser.add_argument("--portfolio", dest="portfolio", default=None)
    remove_parser.add_argument("--prices", dest="prices", default=None)

    set_parser = subparsers.add_parser("set", help="Set the quantity for a holding")
    set_parser.add_argument("symbol")
    set_parser.add_argument("quantity")
    set_parser.add_argument("--portfolio", dest="portfolio", default=None)
    set_parser.add_argument("--prices", dest="prices", default=None)

    price_parser = subparsers.add_parser("price", help="Get or set a price")
    price_parser.add_argument("symbol")
    price_parser.add_argument("price", nargs="?", default=None)
    price_parser.add_argument("--portfolio", dest="portfolio", default=None)
    price_parser.add_argument("--prices", dest="prices", default=None)

    prices_parser = subparsers.add_parser("prices", help="List known prices")
    prices_parser.add_argument("--portfolio", dest="portfolio", default=None)
    prices_parser.add_argument("--prices", dest="prices", default=None)

    export_parser = subparsers.add_parser("export", help="Export portfolio as JSON")
    export_parser.add_argument("--portfolio", dest="portfolio", default=None)
    export_parser.add_argument("--prices", dest="prices", default=None)

    web_parser = subparsers.add_parser("web", help="Start the web UI")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", default="8000")
    web_parser.add_argument("--portfolio", dest="portfolio", default=None)
    web_parser.add_argument("--prices", dest="prices", default=None)

    return parser


def _service_for(args: argparse.Namespace) -> PortfolioService:
    portfolio_path, prices_path = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(prices_path)
    return PortfolioService(portfolio, provider)


def _cmd_init(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    if not prices_path:
        prices_path = DEFAULT_PRICES_PATH

    portfolio = Portfolio(currency="USD")
    _save_portfolio(portfolio_path, portfolio)

    provider = StaticPriceProvider()
    _save_price_provider(provider, prices_path)

    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    service = _service_for(args)
    _print_json(service.get_summary().to_dict())
    return 0


def _cmd_holdings(args: argparse.Namespace) -> int:
    service = _service_for(args)
    _print_holdings_table(service.get_holdings())
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)

    try:
        normalized_symbol = normalize_symbol(args.symbol)
        quantity = _validate_amount(args.quantity, "quantity")
        cost_basis = (
            _validate_amount(args.cost_basis, "cost_basis")
            if args.cost_basis is not None
            else 0.0
        )
        avg_price = (
            _validate_amount(args.avg_price, "avg_price")
            if args.avg_price is not None
            else None
        )
    except ValueError as exc:
        _error(str(exc))
        return 1

    portfolio = _load_portfolio(portfolio_path)

    try:
        portfolio.add_asset(
            normalized_symbol,
            quantity=quantity,
            cost_basis=cost_basis,
            avg_price=avg_price,
        )
    except ValueError as exc:
        _error(str(exc))
        return 1

    _save_portfolio(portfolio_path, portfolio)

    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)
    _print_json(service.get_summary().to_dict())

    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)

    try:
        normalized_symbol = normalize_symbol(args.symbol)
    except ValueError as exc:
        _error(str(exc))
        return 1

    portfolio = _load_portfolio(portfolio_path)

    if not portfolio.remove_asset(normalized_symbol):
        _error(f"No holding found for {normalized_symbol}")
        return 1

    _save_portfolio(portfolio_path, portfolio)

    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)
    _print_json(service.get_summary().to_dict())

    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)

    try:
        normalized_symbol = normalize_symbol(args.symbol)
        quantity = _validate_amount(args.quantity, "quantity")
    except ValueError as exc:
        _error(str(exc))
        return 1

    portfolio = _load_portfolio(portfolio_path)

    try:
        portfolio.set_quantity(normalized_symbol, quantity)
    except ValueError as exc:
        _error(str(exc))
        return 1

    _save_portfolio(portfolio_path, portfolio)

    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)
    _print_json(service.get_summary().to_dict())

    return 0


def _cmd_price(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)

    try:
        normalized_symbol = normalize_symbol(args.symbol)
    except ValueError as exc:
        _error(str(exc))
        return 1

    provider = _load_price_provider(prices_path)

    if args.price is not None:
        try:
            price = _validate_amount(args.price, "price")
        except ValueError as exc:
            _error(str(exc))
            return 1

        try:
            provider.set_price(normalized_symbol, price)
        except (ValueError, NotImplementedError) as exc:
            _error(str(exc))
            return 1

        if not prices_path:
            prices_path = DEFAULT_PRICES_PATH

        _save_price_provider(provider, prices_path)

    value = provider.get_price(normalized_symbol)
    _print_json({normalized_symbol: value})

    return 0


def _cmd_prices(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    provider = _load_price_provider(prices_path)

    symbols = provider.symbols()
    if not symbols:
        portfolio = _load_portfolio(portfolio_path)
        symbols = portfolio.symbols()

    _print_json(provider.get_prices(symbols))

    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    portfolio_path, _ = _resolve_paths(args)
    portfolio = _load_portfolio(portfolio_path)
    _print_json(portfolio.to_dict())
    return 0


def _cmd_web(args: argparse.Namespace) -> int:
    from .web import create_server

    portfolio_path, prices_path = _resolve_paths(args)

    try:
        port = int(args.port)
    except ValueError:
        _error("port must be an integer")
        return 1

    server = create_server(
        port=port,
        host=args.host,
        portfolio_path=portfolio_path,
        prices_path=prices_path,
    )

    actual_port = server.server_address[1]
    print(f"Web UI available at http://{args.host}:{actual_port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


_COMMANDS = {
    "init": _cmd_init,
    "summary": _cmd_summary,
    "holdings": _cmd_holdings,
    "add": _cmd_add,
    "remove": _cmd_remove,
    "set": _cmd_set,
    "price": _cmd_price,
    "prices": _cmd_prices,
    "export": _cmd_export,
    "web": _cmd_web,
}


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    command = getattr(args, "command", None)
    if not command:
        parser.print_help()
        return 0

    handler = _COMMANDS.get(command)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2

    return handler(args)
