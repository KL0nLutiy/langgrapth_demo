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
    def __init__(self, assets: Optional[Mapping[str, object]] = None, currency: str = "USD") -> None:
        self.currency = str(currency or "USD")
        self._assets: Dict[str, Asset] = {}

        if assets:
            for symbol, asset in assets.items():
                if isinstance(asset, Asset):
                    self._assets[asset.symbol] = asset
                elif isinstance(asset, Mapping):
                    parsed = Asset.from_dict(asset)
                    self._assets[parsed.symbol] = parsed
                else:
                    raise TypeError("Asset values must be Asset instances or mappings")

    @property
    def assets(self) -> Dict[str, Asset]:
        return dict(self._assets)

    def get_assets(self) -> Dict[str, Asset]:
        return dict(self._assets)

    def symbols(self) -> List[str]:
        return sorted(self._assets)

    def get_asset(self, symbol: str) -> Optional[Asset]:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return None
        return self._assets.get(normalized)

    def has_asset(self, symbol: str) -> bool:
        return self.get_asset(symbol) is not None

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

        asset = self._assets.get(normalized)
        if asset is None:
            asset = Asset(symbol=normalized, quantity=quantity, cost_basis=cost_basis, name=name)
            self._assets[normalized] = asset
        else:
            asset.quantity = _validate_amount(asset.quantity + quantity, "quantity")
            asset.cost_basis = _validate_amount(asset.cost_basis + cost_basis, "cost_basis")
            if name is not None:
                asset.name = str(name)

        if asset.quantity <= 0 and asset.cost_basis <= 0:
            self._assets.pop(normalized, None)

        return asset

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: float,
        name: Optional[str] = None,
    ) -> Asset:
        quantity = _validate_amount(quantity, "quantity")
        avg_price = _validate_amount(avg_price, "avg_price")
        return self.add_asset(symbol, quantity, quantity * avg_price, name=name)

    def set_quantity(self, symbol: str, quantity: float) -> Optional[Asset]:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        asset = self._assets.get(normalized)
        if asset is None:
            if quantity <= 0:
                return None
            asset = Asset(symbol=normalized, quantity=quantity)
            self._assets[normalized] = asset
            return asset

        if quantity <= 0:
            self._assets.pop(normalized, None)
            return None

        if asset.quantity > 0:
            asset.cost_basis = _validate_amount(asset.cost_basis * (quantity / asset.quantity), "cost_basis")

        asset.quantity = quantity
        return asset

    def set_cost_basis(self, symbol: str, cost_basis: float) -> Optional[Asset]:
        normalized = normalize_symbol(symbol)
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        asset = self._assets.get(normalized)
        if asset is None:
            if cost_basis <= 0:
                return None
            asset = Asset(symbol=normalized, cost_basis=cost_basis)
            self._assets[normalized] = asset
            return asset

        asset.cost_basis = cost_basis

        if asset.quantity <= 0 and asset.cost_basis <= 0:
            self._assets.pop(normalized, None)
            return None

        return asset

    def remove_asset(self, symbol: str) -> bool:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return False
        return self._assets.pop(normalized, None) is not None

    def remove_quantity(self, symbol: str, quantity: float) -> bool:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        asset = self._assets.get(normalized)
        if asset is None:
            return False

        if quantity >= asset.quantity - 1e-12:
            return self.remove_asset(normalized)

        remaining = asset.quantity - quantity
        if remaining <= 0:
            return self.remove_asset(normalized)

        if asset.quantity > 0:
            asset.cost_basis = _validate_amount(asset.cost_basis * (remaining / asset.quantity), "cost_basis")

        asset.quantity = remaining
        return True

    def total_value(self, prices: Optional[object]) -> float:
        total = 0.0
        for symbol, asset in self._assets.items():
            total += asset.value(_price_for(symbol, prices))
        return total

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self._assets.values())

    def unrealized_pnl(self, prices: Optional[object]) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Optional[object]) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for symbol, asset in self._assets.items():
            value = asset.value(_price_for(symbol, prices))
            result[symbol] = value / total if total > 0 else 0.0

        return result

    def value(self, prices: Optional[object]) -> float:
        return self.total_value(prices)

    def pnl(self, prices: Optional[object]) -> float:
        return self.unrealized_pnl(prices)

    def __contains__(self, symbol: str) -> bool:
        return self.has_asset(symbol)

    def __iter__(self):
        return iter(self.symbols())

    def __len__(self) -> int:
        return len(self._assets)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "assets": {symbol: asset.to_dict() for symbol, asset in sorted(self._assets.items())}
        }

        if self.currency and self.currency != "USD":
            data["currency"] = self.currency

        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Portfolio":
        if not isinstance(data, Mapping):
            raise TypeError("Portfolio data must be a mapping")

        currency = data.get("currency", "USD")
        assets_data = data.get("assets", {})
        if assets_data is None:
            assets_data = {}

        portfolio = cls(currency=currency)

        if isinstance(assets_data, Mapping):
            items = assets_data.items()
        elif isinstance(assets_data, list):
            items = [(None, asset) for asset in assets_data]
        else:
            raise TypeError("Portfolio assets must be a mapping or list")

        for symbol, asset_data in items:
            if isinstance(asset_data, Asset):
                asset = asset_data
            elif isinstance(asset_data, Mapping):
                asset = Asset.from_dict(asset_data)
            else:
                raise TypeError("Asset data must be a mapping")

            portfolio._assets[asset.symbol] = asset

        return portfolio
