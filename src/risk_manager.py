"""
src/risk_manager.py
Kockázatkezelési modul – ATR-alapú lot méret, dinamikus SL/TP számítás.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# XAUUSD minimális tick (point) mérete (naplózáshoz megtartható referenciaként)
XAUUSD_PIP = 0.1


@dataclass
class TradeParams:
    """Egy megbízáshoz szükséges kockázati paraméterek."""
    lot_size: float       # Lot méret
    sl_price: float       # Stop Loss ár
    tp_price: float       # Take Profit ár
    sl_ticks: float       # SL távolság tickben/pontban (naplózáshoz)
    tp_ticks: float       # TP távolság tickben/pontban (naplózáshoz)


class RiskManager:
    """
    Kockázatkezelő modul.

    Feladatai:
      1. Dinamikus SL: 1.5 × ATR
      2. Dinamikus TP: Trailing stop által kezelve (0.0)
      3. Pontos MT5 margin/risk kalkuláció tick_value és tick_size alapján
    """

    def __init__(
        self,
        risk_pct: float = 0.015,        # Számlaegyenleg %-a, amit kockáztatunk (1.5%)
        atr_sl_multiplier: float = 1.5, # SL = ATR × szorzó
        fallback_atr_variance: float = 0.002,
    ):
        if not 0 < risk_pct <= 0.1:
            raise ValueError(f"risk_pct {risk_pct} kívül esik a [0, 10%] tartományon!")

        self.risk_pct = risk_pct
        self.atr_sl_multiplier = atr_sl_multiplier
        self.fallback_atr_variance = fallback_atr_variance

    def calculate(
        self,
        balance: float,
        current_price: float,
        atr: float,
        is_buy: bool,
        tick_value: float,
        tick_size: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> TradeParams:
        """
        ATR alapú kockázatszámítás keresztárfolyamokhoz is.

        :param balance:       Számla egyenlege (Pl. EUR)
        :param current_price: Aktuális ask (BUY) vagy bid (SELL) ár
        :param atr:           ATR értéke (ugyanabban az egységben, mint az ár)
        :param is_buy:        True = BUY, False = SELL
        :param tick_value:    1 tick (point) elmozdulás értéke 1 Lot-ra vetítve a számla devizájában
        :param tick_size:     A szimbólum tick mérete (point)
        :param volume_min:    Minimális lot méret
        :param volume_max:    Maximális lot méret
        :param volume_step:   Lot lépésköz
        :return:              TradeParams
        """
        if atr <= 0:
            logger.warning("ATR értéke 0 vagy negatív, fallback SL/TP-t alkalmazunk.")
            atr = current_price * self.fallback_atr_variance

        # --- SL távolság árban ---
        sl_distance = atr * self.atr_sl_multiplier

        if is_buy:
            sl_price = round(current_price - sl_distance, 5)
        else:
            sl_price = round(current_price + sl_distance, 5)

        # MT5 pontos logika szerinti lot számítás a megadott formulával
        ticks_to_sl = abs(current_price - sl_price) / tick_size if tick_size > 0 else 0
        risk_amount = balance * self.risk_pct
        
        if ticks_to_sl > 0 and tick_value > 0:
            raw_lot = risk_amount / (ticks_to_sl * tick_value)
        else:
            logger.error("Érvénytelen tick adatok, minimum lot-ot alkalmazunk.")
            raw_lot = volume_min

        # Lot kerekítés a lépésközhöz + határok betartása
        steps = round(raw_lot / volume_step)
        lot = steps * volume_step
        lot = max(volume_min, min(volume_max, lot))
        lot = round(lot, 2)

        logger.info(
            "RiskManager | Balance=%.2f | ATR=%.4f | Várható Veszteség=%.2f | "
            "Kiszámolt Lot=%.2f",
            balance, atr, risk_amount, lot,
        )

        return TradeParams(
            lot_size=lot,
            sl_price=sl_price,
            tp_price=0.0,
            sl_ticks=round(ticks_to_sl, 2),
            tp_ticks=0.0,
        )
