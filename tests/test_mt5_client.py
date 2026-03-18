"""
tests/test_mt5_client.py
QA-demanded edge-case tests for MT5Client.

Futtatás:
    pytest tests/ -v

Mivel a MetaTrader5 csomag csak Windowson érhető el, az mt5 modult mockolni kell.
Az összes teszt unit-level, nincs szükség élő MT5 terminálra.
"""
import math
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# MT5 csomag mock: Linux/CI környezetben a MetaTrader5 nem installálható
# ---------------------------------------------------------------------------

def _build_mt5_mock() -> MagicMock:
    """Teljes mt5 csomag stub, az összes szükséges konstanssal."""
    mt5 = MagicMock()
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.ORDER_FILLING_IOC = 1
    mt5.ORDER_FILLING_FOK = 0
    mt5.ORDER_FILLING_RETURN = 2
    mt5.TRADE_ACTION_DEAL = 1
    mt5.TRADE_RETCODE_DONE = 10009
    mt5.initialize.return_value = True
    mt5.terminal_info.return_value = MagicMock()  # nem-None → connected
    return mt5


@pytest.fixture(autouse=True)
def mock_mt5(monkeypatch):
    """
    Minden tesztnél becsempésszük a mock mt5-öt a src.mt5_client modulba.
    Ezzel elkerüljük a 'import MetaTrader5' hibát Linux/CI-n.
    """
    mock = _build_mt5_mock()
    # Lecseréljük a modul szintű mt5 változót
    import src.mt5_client as client_mod
    monkeypatch.setattr(client_mod, "mt5", mock)
    # A _FILLING_MAP-et is újratöltjük a mock alapján
    client_mod._FILLING_MAP.clear()
    client_mod._FILLING_MAP["IOC"] = mock.ORDER_FILLING_IOC
    client_mod._FILLING_MAP["FOK"] = mock.ORDER_FILLING_FOK
    client_mod._FILLING_MAP["RETURN"] = mock.ORDER_FILLING_RETURN
    return mock


# ---------------------------------------------------------------------------
# Segédfunkciók
# ---------------------------------------------------------------------------

def _make_client(symbol: str = "XAUUSD", lot: float = 0.01, max_spread: float = 30.0):
    """Előre konfigurált MT5Client example."""
    from src.config import BotConfig, MT5Config, SymbolConfig, RiskConfig, StrategyParams
    from src.mt5_client import MT5Client

    config = BotConfig(
        mt5=MT5Config(terminal_path="", login=0, password="test", server=""),
        symbol=SymbolConfig(symbol=symbol, digits=2),
        risk=RiskConfig(
            lot_size=lot,
            max_lots=1.0,
            stop_loss_pips=50.0,
            take_profit_pips=100.0,
            max_daily_trades=10,
            max_spread_pips=max_spread,
            max_slippage_points=20,
            order_filling="IOC",
        ),
        strategy=StrategyParams(magic_number=123456),
    )
    client = MT5Client(config)
    client._connected = True  # szimulált aktív kapcsolat
    return client


def _make_tick(bid: float = 2000.0, ask: float = 2000.5) -> MagicMock:
    tick = MagicMock()
    tick.bid = bid
    tick.ask = ask
    tick.last = ask
    return tick


# ===========================================================================
# 1. spread_pips() – QA Unhappy Path
# ===========================================================================

class TestSpreadPips:

    def test_normal_spread(self, mock_mt5):
        """Happy path: normál spread számítás."""
        mock_mt5.symbol_info_tick.return_value = _make_tick(bid=2000.0, ask=2000.5)
        client = _make_client()
        spread = client.spread_pips()
        # (2000.5 - 2000.0) / 0.1 = 5.0 pip
        assert spread == pytest.approx(5.0, rel=1e-3)

    def test_spread_no_tick_returns_inf(self, mock_mt5):
        """
        QA Edge-Case: ha nincs tick (piac zárva, kapcsolat megszakadt),
        a spread SOHA nem lehet fals 0.0 – inf-et kell visszaadnia,
        hogy a spread-guard BIZTOSAN blokkolja az ordert.
        """
        mock_mt5.symbol_info_tick.return_value = None
        client = _make_client()
        spread = client.spread_pips()
        assert math.isinf(spread), "Nincs tick → inf spread-et várunk, nem 0.0-t!"
        assert spread > 0, "Az inf pozitív kell legyen"

    def test_spread_guard_blocks_order_on_no_tick(self, mock_mt5):
        """
        Integrációs QA: ha nincs tick, a spread_pips() > max_spread_pips feltétel
        igaz kell legyen → az order NEM kerülhet beküldésre.
        """
        mock_mt5.symbol_info_tick.return_value = None
        client = _make_client(max_spread=30.0)
        spread = client.spread_pips()
        # Pontosan ez az if-ág fut a UI-ban és a stratégiai loopban
        assert spread > client.config.risk.max_spread_pips, \
            "Nincs tick esetén az order guard-nak BLOKKOLNIA kell!"


# ===========================================================================
# 2. _order() / buy() / sell() – SEC-2 Critical Fix
# ===========================================================================

class TestOrderNoTick:

    def test_buy_returns_failure_on_no_tick(self, mock_mt5):
        """
        SEC-2 / QA Critical: symbol_info_tick → None esetén a buy()
        TradeResult(success=False)-t kell visszaadnia, nem crash-elhet.
        """
        mock_mt5.symbol_info_tick.return_value = None
        client = _make_client()
        result = client.buy()
        assert result.success is False
        assert result.order_ticket is None
        assert "Tick" in result.message or "adat" in result.message.lower(), \
            f"Várt 'Tick/adat' szó az üzenetben: '{result.message}'"

    def test_sell_returns_failure_on_no_tick(self, mock_mt5):
        """SEC-2: sell() is ugyanolyan védelemmel rendelkezik."""
        mock_mt5.symbol_info_tick.return_value = None
        client = _make_client()
        result = client.sell()
        assert result.success is False
        assert result.order_ticket is None

    def test_buy_no_tick_no_order_send_called(self, mock_mt5):
        """SEC-2: ha nincs tick, az order_send soha nem hívódhat meg."""
        mock_mt5.symbol_info_tick.return_value = None
        client = _make_client()
        client.buy()
        mock_mt5.order_send.assert_not_called()


# ===========================================================================
# 3. _order() – Bróker elutasítás kezelése (nem-DONE retcode)
# ===========================================================================

class TestOrderBrokerRejection:

    def _setup_normal_tick(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = _make_tick()

    def test_broker_rejection_non_done_retcode(self, mock_mt5):
        """
        QA Edge-Case: Ha a bróker nem TRADE_RETCODE_DONE-val válaszol
        (pl. retcode=10030 INVALID_FILL, 10006 REJECTED), a TradeResult
        success=False kell legyen, és a retcode látható az üzenetben.
        """
        self._setup_normal_tick(mock_mt5)
        rejection = MagicMock()
        rejection.retcode = 10030  # INVALID_FILL
        rejection.comment = "Invalid fill"
        rejection.order = None
        mock_mt5.order_send.return_value = rejection

        client = _make_client()
        result = client.buy()

        assert result.success is False
        assert "10030" in result.message, \
            f"A retcode-nak meg kell jelennie az üzenetben: '{result.message}'"

    def test_broker_order_send_none(self, mock_mt5):
        """
        QA Edge-Case: order_send None-t ad vissza (pl. IPC hiba).
        Nem crash → TradeResult(success=False).
        """
        self._setup_normal_tick(mock_mt5)
        mock_mt5.order_send.return_value = None
        mock_mt5.last_error.return_value = (1, "IPC hiba")

        client = _make_client()
        result = client.buy()

        assert result.success is False

    def test_successful_order(self, mock_mt5):
        """Happy path: sikeres order → success=True, ticket visszaadva."""
        self._setup_normal_tick(mock_mt5)
        ok_result = MagicMock()
        ok_result.retcode = mock_mt5.TRADE_RETCODE_DONE
        ok_result.order = 999001
        ok_result.comment = "OK"
        mock_mt5.order_send.return_value = ok_result

        client = _make_client()
        result = client.buy()

        assert result.success is True
        assert result.order_ticket == 999001

    def test_extreme_sl_tp_values_no_crash(self, mock_mt5):
        """
        QA Edge-Case: extrém nagy SL/TP értékek sem okozhatnak crash-t,
        az order kérés elküldődik (a bróker utasítja vissza, nem a bot).
        """
        self._setup_normal_tick(mock_mt5)
        ok_result = MagicMock()
        ok_result.retcode = mock_mt5.TRADE_RETCODE_DONE
        ok_result.order = 999002
        mock_mt5.order_send.return_value = ok_result

        client = _make_client()
        result = client.buy(sl_pips=999999.0, tp_pips=999999.0)
        # Ne dobjon kivételt – a return értéktől függetlenül
        assert isinstance(result.success, bool)


# ===========================================================================
# 4. Konfigurációs modell – Pydantic fallback biztonság
# ===========================================================================

class TestConfigValidation:

    def test_risk_config_defaults_on_missing_values(self):
        """
        QA UI Fallback: ha az UI üres stringet küld és a kód float()-ra castol,
        a Pydantic default értékek legyenek biztonságosak.
        """
        from src.config import RiskConfig
        cfg = RiskConfig()
        assert cfg.lot_size == pytest.approx(0.01)
        assert cfg.stop_loss_pips == pytest.approx(50.0)
        assert cfg.max_daily_trades == 10
        assert cfg.max_slippage_points == 20
        assert cfg.order_filling == "IOC"

    def test_risk_config_rejects_negative_lot(self):
        """Pydantic ge=0.01 constraint: negatív lot-ot el kell utasítani."""
        from src.config import RiskConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiskConfig(lot_size=-0.5)

    def test_risk_config_rejects_negative_sl(self):
        """Pydantic ge=0.0 constraint: negatív SL-t el kell utasítani."""
        from src.config import RiskConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiskConfig(stop_loss_pips=-10.0)

    def test_password_excluded_from_json(self):
        """
        SEC-1: A jelszó soha nem kerülhet a JSON kimenetbe.
        """
        from src.config import BotConfig, MT5Config
        cfg = BotConfig(mt5=MT5Config(login=12345, password="SECRET_PASS"))
        json_str = cfg.model_dump_json()
        assert "SECRET_PASS" not in json_str, \
            "SEC-1 FAIL: A jelszó plaintext-ben van a JSON-ban!"
        assert "password" not in json_str, \
            "SEC-1 FAIL: A 'password' kulcs megjelent a JSON-ban!"

    def test_order_filling_invalid_value_rejected(self):
        """SEC-4: Érvénytelen order_filling értéket Pydantic-nak el kell utasítania."""
        from src.config import RiskConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiskConfig(order_filling="INVALID_MODE")


# ===========================================================================
# 5. spread_pips() – PERF-1: Egyszer hívja a tick API-t, nem kétszer
# ===========================================================================

class TestPerfSingleTickFetch:

    def test_order_fetches_tick_only_once(self, mock_mt5):
        """
        PERF-1: Az _order() metódus pontosan egyszer kéri le a ticket.
        Dupla API hívás elfogadhatatlan egy éles megbízásnál.
        """
        mock_mt5.symbol_info_tick.return_value = _make_tick()
        ok = MagicMock()
        ok.retcode = mock_mt5.TRADE_RETCODE_DONE
        ok.order = 1
        mock_mt5.order_send.return_value = ok

        client = _make_client()
        client.buy()

        assert mock_mt5.symbol_info_tick.call_count == 1, \
            f"PERF-1 FAIL: symbol_info_tick {mock_mt5.symbol_info_tick.call_count}x hívódott, max 1x megengedett!"


# ===========================================================================
# 6. is_connected – QUAL-1: Heartbeat ellenőrzés
# ===========================================================================

class TestHeartbeat:

    def test_is_connected_false_if_terminal_info_returns_none(self, mock_mt5):
        """
        QUAL-1: Ha az MT5 terminál leáll (terminal_info → None),
        az is_connected property False-t kell visszaadjon és a flag resetelődjön.
        """
        mock_mt5.terminal_info.return_value = None
        client = _make_client()
        assert client._connected is True  # előtte True volt
        result = client.is_connected
        assert result is False
        assert client._connected is False, "A _connected flag-et vissza kell állítani!"

    def test_is_connected_true_with_healthy_terminal(self, mock_mt5):
        """QUAL-1 Happy path: terminál él → is_connected True."""
        mock_mt5.terminal_info.return_value = MagicMock()
        client = _make_client()
        assert client.is_connected is True
