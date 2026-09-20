from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

_EPS = 1e-12


def normalize_symbol(symbol: Any) -> str:
    if symbol is None:
        raise ValueError("symbol must not be empty")

    text = str(symbol).strip().upper()
    if not text:
        raise ValueError("symbol must not be empty")

    return text


def _validate_amount(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"{name} must be finite")

    if number < 0:
        raise ValueError(f"{name} must be non-negative")

    return number


class Asset:
    def __init__(self, symbol: str, quantity: float = 0.0, cost_basis: float = 0.0) -> None:
        self.symbol = normalize_symbol(symbol)
        self.quantity = _validate_amount(quantity, "quantity")
        self.cost_basis = _validate_amount(cost_basis, "cost_basis")

    @property
    def avg_price(self) -> float:
        if self.quantity > _EPS:
            return self.cost_basis / self.quantity
        return 0.0

    @property
    def is_zero(self) -> bool:
        return self.quantity <= _EPS and self.cost_basis <= _EPS

    def value(self, price: float) -> float:
        return self.quantity * _validate_amount(price, "price")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Asset":
        if isinstance(data, Mapping):
            symbol = data.get("symbol", data.get("ticker"))
            quantity = data.get("quantity", 0.0)
            cost_basis = data.get("cost_basis", data.get("cost", 0.0))

            if cost_basis is None:
                avg_price = data.get("avg_price", data.get("average_price"))
                if avg_price is not None:
                    quantity = _validate_amount(quantity, "quantity")
                    cost_basis = quantity * _validate_amount(avg_price, "avg_price")

            return cls(symbol, quantity, cost_basis)

        if isinstance(data, (list, tuple)):
            if len(data) >= 3:
                return cls(data[0], data[1], data[2])
            if len(data) == 2:
                return cls(data[0], data[1], 0.0)
            if len(data) == 1:
                return cls(data[0], 0.0, 0.0)

        raise ValueError("invalid asset data")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Asset):
            return False
        return (
            self.symbol == other.symbol
            and self.quantity == other.quantity
            and self.cost_basis == other.cost_basis
        )

    def __hash__(self) -> int:
        return hash((self.symbol, self.quantity, self.cost_basis))

    def __repr__(self) -> str:
        return (
            f"Asset(symbol={self.symbol!r}, quantity={self.quantity!r}, "
            f"cost_basis={self.cost_basis!r})"
        )


class Portfolio:
    def __init__(self, currency: str = "USD", assets: Optional[Any] = None) -> None:
        self.currency = str(currency or "USD").strip().upper() or "USD"
        self._assets: Dict[str, Asset] = {}

        if assets is None:
            return

        if isinstance(assets, Mapping):
            for symbol, item in assets.items():
                self._add_asset_item(symbol, item)
        else:
            for item in assets:
                self._add_asset_item(None, item)

    def _add_asset_item(self, symbol: Optional[str], item: Any) -> None:
        if isinstance(item, Asset):
            asset = item
        elif isinstance(item, Mapping):
            data = dict(item)
            if symbol is not None and not data.get("symbol"):
                data["symbol"] = symbol
            asset = Asset.from_dict(data)
        elif isinstance(item, (list, tuple)):
            data = list(item)
            if symbol is not None and (not data or data[0] in (None, "")):
                if not data:
                    data.append(symbol)
                else:
                    data[0] = symbol
            asset = Asset.from_dict(data)
        elif isinstance(item, str):
            asset = Asset(item, 0.0, 0.0)
        else:
            if symbol is None:
                raise ValueError("invalid asset data")
            asset = Asset(symbol, item, 0.0)

        self._assets[asset.symbol] = asset

    @property
    def assets(self) -> List[Asset]:
        return [self._assets[symbol] for symbol in self.symbols()]

    def symbols(self) -> List[str]:
        return sorted(self._assets)

    def __len__(self) -> int:
        return len(self._assets)

    def __iter__(self):
        return iter(self.assets)

    def __contains__(self, symbol: Any) -> bool:
        try:
            return normalize_symbol(symbol) in self._assets
        except ValueError:
            return False

    def get_asset(self, symbol: str, default: Optional[Asset] = None) -> Optional[Asset]:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return default
        return self._assets.get(normalized, default)

    def placeholder(self, symbol: str) -> Asset:
        return Asset(symbol, 0.0, 0.0)

    def zero_asset(self, symbol: str) -> Asset:
        asset = self.get_asset(symbol)
        if asset is not None:
            return asset
        return Asset(symbol, 0.0, 0.0)

    def add_asset(self, symbol: str, quantity: float = 0.0, cost_basis: float = 0.0) -> Asset:
        normalized = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")
        cost_basis = _validate_amount(cost_basis, "cost_basis")

        existing = self._assets.get(normalized)
        if existing is None:
            if quantity <= _EPS and cost_basis <= _EPS:
                return Asset(normalized, 0.0, 0.0)

            asset = Asset(normalized, quantity, cost_basis)
            self._assets[normalized] = asset
            return asset

        existing.quantity += quantity
        existing.cost_basis += cost_basis
        return existing

    add = add_asset

    def add_holding(self, symbol: str, quantity: float, avg_price: float) -> Asset:
        quantity = _validate_amount(quantity, "quantity")
        avg_price = _validate_amount(avg_price, "avg_price")
        return self.add_asset(symbol, quantity, quantity * avg_price)

    def set_quantity(self, symbol: str, quantity: float) -> bool:
        normalized = normalize_symbol(symbol)
        asset = self._assets.get(normalized)
        if asset is None:
            return False

        quantity = _validate_amount(quantity, "quantity")

        if quantity <= _EPS:
            del self._assets[normalized]
            return True

        if asset.quantity > _EPS:
            asset.cost_basis = asset.cost_basis * (quantity / asset.quantity)
        else:
            asset.cost_basis = 0.0

        asset.quantity = quantity
        return True

    def remove_asset(self, symbol: str, quantity: Optional[float] = None) -> bool:
        normalized = normalize_symbol(symbol)
        asset = self._assets.get(normalized)
        if asset is None:
            return False

        if quantity is None:
            del self._assets[normalized]
            return True

        quantity = _validate_amount(quantity, "quantity")

        if quantity <= _EPS:
            return True

        if quantity >= asset.quantity - _EPS:
            del self._assets[normalized]
            return True

        if asset.quantity > _EPS:
            cost_removed = asset.cost_basis * (quantity / asset.quantity)
        else:
            cost_removed = 0.0

        asset.quantity = max(0.0, asset.quantity - quantity)
        asset.cost_basis = max(0.0, asset.cost_basis - cost_removed)

        if asset.quantity <= _EPS:
            del self._assets[normalized]

        return True

    remove = remove_asset

    def remove_quantity(self, symbol: str, quantity: float) -> bool:
        return self.remove_asset(symbol, quantity)

    def _price_for(self, symbol: str, prices: Any) -> float:
        getter = getattr(prices, "get_price", None)
        if callable(getter):
            try:
                return float(getter(symbol))
            except Exception:
                return 0.0

        if isinstance(prices, Mapping):
            if symbol in prices:
                try:
                    return float(prices[symbol])
                except Exception:
                    return 0.0

            lower = symbol.lower()
            if lower in prices:
                try:
                    return float(prices[lower])
                except Exception:
                    return 0.0

            return 0.0

        try:
            return float(prices.get(symbol, 0.0))
        except Exception:
            return 0.0

    def total_value(self, prices: Any) -> float:
        total = 0.0
        for symbol in self.symbols():
            asset = self._assets[symbol]
            total += asset.quantity * self._price_for(symbol, prices)
        return total

    def total_cost(self) -> float:
        return sum(asset.cost_basis for asset in self._assets.values())

    def unrealized_pnl(self, prices: Any) -> float:
        return self.total_value(prices) - self.total_cost()

    def allocation(self, prices: Any) -> Dict[str, float]:
        total = self.total_value(prices)
        result: Dict[str, float] = {}

        for symbol in self.symbols():
            asset = self._assets[symbol]
            value = asset.quantity * self._price_for(symbol, prices)
            result[symbol] = value / total if total > 0 else 0.0

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assets": [self._assets[symbol].to_dict() for symbol in self.symbols()]
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Portfolio":
        portfolio = cls()

        if not data:
            return portfolio

        if isinstance(data, Mapping):
            if data.get("currency"):
                portfolio.currency = str(data["currency"]).strip().upper() or "USD"
            assets = data.get("assets", data.get("holdings", []))
        elif isinstance(data, (list, tuple)):
            assets = data
        else:
            return portfolio

        if isinstance(assets, Mapping):
            for symbol, item in assets.items():
                portfolio._add_asset_item(symbol, item)
        elif isinstance(assets, (list, tuple)):
            for item in assets:
                portfolio._add_asset_item(None, item)

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
        self.symbol = normalize_symbol(symbol)
        self.quantity = float(quantity)
        self.price = float(price)
        self.value = float(value)
        self.avg_price = float(avg_price)
        self.profit_loss = float(profit_loss)
        self.profit_loss_pct = float(profit_loss_pct)
        self.allocation_pct = float(allocation_pct)
        self.cost_basis = float(cost_basis)

    @property
    def cost(self) -> float:
        return self.cost_basis

    @property
    def pnl(self) -> float:
        return self.profit_loss

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

    def __repr__(self) -> str:
        return (
            f"AssetValue(symbol={self.symbol!r}, quantity={self.quantity!r}, "
            f"price={self.price!r}, value={self.value!r})"
        )


class PortfolioSummary:
    def __init__(
        self,
        currency: str,
        total_value: float,
        total_cost: float,
        total_profit_loss: float,
        profit_loss_pct: float,
        holdings: Iterable[AssetValue],
    ) -> None:
        self.currency = str(currency or "USD").strip().upper() or "USD"
        self.total_value = float(total_value)
        self.total_cost = float(total_cost)
        self.total_profit_loss = float(total_profit_loss)
        self.profit_loss_pct = float(profit_loss_pct)
        self.holdings = list(holdings)

    @property
    def assets(self) -> List[AssetValue]:
        return self.holdings

    def to_dict(self) -> Dict[str, Any]:
        assets = [holding.to_dict() for holding in self.holdings]
        return {
            "currency": self.currency,
            "total_value": self.total_value,
            "total_cost": self.total_cost,
            "total_profit_loss": self.total_profit_loss,
            "profit_loss_pct": self.profit_loss_pct,
            "assets": assets,
            "holdings": assets,
        }

    def __repr__(self) -> str:
        return (
            f"PortfolioSummary(currency={self.currency!r}, "
            f"total_value={self.total_value!r}, holdings={len(self.holdings)})"
        )
