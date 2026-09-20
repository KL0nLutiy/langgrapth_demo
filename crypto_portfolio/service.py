from __future__ import annotations

from typing import Dict, List, Optional

from .models import Asset, AssetValue, Portfolio, PortfolioSummary
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
            currency="USD",
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
