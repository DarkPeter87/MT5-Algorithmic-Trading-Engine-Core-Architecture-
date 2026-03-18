import pytest
import pandas as pd
import numpy as np
from src.signal_generator import SignalGenerator, IndicatorSnapshot

def test_signal_generator_drops_last_candle():
    sg = SignalGenerator(adx_period=14, ema_fast=50, ema_slow=200, rsi_period=14, bb_period=20, atr_period=14)
    # Create a mock dataframe with required length
    length = sg.min_bars + 5
    df = pd.DataFrame({
        "open": np.linspace(100, 200, length),
        "high": np.linspace(105, 205, length),
        "low": np.linspace(95, 195, length),
        "close": np.linspace(102, 202, length),
        "volume": np.ones(length) * 1000
    })
    
    # We simulate that the 0th candle (last row in our df) is incomplete.
    # The signal generator should drop it and use the previous one as the "current" closed candle.
    snapshot = sg.calculate(df)
    
    assert snapshot is not None
    # Check that it used index -2 for current close
    assert snapshot.close == pytest.approx(float(df["close"].iloc[-2]))

def test_signal_generator_short_dataframe():
    sg = SignalGenerator()
    df = pd.DataFrame({"close": [100]})
    # Should handle gracefully and return None
    assert sg.calculate(df) is None
    
    df_none = None
    assert sg.calculate(df_none) is None

def test_mean_reversion_crossover_properties():
    # Test the crossed properties explicitly
    snap_buy = IndicatorSnapshot(
        close_prev=99.0, bb_lower=100.0, close=101.0
    )
    assert snap_buy.crossed_above_bb_lower is True
    assert snap_buy.crossed_below_bb_upper is False

    snap_sell = IndicatorSnapshot(
        close_prev=101.0, bb_upper=100.0, close=99.0
    )
    assert snap_sell.crossed_below_bb_upper is True
    assert snap_sell.crossed_above_bb_lower is False
