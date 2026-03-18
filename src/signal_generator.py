"""
src/signal_generator.py
Indikátor kalkulátor – ADX, EMA50/200, RSI, Bollinger Bands, ATR.
pandas-ta alapokon, vektorizálva.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

try:
    import pandas_ta as ta
except ImportError:
    ta = None

logger = logging.getLogger(__name__)


@dataclass
class IndicatorSnapshot:
    """
    Egyetlen gyertyára vonatkozó indikátor pillanatkép.
    A SignalGenerator ezt adja vissza a stratégia számára.
    """
    # Regime meghatározó
    adx: float = 0.0

    # Trend-követő
    ema_50: float = 0.0
    ema_200: float = 0.0
    rsi: float = 50.0
    rsi_prev: float = 50.0   # előző gyertya RSI – irány meghatározáshoz

    # Mean-Reversion
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_mid: float = 0.0
    close: float = 0.0
    close_prev: float = 0.0   # előző gyertya Close – crossover detektáláshoz

    # Kockázatkezelés
    atr: float = 0.0

    @property
    def rsi_rising(self) -> bool:
        return self.rsi > self.rsi_prev

    @property
    def rsi_falling(self) -> bool:
        return self.rsi < self.rsi_prev

    @property
    def crossed_below_bb_lower(self) -> bool:
        """Close crosses below the lower BB."""
        return self.close_prev >= self.bb_lower and self.close < self.bb_lower

    @property
    def crossed_above_bb_upper(self) -> bool:
        """Close crosses above the upper BB."""
        return self.close_prev <= self.bb_upper and self.close > self.bb_upper


class SignalGenerator:
    """
    Indikátorokat számol ki egy OHLCV DataFrame-ből,
    és IndicatorSnapshot-ot ad vissza az utolsó zárt gyertyára.

    Indikátorok:
      - ADX(14)
      - EMA(50), EMA(200)
      - RSI(14)
      - Bollinger Bands(20, 2)
      - ATR(14)
    """

    def __init__(
        self,
        adx_period: int = 14,
        ema_fast: int = 50,
        ema_slow: int = 200,
        rsi_period: int = 14,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
    ):
        if ta is None:
            raise ImportError("pandas-ta nincs telepítve: pip install pandas-ta")

        self.adx_period = adx_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period

        # Minimális gyertya szám az összes indikátorhoz
        self.min_bars = max(ema_slow, adx_period, bb_period, rsi_period, atr_period) + 10

    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorSnapshot]:
        """
        Indikátorok kiszámítása és snapshot előállítása.

        :param df: OHLCV DataFrame (oszlopok: open, high, low, close, volume)
        :return: IndicatorSnapshot az utolsó zárt gyertyára, vagy None ha
                 nincs elegendő adat.
        """
        if df is None or len(df) < self.min_bars:
            logger.warning(
                "Nincs elegendő bar: %d (minimum: %d)",
                0 if df is None else len(df),
                self.min_bars,
            )
            return None

        # Drop the last (incomplete) candle to avoid repainting
        df = df.iloc[:-1].copy()

        # --- ADX ---
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=self.adx_period)
        adx_col = f"ADX_{self.adx_period}"
        adx_val = self._last(adx_df, adx_col) if adx_df is not None else 0.0

        # --- EMA ---
        ema_fast_s = ta.ema(df["close"], length=self.ema_fast)
        ema_slow_s = ta.ema(df["close"], length=self.ema_slow)
        ema_fast_val = self._last_series(ema_fast_s)
        ema_slow_val = self._last_series(ema_slow_s)

        # --- RSI ---
        rsi_s = ta.rsi(df["close"], length=self.rsi_period)
        rsi_val = self._last_series(rsi_s, idx=-1)
        rsi_prev_val = self._last_series(rsi_s, idx=-2)

        # --- Bollinger Bands ---
        bb_df = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
        bb_upper_col = f"BBU_{self.bb_period}_{float(self.bb_std)}"
        bb_lower_col = f"BBL_{self.bb_period}_{float(self.bb_std)}"
        bb_mid_col   = f"BBM_{self.bb_period}_{float(self.bb_std)}"
        bb_upper_val = self._last(bb_df, bb_upper_col) if bb_df is not None else 0.0
        bb_lower_val = self._last(bb_df, bb_lower_col) if bb_df is not None else 0.0
        bb_mid_val   = self._last(bb_df, bb_mid_col)   if bb_df is not None else 0.0

        # --- ATR ---
        atr_s = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)
        atr_val = self._last_series(atr_s)

        # --- Close ---
        try:
            close_val = float(df["close"].iloc[-1])
            close_prev_val = float(df["close"].iloc[-2])
        except IndexError:
            logger.warning("DataFrame too short to extract recent closes.")
            return None

        snapshot = IndicatorSnapshot(
            adx=adx_val,
            ema_50=ema_fast_val,
            ema_200=ema_slow_val,
            rsi=rsi_val,
            rsi_prev=rsi_prev_val,
            bb_upper=bb_upper_val,
            bb_lower=bb_lower_val,
            bb_mid=bb_mid_val,
            close=close_val,
            close_prev=close_prev_val,
            atr=atr_val,
        )

        logger.debug(
            "Snapshot | ADX=%.2f | EMA50=%.2f | EMA200=%.2f | RSI=%.2f | "
            "BB[%.2f / %.2f] | ATR=%.4f",
            snapshot.adx, snapshot.ema_50, snapshot.ema_200, snapshot.rsi,
            snapshot.bb_lower, snapshot.bb_upper, snapshot.atr,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Belső segédek
    # ------------------------------------------------------------------

    @staticmethod
    def _last_series(s: Optional[pd.Series], idx: int = -1) -> float:
        """Utolsó (vagy megadott indexű) nem-NaN érték egy Series-ből."""
        if s is None or s.empty:
            return 0.0
        val = s.iloc[idx]
        return float(val) if pd.notna(val) else 0.0

    @staticmethod
    def _last(df: Optional[pd.DataFrame], col: str, idx: int = -1) -> float:
        """Utolsó érték egy DataFrame oszlopából."""
        if df is None or col not in df.columns:
            return 0.0
        val = df[col].iloc[idx]
        return float(val) if pd.notna(val) else 0.0
