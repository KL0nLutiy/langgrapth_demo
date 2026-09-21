from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

from . import (
    Portfolio,
    PortfolioService,
    StaticPriceProvider,
    _validate_amount,
    normalize_symbol,
)

INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Crypto Portfolio</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border: 1px solid #ccc; padding: 0.5rem; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    form { margin: 1rem 0; display: flex; gap: 0.5rem; flex-wrap: wrap; }
    input { padding: 0.25rem; }
    .summary { margin: 1rem 0; }
  </style>
</head>
<body>
  <h1>Crypto Portfolio</h1>

  <div class="summary" id="summary"></div>

  <form id="asset-form">
    <input name="symbol" placeholder="Symbol" required>
    <input name="quantity" type="number" step="any" placeholder="Quantity" required>
    <input name="avg_price" type="number" step="any" placeholder="Avg price">
    <button type="submit">Add asset</button>
  </form>

  <form id="price-form">
    <input name="symbol" placeholder="Symbol" required>
    <input name="price" type="number" step="any" placeholder="Price" required>
    <button type="submit">Set price</button>
  </form>

  <table id="holdings">
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Quantity</th>
        <th>Price</th>
        <th>Value</th>
        <th>Avg</th>
        <th>P/L</th>
        <th>P/L %</th>
        <th>Alloc %</th>
        <th></th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <script>
    async function refresh() {
      const summary = await (await fetch('/api/summary')).json();
      document.getElementById('summary').textContent =
        `Currency: ${summary.currency} | Value: ${summary.total_value} | Cost: ${summary.total_cost} | P/L: ${summary.total_profit_loss}`;

      const holdings = await (await fetch('/api/holdings')).json();
      const tbody = document.querySelector('#holdings tbody');
      tbody.innerHTML = '';

      for (const holding of holdings) {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${holding.symbol}</td>
          <td>${holding.quantity}</td>
          <td>${holding.price}</td>
          <td>${holding.value}</td>
          <td>${holding.avg_price}</td>
          <td>${holding.profit_loss}</td>
          <td>${holding.profit_loss_pct}</td>
          <td>${holding.allocation_pct}</td>
          <td><button data-symbol="${holding.symbol}">Remove</button></td>
        `;
        tbody.appendChild(row);
      }

      document.querySelectorAll('#holdings button[data-symbol]').forEach((button) => {
        button.addEventListener('click', async () => {
          await fetch(`/api/assets/${button.dataset.symbol}`, { method: 'DELETE' });
          refresh();
        });
      });
    }

    document.getElementById('asset-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        symbol: form.symbol.value,
        quantity: Number(form.quantity.value),
        avg_price: Number(form.avg_price.value || 0)
      };

      await fetch('/api/assets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      form.reset();
      refresh();
    });

    document.getElementById('price-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        symbol: form.symbol.value,
        price: Number(form.price.value)
      };

      await fetch('/api/prices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      form.reset();
      refresh();
    });

    refresh();
  </script>
</body>
</html>
"""


def _load_portfolio(path: Optional[str]) -> Portfolio:
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


def _save_portfolio(path: Optional[str], portfolio: Portfolio) -> None:
    if not path:
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(portfolio.to_dict(), handle, indent=2)
        handle.write("\n")


def _load_prices(path: Optional[str]) -> StaticPriceProvider:
    candidate = path or os.environ.get("CRYPTO_PRICES_PATH") or "prices.json"

    if not candidate or not os.path.exists(candidate):
        return StaticPriceProvider({})

    try:
        with open(candidate, "r", encoding="utf-8") as handle:
            content = handle.read()

        if not content.strip():
            return StaticPriceProvider({})

        data = json.loads(content)
        return StaticPriceProvider(data)
    except Exception:
        return StaticPriceProvider({})


def _save_prices(path: Optional[str], provider: StaticPriceProvider) -> None:
    if not path:
        return

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(provider.to_dict(), handle, indent=2)
        handle.write("\n")


class _Handler(BaseHTTPRequestHandler):
    server_version = "CryptoPortfolio/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")

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

    def _read_json(self) -> Dict[str, Any]:
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
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

        if not isinstance(payload, dict):
            return {}

        return payload

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._send_html(INDEX_HTML)
            return

        if path == "/api/summary":
            with self.server.lock:
                payload = self.server.service.get_summary().to_dict()
            self._send_json(payload)
            return

        if path == "/api/holdings":
            with self.server.lock:
                payload = [
                    holding.to_dict()
                    for holding in self.server.service.get_holdings()
                ]
            self._send_json(payload)
            return

        if path == "/api/assets":
            with self.server.lock:
                payload = []
                for symbol in self.server.portfolio.symbols():
                    asset = self.server.portfolio.get_asset(symbol)
                    if asset is not None:
                        payload.append(asset.to_dict())
            self._send_json(payload)
            return

        if path == "/api/prices":
            with self.server.lock:
                payload = self.server.provider.to_dict()
            self._send_json(payload)
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = self._read_json()

        if path == "/api/assets":
            try:
                symbol = normalize_symbol(payload.get("symbol"))
                if not symbol:
                    raise ValueError("symbol is required")

                quantity = _validate_amount(payload.get("quantity", 0.0), "quantity")

                cost_basis = payload.get("cost_basis", payload.get("cost"))
                if cost_basis is None:
                    avg_price = payload.get("avg_price", payload.get("price", 0.0))
                    cost_basis = quantity * _validate_amount(avg_price, "avg_price")
                else:
                    cost_basis = _validate_amount(cost_basis, "cost_basis")

                with self.server.lock:
                    self.server.portfolio.add_asset(symbol, quantity, cost_basis)
                    _save_portfolio(self.server.portfolio_path, self.server.portfolio)

                    asset = self.server.portfolio.get_asset(symbol)
                    summary = self.server.service.get_summary().to_dict()

                self._send_json(
                    {
                        "asset": asset.to_dict() if asset else None,
                        "summary": summary,
                    }
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        if path == "/api/prices":
            try:
                symbol = normalize_symbol(payload.get("symbol"))
                if not symbol:
                    raise ValueError("symbol is required")

                price = _validate_amount(payload.get("price", 0.0), "price")

                with self.server.lock:
                    self.server.provider.set_price(symbol, price)
                    _save_prices(self.server.prices_path, self.server.provider)

                self._send_json({"symbol": symbol, "price": price})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        self._send_json({"error": "not found"}, 404)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path

        if path.startswith("/api/assets/"):
            raw_symbol = unquote(path[len("/api/assets/"):].strip("/"))
            symbol = normalize_symbol(raw_symbol)

            if not symbol:
                self._send_json({"error": "symbol is required"}, 400)
                return

            summary = None
            with self.server.lock:
                removed = self.server.portfolio.remove_asset(symbol)
                if removed:
                    _save_portfolio(self.server.portfolio_path, self.server.portfolio)
                    summary = self.server.service.get_summary().to_dict()

            if not removed:
                self._send_json({"error": f"asset {symbol} not found"}, 404)
            else:
                self._send_json({"removed": True, "summary": summary})
            return

        self._send_json({"error": "not found"}, 404)


def create_server(
    host: str,
    port: int,
    portfolio_path: Optional[str],
    prices_path: Optional[str],
) -> ThreadingHTTPServer:
    class _Server(ThreadingHTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = _Server((host, port), _Handler)
    server.portfolio_path = str(portfolio_path) if portfolio_path else None
    server.prices_path = str(prices_path) if prices_path else None
    server.lock = threading.RLock()

    server.portfolio = _load_portfolio(server.portfolio_path)
    server.provider = _load_prices(server.prices_path)
    server.service = PortfolioService(server.portfolio, server.provider)

    return server
