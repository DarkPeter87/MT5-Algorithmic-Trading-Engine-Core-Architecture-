"""
src/execution_engine.py
Megbízás végrehajtó motor – MT5 order küldés, magic number, slippage kezelés.
"""
import logging
from dataclasses import dataclass
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from .risk_manager import TradeParams

logger = logging.getLogger(__name__)

# Order kitöltési módok leképezése
_FILLING_MAP: dict[str, int] = {}


def _init_filling_map() -> None:
    if mt5 is None or _FILLING_MAP:
        return
    _FILLING_MAP["IOC"]    = mt5.ORDER_FILLING_IOC
    _FILLING_MAP["FOK"]    = mt5.ORDER_FILLING_FOK
    _FILLING_MAP["RETURN"] = mt5.ORDER_FILLING_RETURN


@dataclass
class ExecutionResult:
    """Order küldés eredménye."""
    success: bool
    order_ticket: Optional[int] = None
    message: str = ""
    retcode: Optional[int] = None


class ExecutionEngine:
    """
    MT5 megbízás végrehajtó modul.

    Kezel:
      - Market BUY / SELL megbízások küldése
      - Magic number kezelése
      - Slippage (deviation) konfigurálása
      - Pozíció zárása ticket alapján
      - Részletes naplózás minden order eseményre
    """

    def __init__(
        self,
        magic: int = 123456,
        deviation: int = 20,
        filling: str = "IOC",
        comment: str = "RegimeBot",
    ):
        """
        :param magic:    Expert azonosító (magic number)
        :param deviation: Maximális slippage pontban
        :param filling:  Order kitöltési mód: "IOC", "FOK", "RETURN"
        :param comment:  Order megjegyzés szövege
        """
        self.magic = magic
        self.deviation = deviation
        self.filling = filling
        self.comment = comment
        _init_filling_map()

    # ------------------------------------------------------------------
    # Nyitó megbízások
    # ------------------------------------------------------------------

    def buy(self, symbol: str, params: TradeParams) -> ExecutionResult:
        """Market BUY megbízás küldése."""
        return self._send_order(
            symbol=symbol,
            order_type=mt5.ORDER_TYPE_BUY if mt5 else 0,
            params=params,
        )

    def sell(self, symbol: str, params: TradeParams) -> ExecutionResult:
        """Market SELL megbízás küldése."""
        return self._send_order(
            symbol=symbol,
            order_type=mt5.ORDER_TYPE_SELL if mt5 else 1,
            params=params,
        )

    def _send_order(
        self,
        symbol: str,
        order_type: int,
        params: TradeParams,
    ) -> ExecutionResult:
        """Generikus market order küldés."""
        if mt5 is None:
            return ExecutionResult(False, message="MetaTrader5 csomag nincs telepítve.")

        # Aktuális ár lekérése (egyszer, null-check-kel)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            msg = f"Tick adat nem érhető el ({symbol}) – piac zárva?"
            logger.error(msg)
            return ExecutionResult(False, message=msg)

        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        filling_mode = _FILLING_MAP.get(self.filling, mt5.ORDER_FILLING_IOC)

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       params.lot_size,
            "type":         order_type,
            "price":        price,
            "sl":           params.sl_price,
            "tp":           params.tp_price,
            "deviation":    self.deviation,
            "magic":        self.magic,
            "comment":      self.comment,
            "type_filling": filling_mode,
        }

        direction = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
        logger.info(
            "Order kísérlet | %s %s | Lot=%.2f | Ár=%.2f | SL=%.2f | TP=%.2f",
            direction, symbol, params.lot_size, price, params.sl_price, params.tp_price,
        )

        result = mt5.order_send(request)

        # --- Hibaellenőrzés ---
        if result is None:
            err = mt5.last_error()
            msg = f"order_send None válasz – MT5 hiba: {err}"
            logger.error(msg)
            return ExecutionResult(False, message=msg)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            msg = (
                f"Order elutasítva | retcode={result.retcode} | "
                f"comment='{result.comment}'"
            )
            logger.error(msg)
            return ExecutionResult(
                False,
                retcode=result.retcode,
                message=msg,
            )

        logger.info(
            "✅ Order sikeres | Ticket=%d | %s %.2f lot @ %.2f | SL=%.2f | TP=%.2f",
            result.order, direction, params.lot_size,
            price, params.sl_price, params.tp_price,
        )
        return ExecutionResult(
            True,
            order_ticket=result.order,
            retcode=result.retcode,
            message="OK",
        )

    # ------------------------------------------------------------------
    # Pozíció zárás
    # ------------------------------------------------------------------

    def close_position(self, symbol: str, ticket: int) -> ExecutionResult:
        """
        Nyitott pozíció zárása ticket alapján.
        A zárási ár automatikusan az aktuális piaci ár lesz.
        """
        if mt5 is None:
            return ExecutionResult(False, message="MetaTrader5 nincs telepítve.")

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            msg = f"Pozíció #{ticket} nem található vagy már zárva."
            logger.warning(msg)
            return ExecutionResult(False, message=msg)

        pos = positions[0]
        close_type = (
            mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return ExecutionResult(False, message="Tick adat nem elérhető záráshoz.")

        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        filling_mode = _FILLING_MAP.get(self.filling, mt5.ORDER_FILLING_IOC)

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       pos.volume,
            "type":         close_type,
            "position":     ticket,
            "price":        price,
            "deviation":    self.deviation,
            "magic":        self.magic,
            "comment":      f"CLOSE #{ticket}",
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = getattr(result, "retcode", None)
            comment = getattr(result, "comment", "")
            msg = f"Zárás sikertelen | ticket={ticket} | retcode={retcode} | {comment}"
            logger.error(msg)
            return ExecutionResult(False, retcode=retcode, message=msg)

        logger.info("✅ Pozíció zárva | Ticket=%d | Ár=%.2f", ticket, price)
        return ExecutionResult(True, order_ticket=ticket, message="OK")

    # ------------------------------------------------------------------
    # Segédek
    # ------------------------------------------------------------------

    def get_open_positions(self, symbol: str) -> list:
        """Nyitott pozíciók listája (magic alapján szűrve)."""
        if mt5 is None:
            return []
        positions = mt5.positions_get(symbol=symbol) or []
        return [p for p in positions if p.magic == self.magic]
