from __future__ import annotations

from typing import List, Optional

from .models import AssetValue, Portfolio, PortfolioSummary
from .pricing import PriceProvider


class PortfolioService:
    """Business logic for portfolio operations and valuation."""

    def __init__(
        self,
        portfolio: Portfolio,
        price_provider: PriceProvider,
        currency: Optional[str] = None,
    ) -> None:
        self.portfolio = portfolio
        self.price_provider = price_provider
        self.currency = currency or portfolio.currency or "USD"

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        avg_price: Optional[float] = None,
    ) -> None:
        self.portfolio.add_holding(symbol, quantity, avg_price)

    def remove_holding(self, symbol: str, quantity: Optional[float] = None) -> None:
        self.portfolio.remove_holding(symbol, quantity)

    def set_price(self, symbol: str, price: float) -> None:
        self.price_provider.set_price(symbol, price)

    def get_summary(self) -> PortfolioSummary:
        holdings: List[AssetValue] = []
        total_value = 0.0
        total_cost = 0.0

        for holding in self.portfolio.holdings:
            price = self.price_provider.get_price(holding.symbol)
            value = holding.quantity * price
            cost = holding.cost_basis
            profit_loss = value - cost
            profit_loss_pct = (profit_loss / cost * 100.0) if cost > 0 else 0.0

            holdings.append(
                AssetValue(
                    symbol=holding.symbol,
                    quantity=holding.quantity,
                    price=price,
                    value=value,
                    avg_price=holding.avg_price,
                    profit_loss=profit_loss,
                    profit_loss_pct=profit_loss_pct,
                    allocation_pct=0.0,
                )
            )

            total_value += value
            total_cost += cost

        total_profit_loss = total_value - total_cost
        total_profit_loss_pct = (
            (total_profit_loss / total_cost * 100.0) if total_cost > 0 else 0.0
        )

        for holding in holdings:
            holding.allocation_pct = (
                (holding.value / total_value * 100.0) if total_value > 0 else 0.0
            )

        holdings.sort(key=lambda item: item.value, reverse=True)

        return PortfolioSummary(
            currency=self.currency,
            total_value=total_value,
            total_cost=total_cost,
            total_profit_loss=total_profit_loss,
            profit_loss_pct=total_profit_loss_pct,
            holdings=holdings,
        )
