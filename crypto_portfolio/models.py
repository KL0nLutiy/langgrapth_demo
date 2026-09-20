from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional


def normalize_symbol(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if not normalized:
        raise ValueError("Symbol must not be empty")
    return normalized


def _validate_amount(value: float, name: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative finite number") from exc

    if math.isnan(amount) or math.isinf(amount) or amount < 0:
        raise ValueError(f"{name} must be a non-negative finite number")

    return amount


@dataclass
class Asset:
    symbol: str
    quantity: float = 0.0
    cost_basis: float = 0.0
    name: Optional[str] = None

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        self.quantity = _validate_amount(self.quantity, "quantity")
        self.cost_basis = _validate_amount(self.cost_basis, "cost_basis")

        if self.name is not None:
            self.name = str(self.name)

    @property
    def avg_price(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.cost_basis / self.quantity

    def value(self, price: float) -> float:
        return self.quantity * float(price)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
        }

        if self.name is not None:
            data["name"] = self.name

        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Asset":
        name = data.get("name")
        if name is not None:
            name = str(name)

        quantity = data.get("quantity", 0.0)
        cost_basis = data.get("cost_basis", 0.0)

        return cls(
            symbol=str(data["symbol"]),
            quantity=quantity if quantity is not None else 0.0,
            cost_basis=cost_basis if cost_basis is not None else 0.0,
            name=name,
        )


class Portfolio:
    def __init__(
        self,
        currency: str = "USD",
        assets: Optional[Mapping[str, object]] = None,
    ) -> None:
        self.currency = str(currency or "USD").strip().upper() or "USD"
        self.assets: Dict[str, Asset] = {}

        if assets:
            for _symbol, asset in assets.items():
                if asset is None:
                    continue

                if isinstance(asset, Asset):
                    self.assets[asset.symbol] = asset
                else:
                    asset_obj = Asset.from_dict(asset)
                    self.assets[asset_obj.symbol] = asset_obj

    def __eq__(self, other: object):
        if not isinstance(other, Portfolio):
            return NotImplemented

        return self.currency == other.currency and self.assets == other.assets

    @property
    def holdings(self) -> List[Asset]:
        return [self.assets[symbol] for symbol in sorted(self.assets)]

    def symbols(self) -> List[str]:
        return sorted(self.assets)

    def has_asset(self, symbol: str) -> bool:
        return normalize_symbol(symbol) in self.assets

    def get_asset(self, symbol: str) -> Asset:
        normalized = normalize_symbol(symbol)
        return self.assets.get(normalized, Asset(normalized, 0.0, 0.0))

    def add_asset(
        self,
        symbol: str,
        quantity: float,
        cost_basis: float = 0.0,
        name: Optional[str] = None,
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        if quantity == 0.0 and cost_basis == 0.0:
            return self.get_asset(normalized)

        asset = self.assets.get(normalized)

        if asset is None:
            asset = Asset(normalized, quantity, cost_basis, name)
            self.assets[normalized] = asset
        else:
            asset.quantity += quantity
            asset.cost_basis += cost_basis

            if name is not None:
                asset.name = str(name)

        if asset.quantity == 0.0 and asset.cost_basis == 0.0:
            self.assets.pop(normalized, None)
            return Asset(normalized, 0.0, 0.0, name)

        return asset

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: Optional[float] = None,
    ) -> Asset:
        quantity = _validate_amount(quantity, "quantity")

        if avg_price is None:
            cost_basis = 0.0
        else:
            avg_price = _validate_amount(avg_price, "avg_price")
            cost_basis = quantity * avg_price

        return self.add_asset(symbol, quantity, cost_basis)

    def remove_asset(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)

        if normalized in self.assets:
            del self.assets[normalized]
            return True

        return False

    def remove_holding(self, symbol: str, quantity: Optional[float] = None) -> bool:
        normalized = normalize_symbol(symbol)
        asset = self.assets.get(normalized)

        if asset is None:
            return False

        if quantity is None:
            return self.remove_asset(normalized)

        quantity = _validate_amount(quantity, "quantity")

        if quantity >= asset.quantity:
            return self.remove_asset(normalized)

        remaining = asset.quantity - quantity

        if asset.quantity > 0:
            asset.cost_basis = asset.cost_basis * (remaining / asset.quantity)

        asset.quantity = remaining

        if asset.quantity == 0.0 and asset.cost_basis == 0.0:
            self.remove_asset(normalized)

        return True

    def set_quantity(self, symbol: str, quantity: float) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        if quantity == 0.0:
            self.remove_asset(normalized)
            return Asset(normalized, 0.0, 0.0)

        asset = self.assets.get(normalized)

        if asset is None:
            asset = Asset(normalized, quantity, 0.0)
            self.assets[normalized] = asset
        else:
            if asset.quantity > 0:
                asset.cost_basis = asset.cost_basis * (quantity / asset.quantity)
            else:
                asset.cost_basis = 0.0

            asset.quantity = quantity

        return asset

    def set_cost_basis(self, symbol: str, cost_basis: float) -> Asset:
        normalized = normalize_symbol(symbol)
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        asset = self.assets.get(normalized)

        if asset is None:
            if cost_basis == 0.0:
                return Asset(normalized, 0.0, 0.0)

            asset = Asset(normalized, 0.0, cost_basis)
            self.assets[normalized] = asset
        else:
            asset.cost_basis = cost_basis

            if asset.quantity == 0.0 and asset.cost_basis == 0.0:
                self.assets.pop(normalized, None)
                return Asset(normalized, 0.0, 0.0)

        return asset

    @staticmethod
    def _price_for(symbol: str, prices: Optional[object]) -> float:
        if prices is None:
            return 0.0

        if hasattr(prices, "get_price"):
            return float(prices.get_price(symbol))

        key = str(symbol).upper()

        if isinstance(prices, Mapping):
            if key in prices:
                try:
                    return float(prices[key])
                except (TypeError, ValueError):
                    return 0.0

            for existing_key, existing_value in prices.items():
                if str(existing_key).upper() == key:
                    try:
                        return float(existing_value)
                    except (TypeError, ValueError):
                        return 0.0

            return 0.0

        try:
            for existing_key, existing_value in dict(prices).items():
                if str(existing_key).upper() == key:
                    try:
                        return float(existing_value)
                    except (TypeError, ValueError):
                        return 0.0
        except (TypeError, ValueError):
            pass

        return 0.0

    def total_value(self, prices: Optional[object] = None) -> float:
        total = 0.0

        for asset in self.assets.values():
            price = self._price_for(asset.symbol, prices)
            total += asset.quantity * price

        return total

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self.assets.values())

    def unrealized_pnl(self, prices: Optional[object] = None) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Optional[object] = None) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for symbol in self.symbols():
            asset = self.assets[symbol]
            value = asset.quantity * self._price_for(symbol, prices)
            result[symbol] = (value / total) if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, object]:
        return {
            "currency": self.currency,
            "assets": [
                self.assets[symbol].to_dict() for symbol in sorted(self.assets)
            ],
        }

    @classmethod
    def from_dict(cls, data: object) -> "Portfolio":
        if isinstance(data, list):
            currency = "USD"
            assets_data: object = data
        elif isinstance(data, Mapping):
            currency = data.get("currency") or "USD"
            assets_data = data.get("assets", {})
        else:
            return cls()

        portfolio = cls(currency=currency)

        if isinstance(assets_data, Mapping):
            for _symbol, asset_data in assets_data.items():
                if asset_data is None:
                    continue

                if isinstance(asset_data, Asset):
                    portfolio.assets[asset_data.symbol] = asset_data
                else:
                    asset = Asset.from_dict(asset_data)
                    portfolio.assets[asset.symbol] = asset
        elif isinstance(assets_data, (list, tuple)):
            for asset_data in assets_data:
                if asset_data is None:
                    continue

                if isinstance(asset_data, Asset):
                    portfolio.assets[asset_data.symbol] = asset_data
                else:
                    asset = Asset.from_dict(asset_data)
                    portfolio.assets[asset.symbol] = asset

        return portfolio


@dataclass
class AssetValue:
    symbol: str
    quantity: float = 0.0
    price: float = 0.0
    value: float = 0.0
    avg_price: float = 0.0
    profit_loss: float = 0.0
    profit_loss_pct: float = 0.0
    allocation_pct: float = 0.0


@dataclass
class PortfolioSummary:
    currency: str
    total_value: float
    total_cost: float
    total_profit_loss: float
    profit_loss_pct: float
    holdings: List[AssetValue] = field(default_factory=list)
