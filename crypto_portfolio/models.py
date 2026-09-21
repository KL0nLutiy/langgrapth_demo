from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, List, Optional


def normalize_symbol(symbol: Any) -> str:
    if symbol is None:
        raise ValueError("symbol is required")

    text = str(symbol).strip().upper()
    if not text:
        raise ValueError("symbol is required")

    return text


def _validate_amount(value: Any, name: str, default: float = 0.0) -> float:
    if value is None:
        return float(default)

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"{name} must be a finite number")

    if number < 0:
        raise ValueError(f"{name} must be non-negative")

    return number


class Asset:
    def __init__(
        self,
        symbol: Any,
        quantity: Any = 0.0,
        cost_basis: Optional[Any] = None,
        avg_price: Optional[Any] = None,
    ) -> None:
        self.symbol = normalize_symbol(symbol)
        self.quantity = _validate_amount(quantity, "quantity")

        if avg_price is not None:
            avg_price = _validate_amount(avg_price, "avg_price")
            if cost_basis is None:
                cost_basis = avg_price * self.quantity

        if cost_basis is None:
            cost_basis = 0.0

        self.cost_basis = _validate_amount(cost_basis, "cost_basis")
        self.avg_price = (self.cost_basis / self.quantity) if self.quantity > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
            "avg_price": self.avg_price,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Asset":
        if isinstance(data, Mapping):
            symbol = data.get("symbol")
            quantity = data.get("quantity", 0)
            cost_basis = data.get("cost_basis")
            avg_price = data.get("avg_price")
            return cls(symbol, quantity=quantity, cost_basis=cost_basis, avg_price=avg_price)

        if isinstance(data, (list, tuple)):
            if not data:
                raise ValueError("asset data is required")

            symbol = data[0]
            quantity = data[1] if len(data) > 1 else 0
            cost_basis = data[2] if len(data) > 2 else None
            return cls(symbol, quantity=quantity, cost_basis=cost_basis)

        raise ValueError("asset data must be a mapping or sequence")

    def __repr__(self) -> str:
        return (
            "Asset("
            f"symbol={self.symbol!r}, "
            f"quantity={self.quantity!r}, "
            f"cost_basis={self.cost_basis!r}, "
            f"avg_price={self.avg_price!r}"
            ")"
        )


class Portfolio:
    def __init__(self, currency: str = "USD", assets: Optional[List[Any]] = None) -> None:
        self.currency = str(currency or "USD")
        self._assets: Dict[str, Asset] = {}

        if assets is not None:
            for item in assets:
                if isinstance(item, Asset):
                    asset = item
                else:
                    asset = Asset.from_dict(item)
                self._assets[asset.symbol] = asset

    def add_asset(
        self,
        symbol: Any,
        quantity: Any = 0.0,
        cost_basis: Optional[Any] = None,
        avg_price: Optional[Any] = None,
    ) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")

        if avg_price is not None:
            avg_price = _validate_amount(avg_price, "avg_price")

        if cost_basis is not None:
            cost_basis = _validate_amount(cost_basis, "cost_basis")

        if quantity == 0:
            return self.get_asset(symbol)

        if avg_price is not None:
            cost_basis = avg_price * quantity

        if cost_basis is None:
            cost_basis = 0.0

        cost_basis = _validate_amount(cost_basis, "cost_basis")

        existing = self.get_asset(symbol)
        if existing is not None:
            existing.quantity += quantity
            existing.cost_basis += cost_basis
            existing.avg_price = (
                existing.cost_basis / existing.quantity if existing.quantity > 0 else 0.0
            )
            return existing

        asset = Asset(symbol, quantity=quantity, cost_basis=cost_basis)
        self._assets[asset.symbol] = asset
        return asset

    def add_holding(
        self,
        symbol: Any,
        quantity: Any,
        avg_price: Optional[Any] = None,
        cost_basis: Optional[Any] = None,
    ) -> Optional[Asset]:
        if avg_price is not None:
            return self.add_asset(symbol, quantity=quantity, avg_price=avg_price)

        return self.add_asset(symbol, quantity=quantity, cost_basis=cost_basis)

    def set_quantity(self, symbol: Any, quantity: Any) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")
        asset = self.get_asset(symbol)

        if asset is None:
            raise ValueError(f"Asset {normalize_symbol(symbol)} not found")

        if quantity == 0:
            del self._assets[asset.symbol]
            return None

        asset.quantity = quantity
        asset.cost_basis = asset.avg_price * quantity
        return asset

    def remove_asset(self, symbol: Any, quantity: Optional[Any] = None) -> bool:
        asset = self.get_asset(symbol)

        if asset is None:
            return False

        if quantity is None:
            del self._assets[asset.symbol]
            return True

        quantity = _validate_amount(quantity, "quantity")

        if quantity == 0:
            return False

        if quantity > asset.quantity + 1e-12:
            raise ValueError(f"Cannot remove more than held for {asset.symbol}")

        if quantity >= asset.quantity - 1e-12:
            del self._assets[asset.symbol]
            return True

        asset.quantity -= quantity
        asset.cost_basis = asset.avg_price * asset.quantity
        return True

    def get_asset(self, symbol: Any) -> Optional[Asset]:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return None

        return self._assets.get(normalized)

    def symbols(self) -> List[str]:
        return sorted(self._assets)

    def assets(self) -> List[Asset]:
        return [self._assets[symbol] for symbol in self.symbols()]

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self._assets.values())

    @staticmethod
    def _price_for(prices: Any, symbol: str) -> float:
        if prices is None:
            return 0.0

        if isinstance(prices, Mapping):
            if symbol in prices:
                return float(prices[symbol] or 0.0)

            for key, value in prices.items():
                try:
                    if normalize_symbol(key) == symbol:
                        return float(value or 0.0)
                except ValueError:
                    continue

            return 0.0

        get_price = getattr(prices, "get_price", None)
        if callable(get_price):
            return float(get_price(symbol) or 0.0)

        return 0.0

    def total_value(self, prices: Any = None) -> float:
        total = 0.0
        for asset in self._assets.values():
            total += asset.quantity * self._price_for(prices, asset.symbol)
        return total

    def unrealized_pnl(self, prices: Any = None) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Any = None) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for asset in self._assets.values():
            value = asset.quantity * self._price_for(prices, asset.symbol)
            result[asset.symbol] = (value / total) if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {"assets": [asset.to_dict() for asset in self.assets()]}

    @classmethod
    def from_dict(cls, data: Any) -> "Portfolio":
        portfolio = cls()

        if data is None:
            return portfolio

        if isinstance(data, Mapping):
            if "symbol" in data:
                asset = Asset.from_dict(data)
                portfolio._assets[asset.symbol] = asset
                return portfolio

            currency = data.get("currency")
            if currency:
                portfolio.currency = str(currency)

            if "assets" in data:
                assets_data = data.get("assets")
            elif "holdings" in data:
                assets_data = data.get("holdings")
            else:
                assets_data = data

            if isinstance(assets_data, Mapping):
                items = list(assets_data.items())
            elif isinstance(assets_data, (list, tuple)):
                items = list(assets_data)
            else:
                items = []

            for item in items:
                if (
                    isinstance(item, tuple)
                    and len(item) == 2
                    and isinstance(item[0], str)
                    and isinstance(item[1], Mapping)
                ):
                    asset_data = dict(item[1])
                    asset_data.setdefault("symbol", item[0])
                    asset = Asset.from_dict(asset_data)
                    portfolio._assets[asset.symbol] = asset
                elif isinstance(item, Mapping):
                    asset = Asset.from_dict(item)
                    portfolio._assets[asset.symbol] = asset
                elif isinstance(item, (list, tuple)):
                    asset = Asset.from_dict(item)
                    portfolio._assets[asset.symbol] = asset

        elif isinstance(data, (list, tuple)):
            for item in data:
                asset = Asset.from_dict(item)
                portfolio._assets[asset.symbol] = asset

        return portfolio

    def __repr__(self) -> str:
        return f"Portfolio(currency={self.currency!r}, assets={self.symbols()!r})"


class AssetValue:
    def __init__(
        self,
        symbol: str,
        quantity: float,
        price: float,
        value: float,
        avg_price: float,
        profit_loss: float,
        profit_loss_pct: float,
        allocation_pct: float,
        cost_basis: float,
    ) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.price = price
        self.value = value
        self.avg_price = avg_price
        self.profit_loss = profit_loss
        self.profit_loss_pct = profit_loss_pct
        self.allocation_pct = allocation_pct
        self.cost_basis = cost_basis

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


class PortfolioSummary:
    def __init__(
        self,
        currency: str,
        total_value: float,
        total_cost: float,
        total_profit_loss: float,
        profit_loss_pct: float,
        holdings: List[AssetValue],
    ) -> None:
        self.currency = currency
        self.total_value = total_value
        self.total_cost = total_cost
        self.total_profit_loss = total_profit_loss
        self.profit_loss_pct = profit_loss_pct
        self.holdings = list(holdings or [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "total_value": self.total_value,
            "total_cost": self.total_cost,
            "total_profit_loss": self.total_profit_loss,
            "profit_loss_pct": self.profit_loss_pct,
            "holdings": [holding.to_dict() for holding in self.holdings],
        }
