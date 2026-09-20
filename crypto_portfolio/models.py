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


@dataclass
class PortfolioSummary:
    currency: str
    total_value: float
    total_cost: float
    total_profit_loss: float
    profit_loss_pct: float
    holdings: List[AssetValue] = field(default_factory=list)


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
                    self._store_asset(asset)
                elif isinstance(asset, Mapping):
                    self._store_asset(Asset.from_dict(asset))
                else:
                    self._store_asset(Asset(symbol=str(asset)))

    def __eq__(self, other: object) -> object:
        if not isinstance(other, Portfolio):
            return NotImplemented

        return self.currency == other.currency and self.assets == other.assets

    def __repr__(self) -> str:
        return f"Portfolio(currency={self.currency!r}, assets={self.assets!r})"

    def _store_asset(self, asset: Asset) -> None:
        if asset.quantity == 0 and asset.cost_basis == 0:
            self.assets.pop(asset.symbol, None)
        else:
            self.assets[asset.symbol] = asset

    @property
    def holdings(self) -> List[Asset]:
        return [self.assets[symbol] for symbol in sorted(self.assets)]

    def symbols(self) -> List[str]:
        return sorted(self.assets)

    def get_asset(self, symbol: str) -> Asset:
        normalized = normalize_symbol(symbol)
        if normalized not in self.assets:
            raise KeyError(normalized)
        return self.assets[normalized]

    def has_asset(self, symbol: str) -> bool:
        return normalize_symbol(symbol) in self.assets

    def add_asset(
        self,
        symbol: str,
        quantity: float = 0.0,
        cost_basis: float = 0.0,
        name: Optional[str] = None,
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        asset = self.assets.get(normalized)
        if asset is None:
            asset = Asset(
                symbol=normalized,
                quantity=quantity,
                cost_basis=cost_basis,
                name=name,
            )
        else:
            asset.quantity += quantity
            asset.cost_basis += cost_basis
            if name is not None:
                asset.name = str(name)

        self._store_asset(asset)
        return asset

    def set_quantity(self, symbol: str, quantity: float) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        asset = self.assets.get(normalized)
        if asset is None:
            asset = Asset(symbol=normalized, quantity=quantity, cost_basis=0.0)
        else:
            avg_price = asset.avg_price
            asset.quantity = quantity
            asset.cost_basis = avg_price * quantity

        self._store_asset(asset)

        if asset.quantity == 0 and asset.cost_basis == 0:
            return Asset(symbol=normalized, quantity=0.0, cost_basis=0.0)

        return asset

    def remove_asset(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        return self.assets.pop(normalized, None) is not None

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: Optional[float] = None,
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        if quantity == 0:
            asset = self.assets.get(normalized)
            if asset is None:
                return Asset(symbol=normalized, quantity=0.0, cost_basis=0.0)
            return asset

        if avg_price is None:
            existing = self.assets.get(normalized)
            avg = existing.avg_price if existing is not None else 0.0
        else:
            avg = _validate_amount(avg_price, "avg_price")

        return self.add_asset(normalized, quantity=quantity, cost_basis=quantity * avg)

    def remove_holding(self, symbol: str, quantity: Optional[float] = None) -> bool:
        normalized = normalize_symbol(symbol)
        asset = self.assets.get(normalized)

        if asset is None:
            return False

        if quantity is None:
            return self.remove_asset(normalized)

        quantity = _validate_amount(quantity, "quantity")

        if quantity == 0:
            return True

        if quantity >= asset.quantity:
            return self.remove_asset(normalized)

        avg_price = asset.avg_price
        asset.quantity -= quantity
        asset.cost_basis = asset.quantity * avg_price

        self._store_asset(asset)
        return True

    def _normalized_prices(self, prices: Mapping[str, float]) -> Dict[str, float]:
        if not prices:
            return {}

        normalized: Dict[str, float] = {}
        for key, value in prices.items():
            try:
                symbol = normalize_symbol(key)
            except ValueError:
                continue

            try:
                price = float(value)
            except (TypeError, ValueError):
                price = 0.0

            if math.isnan(price) or math.isinf(price) or price < 0:
                price = 0.0

            normalized[symbol] = price

        return normalized

    def total_value(self, prices: Mapping[str, float]) -> float:
        normalized = self._normalized_prices(prices)
        total = 0.0

        for symbol, asset in self.assets.items():
            total += asset.value(normalized.get(symbol, 0.0))

        return total

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self.assets.values())

    def unrealized_pnl(self, prices: Mapping[str, float]) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Mapping[str, float]) -> Dict[str, float]:
        normalized = self._normalized_prices(prices)
        total = self.total_value(normalized)
        result: Dict[str, float] = {}

        for symbol, asset in self.assets.items():
            value = asset.value(normalized.get(symbol, 0.0))
            result[symbol] = (value / total) if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, object]:
        return {
            "currency": self.currency,
            "assets": {
                symbol: self.assets[symbol].to_dict() for symbol in sorted(self.assets)
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Portfolio":
        currency = data.get("currency", "USD")
        assets = data.get("assets", {})

        if isinstance(assets, list):
            normalized_assets: Dict[str, object] = {}
            for index, item in enumerate(assets):
                if item is None:
                    continue
                if isinstance(item, Mapping):
                    symbol = item.get("symbol", f"ASSET_{index}")
                    normalized_assets[str(symbol)] = item
                else:
                    normalized_assets[str(item)] = item
            assets = normalized_assets
        elif not isinstance(assets, Mapping):
            assets = {}

        return cls(currency=str(currency), assets=assets)
