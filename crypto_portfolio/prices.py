from abc import ABC, abstractmethod
from typing import Dict, Iterable, Mapping, Optional


class PriceProvider(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    def get_prices(self, symbols: Iterable[str]) -> Dict[str, float]:
        return {str(symbol).upper(): self.get_price(symbol) for symbol in symbols}

    def set_price(self, symbol: str, price: float) -> None:
        raise NotImplementedError


class StaticPriceProvider(PriceProvider):
    def __init__(self, prices: Mapping[str, float]) -> None:
        self.prices: Dict[str, float] = {
            str(symbol).upper(): float(price) for symbol, price in prices.items()
        }

    def get_price(self, symbol: str) -> float:
        return self.prices.get(str(symbol).upper(), 0.0)

    def set_price(self, symbol: str, price: float) -> None:
        self.prices[str(symbol).upper()] = float(price)


class SamplePriceProvider(StaticPriceProvider):
    DEFAULT_PRICES: Mapping[str, float] = {
        "BTC": 65000.0,
        "ETH": 3500.0,
        "SOL": 150.0,
        "USDC": 1.0,
    }

    def __init__(self, prices: Optional[Mapping[str, float]] = None) -> None:
        super().__init__(prices if prices is not None else self.DEFAULT_PRICES)
