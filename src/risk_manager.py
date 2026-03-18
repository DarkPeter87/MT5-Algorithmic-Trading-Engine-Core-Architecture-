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
      1. Lot méret számítása: account_balance × risk_pct / (SL_pips × pip_value)
      2. Dinamikus SL: 1.5 × ATR
      3. Dinamikus TP: 2.5 × ATR (kedvező Risk:Reward = ~1:1.67)
      4. Lot limitek betartása (min_lot / max_lot)

    Megjegyzés: Ez egy általánosított implementáció. Éles kereskedés előtt
    a pip_value-t szimbólum- és számlatipus-specifikusan kell beállítani.
    """

    def __init__(
        self,
        risk_pct: float = 0.015,        # Számlaegyenleg %-a, amit kockáztatunk (1.5%)
        atr_sl_multiplier: float = 1.5, # SL = ATR × szorzó
        atr_tp_multiplier: float = 3.0, # (NEM HASZNÁLJUK = TRAILING STOP TÖRLÉS)
        fallback_atr_variance: float = 0.002,
        min_lot: float = 0.01,
        max_lot: float = 10.0,
        lot_step: float = 0.01,
    ):
        if not 0 < risk_pct <= 0.1:
            raise ValueError(f"risk_pct {risk_pct} kívül esik a [0, 10%] tartományon!")

        self.risk_pct = risk_pct
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.fallback_atr_variance = fallback_atr_variance
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step

    def calculate(
        self,
        balance: float,
        current_price: float,
        atr: float,
        is_buy: bool,
        tick_value: float,
        tick_size: float,
    ) -> TradeParams:
        """
        ATR alapú kockázatszámítás keresztárfolyamokhoz is.

        :param balance:       Számla egyenlege (Pl. EUR)
        :param current_price: Aktuális ask (BUY) vagy bid (SELL) ár
        :param atr:           ATR értéke (ugyanabban az egységben, mint az ár)
        :param is_buy:        True = BUY, False = SELL
        :param tick_value:    1 tick (point) elmozdulás értéke 1 Lot-ra vetítve a számla devizájában
        :param tick_size:     A szimbólum tick mérete (point)
        :return:              TradeParams
        """
        if atr <= 0:
            logger.warning("ATR értéke 0 vagy negatív, fallback SL/TP-t alkalmazunk.")
            atr = current_price * self.fallback_atr_variance

        # --- SL és TP távolság árban ---
        sl_distance = atr * self.atr_sl_multiplier
        # TP távolság nem használt, mivel dinamikus Trailing Stop él.
        # TP eltávolítva: Trailing Stop logika veszi át az uralmat.
        tp_price = 0.0

        if is_buy:
            sl_price = current_price - sl_distance
        else:
            sl_price = current_price + sl_distance

        # SL távolság pipban (tick-ben) a lot méret számításhoz
        sl_ticks = sl_distance / tick_size if tick_size > 0 else sl_distance
        tp_ticks = 0.0 # TP eltávolítva: Trailing Stop logika veszi át az uralmat.

        # --- Lot méret számítás ---
        # Kockáztatott összeg
        risk_amount = balance * self.risk_pct
        
        # Veszteség 1 loton a számla devizájában = (sl_távolság_tickben) * (1_tick_értéke_1_lotra)
        loss_per_lot = sl_ticks * tick_value

        if loss_per_lot <= 0:
            logger.error("loss_per_lot = 0, minimum lot-ot alkalmazunk.")
            raw_lot = self.min_lot
        else:
            raw_lot = risk_amount / loss_per_lot

        # Lot kerekítés a lépésközhöz + határok betartása
        lot = self._round_lot(raw_lot)

        logger.info(
            "RiskManager | Balance=%.2f | ATR=%.4f | SL=%.2f pont | TP=%.2f pont | "
            "Kockázat=%.2f Számladevizában | Lot=%.2f",
            balance, atr, sl_ticks, tp_ticks, risk_amount, lot,
        )

        return TradeParams(
            lot_size=lot,
            sl_price=round(sl_price, 5),
            tp_price=round(tp_price, 5),
            sl_ticks=round(sl_ticks, 2),
            tp_ticks=round(tp_ticks, 2),
        )

    def _round_lot(self, raw_lot: float) -> float:
        """Lot kerekítése a megengedett lépésközre, min/max határok között."""
        # Lépésköz szerinti kerekítés
        steps = round(raw_lot / self.lot_step)
        lot = steps * self.lot_step
        lot = max(self.min_lot, min(self.max_lot, lot))
        return round(lot, 2)
