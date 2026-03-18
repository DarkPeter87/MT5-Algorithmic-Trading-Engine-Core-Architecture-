"""
Stratégia alap és keret – később ide építed be a saját stratégiádat.
A döntés csak a beállított paraméterek és (opcionálisan) áradatok alapján történik.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Any
import logging

from .config import BotConfig, StrategyParams

logger = logging.getLogger(__name__)


class Signal(str, Enum):
    NONE = "none"
    BUY = "buy"
    SELL = "sell"


class StrategyBase(ABC):
    """
    Alaposztály minden stratégiához.
    A konfigurációból minden paraméter (strategy.param_1, param_2, stb.) elérhető.
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.params: StrategyParams = config.strategy

    @abstractmethod
    def get_signal(self, market_data: Optional[Any] = None) -> Signal:
        """
        Döntés: BUY, SELL vagy NONE.
        market_data: opcionális (pl. DataFrame OHLCV vagy MT5 rates).
        Ha később kapsz stratégiát, itt implementálod a logikát.
        """
        pass

    def is_enabled(self) -> bool:
        return self.params.enabled


class PlaceholderStrategy(StrategyBase):
    """
    Placeholder stratégia – nem ad szignált.
    Később cseréld ki a saját stratégiádra, ami használja param_1, param_2, param_3, timeframe_minutes stb.
    """

    def get_signal(self, market_data: Optional[Any] = None) -> Signal:
        if not self.is_enabled():
            return Signal.NONE
        # Példa: később itt pl. RSI(market_data, period=self.params.param_1) < 30 -> BUY
        return Signal.NONE
