from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "Asset",
    "AssetValue",
    "Portfolio",
    "PortfolioService",
    "PortfolioSummary",
    "PriceProvider",
    "SamplePriceProvider",
    "StaticPriceProvider",
    "normalize_symbol",
    "_validate_amount",
]


def normalize_symbol(symbol: Any) -> str:
    if symbol is None:
        return ""
    return str(symbol).strip().upper()


def _validate_amount(value: Any, name: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    if not math.isfinite(amount):
        raise ValueError(f"{name} must be finite")

    if amount < 0:
        raise ValueError(f"{name} must be non-negative")

    return amount


@dataclass
class Asset:
    symbol: str
    quantity: float = 0.0
    cost_basis: float = 0.0

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        if not self.symbol:
            raise ValueError("symbol is required")

        self.quantity = _validate_amount(self.quantity, "quantity")
        self.cost_basis = _validate_amount(self.cost_basis, "cost_basis")

    @property
    def avg_price(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.cost_basis / self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Asset":
        if isinstance(data, Asset):
            return data

        if isinstance(data, Mapping):
            symbol = data.get("symbol", data.get("ticker", data.get("id")))
            quantity = data.get("quantity", data.get("qty", 0.0))
            cost_basis = data.get("cost_basis", data.get("cost"))

            if cost_basis is None:
                avg_price = data.get("avg_price", data.get("price"))
                if avg_price is not None:
                    quantity_value = _validate_amount(quantity, "quantity")
                    cost_basis = quantity_value * _validate_amount(avg_price, "avg_price")
                else:
                    cost_basis = 0.0

            return cls(symbol=symbol, quantity=quantity, cost_basis=cost_basis)

        if isinstance(data, (list, tuple)):
            if len(data) >= 2:
                return cls(
                    symbol=data[0],
                    quantity=data[1],
                    cost_basis=data[2] if len(data) > 2 else 0.0,
                )

        raise ValueError("invalid asset payload")


class Portfolio:
    def __init__(self, currency: str = "USD", assets: Optional[Any] = None) -> None:
        self.currency = normalize_symbol(currency) or "USD"
        self._assets: Dict[str, Asset] = {}

        if assets is not None:
            self._load_assets(assets)

    def _load_assets(self, assets: Any) -> None:
        if isinstance(assets, Mapping):
            for symbol, value in assets.items():
                self._merge_asset(symbol, self._asset_from_any(value))
        elif isinstance(assets, (list, tuple, set)):
            for value in assets:
                asset = self._asset_from_any(value)
                if asset is not None:
                    self._merge_asset(asset.symbol, asset)

    @staticmethod
    def _asset_from_any(value: Any) -> Optional[Asset]:
        try:
            if isinstance(value, Asset):
                return value
            if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
                return Asset.from_dict(value)
        except ValueError:
            return None
        return None

    def _merge_asset(self, symbol: Any, asset: Optional[Asset]) -> None:
        if asset is None:
            return

        normalized = normalize_symbol(symbol)
        if not normalized:
            return

        quantity = asset.quantity
        cost_basis = asset.cost_basis

        if quantity == 0 and cost_basis == 0:
            return

        existing = self._assets.get(normalized)
        if existing is None:
            self._assets[normalized] = Asset(
                symbol=normalized,
                quantity=quantity,
                cost_basis=cost_basis,
            )
        else:
            existing.quantity += quantity
            existing.cost_basis += cost_basis

            if existing.quantity == 0 and existing.cost_basis == 0:
                del self._assets[normalized]

    def symbols(self) -> List[str]:
        return sorted(self._assets)

    def get_asset(self, symbol: str) -> Optional[Asset]:
        return self._assets.get(normalize_symbol(symbol))

    def add_asset(self, symbol: str, quantity: float, cost_basis: float = 0.0) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        asset = Asset(symbol=symbol, quantity=quantity, cost_basis=cost_basis)
        self._merge_asset(symbol, asset)
        return self.get_asset(symbol)

    def add_holding(self, symbol: str, quantity: float, avg_price: float = 0.0) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")
        avg_price = _validate_amount(avg_price, "avg_price")
        return self.add_asset(symbol, quantity, quantity * avg_price)

    def set_quantity(self, symbol: str, quantity: float) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")
        asset = self.get_asset(symbol)

        if asset is None:
            return None

        if quantity == 0:
            del self._assets[asset.symbol]
            return None

        avg_price = asset.avg_price
        asset.quantity = quantity
        asset.cost_basis = quantity * avg_price
        return asset

    def remove_asset(self, symbol: str, quantity: Optional[float] = None) -> bool:
        asset = self.get_asset(symbol)
        if asset is None:
            return False

        if quantity is None:
            del self._assets[asset.symbol]
            return True

        quantity = _validate_amount(quantity, "quantity")

        if quantity == 0:
            return True

        if quantity >= asset.quantity:
            del self._assets[asset.symbol]
            return True

        avg_price = asset.avg_price
        asset.quantity -= quantity
        asset.cost_basis = asset.quantity * avg_price

        if asset.quantity == 0:
            del self._assets[asset.symbol]

        return True

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self._assets.values())

    @staticmethod
    def _price_for(prices: Any, symbol: str) -> float:
        if prices is None:
            return 0.0

        normalized = normalize_symbol(symbol)

        if isinstance(prices, Mapping):
            value = prices.get(normalized)
            if value is None and normalized != symbol:
                value = prices.get(symbol)

            try:
                price = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

            if not math.isfinite(price) or price < 0:
                return 0.0

            return price

        get_price = getattr(prices, "get_price", None)
        if callable(get_price):
            try:
                price = float(get_price(normalized) or 0.0)
            except (TypeError, ValueError):
                return 0.0

            if not math.isfinite(price) or price < 0:
                return 0.0

            return price

        return 0.0

    def total_value(self, prices: Any) -> float:
        total = 0.0
        for asset in self._assets.values():
            total += asset.quantity * self._price_for(prices, asset.symbol)
        return total

    def unrealized_pnl(self, prices: Any) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Any) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for symbol in self.symbols():
            asset = self._assets[symbol]
            value = asset.quantity * self._price_for(prices, symbol)
            result[symbol] = (value / total) if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "assets": {
                symbol: self._assets[symbol].to_dict()
                for symbol in self.symbols()
            },
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Portfolio":
        if data is None:
            return cls()

        if isinstance(data, Portfolio):
            return data

        if isinstance(data, Mapping):
            currency = data.get("currency", "USD")
            assets = data.get("assets", {})
            return cls(currency=currency, assets=assets)

        return cls(assets=data)


class PriceProvider:
    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    def set_price(self, symbol: str, price: float) -> None:
        raise NotImplementedError

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, float]:
        result: Dict[str, float] = {}

        for symbol in symbols or []:
            normalized = normalize_symbol(symbol)
            if normalized:
                result[normalized] = self.get_price(normalized)

        return result

    def symbols(self) -> List[str]:
        return []

    def to_dict(self) -> Dict[str, Any]:
        return {"prices": {}}


class StaticPriceProvider(PriceProvider):
    def __init__(self, prices: Optional[Any] = None) -> None:
        self._prices: Dict[str, float] = {}

        if prices is not None:
            self._load(prices)

    def _load(self, data: Any) -> None:
        if (
            isinstance(data, Mapping)
            and "prices" in data
            and isinstance(data.get("prices"), (Mapping, list, tuple))
        ):
            data = data.get("prices")

        if isinstance(data, Mapping):
            for symbol, price in data.items():
                self._set_raw(symbol, price)
        elif isinstance(data, (list, tuple)):
            for item in data:
                if isinstance(item, Mapping):
                    symbol = item.get("symbol", item.get("ticker"))
                    price = item.get("price")
                    if symbol is not None and price is not None:
                        self._set_raw(symbol, price)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    self._set_raw(item[0], item[1])

    def _set_raw(self, symbol: Any, price: Any) -> None:
        normalized = normalize_symbol(symbol)
        if not normalized:
            return

        try:
            self._prices[normalized] = _validate_amount(price, "price")
        except ValueError:
            return

    def get_price(self, symbol: str) -> float:
        return self._prices.get(normalize_symbol(symbol), 0.0)

    def set_price(self, symbol: str, price: float) -> None:
        normalized = normalize_symbol(symbol)
        if not normalized:
            raise ValueError("symbol is required")

        self._prices[normalized] = _validate_amount(price, "price")

    def symbols(self) -> List[str]:
        return sorted(self._prices)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prices": {
                symbol: self._prices[symbol]
                for symbol in self.symbols()
            }
        }


class SamplePriceProvider(StaticPriceProvider):
    def __init__(self) -> None:
        super().__init__(
            {
                "BTC": 65000.0,
                "ETH": 3500.0,
                "SOL": 150.0,
                "ADA": 0.5,
                "DOGE": 0.1,
                "LTC": 80.0,
                "XRP": 0.6,
                "DOT": 7.0,
                "AVAX": 35.0,
                "LINK": 15.0,
            }
        )


@dataclass
class AssetValue:
    symbol: str
    quantity: float
    price: float
    value: float
    avg_price: float
    profit_loss: float
    profit_loss_pct: float
    allocation_pct: float
    cost_basis: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "value": self.value,
            "avg_price": self.avg_price,
            "profit_loss": self.profit_loss,
            "profit_loss_pct": self.profit_loss_pct,
            "allocation_pct": self.allocation_pct,
            "cost_basis": self.cost_basis,
        }


@dataclass
class PortfolioSummary:
    currency: str
    total_value: float
    total_cost: float
    total_profit_loss: float
    profit_loss_pct: float
    holdings: List[AssetValue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "total_value": self.total_value,
            "total_cost": self.total_cost,
            "total_profit_loss": self.total_profit_loss,
            "profit_loss_pct": self.profit_loss_pct,
            "holdings": [holding.to_dict() for holding in self.holdings],
        }


class PortfolioService:
    def __init__(self, portfolio: Portfolio, provider: Optional[PriceProvider]) -> None:
        self.portfolio = portfolio
        self.provider = provider

    def _get_price(self, symbol: str) -> float:
        return Portfolio._price_for(self.provider, symbol)

    def get_holding(self, symbol: str) -> Optional[AssetValue]:
        asset = self.portfolio.get_asset(symbol)
        if asset is None:
            return None

        price = self._get_price(asset.symbol)
        value = asset.quantity * price
        cost = asset.cost_basis
        profit_loss = value - cost

        if cost > 0:
            profit_loss_pct = (profit_loss / cost) * 100.0
        else:
            profit_loss_pct = 0.0

        total_value = self.portfolio.total_value(self.provider)
        allocation_pct = (value / total_value) * 100.0 if total_value > 0 else 0.0

        return AssetValue(
            symbol=asset.symbol,
            quantity=asset.quantity,
            price=price,
            value=value,
            avg_price=asset.avg_price,
            profit_loss=profit_loss,
            profit_loss_pct=profit_loss_pct,
            allocation_pct=allocation_pct,
            cost_basis=cost,
        )

    def get_holdings(self) -> List[AssetValue]:
        holdings: List[AssetValue] = []

        for symbol in self.portfolio.symbols():
            holding = self.get_holding(symbol)
            if holding is not None:
                holdings.append(holding)

        return holdings

    def get_summary(self) -> PortfolioSummary:
        holdings = self.get_holdings()
        total_value = sum(holding.value for holding in holdings)
        total_cost = self.portfolio.total_cost()
        total_profit_loss = total_value - total_cost

        if total_cost > 0:
            profit_loss_pct = (total_profit_loss / total_cost) * 100.0
        else:
            profit_loss_pct = 0.0

        return PortfolioSummary(
            currency=self.portfolio.currency,
            total_value=total_value,
            total_cost=total_cost,
            total_profit_loss=total_profit_loss,
            profit_loss_pct=profit_loss_pct,
            holdings=holdings,
        )

    summary = get_summary

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, float]:
        if symbols is None:
            symbols = self.portfolio.symbols()

        result: Dict[str, float] = {}
        for symbol in symbols:
            normalized = normalize_symbol(symbol)
            if normalized:
                result[normalized] = self._get_price(normalized)

        return result

    def add_asset(self, symbol: str, quantity: float, cost_basis: float = 0.0) -> Optional[Asset]:
        return self.portfolio.add_asset(symbol, quantity, cost_basis)

    def add_holding(self, symbol: str, quantity: float, avg_price: float = 0.0) -> Optional[Asset]:
        return self.portfolio.add_holding(symbol, quantity, avg_price)

    def set_quantity(self, symbol: str, quantity: float) -> Optional[Asset]:
        return self.portfolio.set_quantity(symbol, quantity)

    def remove_asset(self, symbol: str, quantity: Optional[float] = None) -> bool:
        return self.portfolio.remove_asset(symbol, quantity)

    def set_price(self, symbol: str, price: float) -> float:
        if self.provider is None or not hasattr(self.provider, "set_price"):
            raise ValueError("price provider does not support set_price")

        self.provider.set_price(symbol, price)
        return self._get_price(symbol)
