"""
src/risk_manager.py
Kockázatkezelési modul – ATR-alapú lot méret, dinamikus SL/TP számítás.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Arany (XAUUSD) pip mérete
XAUUSD_PIP = 0.1


@dataclass
class TradeParams:
    """Egy megbízáshoz szükséges kockázati paraméterek."""
    lot_size: float       # Lot méret
    sl_price: float       # Stop Loss ár
    tp_price: float       # Take Profit ár
    sl_pips: float        # SL távolság pipban (naplózáshoz)
    tp_pips: float        # TP távolság pipban (naplózáshoz)


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
        risk_pct: float = 0.01,        # Számlaegyenleg %-a, amit kockáztatunk (1%)
        atr_sl_multiplier: float = 1.5, # SL = ATR × szorzó
        atr_tp_multiplier: float = 2.5, # TP = ATR × szorzó
        pip_value: float = 10.0,        # USD értéke 1 pipnak, 1 standard lot esetén (XAUUSD = $10)
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
        self.pip_value = pip_value
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
        pip_size: float = XAUUSD_PIP,
    ) -> TradeParams:
        """
        ATR alapú kockázatszámítás.

        :param balance:       Számla egyenlege (USD)
        :param current_price: Aktuális ask (BUY) vagy bid (SELL) ár
        :param atr:           ATR értéke (ugyanabban az egységben, mint az ár)
        :param is_buy:        True = BUY, False = SELL
        :param pip_size:      1 pip értéke az adott szimbólumon (XAUUSD = 0.1)
        :return:              TradeParams
        """
        if atr <= 0:
            logger.warning("ATR értéke 0 vagy negatív, fallback SL/TP-t alkalmazunk.")
            atr = current_price * self.fallback_atr_variance

        # --- SL és TP távolság árban ---
        sl_distance = atr * self.atr_sl_multiplier
        tp_distance = atr * self.atr_tp_multiplier

        if is_buy:
            sl_price = current_price - sl_distance
            tp_price = current_price + tp_distance
        else:
            sl_price = current_price + sl_distance
            tp_price = current_price - tp_distance

        # SL távolság pipban (lot méret számításhoz)
        sl_pips = sl_distance / pip_size if pip_size > 0 else sl_distance
        tp_pips = tp_distance / pip_size if pip_size > 0 else tp_distance

        # --- Lot méret számítás ---
        # Kockáztatott összeg = balance × risk_pct
        # Veszteség 1 loton = sl_pips × pip_value
        risk_amount = balance * self.risk_pct
        loss_per_lot = sl_pips * self.pip_value

        if loss_per_lot <= 0:
            logger.error("loss_per_lot = 0, minimum lot-ot alkalmazunk.")
            raw_lot = self.min_lot
        else:
            raw_lot = risk_amount / loss_per_lot

        # Lot kerekítés a lépésközhöz + határok betartása
        lot = self._round_lot(raw_lot)

        logger.info(
            "RiskManager | Balance=%.2f | ATR=%.4f | SL=%.2f pip | TP=%.2f pip | "
            "Kockázat=%.2f USD | Lot=%.2f",
            balance, atr, sl_pips, tp_pips, risk_amount, lot,
        )

        return TradeParams(
            lot_size=lot,
            sl_price=round(sl_price, 2),
            tp_price=round(tp_price, 2),
            sl_pips=round(sl_pips, 1),
            tp_pips=round(tp_pips, 1),
        )

    def _round_lot(self, raw_lot: float) -> float:
        """Lot kerekítése a megengedett lépésközre, min/max határok között."""
        # Lépésköz szerinti kerekítés
        steps = round(raw_lot / self.lot_step)
        lot = steps * self.lot_step
        lot = max(self.min_lot, min(self.max_lot, lot))
        return round(lot, 2)
