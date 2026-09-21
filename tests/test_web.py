import json
import threading
import urllib.request
from typing import Any, Dict, Optional

from crypto_portfolio.web import create_server


def _request(
    base: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    method: Optional[str] = None,
) -> Dict[str, Any]:
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        base + path,
        data=data,
        headers=headers,
        method=method or ("POST" if data is not None else "GET"),
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_web_ui_and_api(tmp_path):
    portfolio_path = str(tmp_path / "portfolio.json")
    prices_path = str(tmp_path / "prices.json")

    server = create_server("127.0.0.1", 0, portfolio_path, prices_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        with urllib.request.urlopen(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "Crypto Portfolio" in html

        payload = _request(
            base,
            "/api/assets",
            {"symbol": "btc", "quantity": 2, "avg_price": 50},
            method="POST",
        )
        assert payload["asset"]["symbol"] == "BTC"
        assert payload["summary"]["total_cost"] == 100.0

        _request(base, "/api/prices", {"symbol": "BTC", "price": 100}, method="POST")

        summary = _request(base, "/api/summary")
        assert summary["total_value"] == 200.0
        assert summary["total_profit_loss"] == 100.0

        holdings = _request(base, "/api/holdings")
        assert holdings[0]["symbol"] == "BTC"
        assert holdings[0]["allocation_pct"] == 100.0

        _request(base, "/api/assets/BTC", method="DELETE")

        summary = _request(base, "/api/summary")
        assert summary["total_value"] == 0.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
