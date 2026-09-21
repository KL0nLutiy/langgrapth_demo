from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from .models import _validate_amount, normalize_symbol


class PriceProvider:
    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, float]:
        result: Dict[str, float] = {}

        for symbol in symbols or []:
            try:
                normalized = normalize_symbol(symbol)
            except ValueError:
                continue

            if normalized not in result:
                result[normalized] = self.get_price(normalized)

        return result

    def set_price(self, symbol: str, price: float) -> None:
        raise NotImplementedError

    def symbols(self) -> List[str]:
        return []


class StaticPriceProvider(PriceProvider):
    def __init__(self, prices: Optional[Any] = None) -> None:
        self._prices: Dict[str, float] = {}

        if prices is None:
            return

        if isinstance(prices, Mapping):
            items = list(prices.items())
        elif isinstance(prices, (list, tuple)):
            items = []
            for item in prices:
                if isinstance(item, Mapping):
                    symbol = item.get("symbol")
                    price = item.get("price")
                    if symbol is not None and price is not None:
                        items.append((symbol, price))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    items.append((item[0], item[1]))
        else:
            return

        for symbol, price in items:
            try:
                normalized = normalize_symbol(symbol)
                self._prices[normalized] = _validate_amount(price, "price")
            except ValueError:
                continue

    def get_price(self, symbol: str) -> float:
        try:
            normalized = normalize_symbol(symbol)
        except ValueError:
            return 0.0

        return float(self._prices.get(normalized, 0.0))

    def set_price(self, symbol: str, price: float) -> None:
        normalized = normalize_symbol(symbol)
        self._prices[normalized] = _validate_amount(price, "price")

    def symbols(self) -> List[str]:
        return sorted(self._prices)


class SamplePriceProvider(StaticPriceProvider):
    SAMPLE_PRICES: Dict[str, float] = {
        "BTC": 120.0,
        "ETH": 30.0,
        "SOL": 10.0,
        "ADA": 0.5,
        "DOGE": 0.1,
        "LTC": 50.0,
        "XRP": 0.5,
        "DOT": 5.0,
        "AVAX": 20.0,
        "LINK": 15.0,
    }

    def __init__(self, prices: Optional[Any] = None) -> None:
        merged = dict(self.SAMPLE_PRICES)

        if prices is not None:
            if isinstance(prices, Mapping):
                for symbol, price in prices.items():
                    try:
                        merged[normalize_symbol(symbol)] = _validate_amount(price, "price")
                    except ValueError:
                        continue
            else:
                temp = StaticPriceProvider(prices)
                merged.update(temp._prices)

        super().__init__(merged)
