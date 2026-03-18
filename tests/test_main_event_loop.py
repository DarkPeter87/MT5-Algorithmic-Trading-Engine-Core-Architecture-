import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from main import RegimeBot, BotConfig

def test_main_loop_no_repainting_fetches_once():
    config = BotConfig(dry_run=True, poll_interval_sec=0)
    bot = RegimeBot(config)
    
    bot.feed = MagicMock()
    bot.feed.is_connected = True
    
    time1 = pd.Timestamp("2026-03-18 10:00:00")
    time2 = pd.Timestamp("2026-03-18 10:15:00")
    
    # First iteration: fetches time1 -> checks last_bar_time (None) -> fetches OHLCV
    # Second iteration: fetches time1 again -> checks last_bar_time (time1) -> skips OHLCV
    # Third iteration: fetches time2 -> checks last_bar_time (time1) -> fetches OHLCV
    # Fourth iteration: raises Exception to break the while True loop
    bot.feed.fetch_last_closed_bar_time.side_effect = [time1, time1, time2, KeyboardInterrupt]
    
    # Return mock OHLCV dataframe 
    bot.feed.fetch_ohlcv.return_value = pd.DataFrame([{"time": time1, "close": 100}])
    bot.signals.calculate = MagicMock(return_value=None)  # skip real indicators
    
    with patch("time.sleep"):
        try:
            bot._run_loop()
        except KeyboardInterrupt:
            pass
            
    # fetch_ohlcv should only have been called TWICE (for time1 and time2) 
    # despite the loop running 3 times
    assert bot.feed.fetch_ohlcv.call_count == 2

def test_main_loop_reconnect_logic():
    config = BotConfig(dry_run=True, poll_interval_sec=0)
    bot = RegimeBot(config)
    
    bot.feed = MagicMock()
    # First iteration: disconnected -> tries to connect, succeeds
    # Second iteration: connected -> raises KeyboardInterrupt
    
    # We use a trick: is_connected starts as False, then the connect mock sets it to True inside 
    def mock_connect(*args, **kwargs):
        bot.feed.is_connected = True
        return True
        
    bot.feed.is_connected = False
    bot.feed.connect.side_effect = mock_connect
    
    # On the second loop (when connected = True), fetch_last_closed_bar_time will abort it
    bot.feed.fetch_last_closed_bar_time.side_effect = KeyboardInterrupt
    
    with patch("time.sleep"):
        try:
            bot._run_loop()
        except KeyboardInterrupt:
            pass
            
    assert bot.feed.connect.call_count == 1
    assert bot.feed.is_connected is True
