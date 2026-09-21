from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlsplit

try:
    from http.server import ThreadingHTTPServer
except ImportError:  # pragma: no cover - fallback for older Python versions
    from http.server import HTTPServer as ThreadingHTTPServer

from .models import Portfolio, _validate_amount, normalize_symbol
from .pricing import PriceProvider, SamplePriceProvider, StaticPriceProvider
from .service import PortfolioService

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Portfolio</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; background: #f7f9fc; color: #1f2933; }
    h1 { margin-bottom: 0.25rem; }
    .card { background: #fff; border: 1px solid #e4e7eb; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #e4e7eb; }
    button { background: #2563eb; color: white; border: 0; border-radius: 6px; padding: 0.5rem 0.75rem; cursor: pointer; }
    input { padding: 0.4rem; border: 1px solid #cbd2d9; border-radius: 6px; margin-right: 0.5rem; }
    .summary span { margin-right: 1.5rem; }
  </style>
</head>
<body>
  <h1>Crypto Portfolio</h1>

  <div class="card" id="summary">Loading summary...</div>

  <div class="card">
    <h2>Holdings</h2>
    <table id="holdings">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Quantity</th>
          <th>Avg Price</th>
          <th>Price</th>
          <th>Value</th>
          <th>P/L</th>
          <th>Allocation</th>
          <th></th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="card">
    <h2>Add Asset</h2>
    <form id="add-form">
      <input name="symbol" placeholder="Symbol" required>
      <input name="quantity" type="number" step="any" placeholder="Quantity" required>
      <input name="avg_price" type="number" step="any" placeholder="Avg price">
      <button type="submit">Add</button>
    </form>
  </div>

  <div class="card">
    <h2>Set Price</h2>
    <form id="price-form">
      <input name="symbol" placeholder="Symbol" required>
      <input name="price" type="number" step="any" placeholder="Price" required>
      <button type="submit">Set Price</button>
    </form>
  </div>

  <script>
    async function fetchJSON(url, options) {
      const response = await fetch(url, options);
      return response.json();
    }

    function format(value) {
      return Number(value || 0).toFixed(2);
    }

    async function load() {
      const summary = await fetchJSON('/api/summary');
      document.getElementById('summary').innerHTML =
        `<span>Total value: ${format(summary.total_value)} ${summary.currency}</span>` +
        `<span>Total cost: ${format(summary.total_cost)} ${summary.currency}</span>` +
        `<span>Profit/Loss: ${format(summary.total_profit_loss)} ${summary.currency} (${format(summary.profit_loss_pct)}%)</span>`;

      const holdings = await fetchJSON('/api/holdings');
      const tbody = document.querySelector('#holdings tbody');
      tbody.innerHTML = '';

      holdings.forEach((holding) => {
        const row = document.createElement('tr');
        row.innerHTML =
          `<td>${holding.symbol}</td>` +
          `<td>${holding.quantity}</td>` +
          `<td>${format(holding.avg_price)}</td>` +
          `<td>${format(holding.price)}</td>` +
          `<td>${format(holding.value)}</td>` +
          `<td>${format(holding.profit_loss)}</td>` +
          `<td>${format(holding.allocation_pct)}%</td>` +
          `<td><button data-symbol="${holding.symbol}">Remove</button></td>`;
        tbody.appendChild(row);
      });

      document.querySelectorAll('#holdings button').forEach((button) => {
        button.addEventListener('click', async () => {
          await fetchJSON(`/api/assets/${button.dataset.symbol}`, { method: 'DELETE' });
          load();
        });
      });
    }

    document.getElementById('add-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        symbol: form.symbol.value,
        quantity: Number(form.quantity.value),
        avg_price: form.avg_price.value ? Number(form.avg_price.value) : undefined
      };

      await fetchJSON('/api/assets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      form.reset();
      load();
    });

    document.getElementById('price-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;

      await fetchJSON('/api/prices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol.value,
          price: Number(form.price.value)
        })
      });

      form.reset();
      load();
    });

    load();
  </script>
</body>
</html>
"""


def _load_portfolio(path: str | None) -> Portfolio:
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


def _save_portfolio(path: str | None, portfolio: Portfolio) -> None:
    if not path:
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(portfolio.to_dict(), handle, indent=2)
        handle.write("\n")


def _normalize_prices(data: object) -> object:
    if isinstance(data, Mapping):
        if "prices" in data and isinstance(data.get("prices"), (Mapping, list, tuple)):
            return _normalize_prices(data.get("prices"))

        prices = {}
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


def _load_price_provider(path: str | None) -> PriceProvider:
    if not path or not os.path.exists(path):
        return SamplePriceProvider()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        if not content.strip():
            return StaticPriceProvider()

        data = json.loads(content)
        return StaticPriceProvider(_normalize_prices(data))
    except Exception:
        return StaticPriceProvider()


def _save_price_provider(path: str | None, provider: PriceProvider) -> None:
    if not path:
        return

    prices = {symbol: provider.get_price(symbol) for symbol in provider.symbols()}

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(prices, handle, indent=2)
        handle.write("\n")


class _PortfolioHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        portfolio_path: str | None,
        prices_path: str | None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.portfolio_path = portfolio_path
        self.prices_path = prices_path
        self.lock = threading.Lock()
        self.portfolio = _load_portfolio(portfolio_path)
        self.provider = _load_price_provider(prices_path)


class _Handler(BaseHTTPRequestHandler):
    server_version = "CryptoPortfolio/0.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}

        raw = self.rfile.read(length)
        if not raw:
            return {}

        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

        return data if isinstance(data, dict) else {}

    def _service(self) -> PortfolioService:
        return PortfolioService(self.server.portfolio, self.server.provider)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path

        if path == "/":
            self._send_html(_HTML)
            return

        if path == "/api/summary":
            with self.server.lock:
                service = self._service()
                self._send_json(service.get_summary().to_dict())
            return

        if path == "/api/holdings":
            with self.server.lock:
                service = self._service()
                self._send_json([holding.to_dict() for holding in service.get_holdings()])
            return

        if path == "/api/assets":
            with self.server.lock:
                self._send_json([asset.to_dict() for asset in self.server.portfolio.assets()])
            return

        if path == "/api/prices":
            with self.server.lock:
                provider = self.server.provider
                self._send_json(
                    {symbol: provider.get_price(symbol) for symbol in provider.symbols()}
                )
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path

        if path == "/api/assets":
            payload = self._read_json()
            symbol = payload.get("symbol")

            if not symbol:
                self._send_json({"error": "symbol is required"}, status=400)
                return

            quantity = payload.get("quantity", 0)
            avg_price = payload.get("avg_price")
            cost_basis = payload.get("cost_basis")

            with self.server.lock:
                service = self._service()

                try:
                    asset = service.add_asset(
                        symbol,
                        quantity=quantity,
                        cost_basis=cost_basis,
                        avg_price=avg_price,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return

                _save_portfolio(self.server.portfolio_path, self.server.portfolio)
                summary = service.get_summary()

            asset_payload = asset.to_dict() if asset is not None else None
            self._send_json({"asset": asset_payload, "summary": summary.to_dict()})
            return

        if path == "/api/prices":
            payload = self._read_json()
            symbol = payload.get("symbol")
            price = payload.get("price")

            if not symbol or price is None:
                self._send_json({"error": "symbol and price are required"}, status=400)
                return

            with self.server.lock:
                try:
                    normalized_symbol = normalize_symbol(symbol)
                    self.server.provider.set_price(normalized_symbol, price)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return

                _save_price_provider(self.server.prices_path, self.server.provider)

            self._send_json({"symbol": normalized_symbol, "price": float(price)})
            return

        self._send_json({"error": "not found"}, status=404)

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path

        if path.startswith("/api/assets/"):
            symbol = unquote(path[len("/api/assets/"):])

            with self.server.lock:
                try:
                    normalized_symbol = normalize_symbol(symbol)
                except ValueError:
                    self._send_json({"error": "symbol is required"}, status=400)
                    return

                removed = self.server.portfolio.remove_asset(normalized_symbol)
                _save_portfolio(self.server.portfolio_path, self.server.portfolio)

                service = self._service()
                summary = service.get_summary()

            if not removed:
                self._send_json(
                    {"error": "asset not found", "summary": summary.to_dict()},
                    status=404,
                )
            else:
                self._send_json({"removed": True, "summary": summary.to_dict()})
            return

        self._send_json({"error": "not found"}, status=404)


def create_server(
    host: str,
    port: int,
    portfolio_path: str | None,
    prices_path: str | None,
) -> _PortfolioHTTPServer:
    return _PortfolioHTTPServer((host, port), _Handler, portfolio_path, prices_path)
