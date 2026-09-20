import contextlib
import io
import json
import os
import tempfile

from crypto_portfolio import (
    Asset,
    Portfolio,
    PortfolioService,
    SamplePriceProvider,
    StaticPriceProvider,
)
from crypto_portfolio.cli import main as cli_main


def test_asset_normalizes_symbol_and_validates():
    asset = Asset(symbol="btc", quantity=1.5, cost_basis=100.0)

    assert asset.symbol == "BTC"
    assert asset.quantity == 1.5
    assert asset.cost_basis == 100.0

    try:
        Asset(symbol="BTC", quantity=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative quantity")


def test_portfolio_add_remove_and_set():
    portfolio = Portfolio()

    portfolio.add_asset("BTC", quantity=1.0, cost_basis=100.0)
    portfolio.add_asset("btc", quantity=0.5, cost_basis=50.0)

    assert portfolio.symbols() == ["BTC"]

    asset = portfolio.get_asset("BTC")
    assert asset.quantity == 1.5
    assert asset.cost_basis == 150.0

    portfolio.set_quantity("BTC", 2.0)
    assert portfolio.get_asset("BTC").quantity == 2.0

    assert portfolio.remove_asset("BTC") is True
    assert portfolio.symbols() == []


def test_portfolio_value_pnl_and_allocation():
    portfolio = Portfolio()
    portfolio.add_asset("BTC", quantity=1.0, cost_basis=100.0)
    portfolio.add_asset("ETH", quantity=1.0, cost_basis=50.0)

    prices = {"BTC": 100.0, "ETH": 50.0}

    assert portfolio.total_value(prices) == 150.0
    assert portfolio.total_cost() == 150.0
    assert portfolio.unrealized_pnl(prices) == 0.0

    allocation = portfolio.allocation(prices)
    assert abs(allocation["BTC"] - (100.0 / 150.0)) < 1e-12
    assert abs(allocation["ETH"] - (50.0 / 150.0)) < 1e-12
    assert abs(sum(allocation.values()) - 1.0) < 1e-12


def test_price_providers():
    provider = StaticPriceProvider({"btc": 10.0, "ETH": 20.0})

    assert provider.get_price("BTC") == 10.0
    assert provider.get_price("eth") == 20.0
    assert provider.get_price("SOL") == 0.0

    sample = SamplePriceProvider()
    assert sample.get_price("BTC") > 0


def test_price_provider_set_price():
    provider = StaticPriceProvider({"BTC": 10.0})

    provider.set_price("btc", 20.0)

    assert provider.get_price("BTC") == 20.0


def test_portfolio_add_holding_uses_average_price():
    portfolio = Portfolio()

    portfolio.add_holding("BTC", 2.0, avg_price=50.0)

    asset = portfolio.get_asset("BTC")
    assert asset.quantity == 2.0
    assert asset.cost_basis == 100.0
    assert asset.avg_price == 50.0


def test_portfolio_remove_holding_partial():
    portfolio = Portfolio()

    portfolio.add_holding("BTC", 2.0, avg_price=50.0)
    portfolio.remove_holding("BTC", 1.0)

    asset = portfolio.get_asset("BTC")
    assert asset.quantity == 1.0
    assert asset.cost_basis == 50.0


def test_allocation_zero_value():
    portfolio = Portfolio()
    portfolio.add_asset("BTC", quantity=1.0, cost_basis=100.0)

    allocation = portfolio.allocation({"BTC": 0.0})

    assert allocation == {"BTC": 0.0}


def test_portfolio_persistence():
    portfolio = Portfolio(currency="usd")
    portfolio.add_asset("BTC", quantity=1.0, cost_basis=100.0, name="Bitcoin")
    portfolio.add_asset("ETH", quantity=2.0, cost_basis=50.0)

    data = portfolio.to_dict()
    restored = Portfolio.from_dict(data)

    assert restored.currency == "USD"
    assert restored.symbols() == ["BTC", "ETH"]
    assert restored.get_asset("BTC").name == "Bitcoin"
    assert restored.get_asset("ETH").cost_basis == 50.0


def test_cli_add_and_summary():
    with tempfile.TemporaryDirectory() as tmp:
        portfolio_path = os.path.join(tmp, "portfolio.json")
        prices_path = os.path.join(tmp, "prices.json")

        with open(prices_path, "w", encoding="utf-8") as handle:
            json.dump({"BTC": 100.0, "ETH": 50.0}, handle)

        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            assert cli_main(["init", "--portfolio", portfolio_path]) == 0
            assert cli_main(
                [
                    "add",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "btc",
                    "--quantity",
                    "2",
                    "--cost-basis",
                    "150",
                ]
            ) == 0
            assert cli_main(
                [
                    "summary",
                    "--portfolio",
                    portfolio_path,
                    "--prices",
                    prices_path,
                ]
            ) == 0

        text = output.getvalue()

        assert "Portfolio value: 200.00 USD" in text
        assert "Total cost basis: 150.00 USD" in text
        assert "Unrealized P&L: 50.00 USD" in text
        assert "BTC" in text


def test_cli_summary_empty():
    with tempfile.TemporaryDirectory() as tmp:
        portfolio_path = os.path.join(tmp, "portfolio.json")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            assert cli_main(["init", "--portfolio", portfolio_path]) == 0
            assert cli_main(["summary", "--portfolio", portfolio_path]) == 0

        text = output.getvalue()

        assert "Portfolio value: 0.00 USD" in text
        assert "Total cost basis: 0.00 USD" in text
        assert "Unrealized P&L: 0.00 USD" in text


def test_cli_set_and_remove():
    with tempfile.TemporaryDirectory() as tmp:
        portfolio_path = os.path.join(tmp, "portfolio.json")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            assert cli_main(["init", "--portfolio", portfolio_path]) == 0
            assert cli_main(
                [
                    "add",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "BTC",
                    "--quantity",
                    "1",
                    "--cost-basis",
                    "100",
                ]
            ) == 0
            assert cli_main(
                [
                    "set",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "BTC",
                    "--quantity",
                    "2",
                ]
            ) == 0

        with open(portfolio_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["assets"][0]["quantity"] == 2.0
        assert data["assets"][0]["cost_basis"] == 200.0

        with contextlib.redirect_stdout(output):
            assert cli_main(
                [
                    "set",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "BTC",
                    "--cost-basis",
                    "300",
                ]
            ) == 0

        with open(portfolio_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["assets"][0]["quantity"] == 2.0
        assert data["assets"][0]["cost_basis"] == 300.0

        with contextlib.redirect_stdout(output):
            assert cli_main(
                [
                    "remove",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "BTC",
                ]
            ) == 0

        with open(portfolio_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["assets"] == []


def test_cli_invalid_quantity():
    with tempfile.TemporaryDirectory() as tmp:
        portfolio_path = os.path.join(tmp, "portfolio.json")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            assert cli_main(["init", "--portfolio", portfolio_path]) == 0
            assert cli_main(
                [
                    "add",
                    "--portfolio",
                    portfolio_path,
                    "--symbol",
                    "BTC",
                    "--quantity",
                    "-1",
                    "--cost-basis",
                    "100",
                ]
            ) == 1

        assert "Error" in output.getvalue()


def test_service_summary():
    portfolio = Portfolio()
    provider = StaticPriceProvider({"BTC": 100.0, "ETH": 50.0})
    service = PortfolioService(portfolio, provider)

    service.add_holding("BTC", 2.0, avg_price=50.0)
    service.add_holding("ETH", 1.0, avg_price=60.0)

    summary = service.get_summary()

    assert summary.currency == "USD"
    assert summary.total_value == 250.0
    assert summary.total_cost == 160.0
    assert summary.total_profit_loss == 90.0
    assert summary.holdings[0].symbol == "BTC"
    assert abs(summary.holdings[0].allocation_pct - 80.0) < 1e-12
    assert abs(summary.holdings[1].allocation_pct - 20.0) < 1e-12

    service.set_price("BTC", 120.0)

    summary = service.get_summary()

    assert summary.total_value == 290.0
    assert summary.total_cost == 160.0
    assert summary.total_profit_loss == 130.0

    service.remove_holding("BTC", 1.0)

    summary = service.get_summary()

    assert summary.total_value == 170.0
    assert summary.total_cost == 110.0
