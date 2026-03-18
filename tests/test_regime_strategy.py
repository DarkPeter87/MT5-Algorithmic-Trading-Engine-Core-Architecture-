import pytest
from src.regime_strategy import RegimeStrategy, Regime, Signal
from src.signal_generator import IndicatorSnapshot

def test_regime_boundaries():
    strategy = RegimeStrategy(adx_threshold=25.0, rsi_overbought=70.0, rsi_oversold=30.0)
    
    # Test exactly 25.0 threshold logic
    # As modified: adx >= 25.0 is TRENDING
    assert strategy._detect_regime(25.0) == Regime.TRENDING
    assert strategy._detect_regime(24.9) == Regime.RANGING

def test_trending_signals_exact_rsi():
    strategy = RegimeStrategy()
    
    # BUY signal exactly at overbought boundary <= 70.0
    snap = IndicatorSnapshot(
        adx=30.0, ema_50=200.0, ema_200=100.0, rsi=70.0, rsi_prev=60.0 # rising
    )
    result = strategy.evaluate(snap)
    assert result.signal == Signal.BUY
    
    # SELL signal exactly at oversold boundary >= 30.0
    snap = IndicatorSnapshot(
        adx=30.0, ema_50=100.0, ema_200=200.0, rsi=30.0, rsi_prev=40.0 # falling
    )
    result = strategy.evaluate(snap)
    assert result.signal == Signal.SELL

def test_ranging_signals():
    strategy = RegimeStrategy()
    
    snap_buy = IndicatorSnapshot(
        adx=20.0, 
        close_prev=99.0, bb_lower=100.0, close=101.0, # crossed_above_bb_lower
        rsi=30.0 # exactly 30.0 is allowed now <= 30
    )
    result = strategy.evaluate(snap_buy)
    assert result.signal == Signal.BUY
    
    snap_sell = IndicatorSnapshot(
        adx=20.0,
        close_prev=101.0, bb_upper=100.0, close=99.0, # crossed_below_bb_upper
        rsi=70.0 # exactly 70 is allowed now >= 70
    )
    result = strategy.evaluate(snap_sell)
    assert result.signal == Signal.SELL
