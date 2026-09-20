from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

def normalize_symbol(symbol: Any) -> str:
    if symbol is None:
        raise ValueError("symbol must not be empty")

    text = str(symbol).strip().upper()
    if not text:
        raise ValueError("symbol must not be empty")

    if not all(ch.isalnum() or ch in "-_" for ch in text):
        raise ValueError(f"invalid symbol: {symbol!r}")

    return text


def _validate_amount(value: Any, name: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    if math.isnan(amount) or math.isinf(amount):
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
        self.quantity = _validate_amount(self.quantity, "quantity")
        self.cost_basis = _validate_amount(self.cost_basis, "cost_basis")

    @property
    def avg_price(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.cost_basis / self.quantity

    def value(self, price: float) -> float:
        return self.quantity * _validate_amount(price, "price")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Asset":
        if isinstance(data, Mapping):
            symbol = data.get("asset", data.get("symbol"))
            quantity = data.get("quantity", 0.0)
            cost_basis = data.get("cost_basis", data.get("cost", 0.0))
        elif isinstance(data, (list, tuple)):
            if not data:
                raise ValueError("asset data must not be empty")
            symbol = data[0]
            quantity = data[1] if len(data) > 1 else 0.0
            cost_basis = data[2] if len(data) > 2 else 0.0
        else:
            raise ValueError("asset data must be a mapping or sequence")

        return cls(symbol=symbol, quantity=quantity, cost_basis=cost_basis)


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
    cost_basis: float = 0.0

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        self.quantity = _validate_amount(self.quantity, "quantity")
        self.price = _validate_amount(self.price, "price")
        self.value = _validate_amount(self.value, "value")
        self.avg_price = _validate_amount(self.avg_price, "avg_price")
        self.allocation_pct = _validate_amount(self.allocation_pct, "allocation_pct")
        self.cost_basis = _validate_amount(self.cost_basis, "cost_basis")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "value": self.value,
            "avg_price": self.avg_price,
            "cost_basis": self.cost_basis,
            "profit_loss": self.profit_loss,
            "profit_loss_pct": self.profit_loss_pct,
            "allocation_pct": self.allocation_pct,
        }


@dataclass
class PortfolioSummary:
    currency: str = "USD"
    total_value: float = 0.0
    total_cost: float = 0.0
    total_profit_loss: float = 0.0
    profit_loss_pct: float = 0.0
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


def _price_for(symbol: str, prices: Any) -> float:
    if prices is None:
        return 0.0

    if isinstance(prices, Mapping):
        for key in (symbol, symbol.lower(), symbol.upper()):
            if key in prices:
                try:
                    return _validate_amount(prices[key], "price")
                except ValueError:
                    return 0.0
        return 0.0

    get_price = getattr(prices, "get_price", None)
    if callable(get_price):
        try:
            return _validate_amount(get_price(symbol), "price")
        except ValueError:
            return 0.0

    return 0.0


class Portfolio:
    def __init__(self, currency: str = "USD", holdings: Optional[Iterable[Any]] = None) -> None:
        self.currency = str(currency or "USD").upper()
        self._assets: Dict[str, Asset] = {}

        if holdings:
            for item in holdings:
                if isinstance(item, Asset):
                    self._assets[item.symbol] = item
                elif isinstance(item, Mapping):
                    asset = Asset.from_dict(item)
                    self._assets[asset.symbol] = asset
                elif isinstance(item, (list, tuple)):
                    asset = Asset.from_dict(item)
                    self._assets[asset.symbol] = asset

    def symbols(self) -> List[str]:
        return sorted(symbol for symbol, asset in self._assets.items() if asset.quantity > 0)

    def get_asset(self, symbol: str) -> Optional[Asset]:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return None
        return self._assets.get(normalized)

    def add_asset(
        self,
        symbol: str,
        quantity: float = 0.0,
        cost_basis: float = 0.0,
        avg_price: Optional[float] = None,
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        if avg_price is not None:
            avg_price = _validate_amount(avg_price, "avg_price")
            cost_basis = quantity * avg_price
        else:
            cost_basis = _validate_amount(cost_basis, "cost_basis")

        if quantity == 0:
            cost_basis = 0.0

        existing = self._assets.get(normalized)
        if existing is None:
            if quantity == 0:
                return Asset(normalized, 0.0, 0.0)

            asset = Asset(normalized, quantity, cost_basis)
            self._assets[normalized] = asset
            return asset

        existing.quantity += quantity
        existing.cost_basis += cost_basis
        return existing

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: Optional[float] = None,
        cost_basis: Optional[float] = None,
    ) -> Asset:
        if avg_price is not None:
            return self.add_asset(symbol, quantity=quantity, avg_price=avg_price)
        if cost_basis is not None:
            return self.add_asset(symbol, quantity=quantity, cost_basis=cost_basis)
        return self.add_asset(symbol, quantity=quantity)

    def set_quantity(self, symbol: str, quantity: float) -> Optional[Asset]:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        asset = self._assets.get(normalized)
        if asset is None:
            if quantity == 0:
                return None
            raise ValueError(f"Unknown asset: {normalized}")

        if quantity == 0:
            del self._assets[normalized]
            return None

        avg_price = asset.avg_price
        asset.quantity = quantity
        asset.cost_basis = quantity * avg_price
        return asset

    def remove_asset(self, symbol: str) -> bool:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return False

        return self._assets.pop(normalized, None) is not None

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self._assets.values() if asset.quantity > 0)

    def total_value(self, prices: Any) -> float:
        total = 0.0
        for asset in self._assets.values():
            if asset.quantity <= 0:
                continue
            total += asset.value(_price_for(asset.symbol, prices))
        return total

    def unrealized_pnl(self, prices: Any) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Any) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for symbol in self.symbols():
            asset = self._assets[symbol]
            value = asset.value(_price_for(symbol, prices))
            result[symbol] = (value / total) if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, Any]:
        holdings = [self._assets[symbol].to_dict() for symbol in self.symbols()]
        return {
            "currency": self.currency,
            "holdings": holdings,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Portfolio":
        portfolio = cls()

        if data is None:
            return portfolio

        if isinstance(data, (list, tuple)):
            holdings: Any = data
        elif isinstance(data, Mapping):
            portfolio.currency = str(data.get("currency", "USD") or "USD").upper()
            holdings = data.get("holdings", data.get("assets", []))
            if holdings is None:
                holdings = []
        else:
            raise ValueError("portfolio data must be a mapping or sequence")

        if isinstance(holdings, Mapping):
            for symbol, value in holdings.items():
                if isinstance(value, Mapping):
                    quantity = value.get("quantity", 0.0)
                    cost_basis = value.get("cost_basis", value.get("cost", 0.0))
                elif isinstance(value, (int, float)):
                    quantity = value
                    cost_basis = 0.0
                elif isinstance(value, (list, tuple)):
                    quantity = value[1] if len(value) > 1 else 0.0
                    cost_basis = value[2] if len(value) > 2 else 0.0
                else:
                    continue

                try:
                    portfolio.add_asset(symbol, quantity=quantity, cost_basis=cost_basis)
                except ValueError:
                    continue
        elif isinstance(holdings, (list, tuple)):
            for item in holdings:
                try:
                    if isinstance(item, Asset):
                        portfolio.add_asset(
                            item.symbol,
                            quantity=item.quantity,
                            cost_basis=item.cost_basis,
                        )
                    elif isinstance(item, Mapping):
                        asset = Asset.from_dict(item)
                        portfolio.add_asset(
                            asset.symbol,
                            quantity=asset.quantity,
                            cost_basis=asset.cost_basis,
                        )
                    elif isinstance(item, (list, tuple)):
                        asset = Asset.from_dict(item)
                        portfolio.add_asset(
                            asset.symbol,
                            quantity=asset.quantity,
                            cost_basis=asset.cost_basis,
                        )
                    else:
                        continue
                except ValueError:
                    continue
        else:
            raise ValueError("holdings must be a mapping or sequence")

        return portfolio
