"""
src/regime_strategy.py
Regime-Switching stratégia logika.

Két rezsim:
  Regime 1 – Trending (ADX > 25):   EMA crossover + RSI irány szignál
  Regime 2 – Ranging  (ADX <= 25):  Bollinger Band crossover + RSI szélső értékek
"""
import logging
from enum import Enum
from dataclasses import dataclass

from .signal_generator import IndicatorSnapshot

logger = logging.getLogger(__name__)


class Regime(str, Enum):
    TRENDING = "TRENDING"
    RANGING  = "RANGING"


class Signal(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    NONE = "NONE"


@dataclass
class StrategyResult:
    """A stratégia döntésének eredménye."""
    signal: Signal
    regime: Regime
    reason: str = ""

    def is_actionable(self) -> bool:
        return self.signal != Signal.NONE


class RegimeStrategy:
    """
    Regime-Switching stratégia motor.

    Konfiguráció:
      adx_threshold   – ADX határ a rezsim váltáshoz (alapértelmezett: 25)
      rsi_overbought  – RSI felső határ (alapértelmezett: 70)
      rsi_oversold    – RSI alsó határ  (alapértelmezett: 30)
    """

    def __init__(
        self,
        adx_threshold: float = 25.0,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
    ):
        self.adx_threshold = adx_threshold
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    # ------------------------------------------------------------------
    # Fő döntési pont
    # ------------------------------------------------------------------

    def evaluate(self, snap: IndicatorSnapshot) -> StrategyResult:
        """
        Indikátor snapshot alapján szignált generál.

        :param snap: IndicatorSnapshot az aktuális gyertyára
        :return: StrategyResult (signal + regime + indoklás)
        """
        regime = self._detect_regime(snap.adx)

        if regime == Regime.TRENDING:
            result = self._trending_signal(snap)
        else:
            result = self._ranging_signal(snap)

        logger.info(
            "Stratégia → Rezsim: %s | Szignál: %s | Ok: %s",
            result.regime.value, result.signal.value, result.reason,
        )
        return result

    # ------------------------------------------------------------------
    # Rezsim detektálás
    # ------------------------------------------------------------------

    def _detect_regime(self, adx: float) -> Regime:
        regime = Regime.TRENDING if adx >= self.adx_threshold else Regime.RANGING
        logger.debug("ADX=%.2f → Rezsim: %s", adx, regime.value)
        return regime

    # ------------------------------------------------------------------
    # Regime 1: Trending Market (ADX > 25)
    # ------------------------------------------------------------------

    def _trending_signal(self, snap: IndicatorSnapshot) -> StrategyResult:
        """
        BUY:  EMA50 > EMA200 ÉS RSI emelkedik ÉS RSI < 70 (nem túlvásárolt)
        SELL: EMA50 < EMA200 ÉS RSI esik    ÉS RSI > 30 (nem túleladott)
        """
        ema_bull = snap.ema_50 > snap.ema_200
        ema_bear = snap.ema_50 < snap.ema_200

        # BUY feltételek
        if (
            ema_bull
            and snap.rsi_rising
            and snap.rsi <= self.rsi_overbought
        ):
            return StrategyResult(
                signal=Signal.BUY,
                regime=Regime.TRENDING,
                reason=(
                    f"EMA50({snap.ema_50:.2f}) > EMA200({snap.ema_200:.2f}), "
                    f"RSI emelkedik ({snap.rsi_prev:.1f}→{snap.rsi:.1f}), "
                    f"RSI < {self.rsi_overbought}"
                ),
            )

        # SELL feltételek
        if (
            ema_bear
            and snap.rsi_falling
            and snap.rsi >= self.rsi_oversold
        ):
            return StrategyResult(
                signal=Signal.SELL,
                regime=Regime.TRENDING,
                reason=(
                    f"EMA50({snap.ema_50:.2f}) < EMA200({snap.ema_200:.2f}), "
                    f"RSI esik ({snap.rsi_prev:.1f}→{snap.rsi:.1f}), "
                    f"RSI > {self.rsi_oversold}"
                ),
            )

        return StrategyResult(
            signal=Signal.NONE,
            regime=Regime.TRENDING,
            reason="Trending – nincs egyértelmű szignál",
        )

    # ------------------------------------------------------------------
    # Regime 2: Ranging/Sideways Market (ADX <= 25)
    # ------------------------------------------------------------------

    def _ranging_signal(self, snap: IndicatorSnapshot) -> StrategyResult:
        """
        BUY:  Close keresztezi le az alsó BB-t ALULRÓL ÉS RSI <= 30 (túleladott)
        SELL: Close keresztezi fel a felső BB-t FELÜLRŐL ÉS RSI >= 70 (túlvásárolt)
        """
        # BUY: BB alsó sáv crossover lefelé + RSI túleladott
        if snap.crossed_below_bb_lower and snap.rsi <= self.rsi_oversold:
            return StrategyResult(
                signal=Signal.BUY,
                regime=Regime.RANGING,
                reason=(
                    f"Close({snap.close:.2f}) > BB_lower({snap.bb_lower:.2f}) "
                    f"[crossover lefelé], RSI={snap.rsi:.1f} < {self.rsi_oversold}"
                ),
            )

        # SELL: BB felső sáv crossover felfelé + RSI túlvásárolt
        if snap.crossed_above_bb_upper and snap.rsi >= self.rsi_overbought:
            return StrategyResult(
                signal=Signal.SELL,
                regime=Regime.RANGING,
                reason=(
                    f"Close({snap.close:.2f}) > BB_upper({snap.bb_upper:.2f}) "
                    f"[crossover felfelé], RSI={snap.rsi:.1f} > {self.rsi_overbought}"
                ),
            )

        return StrategyResult(
            signal=Signal.NONE,
            regime=Regime.RANGING,
            reason="Ranging – nincs BB crossover + RSI szélső érték",
        )
