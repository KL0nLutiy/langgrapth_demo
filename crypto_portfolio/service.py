from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from .models import (
    Asset,
    AssetValue,
    Portfolio,
    PortfolioSummary,
    _validate_amount,
    normalize_symbol,
)
from .pricing import PriceProvider


class PortfolioService:
    def __init__(self, portfolio: Portfolio, provider: PriceProvider) -> None:
        self.portfolio = portfolio
        self.provider = provider

    def _get_price(self, symbol: str) -> float:
        if self.provider is None:
            return 0.0

        if isinstance(self.provider, Mapping):
            return Portfolio._price_for(self.provider, symbol)

        get_price = getattr(self.provider, "get_price", None)
        if callable(get_price):
            return float(get_price(symbol) or 0.0)

        return 0.0

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

        if isinstance(self.provider, Mapping):
            return {symbol: Portfolio._price_for(self.provider, symbol) for symbol in symbols}

        get_prices = getattr(self.provider, "get_prices", None)
        if callable(get_prices):
            return get_prices(symbols)

        return {symbol: self._get_price(symbol) for symbol in symbols}

    def get_price(self, symbol: str) -> float:
        return self._get_price(symbol)

    def add_asset(
        self,
        symbol: str,
        quantity: Any = 0.0,
        cost_basis: Optional[Any] = None,
        avg_price: Optional[Any] = None,
    ) -> Optional[Asset]:
        normalized_symbol = normalize_symbol(symbol)
        quantity = _validate_amount(quantity, "quantity")

        if avg_price is not None:
            avg_price = _validate_amount(avg_price, "avg_price")

        if cost_basis is not None:
            cost_basis = _validate_amount(cost_basis, "cost_basis")

        if quantity == 0:
            return self.portfolio.get_asset(normalized_symbol)

        if avg_price is not None:
            cost_basis = avg_price * quantity

        if cost_basis is None:
            cost_basis = 0.0

        cost_basis = _validate_amount(cost_basis, "cost_basis")

        return self.portfolio.add_asset(
            normalized_symbol,
            quantity=quantity,
            cost_basis=cost_basis,
        )

    def set_quantity(self, symbol: str, quantity: Any) -> Optional[Asset]:
        quantity = _validate_amount(quantity, "quantity")
        return self.portfolio.set_quantity(symbol, quantity)

    def remove_asset(self, symbol: str, quantity: Optional[Any] = None) -> bool:
        return self.portfolio.remove_asset(symbol, quantity)

    def set_price(self, symbol: str, price: Any) -> float:
        price = _validate_amount(price, "price")
        self.provider.set_price(symbol, price)
        return price

    def export(self) -> Dict[str, Any]:
        return self.portfolio.to_dict()
