from __future__ import annotations

import html
import json
import os
import socketserver
import urllib.parse
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from .cli import (
    DEFAULT_PORTFOLIO_PATH,
    DEFAULT_PRICES_PATH,
    _load_portfolio,
    _load_price_provider,
    _save_portfolio,
    _save_price_provider,
)
from .models import PortfolioSummary
from .service import PortfolioService


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_STYLE = """
<style>
body { font-family: Arial, Helvetica, sans-serif; margin: 24px; color: #1f2933; }
table { border-collapse: collapse; width: 100%; max-width: 960px; }
th, td { border: 1px solid #cbd2d9; padding: 8px 10px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
h1, h2 { margin-bottom: 12px; }
</style>
"""

_SCRIPT = """
<script>
async function refresh() {
  try {
    const response = await fetch('/api/portfolio');
    const data = await response.json();
    const element = document.getElementById('total-value');
    if (element) {
      element.textContent = Number(data.total_value || 0).toFixed(2);
    }
  } catch (error) {
    console.error(error);
  }
}
refresh();
</script>
"""


class PortfolioRequestHandler(BaseHTTPRequestHandler):
    server_version = "CryptoPortfolio/0.1"

    def __init__(
        self,
        *args: Any,
        portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
        prices_path: Optional[str] = None,
        service: Optional[PortfolioService] = None,
        **kwargs: Any,
    ) -> None:
        self.portfolio_path = portfolio_path
        self.prices_path = prices_path
        self._injected_service = service
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _service(self) -> PortfolioService:
        if self._injected_service is not None:
            return self._injected_service

        portfolio = _load_portfolio(self.portfolio_path)
        provider = _load_price_provider(self.prices_path)
        return PortfolioService(portfolio, provider)

    def _all_prices(self, service: PortfolioService) -> Dict[str, float]:
        symbols = service.provider.symbols()
        if symbols:
            return service.get_prices(symbols)
        return {}

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str, status: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0

        if length <= 0:
            return {}

        raw = self.rfile.read(length)
        if not raw:
            return {}

        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _normalize_path(self, path: str) -> str:
        if len(path) > 1:
            path = path.rstrip("/")
        if not path:
            path = "/"
        return path

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = self._normalize_path(parsed.path)

        try:
            if path in {"/", "/index.html"}:
                service = self._service()
                self._send_html(_render_ui(service.get_summary()))
            elif path in {"/api/portfolio", "/api/summary"}:
                service = self._service()
                self._send_json(service.get_summary().to_dict())
            elif path == "/api/assets":
                service = self._service()
                self._send_json([holding.to_dict() for holding in service.get_holdings()])
            elif path == "/api/prices":
                service = self._service()
                self._send_json(self._all_prices(service))
            elif path == "/health":
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = self._normalize_path(parsed.path)
        body = self._read_json()

        try:
            service = self._service()

            if path in {"/api/assets", "/api/portfolio/assets"}:
                if not isinstance(body, dict) or "symbol" not in body:
                    raise ValueError("symbol is required")

                symbol = body["symbol"]

                if body.get("remove"):
                    ok = service.remove_asset(symbol, body.get("quantity"))
                    if not ok:
                        self._send_json({"error": "asset not found"}, status=404)
                        return
                elif (
                    "set_quantity" in body
                    or body.get("action") == "set"
                    or ("quantity" in body and body.get("set"))
                ):
                    quantity = body.get("set_quantity", body.get("quantity", 0.0))
                    ok = service.set_quantity(symbol, quantity)
                    if not ok:
                        self._send_json({"error": "asset not found"}, status=404)
                        return
                else:
                    service.add_asset(
                        symbol,
                        body.get("quantity", 0.0),
                        body.get("cost_basis", body.get("cost", 0.0)),
                        body.get("avg_price", body.get("avg")),
                    )

                if self._injected_service is None:
                    _save_portfolio(self.portfolio_path, service.portfolio)

                self._send_json(service.get_summary().to_dict(), status=201)

            elif path in {"/api/prices", "/api/portfolio/prices"}:
                if not isinstance(body, dict) or "symbol" not in body or "price" not in body:
                    raise ValueError("symbol and price are required")

                service.set_price(body["symbol"], body["price"])

                if self._injected_service is None and self.prices_path:
                    _save_price_provider(service.provider, self.prices_path)

                self._send_json(self._all_prices(service), status=201)

            else:
                self._send_json({"error": "not found"}, status=404)

        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def _render_ui(summary: PortfolioSummary) -> str:
    rows = []

    for holding in summary.holdings:
        rows.append(
            "<tr>"
            f"<td>{html.escape(holding.symbol)}</td>"
            f"<td>{holding.quantity:.4f}</td>"
            f"<td>{holding.price:.2f}</td>"
            f"<td>{holding.value:.2f}</td>"
            f"<td>{holding.cost_basis:.2f}</td>"
            f"<td>{holding.profit_loss:.2f}</td>"
            f"<td>{holding.profit_loss_pct:.2f}%</td>"
            f"<td>{holding.allocation_pct:.2f}%</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Crypto Portfolio</title>
{_STYLE}
</head>
<body>
<h1>Crypto Portfolio</h1>
<h2>Portfolio</h2>
<div id="assets">
<table>
<thead>
<tr>
<th>Symbol</th>
<th>Quantity</th>
<th>Price</th>
<th>Value</th>
<th>Cost</th>
<th>PnL</th>
<th>PnL%</th>
<th>Alloc%</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
<p>Total value: <span id="total-value">{summary.total_value:.2f}</span> {html.escape(summary.currency)}</p>
<p>Total cost: {summary.total_cost:.2f} {html.escape(summary.currency)}</p>
<p>Total PnL: {summary.total_profit_loss:.2f} ({summary.profit_loss_pct:.2f}%)</p>
{_SCRIPT}
</body>
</html>
"""


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
    prices_path: Optional[str] = None,
    service: Optional[PortfolioService] = None,
) -> ThreadingHTTPServer:
    if isinstance(host, tuple):
        host, port = host

    host = str(host or "127.0.0.1")

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0

    if port < 0:
        port = 0

    if portfolio_path is None:
        portfolio_path = DEFAULT_PORTFOLIO_PATH

    handler = partial(
        PortfolioRequestHandler,
        portfolio_path=portfolio_path,
        prices_path=prices_path,
        service=service,
    )

    return ThreadingHTTPServer((host, port), handler)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
    prices_path: Optional[str] = None,
    service: Optional[PortfolioService] = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        portfolio_path=portfolio_path,
        prices_path=prices_path,
        service=service,
    )

    print(f"Serving on http://{host}:{server.server_address[1]}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
