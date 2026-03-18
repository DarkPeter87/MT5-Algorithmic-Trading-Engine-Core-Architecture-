"""
main.py – Regime-Switching MT5 Trading Bot
==========================================
Futtatás: python main.py

Architektúra:
  DataFeed         → OHLCV adatok lekérése MT5-ből
  SignalGenerator  → ADX / EMA / RSI / BB / ATR kiszámítása
  RegimeStrategy   → Regime detektálás + szignál generálás
  RiskManager      → Lot méret + dinamikus SL/TP (ATR alapon)
  ExecutionEngine  → MT5 order küldés és kezelés

Konfiguráció:
  Minden paramétert a BotConfig dataclass-ban állíts be (lejjebb).
  Éles kereskedésre kapcsoláshoz: DRY_RUN = False (lásd CONFIG).
"""
import logging
import time
from dataclasses import dataclass, field

# ─── Projekt modulok ────────────────────────────────────────────────────────
from src.data_feed import DataFeed
from src.signal_generator import SignalGenerator
from src.regime_strategy import RegimeStrategy, Signal
from src.risk_manager import RiskManager, XAUUSD_PIP
from src.execution_engine import ExecutionEngine

# ─── Naplózás ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("RegimeBot")


# ============================================================================
# ⚙️  KONFIGURÁCIÓ – itt módosítsd a bot beállításait
# ============================================================================
@dataclass
class BotConfig:
    # MT5 kapcsolat
    symbol:             str   = "XAUEUR"
    timeframe_minutes:  int   = 15       # M15 alapértelmezett
    bars:               int   = 500      # Letöltött gyertyák száma

    # MT5 bejelentkezés (üres = már bejelentkezett terminál)
    mt5_path:           str   = ""
    mt5_login:          int   = 0
    mt5_password:       str   = ""
    mt5_server:         str   = ""

    # Stratégia paraméterek
    adx_threshold:      float = 25.0
    rsi_overbought:     float = 70.0
    rsi_oversold:       float = 30.0

    # Indikátor periódusok
    adx_period:         int   = 14
    ema_fast:           int   = 50
    ema_slow:           int   = 200
    rsi_period:         int   = 14
    bb_period:          int   = 20
    bb_std:             float = 2.0
    atr_period:         int   = 14

    # Kockázatkezelés
    risk_pct:           float = 0.01    # Számlaegyenleg 1%-a / trade
    atr_sl_multi:       float = 1.5     # SL = ATR × 1.5
    atr_tp_multi:       float = 3.0     # TP = ATR × 3.0
    min_lot:            float = 0.01
    max_lot:            float = 1.0
    lot_step:           float = 0.01

    # Végrehajtás
    magic:              int   = 777001
    deviation:          int   = 20      # Max slippage (pontban)
    filling:            str   = "IOC"
    comment:            str   = "RegimeBot"

    # Loop vezérlés
    poll_interval_sec:  int   = 60      # Másodpercenként ellenőrzi az új gyertyát
    max_open_positions: int   = 1       # Egyszerre max 1 nyitott pozíció

    # Biztonság – DRY_RUN = True → nem küld valódi ordert, csak naplóz
    dry_run:            bool  = False


# ============================================================================
# Fő Bot osztály
# ============================================================================
class RegimeBot:
    """
    Regime-Switching trading bot fő vezérlő osztálya.
    Összefogja az összes modult és futtatja az event loop-ot.
    """

    def __init__(self, config: BotConfig):
        self.cfg = config

        # Modulok példányosítása
        self.feed = DataFeed(
            symbol=config.symbol,
            timeframe_minutes=config.timeframe_minutes,
            bars=config.bars,
        )
        self.signals = SignalGenerator(
            adx_period=config.adx_period,
            ema_fast=config.ema_fast,
            ema_slow=config.ema_slow,
            rsi_period=config.rsi_period,
            bb_period=config.bb_period,
            bb_std=config.bb_std,
            atr_period=config.atr_period,
        )
        self.strategy = RegimeStrategy(
            adx_threshold=config.adx_threshold,
            rsi_overbought=config.rsi_overbought,
            rsi_oversold=config.rsi_oversold,
        )
        self.risk = RiskManager(
            risk_pct=config.risk_pct,
            atr_sl_multiplier=config.atr_sl_multi,
            atr_tp_multiplier=config.atr_tp_multi,
            min_lot=config.min_lot,
            max_lot=config.max_lot,
            lot_step=config.lot_step,
        )
        self.executor = ExecutionEngine(
            magic=config.magic,
            deviation=config.deviation,
            filling=config.filling,
            comment=config.comment,
        )

    # ------------------------------------------------------------------
    # Bot életciklus
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Kapcsolódás MT5-höz és loop indítása."""
        logger.info("=" * 60)
        logger.info("RegimeBot indul | Szimbólum: %s | TF: M%d | DRY_RUN: %s",
                    self.cfg.symbol, self.cfg.timeframe_minutes, self.cfg.dry_run)
        logger.info("=" * 60)

        if not self.feed.connect(
            path=self.cfg.mt5_path,
            login=self.cfg.mt5_login,
            password=self.cfg.mt5_password,
            server=self.cfg.mt5_server,
        ):
            logger.critical("MT5 kapcsolódás sikertelen – bot leáll.")
            return

        try:
            self._run_loop()
        except KeyboardInterrupt:
            logger.info("Bot leállítva (Ctrl+C).")
        finally:
            self.feed.disconnect()

    def _run_loop(self) -> None:
        """
        Fő eseményhurok – minden tick_intervalban fut:
          1. OHLCV lekérés
          2. Indikátor számítás
          3. Stratégia értékelés
          4. Kockázat számítás
          5. Order küldés (ha van szignál és szabad pozíció)
        """
        last_bar_time = None

        while True:
            # ── Kapcsolat ellenőrzés ──────────────────────────────────────
            if not self.feed.is_connected:
                logger.error("MT5 kapcsolat megszakadt. Újracsatlakozás megkísérlése...")
                if self.feed.connect(
                    path=self.cfg.mt5_path,
                    login=self.cfg.mt5_login,
                    password=self.cfg.mt5_password,
                    server=self.cfg.mt5_server,
                ):
                    logger.info("Sikeres újracsatlakozás!")
                else:
                    logger.error("Újracsatlakozás sikertelen. Várunk %ds-t...", self.cfg.poll_interval_sec)
                    time.sleep(self.cfg.poll_interval_sec)
                continue

            # ── Új gyertya detektálás (PERF-1: Csak 1 gyertya lekérése) ──
            current_bar_time = self.feed.fetch_last_closed_bar_time()
            if current_bar_time is None:
                logger.warning("Nem sikerült az utolsó gyertyát lekérni. Újrapróbálás...")
                time.sleep(self.cfg.poll_interval_sec)
                continue

            if current_bar_time == last_bar_time:
                # Nem zárult még új gyertya → várakozás
                time.sleep(self.cfg.poll_interval_sec)
                continue

            # ── OHLCV lekérés (Csak ha új gyertya van) ───────────────────
            df = self.feed.fetch_ohlcv()
            if df is None:
                logger.warning("Nem sikerült OHLCV adatot lekérni. Újrapróbálás...")
                time.sleep(self.cfg.poll_interval_sec)
                continue

            last_bar_time = current_bar_time
            logger.info("── Új gyertya: %s ──────────────────────────────────",
                        current_bar_time)

            # ── Indikátor számítás ───────────────────────────────────────
            snapshot = self.signals.calculate(df)
            if snapshot is None:
                logger.warning("Indikátor számítás sikertelen (nincs elegendő adat).")
                continue

            # ── Stratégia értékelés ──────────────────────────────────────
            decision = self.strategy.evaluate(snapshot)

            if not decision.is_actionable():
                logger.info("Nincs szignál – várakozás a következő gyertyára.")
                continue

            # ── Pozíció limit ellenőrzés ─────────────────────────────────
            open_positions = self.executor.get_open_positions(self.cfg.symbol)
            if len(open_positions) >= self.cfg.max_open_positions:
                logger.info(
                    "Max pozíció limit elérve (%d) – új order kihagyva.",
                    self.cfg.max_open_positions,
                )
                continue

            # ── Kockázat számítás ────────────────────────────────────────
            balance = self.feed.get_account_balance()
            tick = self.feed.get_current_tick()
            if tick is None:
                logger.error("Tick adat nem elérhető – order kihagyva.")
                continue

            bid, ask = tick
            is_buy = decision.signal == Signal.BUY
            current_price = ask if is_buy else bid

            trade_params = self.risk.calculate(
                balance=balance,
                current_price=current_price,
                atr=snapshot.atr,
                is_buy=is_buy,
                pip_size=XAUUSD_PIP,
            )

            # ── Order küldés (vagy DRY_RUN log) ─────────────────────────
            self._execute(decision.signal, trade_params)

    def _execute(self, signal: Signal, params) -> None:
        """Order küldés vagy DRY_RUN naplózás."""
        direction = signal.value
        if self.cfg.dry_run:
            logger.info(
                "🚧 DRY_RUN | %s | Lot=%.2f | SL=%.2f | TP=%.2f",
                direction, params.lot_size, params.sl_price, params.tp_price,
            )
            return

        if signal == Signal.BUY:
            result = self.executor.buy(self.cfg.symbol, params)
        else:
            result = self.executor.sell(self.cfg.symbol, params)

        if result.success:
            logger.info("✅ %s order leadva | Ticket: %s", direction, result.order_ticket)
        else:
            logger.error("❌ %s order sikertelen: %s", direction, result.message)


# ============================================================================
# Belépési pont
# ============================================================================
if __name__ == "__main__":
    # ── Konfiguráció ─────────────────────────────────────────────────────
    CONFIG = BotConfig(
        symbol="XAUEUR",
        timeframe_minutes=15,
        bars=500,

        # MT5 bejelentkezés (hagyd üresen ha az MT5 már be van jelentkezve)
        mt5_login=0,
        mt5_password="",
        mt5_server="",

        # Stratégia
        adx_threshold=25.0,

        # Kockázat: 1% per trade, ATR-alapú SL/TP
        risk_pct=0.01,
        atr_tp_multi=3.0,

        # ⚠️ DRY_RUN = True → nem küld valódi ordereket!
        # Állítsd False-ra, ha élesen akarsz kereskedni.
        dry_run=False,
    )

    bot = RegimeBot(CONFIG)
    bot.start()
