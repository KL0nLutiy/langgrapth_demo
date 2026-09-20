from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional

from .models import _validate_amount, normalize_symbol


class PriceProvider:
    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    def get_prices(self, symbols: Iterable[str]) -> Dict[str, float]:
        result: Dict[str, float] = {}

        if symbols is None:
            return result

        for symbol in symbols:
            try:
                normalized = normalize_symbol(symbol)
            except ValueError:
                continue

            result[normalized] = self.get_price(normalized)

        return result

    def set_price(self, symbol: str, price: float) -> None:
        raise NotImplementedError


class StaticPriceProvider(PriceProvider):
    def __init__(self, prices: Optional[object] = None) -> None:
        self._prices: Dict[str, float] = {}

        if not prices:
            return

        if isinstance(prices, Mapping):
            items = prices.items()
        else:
            items = prices

        for symbol, price in items:
            self.set_price(symbol, price)

    def get_price(self, symbol: str) -> float:
        return self._prices.get(normalize_symbol(symbol), 0.0)

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[normalize_symbol(symbol)] = _validate_amount(price, "price")

    def to_dict(self) -> Dict[str, float]:
        return dict(self._prices)


class SamplePriceProvider(StaticPriceProvider):
    def __init__(self) -> None:
        super().__init__(
            {
                "BTC": 65000.0,
                "ETH": 3500.0,
                "SOL": 150.0,
                "ADA": 0.5,
                "DOGE": 0.1,
                "LTC": 80.0,
                "XRP": 0.6,
                "DOT": 7.0,
                "AVAX": 35.0,
                "LINK": 15.0,
            }
        )
