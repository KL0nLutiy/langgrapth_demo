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


def _run_cli(*argv: str):
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_main(list(argv))

    return code, stdout.getvalue(), stderr.getvalue()


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


def test_price_provider_get_prices():
    provider = StaticPriceProvider({"BTC": 10.0})

    prices = provider.get_prices(["btc", "eth", ""])

    assert prices == {"BTC": 10.0, "ETH": 0.0}


def test_price_provider_symbols():
    provider = StaticPriceProvider({"BTC": 1.0, "ETH": 2.0})

    assert provider.symbols() == ["BTC", "ETH"]


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


def test_add_asset_zero_creates_placeholder():
    portfolio = Portfolio()

    asset = portfolio.add_asset("BTC")

    assert asset is not None
    assert portfolio.get_asset("BTC").quantity == 0.0


def test_add_holding_zero_no_cost_no_create():
    portfolio = Portfolio()

    assert portfolio.add_holding("BTC", 0.0) is None
    assert portfolio.symbols() == []


def test_set_quantity_missing_raises():
    portfolio = Portfolio()

    try:
        portfolio.set_quantity("BTC", 1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing asset")


def test_set_quantity_missing_zero_returns_none():
    portfolio = Portfolio()

    assert portfolio.set_quantity("BTC", 0.0) is None
    assert portfolio.symbols() == []


def test_portfolio_roundtrip():
    portfolio = Portfolio(currency="usd")
    portfolio.add_holding("BTC", 1.5, avg_price=100.0, name="Bitcoin")
    portfolio.add_asset("ETH", 2.0, cost_basis=10.0)

    data = portfolio.to_dict()
    restored = Portfolio.from_dict(data)

    assert restored.currency == "USD"
    assert restored.symbols() == ["BTC", "ETH"]

    btc = restored.get_asset("BTC")
    assert btc.quantity == 1.5
    assert btc.cost_basis == 150.0
    assert btc.name == "Bitcoin"

    eth = restored.get_asset("ETH")
    assert eth.quantity == 2.0
    assert eth.cost_basis == 10.0


def test_portfolio_from_dict_list():
    data = [
        {
            "symbol": "btc",
            "quantity": 1.0,
            "cost_basis": 100.0,
        }
    ]

    portfolio = Portfolio.from_dict(data)

    assert portfolio.get_asset("BTC").quantity == 1.0
    assert portfolio.get_asset("BTC").cost_basis == 100.0


def test_portfolio_from_dict_assets_list():
    data = {
        "currency": "usd",
        "assets": [
            {
                "symbol": "BTC",
                "quantity": 1.0,
                "cost_basis": 100.0,
            }
        ],
    }

    portfolio = Portfolio.from_dict(data)

    assert portfolio.currency == "USD"
    assert portfolio.get_asset("BTC").quantity == 1.0


def test_service_summary():
    portfolio = Portfolio()
    portfolio.add_holding("BTC", 1.0, avg_price=100.0)
    portfolio.add_holding("ETH", 2.0, avg_price=50.0)

    provider = StaticPriceProvider({"BTC": 110.0, "ETH": 45.0})
    summary = PortfolioService(portfolio, provider).get_summary()

    assert summary.currency == "USD"
    assert summary.total_value == 200.0
    assert summary.total_cost == 200.0
    assert summary.total_profit_loss == 0.0
    assert [holding.symbol for holding in summary.holdings] == ["BTC", "ETH"]

    btc = summary.holdings[0]
    assert btc.value == 110.0
    assert btc.profit_loss == 10.0
    assert abs(btc.allocation_pct - 55.0) < 1e-9

    eth = summary.holdings[1]
    assert eth.value == 90.0
    assert eth.profit_loss == -10.0
    assert abs(eth.allocation_pct - 45.0) < 1e-9


def test_service_summary_missing_price():
    portfolio = Portfolio()
    portfolio.add_holding("BTC", 1.0, avg_price=100.0)

    summary = PortfolioService(portfolio, StaticPriceProvider()).get_summary()

    assert summary.total_value == 0.0
    assert summary.total_cost == 100.0
    assert summary.total_profit_loss == -100.0
    assert summary.holdings[0].price == 0.0
    assert summary.holdings[0].allocation_pct == 0.0


def test_service_get_holding():
    portfolio = Portfolio()
    portfolio.add_holding("BTC", 1.0, avg_price=100.0)

    provider = StaticPriceProvider({"BTC": 120.0})
    service = PortfolioService(portfolio, provider)

    holding = service.get_holding("BTC")

    assert holding is not None
    assert holding.symbol == "BTC"
    assert holding.price == 120.0
    assert holding.value == 120.0
    assert holding.avg_price == 100.0
    assert holding.profit_loss == 20.0
    assert abs(holding.profit_loss_pct - 20.0) < 1e-9
    assert abs(holding.allocation_pct - 100.0) < 1e-9

    assert service.get_holding("ETH") is None


def test_cli_init_add_summary(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli("init", "--portfolio", str(portfolio_path))
    assert code == 0
    assert portfolio_path.exists()

    code, out, err = _run_cli(
        "add",
        "BTC",
        "1.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["currency"] == "USD"
    assert data["assets"]["BTC"]["quantity"] == 1.0
    assert data["assets"]["BTC"]["cost_basis"] == 100.0

    code, out, err = _run_cli("summary", "--portfolio", str(portfolio_path))
    assert code == 0
    assert "Portfolio value: 65000.00 USD" in out


def test_cli_price_and_summary(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"
    prices_path = tmp_path / "prices.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "2.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli(
        "price",
        "BTC",
        "120.0",
        "--prices",
        str(prices_path),
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0
    assert prices_path.exists()

    code, out, err = _run_cli(
        "summary",
        "--prices",
        str(prices_path),
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0
    assert "Portfolio value: 240.00 USD" in out
    assert "Unrealized P&L: 40.00 USD (20.00%)" in out


def test_cli_remove_partial(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "2.0",
        "--avg-price",
        "50.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli(
        "remove",
        "BTC",
        "1.0",
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["assets"]["BTC"]["quantity"] == 1.0
    assert data["assets"]["BTC"]["cost_basis"] == 50.0


def test_cli_remove_all(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "1.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli("remove", "BTC", "--portfolio", str(portfolio_path))
    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["assets"] == {}


def test_cli_set_quantity(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "2.0",
        "--avg-price",
        "50.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli(
        "set",
        "BTC",
        "3.0",
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["assets"]["BTC"]["quantity"] == 3.0
    assert data["assets"]["BTC"]["cost_basis"] == 150.0


def test_cli_set_zero_existing_removes(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "1.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli(
        "set",
        "BTC",
        "0.0",
        "--portfolio",
        str(portfolio_path),
    )
    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["assets"] == {}


def test_cli_global_options_before_command(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli("--portfolio", str(portfolio_path), "init")

    assert code == 0
    assert portfolio_path.exists()


def test_cli_no_command_prints_help():
    code, out, err = _run_cli()

    assert code == 0
    assert "usage" in out.lower()


def test_cli_invalid_quantity_returns_nonzero(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli(
        "add",
        "BTC",
        "not-a-number",
        "--portfolio",
        str(portfolio_path),
    )

    assert code != 0


def test_cli_negative_quantity_returns_error(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli(
        "add",
        "BTC",
        "-1.0",
        "--portfolio",
        str(portfolio_path),
    )

    assert code == 1
    assert "Error" in err


def test_cli_remove_missing_returns_error(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli("remove", "BTC", "--portfolio", str(portfolio_path))

    assert code == 1
    assert "No holdings found" in err


def test_cli_set_missing_returns_error(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli(
        "set",
        "BTC",
        "1.0",
        "--portfolio",
        str(portfolio_path),
    )

    assert code == 1
    assert "Error" in err


def test_cli_price_negative_returns_error(tmp_path):
    prices_path = tmp_path / "prices.json"

    code, out, err = _run_cli(
        "price",
        "BTC",
        "-1.0",
        "--prices",
        str(prices_path),
    )

    assert code == 1
    assert "Error" in err


def test_cli_export_empty(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    code, out, err = _run_cli("export", "--portfolio", str(portfolio_path))

    assert code == 0
    assert json.loads(out) == {"currency": "USD", "assets": {}}


def test_cli_portfolio_list_format(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_text(
        json.dumps(
            [
                {
                    "symbol": "BTC",
                    "quantity": 1.0,
                    "cost_basis": 100.0,
                }
            ]
        ),
        encoding="utf-8",
    )

    code, out, err = _run_cli("summary", "--portfolio", str(portfolio_path))

    assert code == 0
    assert "Portfolio value" in out


def test_cli_prices_list_format(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"
    prices_path = tmp_path / "prices.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "1.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )

    prices_path.write_text(json.dumps([["BTC", 120.0]]), encoding="utf-8")

    code, out, err = _run_cli(
        "summary",
        "--prices",
        str(prices_path),
        "--portfolio",
        str(portfolio_path),
    )

    assert code == 0
    assert "Portfolio value: 120.00 USD" in out


def test_cli_init_overwrites(tmp_path):
    portfolio_path = tmp_path / "portfolio.json"

    _run_cli("init", "--portfolio", str(portfolio_path))
    _run_cli(
        "add",
        "BTC",
        "1.0",
        "--avg-price",
        "100.0",
        "--portfolio",
        str(portfolio_path),
    )

    code, out, err = _run_cli("init", "--portfolio", str(portfolio_path))

    assert code == 0

    data = json.loads(portfolio_path.read_text(encoding="utf-8"))
    assert data["assets"] == {}
