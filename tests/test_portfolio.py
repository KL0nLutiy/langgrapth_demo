import contextlib
import io
import json

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

    assert allocation["BTC"] == 0.0
    assert sum(allocation.values()) == 0.0


def test_service_summary_calculates_allocation_and_sorts():
    portfolio = Portfolio()
    portfolio.add_holding("BTC", 1.0, avg_price=100.0)
    portfolio.add_holding("ETH", 2.0, avg_price=50.0)

    provider = StaticPriceProvider({"BTC": 120.0, "ETH": 40.0})
    service = PortfolioService(portfolio, provider)
    summary = service.get_summary()

    assert summary.total_value == 200.0
    assert summary.total_cost == 200.0
    assert summary.total_profit_loss == 0.0
    assert [holding.symbol for holding in summary.holdings] == ["BTC", "ETH"]
    assert summary.holdings[0].allocation_pct == 60.0
    assert summary.holdings[1].allocation_pct == 40.0


def test_cli_init_add_summary(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"
    prices_path = tmp_path / "prices.json"
    prices_path.write_text(json.dumps([["BTC", 100.0], ["ETH", 50.0]]))

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli_main(["init", "--portfolio", str(portfolio_path)]) == 0
        assert cli_main([
            "add",
            "--portfolio", str(portfolio_path),
            "--symbol", "btc",
            "--quantity", "1",
            "--cost-basis", "90",
        ]) == 0
        assert cli_main([
            "summary",
            "--portfolio", str(portfolio_path),
            "--prices", str(prices_path),
        ]) == 0

    text = output.getvalue()
    assert "Portfolio value: 100.00 USD" in text
    assert "BTC" in text

    data = json.loads(portfolio_path.read_text())
    assert data["assets"]["BTC"]["quantity"] == 1.0
    assert data["assets"]["BTC"]["cost_basis"] == 90.0


def test_cli_set_price(tmp_path):
    prices_path = tmp_path / "prices.json"
    prices_path.write_text(json.dumps({"BTC": 10.0}))

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli_main([
            "set-price",
            "--prices", str(prices_path),
            "--symbol", "btc",
            "--price", "20",
        ]) == 0

    data = json.loads(prices_path.read_text())
    assert data["BTC"] == 20.0
