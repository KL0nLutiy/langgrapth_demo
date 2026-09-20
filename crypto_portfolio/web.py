from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .cli import (
    _load_portfolio,
    _load_price_provider,
    _save_portfolio,
    _save_price_provider,
)
from .models import Portfolio, normalize_symbol
from .pricing import StaticPriceProvider
from .service import PortfolioService

DEFAULT_PORTFOLIO_PATH = "portfolio.json"
DEFAULT_PRICES_PATH = "prices.json"


def _render_ui(service: PortfolioService) -> str:
    summary = service.get_summary().to_dict()
    rows = []

    for holding in summary["holdings"]:
        asset = str(holding.get("asset", ""))
        rows.append(
            "<tr>"
            f'<td data-asset="{html.escape(asset)}">{html.escape(asset)}</td>'
            f"<td>{float(holding.get('quantity', 0.0)):.6f}</td>"
            f"<td>{float(holding.get('price', 0.0)):.2f}</td>"
            f"<td>{float(holding.get('value', 0.0)):.2f}</td>"
            f"<td>{float(holding.get('avg_price', 0.0)):.2f}</td>"
            f"<td>{float(holding.get('profit_loss', 0.0)):.2f}</td>"
            f"<td>{float(holding.get('profit_loss_pct', 0.0)):.2f}%</td>"
            f"<td>{float(holding.get('allocation_pct', 0.0)):.2f}%</td>"
            "</tr>"
        )

    table = "\n".join(rows)
    currency = html.escape(str(summary.get("currency", "USD")))
    total_value = float(summary.get("total_value", 0.0))
    total_cost = float(summary.get("total_cost", 0.0))
    total_profit_loss = float(summary.get("total_profit_loss", 0.0))
    profit_loss_pct = float(summary.get("profit_loss_pct", 0.0))

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Crypto Portfolio</title>
</head>
<body>
<h1>Crypto Portfolio</h1>
<p>Currency: {currency}</p>
<p>Total value: {total_value:.2f}</p>
<p>Total cost: {total_cost:.2f}</p>
<p>Profit/Loss: {total_profit_loss:.2f} ({profit_loss_pct:.2f}%)</p>
<table border="1">
<thead>
<tr><th>Asset</th><th>Quantity</th><th>Price</th><th>Value</th><th>Avg Price</th><th>P/L</th><th>P/L %</th><th>Allocation %</th></tr>
</thead>
<tbody>
{table}
</tbody>
</table>
<script>
async function refresh() {{
  const response = await fetch('/api/summary');
  const data = await response.json();
  document.title = 'Crypto Portfolio - ' + data.total_value.toFixed(2);
}}
refresh();
</script>
</body>
</html>
"""


def _make_handler(
    service: PortfolioService,
    portfolio_path: str,
    prices_path: Optional[str],
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html_text: str) -> None:
            body = html_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}

            raw = self.rfile.read(length)
            if not raw:
                return {}

            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def _save_portfolio(self) -> None:
            _save_portfolio(portfolio_path, service.portfolio)

        def _save_prices(self) -> None:
            if prices_path and isinstance(service.provider, StaticPriceProvider):
                _save_price_provider(service.provider, prices_path)

        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/":
                    self._send_html(_render_ui(service))
                elif path == "/api/summary":
                    self._send_json(service.get_summary().to_dict())
                elif path == "/api/holdings":
                    self._send_json([holding.to_dict() for holding in service.get_holdings()])
                elif path == "/api/prices":
                    symbols = query.get("symbols") or service.portfolio.symbols()
                    self._send_json(service.get_prices(symbols))
                elif path == "/api/price":
                    symbol = query.get("symbol", [""])[0]
                    if not symbol:
                        self._send_json({"error": "symbol is required"}, 400)
                        return

                    try:
                        normalized = normalize_symbol(symbol)
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, 400)
                        return

                    price = service.get_price(normalized)
                    self._send_json({normalized: price, "asset": normalized, "price": price})
                else:
                    self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                body = self._read_json()

                if path == "/api/add":
                    symbol = body.get("asset") or body.get("symbol")
                    if symbol is None:
                        self._send_json({"error": "asset is required"}, 400)
                        return

                    quantity = body.get("quantity", 0.0)
                    if quantity is None:
                        quantity = 0.0

                    cost_basis = body.get("cost_basis", 0.0)
                    if cost_basis is None:
                        cost_basis = 0.0

                    avg_price = body.get("avg_price")

                    try:
                        service.add_asset(
                            symbol,
                            quantity=quantity,
                            cost_basis=cost_basis,
                            avg_price=avg_price,
                        )
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, 400)
                        return

                    self._save_portfolio()
                    self._send_json(service.get_summary().to_dict())

                elif path == "/api/remove":
                    symbol = body.get("asset") or body.get("symbol")
                    if symbol is None:
                        self._send_json({"error": "asset is required"}, 400)
                        return

                    try:
                        removed = service.remove_asset(symbol)
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, 400)
                        return

                    if not removed:
                        self._send_json({"error": "holding not found"}, 404)
                        return

                    self._save_portfolio()
                    self._send_json(service.get_summary().to_dict())

                elif path == "/api/set":
                    symbol = body.get("asset") or body.get("symbol")
                    quantity = body.get("quantity")

                    if symbol is None or quantity is None:
                        self._send_json({"error": "asset and quantity are required"}, 400)
                        return

                    try:
                        service.set_quantity(symbol, quantity)
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, 400)
                        return

                    self._save_portfolio()
                    self._send_json(service.get_summary().to_dict())

                elif path == "/api/price":
                    symbol = body.get("asset") or body.get("symbol")
                    price = body.get("price")

                    if symbol is None or price is None:
                        self._send_json({"error": "asset and price are required"}, 400)
                        return

                    try:
                        service.set_price(symbol, price)
                    except (ValueError, NotImplementedError) as exc:
                        self._send_json({"error": str(exc)}, 400)
                        return

                    self._save_prices()

                    normalized = normalize_symbol(symbol)
                    current_price = service.get_price(normalized)
                    self._send_json(
                        {normalized: current_price, "asset": normalized, "price": current_price}
                    )
                else:
                    self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)

    return Handler


def create_server(
    port: int = 0,
    *args: Any,
    host: Optional[str] = None,
    portfolio_path: Optional[str] = None,
    prices_path: Optional[str] = None,
    service: Optional[PortfolioService] = None,
) -> ThreadingHTTPServer:
    if host is None:
        host = "127.0.0.1"

    if args:
        if len(args) == 1:
            if portfolio_path is None:
                portfolio_path = args[0]
            else:
                host = args[0]
        elif len(args) == 2:
            if portfolio_path is None and prices_path is None:
                portfolio_path, prices_path = args
            else:
                host, portfolio_path = args
        elif len(args) == 3:
            host, portfolio_path, prices_path = args

    if portfolio_path is None:
        portfolio_path = DEFAULT_PORTFOLIO_PATH

    if service is None:
        portfolio = _load_portfolio(portfolio_path)
        provider = _load_price_provider(prices_path)
        service = PortfolioService(portfolio, provider)

    handler_class = _make_handler(service, portfolio_path, prices_path)
    server = ThreadingHTTPServer((host, port), handler_class)
    server.daemon_threads = True
    server.service = service
    server.portfolio_path = portfolio_path
    server.prices_path = prices_path

    return server
