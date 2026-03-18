"""
MetaTrader 5 kapcsolat és kereskedési motor.
Arany (XAUUSD) és más szimbólumok támogatása.
"""
import logging
from datetime import datetime  # PERF-3: fájl tetején, nem hot-loop-ban
from typing import Optional, Any
from dataclasses import dataclass

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from .config import BotConfig, RiskConfig, SymbolConfig

logger = logging.getLogger(__name__)

# SEC-4: order kitöltési mód leképezés string → MT5 konstans
_FILLING_MAP: dict[str, int] = {}  # futáskor töltjük fel, ha az mt5 csomag elérhető


def _init_filling_map() -> None:
    """MT5 kitöltési módok regisztrációja (csak ha az mt5 csomag telepített)."""
    if mt5 is None:
        return
    _FILLING_MAP["IOC"] = mt5.ORDER_FILLING_IOC
    _FILLING_MAP["FOK"] = mt5.ORDER_FILLING_FOK
    _FILLING_MAP["RETURN"] = mt5.ORDER_FILLING_RETURN


@dataclass
class TradeResult:
    success: bool
    order_ticket: Optional[int] = None
    message: str = ""


def _pip_size(symbol: str, digits: int) -> float:
    """Pip méret a szimbólum és digits alapján (aranynál általában 0.1 vagy 1.0)."""
    if "XAU" in symbol.upper() or "GOLD" in symbol.upper():
        return 0.1  # arany: 1 pip = 0.1
    return 10 ** (-digits) if digits else 0.01


class MT5Client:
    """MT5 API burkoló: kapcsolat, árak, order küldés."""

    def __init__(self, config: BotConfig):
        self.config = config
        self._connected = False
        _init_filling_map()

    def connect(self, path: str = "", login: int = 0, password: str = "", server: str = "") -> bool:
        """Kapcsolódás az MT5 terminálhoz."""
        if mt5 is None:
            logger.error("MetaTrader5 csomag nincs telepítve. Pip install MetaTrader5")
            return False
        init_params: dict[str, Any] = {}
        if path:
            init_params["path"] = path
        if login:
            init_params["login"] = login
        if password:
            init_params["password"] = password
        if server:
            init_params["server"] = server
        ok = mt5.initialize(**init_params) if init_params else mt5.initialize()
        if not ok:
            logger.error("MT5 initialize sikertelen: %s", mt5.last_error())
            return False
        self._connected = True
        logger.info("MT5 kapcsolódva: %s", mt5.terminal_info())
        return True

    def disconnect(self) -> None:
        if mt5 and self._connected:
            mt5.shutdown()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        """QUAL-1: Valódi terminál heartbeat – nem csak a flag-et ellenőrzi."""
        if not self._connected or mt5 is None:
            return False
        info = mt5.terminal_info()
        if info is None:
            # Terminál megszűnt → flag visszaállítása
            self._connected = False
            return False
        return True

    def symbol_info(self) -> Optional[Any]:
        sym = self.config.symbol.symbol
        if not mt5:
            return None
        info = mt5.symbol_info(sym)
        if info is None:
            mt5.symbol_info_select(sym)
            info = mt5.symbol_info(sym)
        return info

    def current_price(self) -> Optional[tuple[float, float, float]]:
        """Bid, Ask, Last tuple vagy None (piaczáráskor, hibás szimbólumnál)."""
        if not mt5 or not self.is_connected:
            return None
        tick = mt5.symbol_info_tick(self.config.symbol.symbol)
        if tick is None:
            return None
        return (tick.bid, tick.ask, tick.last)

    def spread_pips(self) -> float:
        """
        Jelenlegi spread pipban.
        ⚠️ QA FIX: Ha nincs tick adat (piaczárva / nincs kapcsolat), float('inf')-t ad
        vissza, így a spread-limit ellenőrzés biztonságosan BLOKKOLJA az ordert,
        nem engedi át fals 0.0-val.
        """
        prices = self.current_price()
        if prices is None:
            return float("inf")  # SEC-2 / QA: fals 0.0 helyett inf → blokkolja a megbízást
        bid, ask = prices[0], prices[1]
        pip = _pip_size(self.config.symbol.symbol, self.config.symbol.digits)
        if pip <= 0:
            return float("inf")
        return (ask - bid) / pip

    def buy(
        self,
        lots: Optional[float] = None,
        sl_pips: Optional[float] = None,
        tp_pips: Optional[float] = None,
        comment: str = "",
    ) -> TradeResult:
        """Vételi order küldése."""
        return self._order(mt5.ORDER_TYPE_BUY if mt5 else 0, lots, sl_pips, tp_pips, comment)

    def sell(
        self,
        lots: Optional[float] = None,
        sl_pips: Optional[float] = None,
        tp_pips: Optional[float] = None,
        comment: str = "",
    ) -> TradeResult:
        """Eladási order küldése."""
        return self._order(mt5.ORDER_TYPE_SELL if mt5 else 1, lots, sl_pips, tp_pips, comment)

    def _order(
        self,
        order_type: int,
        lots: Optional[float],
        sl_pips: Optional[float],
        tp_pips: Optional[float],
        comment: str,
    ) -> TradeResult:
        if not mt5 or not self.is_connected:
            return TradeResult(False, message="Nincs MT5 kapcsolat")

        sym = self.config.symbol.symbol
        risk: RiskConfig = self.config.risk

        # SEC-2 / PERF-1: tick egyszeri lekérés – null-ellenőrzéssel
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            logger.warning("Tick adat nem elérhető a(z) %s szimbólumra. Piac zárva?", sym)
            return TradeResult(False, message="Tick adat nem elérhető (piac zárva?)")

        # PERF-1: egyetlen tick példányból olvasunk
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        lot = lots if lots is not None else risk.lot_size
        lot = min(lot, risk.max_lots)
        pip = _pip_size(sym, self.config.symbol.digits)

        sl = sl_pips if sl_pips is not None else risk.stop_loss_pips
        tp = tp_pips if tp_pips is not None else risk.take_profit_pips

        sl_price = price - pip * sl if order_type == mt5.ORDER_TYPE_BUY else price + pip * sl
        tp_price = price + pip * tp if order_type == mt5.ORDER_TYPE_BUY else price - pip * tp

        if sl <= 0:
            sl_price = 0.0
        if tp <= 0:
            tp_price = 0.0

        # SEC-4: type_filling a konfigból (IOC / FOK / RETURN)
        filling_mode = _FILLING_MAP.get(risk.order_filling, mt5.ORDER_FILLING_IOC)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": round(lot, 2),
            "type": order_type,
            "price": price,
            "sl": sl_price if sl > 0 else 0.0,
            "tp": tp_price if tp > 0 else 0.0,
            "deviation": risk.max_slippage_points,   # SEC-3: konfigurálható slippage
            "magic": self.config.strategy.magic_number,
            "comment": comment or self.config.strategy.comment,
            "type_filling": filling_mode,             # SEC-4: explicit fill típus
        }

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            return TradeResult(False, message=str(err))
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return TradeResult(False, message=f"retcode={result.retcode} {result.comment}")
        return TradeResult(True, order_ticket=result.order, message="OK")

    def positions_open(self, symbol: Optional[str] = None) -> list:
        """Nyitott pozíciók listája."""
        if not mt5:
            return []
        sym = symbol or self.config.symbol.symbol
        return list(mt5.positions_get(symbol=sym) or [])

    def daily_trades_count(self) -> int:
        """
        Ma nyitott ügyletek számlálása (magic alapján).
        PERF-2: szimbólum szintű szűrés az API-ban – nem az összes pozíciót töltjük le.
        """
        if not mt5:
            return 0
        today = datetime.now().date()
        count = 0
        # PERF-2: szimbólum-szintű szűrés az MT5 API-ban
        sym = self.config.symbol.symbol
        for pos in mt5.positions_get(symbol=sym) or []:
            if pos.magic != self.config.strategy.magic_number:
                continue
            if hasattr(pos, "time") and pos.time:
                t = datetime.fromtimestamp(pos.time).date()
                if t == today:
                    count += 1
        return count
