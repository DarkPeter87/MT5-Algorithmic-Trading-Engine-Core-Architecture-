"""
src/data_feed.py
Kapcsolat & Adat modul – MT5 inizializáció és OHLCV lekérés.
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger(__name__)


class DataFeed:
    """
    MT5 terminál kapcsolat + OHLCV adatlekérés.

    Felelős:
      - mt5.initialize() / shutdown()
      - Szimbólum elérhetővé tétele a terminálban
      - Bars (OHLCV) lekérése pandas DataFrame-ként
    """

    # MT5 timeframe konstansok leképezése percekre
    TIMEFRAME_MAP: dict[int, int] = {}

    def __init__(self, symbol: str, timeframe_minutes: int = 15, bars: int = 500):
        """
        :param symbol: Pl. "XAUUSD"
        :param timeframe_minutes: 1, 5, 15, 30, 60, 240, 1440
        :param bars: Lekérendő gyertyák száma (elegendő az indikátorokhoz)
        """
        self.symbol = symbol
        self.timeframe_minutes = timeframe_minutes
        self.bars = bars
        self._connected = False

    # ------------------------------------------------------------------
    # Kapcsolat
    # ------------------------------------------------------------------

    def connect(
        self,
        path: str = "",
        login: int = 0,
        password: str = "",
        server: str = "",
    ) -> bool:
        """MT5 terminál inicializálása. False → az alkalmazás ne induljon el."""
        if mt5 is None:
            logger.critical("MetaTrader5 csomag nincs telepítve (pip install MetaTrader5).")
            return False

        # Feltölti a timeframe térképet (mt5 konstansok futáskor elérhetők)
        self._init_timeframe_map()

        params: dict = {}
        if path:
            params["path"] = path
        if login:
            params["login"] = login
        if password:
            params["password"] = password
        if server:
            params["server"] = server

        ok = mt5.initialize(**params) if params else mt5.initialize()
        if not ok:
            logger.error("MT5 initialize hiba: %s", mt5.last_error())
            return False

        # Szimbólum elérhetővé tétele
        if not mt5.symbol_select(self.symbol, True):
            logger.error("Szimbólum '%s' nem érhető el a terminálban.", self.symbol)
            mt5.shutdown()
            return False

        self._connected = True
        info = mt5.terminal_info()
        logger.info("MT5 kapcsolódva | Terminal: %s | Build: %s",
                    getattr(info, "name", "?"), getattr(info, "build", "?"))
        return True

    def disconnect(self) -> None:
        """Terminál kapcsolat bontása."""
        if mt5 and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 kapcsolat bontva.")

    @property
    def is_connected(self) -> bool:
        """Valódi heartbeat – nem csak a flag."""
        if not self._connected or mt5 is None:
            return False
        return mt5.terminal_info() is not None

    # ------------------------------------------------------------------
    # Adatok
    # ------------------------------------------------------------------

    def fetch_ohlcv(self) -> Optional[pd.DataFrame]:
        """
        Legfrissebb N gyertyát tölt le a beállított szimbólumra és időkeretre.

        :return: DataFrame oszlopokkal: time, open, high, low, close, volume
                 Utolsó sor = legfrissebb zárt gyertya.
                 None ha hiba vagy nincs kapcsolat.
        """
        if not self.is_connected:
            logger.warning("fetch_ohlcv: nincs MT5 kapcsolat.")
            return None

        tf = self._get_mt5_timeframe()
        if tf is None:
            logger.error("Nem támogatott timeframe: %d perc", self.timeframe_minutes)
            return None

        rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, self.bars)
        if rates is None or len(rates) == 0:
            logger.error("Nincs adat: %s | hiba: %s", self.symbol, mt5.last_error())
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        df = df.reset_index(drop=True)

        logger.debug("OHLCV lekérve: %d sor | utolsó gyertya: %s", len(df), df["time"].iloc[-1])
        return df

    def get_current_tick(self) -> Optional[tuple[float, float]]:
        """(bid, ask) tuple vagy None."""
        if not self.is_connected or mt5 is None:
            return None
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None
        return (tick.bid, tick.ask)

    def fetch_last_closed_bar_time(self) -> Optional[pd.Timestamp]:
        """
        Legfrissebb lezárt gyertya idejének lekérése.
        Csak 1 darab adatot tölt le (index 1 = utolsó zárt).
        """
        if not self.is_connected:
            return None

        tf = self._get_mt5_timeframe()
        if tf is None:
            return None

        rates = mt5.copy_rates_from_pos(self.symbol, tf, 1, 1)
        if rates is None or len(rates) == 0:
            return None

        return pd.to_datetime(rates[0]["time"], unit="s")

    def get_account_balance(self) -> float:
        """A kereskedési számla egyenlege vagy 0.0."""
        if not self.is_connected or mt5 is None:
            return 0.0
        info = mt5.account_info()
        return getattr(info, "balance", 0.0) if info else 0.0

    # ------------------------------------------------------------------
    # Belső segédek
    # ------------------------------------------------------------------

    def _init_timeframe_map(self) -> None:
        if mt5 is None or self.TIMEFRAME_MAP:
            return
        DataFeed.TIMEFRAME_MAP = {
            1:    mt5.TIMEFRAME_M1,
            5:    mt5.TIMEFRAME_M5,
            15:   mt5.TIMEFRAME_M15,
            30:   mt5.TIMEFRAME_M30,
            60:   mt5.TIMEFRAME_H1,
            240:  mt5.TIMEFRAME_H4,
            1440: mt5.TIMEFRAME_D1,
        }

    def _get_mt5_timeframe(self) -> Optional[int]:
        self._init_timeframe_map()
        return self.TIMEFRAME_MAP.get(self.timeframe_minutes)
