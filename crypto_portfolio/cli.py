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


class _CliError(Exception):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliError(message)


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


def _default_prices_path(portfolio_path: str) -> str:
    directory = os.path.dirname(os.path.abspath(portfolio_path))
    return os.path.join(directory, DEFAULT_PRICES_PATH)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--portfolio",
        dest="portfolio",
        default=None,
        help="Path to the portfolio JSON file.",
    )
    parser.add_argument(
        "--prices",
        dest="prices",
        default=None,
        help="Path to the prices JSON file.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="crypto-portfolio", description="Crypto portfolio tracker")
    parser.add_argument(
        "--portfolio",
        dest="global_portfolio",
        default=None,
        help="Path to the portfolio JSON file.",
    )
    parser.add_argument(
        "--prices",
        dest="global_prices",
        default=None,
        help="Path to the prices JSON file.",
    )

    sub = parser.add_subparsers(dest="command", metavar="command")

    for name in ("init", "new"):
        p = sub.add_parser(name, help="Initialize portfolio and prices files.")
        _add_common(p)
        p.add_argument("--currency", default="USD", help="Portfolio currency.")

    for name in ("add", "buy"):
        p = sub.add_parser(name, help="Add or increase an asset.")
        _add_common(p)
        p.add_argument("--symbol", "-s", required=True, help="Asset symbol.")
        p.add_argument("--quantity", "-q", type=float, default=0.0, help="Quantity to add.")
        p.add_argument(
            "--cost-basis",
            "--cost",
            dest="cost_basis",
            type=float,
            default=0.0,
            help="Cost basis to add.",
        )
        p.add_argument(
            "--avg-price",
            "--avg",
            dest="avg_price",
            type=float,
            default=None,
            help="Average purchase price. If provided, cost basis is derived.",
        )

    for name in ("set", "update"):
        p = sub.add_parser(name, help="Set quantity for an existing asset.")
        _add_common(p)
        p.add_argument("--symbol", "-s", required=True, help="Asset symbol.")
        p.add_argument("--quantity", "-q", type=float, required=True, help="New quantity.")

    for name in ("remove", "sell", "delete"):
        p = sub.add_parser(name, help="Remove an asset or a quantity of an asset.")
        _add_common(p)
        p.add_argument("--symbol", "-s", required=True, help="Asset symbol.")
        p.add_argument(
            "--quantity",
            "-q",
            type=float,
            default=None,
            help="Optional quantity to remove. Omit to remove the whole asset.",
        )

    for name in ("price", "set-price"):
        p = sub.add_parser(name, help="Set a price for an asset.")
        _add_common(p)
        p.add_argument("--symbol", "-s", required=True, help="Asset symbol.")
        p.add_argument("--price", "-p", type=float, required=True, help="Price value.")

    for name in ("portfolio", "list", "show"):
        p = sub.add_parser(name, help="Show the portfolio.")
        _add_common(p)
        p.add_argument("--json", action="store_true", dest="as_json", help="Output JSON.")

    for name in ("prices", "price-list", "list-prices"):
        p = sub.add_parser(name, help="Show known prices.")
        _add_common(p)
        p.add_argument("--json", action="store_true", dest="as_json", help="Output JSON.")

    for name in ("export", "dump"):
        p = sub.add_parser(name, help="Export portfolio JSON.")
        _add_common(p)
        p.add_argument("--indent", type=int, default=2, help="JSON indent.")

    for name in ("serve", "web"):
        p = sub.add_parser(name, help="Run the web server.")
        _add_common(p)
        p.add_argument("--host", default="127.0.0.1", help="Host to bind.")
        p.add_argument("--port", type=int, default=8000, help="Port to bind.")

    return parser


def _format_portfolio(summary: "PortfolioSummary") -> str:
    lines = ["Portfolio"]

    if not summary.holdings:
        lines.append("No assets.")
        return "\n".join(lines)

    lines.append(
        f"{'Symbol':<8} {'Quantity':>10} {'Price':>12} {'Value':>12} "
        f"{'Cost':>12} {'PnL':>12} {'PnL%':>8} {'Alloc%':>8}"
    )

    for holding in summary.holdings:
        lines.append(
            f"{holding.symbol:<8} {holding.quantity:>10.4f} {holding.price:>12.2f} "
            f"{holding.value:>12.2f} {holding.cost_basis:>12.2f} "
            f"{holding.profit_loss:>12.2f} {holding.profit_loss_pct:>7.2f}% "
            f"{holding.allocation_pct:>7.2f}%"
        )

    lines.append(
        f"{'Total':<8} {'':>10} {'':>12} {summary.total_value:>12.2f} "
        f"{summary.total_cost:>12.2f} {summary.total_profit_loss:>12.2f} "
        f"{summary.profit_loss_pct:>7.2f}% {'100.00%':>8}"
    )

    return "\n".join(lines)


def _format_prices(prices: Dict[str, float]) -> str:
    lines = ["Portfolio Prices"]

    if not prices:
        lines.append("No prices.")
        return "\n".join(lines)

    lines.append(f"{'Symbol':<8} {'Price':>12}")

    for symbol in sorted(prices):
        lines.append(f"{symbol:<8} {float(prices[symbol]):>12.2f}")

    return "\n".join(lines)


def _dispatch(args: argparse.Namespace) -> int:
    portfolio_path, prices_path = _resolve_paths(args)
    command = getattr(args, "command", None)

    if command in {"init", "new"}:
        portfolio = Portfolio(currency=getattr(args, "currency", "USD"))
        _save_portfolio(portfolio_path, portfolio)

        if prices_path is None:
            prices_path = _default_prices_path(portfolio_path)

        _save_price_provider(StaticPriceProvider(), prices_path)

        print(f"Initialized portfolio at {portfolio_path}")
        print(f"Initialized prices at {prices_path}")
        return 0

    portfolio = _load_portfolio(portfolio_path)
    provider = _load_price_provider(prices_path)
    service = PortfolioService(portfolio, provider)

    if command in {"add", "buy"}:
        asset = service.add_asset(args.symbol, args.quantity, args.cost_basis, args.avg_price)
        _save_portfolio(portfolio_path, portfolio)
        print(
            f"Added {asset.symbol}: quantity={asset.quantity:.4f} "
            f"cost_basis={asset.cost_basis:.2f}"
        )
        return 0

    if command in {"set", "update"}:
        ok = service.set_quantity(args.symbol, args.quantity)
        if not ok:
            raise _CliError(f"asset {normalize_symbol(args.symbol)} not found")

        _save_portfolio(portfolio_path, portfolio)

        if float(args.quantity) <= 0:
            print(f"Removed {normalize_symbol(args.symbol)}")
        else:
            print(f"Set {normalize_symbol(args.symbol)} quantity to {float(args.quantity):.4f}")

        return 0

    if command in {"remove", "sell", "delete"}:
        ok = service.remove_asset(args.symbol, args.quantity)
        if not ok:
            raise _CliError(f"asset {normalize_symbol(args.symbol)} not found")

        _save_portfolio(portfolio_path, portfolio)

        if args.quantity is not None and float(args.quantity) <= 0:
            print(f"No change for {normalize_symbol(args.symbol)}")
        else:
            print(f"Removed {normalize_symbol(args.symbol)}")

        return 0

    if command in {"price", "set-price"}:
        service.set_price(args.symbol, args.price)

        if prices_path is None:
            prices_path = _default_prices_path(portfolio_path)

        _save_price_provider(provider, prices_path)
        print(f"Set price for {normalize_symbol(args.symbol)} to {float(args.price):.2f}")
        return 0

    if command in {"portfolio", "list", "show"}:
        summary = service.get_summary()

        if getattr(args, "as_json", False):
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            print(_format_portfolio(summary))

        return 0

    if command in {"prices", "price-list", "list-prices"}:
        symbols = provider.symbols()
        prices = service.get_prices(symbols) if symbols else {}

        if getattr(args, "as_json", False):
            print(json.dumps(prices, indent=2))
        else:
            print(_format_prices(prices))

        return 0

    if command in {"export", "dump"}:
        print(json.dumps(portfolio.to_dict(), indent=getattr(args, "indent", 2)))
        return 0

    if command in {"serve", "web"}:
        from .web import create_server

        server = create_server(
            host=args.host,
            port=args.port,
            portfolio_path=portfolio_path,
            prices_path=prices_path,
        )
        print(f"Serving on http://{args.host}:{server.server_address[1]}")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

        return 0

    raise _CliError(f"unknown command {command}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()

    try:
        args = parser.parse_args(argv)
    except _CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        return int(exc.code or 0)

    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    try:
        return _dispatch(args)
    except _CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
