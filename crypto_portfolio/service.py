from __future__ import annotations

from typing import Dict, List, Optional

from .models import Asset, AssetValue, Portfolio, PortfolioSummary, _validate_amount
from .pricing import PriceProvider


class PortfolioService:
    def __init__(self, portfolio: Portfolio, provider: PriceProvider) -> None:
        self.portfolio = portfolio
        self.provider = provider

    def get_holding(self, symbol: str) -> Optional[AssetValue]:
        asset = self.portfolio.get_asset(symbol)
        if asset is None:
            return None

        price = self.provider.get_price(asset.symbol)
        value = asset.value(price)
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

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, float]:
        if symbols is None:
            symbols = self.portfolio.symbols()

        return self.provider.get_prices(symbols)

    def get_price(self, symbol: str) -> float:
        return self.provider.get_price(symbol)

    def add_asset(
        self,
        symbol: str,
        quantity: float = 0.0,
        cost_basis: float = 0.0,
        avg_price: Optional[float] = None,
    ) -> Asset:
        if avg_price is not None:
            quantity = _validate_amount(quantity, "quantity")
            avg_price = _validate_amount(avg_price, "avg_price")
            cost_basis = quantity * avg_price
        else:
            quantity = _validate_amount(quantity, "quantity")
            cost_basis = _validate_amount(cost_basis, "cost_basis")

        return self.portfolio.add_asset(
            symbol,
            quantity=quantity,
            cost_basis=cost_basis,
        )

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
        return self.portfolio.set_quantity(symbol, quantity)

    def remove_asset(self, symbol: str) -> bool:
        return self.portfolio.remove_asset(symbol)

    def set_price(self, symbol: str, price: float) -> None:
        self.provider.set_price(symbol, price)
