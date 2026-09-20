from __future__ import annotations

from typing import List

from .models import AssetValue, Portfolio, PortfolioSummary
from .pricing import PriceProvider


class PortfolioService:
    def __init__(self, portfolio: Portfolio, provider: PriceProvider) -> None:
        self.portfolio = portfolio
        self.provider = provider

    def get_summary(self) -> PortfolioSummary:
        symbols = self.portfolio.symbols()
        prices = self.provider.get_prices(symbols)

        total_value = 0.0
        total_cost = self.portfolio.total_cost()
        holdings: List[AssetValue] = []

        for symbol in symbols:
            asset = self.portfolio.get_asset(symbol)
            if asset is None:
                continue

            price = float(prices.get(symbol, 0.0))
            value = asset.value(price)
            total_value += value

            profit_loss = value - asset.cost_basis
            profit_loss_pct = (profit_loss / asset.cost_basis * 100.0) if asset.cost_basis > 0 else 0.0

            holdings.append(
                AssetValue(
                    symbol=asset.symbol,
                    quantity=asset.quantity,
                    price=price,
                    value=value,
                    avg_price=asset.avg_price,
                    profit_loss=profit_loss,
                    profit_loss_pct=profit_loss_pct,
                    allocation_pct=0.0,
                )
            )

        for holding in holdings:
            holding.allocation_pct = (holding.value / total_value * 100.0) if total_value > 0 else 0.0

        total_profit_loss = total_value - total_cost
        profit_loss_pct = (total_profit_loss / total_cost * 100.0) if total_cost > 0 else 0.0

        return PortfolioSummary(
            currency=self.portfolio.currency,
            total_value=total_value,
            total_cost=total_cost,
            total_profit_loss=total_profit_loss,
            profit_loss_pct=profit_loss_pct,
            holdings=holdings,
        )
