import pytest
from src.risk_manager import RiskManager

def test_risk_manager_fallback():
    # ATR is zero -> should trigger the fallback logic
    rm = RiskManager(risk_pct=0.01, fallback_atr_variance=0.005)
    
    params = rm.calculate(balance=1000, current_price=2000.0, atr=0.0, is_buy=True, tick_value=10.0, tick_size=0.1)
    
    # Given: fallback atr = 2000.0 * 0.005 = 10.0
    # SL distance = 10.0 * 1.5 = 15.0
    # TP is now completely handled by trailing stops
    assert params.sl_price == pytest.approx(1985.0)
    assert params.tp_price == 0.0

def test_risk_manager_lot_calculation():
    # 1000 balance, risk 1% = $10 risk amount
    # tick_value = $10 per tick size (for XAUUSD 0.1 tick)
    rm = RiskManager(risk_pct=0.01, min_lot=0.01)
    
    # 50 ticks SL
    # atr = 3.333 -> SL distance = 5.0 -> 50.0 ticks inside code
    # loss per lot = 50 * 10 = $500
    # expected lot size = $10 / $500 = 0.02
    params = rm.calculate(balance=1000, current_price=2000.0, atr=3.3333333, is_buy=True, tick_value=10.0, tick_size=0.1)
    
    assert params.sl_ticks == pytest.approx(50.0)
    assert params.lot_size == pytest.approx(0.02)
