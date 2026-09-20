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


def _price_for(symbol: str, prices: Optional[object]) -> float:
    if prices is None:
        return 0.0

    if isinstance(prices, Mapping):
        raw = prices.get(symbol, 0.0)
    elif hasattr(prices, "get_price"):
        raw = prices.get_price(symbol)
    else:
        return 0.0

    try:
        price = float(raw)
    except (TypeError, ValueError):
        return 0.0

    if math.isnan(price) or math.isinf(price):
        return 0.0

    return price


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
        if not isinstance(data, Mapping):
            raise TypeError("Asset data must be a mapping")

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
    def __init__(self, assets: Optional[List[Asset]] = None) -> None:
        self._assets: Dict[str, Asset] = {}

        if assets:
            for asset in assets:
                self._assets[asset.symbol] = asset

    @property
    def assets(self) -> List[Asset]:
        return [self._assets[symbol] for symbol in sorted(self._assets)]

    def symbols(self) -> List[str]:
        return sorted(self._assets)

    def get_asset(self, symbol: str) -> Optional[Asset]:
        return self._assets.get(normalize_symbol(symbol))

    def add_asset(
        self,
        symbol: str,
        quantity: float,
        cost_basis: float,
        name: Optional[str] = None,
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        existing = self._assets.get(normalized)
        if existing is None:
            asset = Asset(
                symbol=normalized,
                quantity=quantity,
                cost_basis=cost_basis,
                name=name,
            )
            self._assets[normalized] = asset
            return asset

        existing.quantity += quantity
        existing.cost_basis += cost_basis
        if name is not None:
            existing.name = str(name)
        return existing

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: float,
        name: Optional[str] = None,
    ) -> Asset:
        quantity = _validate_amount(quantity, "quantity")
        avg_price = _validate_amount(avg_price, "avg_price")
        return self.add_asset(
            symbol,
            quantity=quantity,
            cost_basis=quantity * avg_price,
            name=name,
        )

    def set_quantity(self, symbol: str, quantity: float) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        existing = self._assets.get(normalized)
        if existing is None:
            return self.add_asset(normalized, quantity=quantity, cost_basis=0.0)

        existing.quantity = quantity
        if quantity == 0.0:
            existing.cost_basis = 0.0
        return existing

    def remove_asset(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        return self._assets.pop(normalized, None) is not None

    def total_value(self, prices: Optional[object]) -> float:
        return sum(
            asset.value(_price_for(asset.symbol, prices))
            for asset in self.assets
        )

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self.assets)

    def unrealized_pnl(self, prices: Optional[object]) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Optional[object]) -> Dict[str, float]:
        total = self.total_value(prices)
        if total <= 0:
            return {asset.symbol: 0.0 for asset in self.assets}

        return {
            asset.symbol: asset.value(_price_for(asset.symbol, prices)) / total
            for asset in self.assets
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "assets": [asset.to_dict() for asset in self.assets],
        }

    @classmethod
    def from_dict(cls, data: object) -> "Portfolio":
        if isinstance(data, Mapping):
            raw_assets = data.get("assets", [])
        elif isinstance(data, list):
            raw_assets = data
        else:
            raise TypeError("Portfolio data must be a mapping or list")

        if not isinstance(raw_assets, list):
            raise TypeError("Portfolio assets must be a list")

        portfolio = cls()
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, Mapping):
                raise TypeError("Each portfolio asset must be a mapping")

            asset = Asset.from_dict(raw_asset)
            if asset.quantity == 0.0 and asset.cost_basis == 0.0:
                portfolio._assets[asset.symbol] = asset
                continue

            portfolio.add_asset(
                asset.symbol,
                quantity=asset.quantity,
                cost_basis=asset.cost_basis,
                name=asset.name,
            )

        return portfolio
