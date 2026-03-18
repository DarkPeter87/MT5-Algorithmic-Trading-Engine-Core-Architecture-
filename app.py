"""
MT5 Aranykereskedő Bot – vizuális felület.
Minden paraméter itt állítható; a stratégiát később beépítheted.
Futtatás: streamlit run app.py
"""
import json
import logging
from pathlib import Path

import streamlit as st
import pandas as pd
from platformdirs import user_config_dir

from src.config import BotConfig, MT5Config, SymbolConfig, RiskConfig, StrategyParams
from src.mt5_client import MT5Client
from src.strategy_base import StrategyBase, PlaceholderStrategy, Signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SEC-5: platform-helyes konfig könyvtár (nem a projekt gyökér, nem kerül git-be)
CONFIG_FILE = Path(user_config_dir("GoldBot")) / "config_saved.json"
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
st.set_page_config(page_title="MT5 Gold Trader Bot", layout="wide", initial_sidebar_state="expanded")


def load_saved_config() -> BotConfig | None:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return BotConfig.model_validate(data)
        except Exception as e:
            logger.warning("Konfig betöltése sikertelen: %s", e)
    return None


def save_config(config: BotConfig) -> None:
    CONFIG_FILE.write_text(config.model_dump_json(indent=2), encoding="utf-8")


def default_config() -> BotConfig:
    return BotConfig()


def build_config_from_ui() -> BotConfig:
    """UI mezőkből összerakja a BotConfig-ot."""
    return BotConfig(
        mt5=MT5Config(
            terminal_path=st.session_state.get("mt5_path", ""),
            login=int(st.session_state.get("mt5_login", 0)),
            password=st.session_state.get("mt5_password", ""),
            server=st.session_state.get("mt5_server", ""),
        ),
        symbol=SymbolConfig(
            symbol=st.session_state.get("symbol", "XAUUSD"),
            digits=int(st.session_state.get("symbol_digits", 2)),
        ),
        risk=RiskConfig(
            lot_size=float(st.session_state.get("lot_size", 0.01)),
            max_lots=float(st.session_state.get("max_lots", 1.0)),
            stop_loss_pips=float(st.session_state.get("sl_pips", 50.0)),
            take_profit_pips=float(st.session_state.get("tp_pips", 100.0)),
            max_daily_trades=int(st.session_state.get("max_daily_trades", 10)),
            max_spread_pips=float(st.session_state.get("max_spread_pips", 30.0)),
        ),
        strategy=StrategyParams(
            enabled=bool(st.session_state.get("strategy_enabled", True)),
            timeframe_minutes=int(st.session_state.get("timeframe", 15)),
            magic_number=int(st.session_state.get("magic", 123456)),
            param_1=float(st.session_state.get("param_1", 14.0)),
            param_2=float(st.session_state.get("param_2", 20.0)),
            param_3=float(st.session_state.get("param_3", 0.02)),
            comment=st.session_state.get("strategy_comment", "GoldBot"),
        ),
    )


def init_session_config():
    if "bot_config" not in st.session_state:
        saved = load_saved_config()
        c = saved or default_config()
        st.session_state["bot_config"] = c
        st.session_state["mt5_path"] = c.mt5.terminal_path or ""
        st.session_state["mt5_login"] = c.mt5.login
        st.session_state["mt5_password"] = c.mt5.password or ""
        st.session_state["mt5_server"] = c.mt5.server or ""
        st.session_state["symbol"] = c.symbol.symbol
        st.session_state["symbol_digits"] = c.symbol.digits
        st.session_state["lot_size"] = c.risk.lot_size
        st.session_state["max_lots"] = c.risk.max_lots
        st.session_state["sl_pips"] = c.risk.stop_loss_pips
        st.session_state["tp_pips"] = c.risk.take_profit_pips
        st.session_state["max_daily_trades"] = c.risk.max_daily_trades
        st.session_state["max_spread_pips"] = c.risk.max_spread_pips
        st.session_state["strategy_enabled"] = c.strategy.enabled
        st.session_state["timeframe"] = c.strategy.timeframe_minutes
        st.session_state["magic"] = c.strategy.magic_number
        st.session_state["param_1"] = c.strategy.param_1
        st.session_state["param_2"] = c.strategy.param_2
        st.session_state["param_3"] = c.strategy.param_3
        st.session_state["strategy_comment"] = c.strategy.comment
    if "mt5_client" not in st.session_state:
        st.session_state["mt5_client"] = None


def main():
    init_session_config()

    st.title("MT5 Aranykereskedő Bot")
    st.caption("Minden paraméter a felületen állítható. A stratégiát később beépítheted.")

    # ---- Oldalsáv: MT5 kapcsolat ----
    with st.sidebar:
        st.header("MT5 Kapcsolat")
        st.text_input("Terminal útvonal (opcionális)", key="mt5_path", placeholder="C:\\Program Files\\...\\terminal64.exe")
        st.number_input("Login (0 = jelenlegi)", key="mt5_login", value=st.session_state.get("mt5_login", 0), step=1)
        st.text_input("Jelszó (opcionális)", key="mt5_password", type="password")
        st.text_input("Szerver (opcionális)", key="mt5_server")

        if st.button("Kapcsolódás MT5-höz"):
            config = build_config_from_ui()
            st.session_state["bot_config"] = config
            client = MT5Client(config)
            ok = client.connect(
                path=config.mt5.terminal_path or "",
                login=config.mt5.login,
                password=config.mt5.password or "",
                server=config.mt5.server or "",
            )
            if ok:
                st.session_state["mt5_client"] = client
                st.success("MT5 kapcsolódva.")
            else:
                st.session_state["mt5_client"] = None
                st.error("Kapcsolódás sikertelen. Nyisd meg az MT5 terminált előbb.")

        if st.button("Kapcsolat bontása"):
            if st.session_state.get("mt5_client"):
                st.session_state["mt5_client"].disconnect()
                st.session_state["mt5_client"] = None
            st.info("Kapcsolat bontva.")

        st.divider()
        if st.session_state.get("mt5_client") and st.session_state["mt5_client"].is_connected:
            st.success("Online")
        else:
            st.warning("Nincs kapcsolat")

    # ---- Fő terület: paraméterek lapokban ----
    tab_symbol, tab_risk, tab_strategy, tab_status, tab_actions = st.tabs([
        "Szimbólum (arany)", "Kockázat", "Stratégia", "Státusz", "Műveletek"
    ])

    with tab_symbol:
        st.subheader("Szimbólum beállítások")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Szimbólum", key="symbol", value=st.session_state.get("symbol", "XAUUSD"),
                          help="Pl. XAUUSD, GOLD")
        with c2:
            st.number_input("Tizedesjegyek", key="symbol_digits", value=st.session_state.get("symbol_digits", 2), min_value=0, max_value=5)

    with tab_risk:
        st.subheader("Kockázatkezelés")
        c1, c2 = st.columns(2)
        with c1:
            st.slider("Lot méret", key="lot_size", min_value=0.01, max_value=10.0, value=float(st.session_state.get("lot_size", 0.01)), step=0.01)
            st.slider("Max lot / pozíció", key="max_lots", min_value=0.01, max_value=100.0, value=float(st.session_state.get("max_lots", 1.0)), step=0.01)
            st.number_input("Stop loss (pip)", key="sl_pips", value=float(st.session_state.get("sl_pips", 50.0)), min_value=0.0, step=1.0)
        with c2:
            st.number_input("Take profit (pip)", key="tp_pips", value=float(st.session_state.get("tp_pips", 100.0)), min_value=0.0, step=1.0)
            st.number_input("Max napi ügylet", key="max_daily_trades", value=int(st.session_state.get("max_daily_trades", 10)), min_value=0, step=1)
            st.number_input("Max spread (pip) – ennél nagyobb spreadnél nem nyitunk", key="max_spread_pips", value=float(st.session_state.get("max_spread_pips", 30.0)), min_value=0.0, step=0.5)

    with tab_strategy:
        st.subheader("Stratégia paraméterek (később bővíthető)")
        st.checkbox("Stratégia bekapcsolva", key="strategy_enabled", value=st.session_state.get("strategy_enabled", True))
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox("Időkeret (perc)", key="timeframe", options=[1, 5, 15, 30, 60, 240, 1440], format_func=lambda x: f"{x} perc")
            st.number_input("Magic number", key="magic", value=st.session_state.get("magic", 123456), min_value=0)
            st.text_input("Order megjegyzés", key="strategy_comment", value=st.session_state.get("strategy_comment", "GoldBot"))
        with c2:
            st.number_input("Stratégia paraméter 1", key="param_1", value=float(st.session_state.get("param_1", 14.0)), step=0.1)
            st.number_input("Stratégia paraméter 2", key="param_2", value=float(st.session_state.get("param_2", 20.0)), step=0.1)
            st.number_input("Stratégia paraméter 3", key="param_3", value=float(st.session_state.get("param_3", 0.02)), step=0.01)
        st.caption("A param_1/2/3 értékeket a később beépített stratégia fogja használni (pl. RSI periódus, küszöbök).")

    with tab_status:
        st.subheader("Státusz és árak")
        client = st.session_state.get("mt5_client")
        if client and client.is_connected:
            price = client.current_price()
            if price:
                bid, ask, last = price
                st.metric("Bid", f"{bid:.2f}")
                st.metric("Ask", f"{ask:.2f}")
                st.metric("Spread (pip)", f"{client.spread_pips():1f}")
            positions = client.positions_open()
            st.write(f"Nyitott pozíciók: **{len(positions)}**")
            if positions:
                df = pd.DataFrame([{
                    "Ticket": p.ticket, "Típus": "Buy" if p.type == 0 else "Sell",
                    "Lot": p.volume, "Nyitás": p.price_open, "SL": p.sl, "TP": p.tp
                } for p in positions])
                st.dataframe(df, use_container_width=True)
            st.write("Ma nyitott ügyletek (magic):", client.daily_trades_count())
        else:
            st.info("Nincs MT5 kapcsolat. Kapcsolódj az oldalsávból.")

    with tab_actions:
        st.subheader("Műveletek")
        st.caption("Konfig mentése / manuális teszt order (ha van kapcsolat).")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Konfiguráció mentése"):
                cfg = build_config_from_ui()
                save_config(cfg)
                st.session_state["bot_config"] = cfg
                st.success("Konfig mentve: config_saved.json")

            if st.button("Manuális VÉTEL (teszt)"):
                client = st.session_state.get("mt5_client")
                if not client or not client.is_connected:
                    st.error("Előbb kapcsolódj az MT5-höz.")
                else:
                    cfg = build_config_from_ui()
                    st.session_state["bot_config"] = cfg
                    client.config = cfg
                    if client.spread_pips() > cfg.risk.max_spread_pips:
                        st.warning(f"Spread túl magas ({client.spread_pips():.1f} > {cfg.risk.max_spread_pips})")
                    else:
                        r = client.buy(comment=cfg.strategy.comment)
                        if r.success:
                            st.success(f"Vétel leadva, ticket: {r.order_ticket}")
                        else:
                            st.error(r.message)

            if st.button("Manuális ELADÁS (teszt)"):
                client = st.session_state.get("mt5_client")
                if not client or not client.is_connected:
                    st.error("Előbb kapcsolódj az MT5-höz.")
                else:
                    cfg = build_config_from_ui()
                    st.session_state["bot_config"] = cfg
                    client.config = cfg
                    if client.spread_pips() > cfg.risk.max_spread_pips:
                        st.warning(f"Spread túl magas ({client.spread_pips():.1f} > {cfg.risk.max_spread_pips})")
                    else:
                        r = client.sell(comment=cfg.strategy.comment)
                        if r.success:
                            st.success(f"Eladás leadva, ticket: {r.order_ticket}")
                        else:
                            st.error(r.message)
        with c2:
            st.info("A stratégia alapú automata kereskedés a később beépített stratégiával fog működni (pl. EA vagy időzített ellenőrzés).")

    # Konfig szinkron: UI -> session config
    try:
        st.session_state["bot_config"] = build_config_from_ui()
    except Exception:
        pass


if __name__ == "__main__":
    main()
