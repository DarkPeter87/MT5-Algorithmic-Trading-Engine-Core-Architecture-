"""
Konfigurációs modellek - minden paraméter típuskezelt és UI-ról töltődik.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class MT5Config(BaseModel):
    """MetaTrader 5 kapcsolat beállítások."""
    terminal_path: str = Field("", description="MT5 terminal exe teljes útvonala (üres = alapértelmezett)")
    login: int = Field(0, description="Fiók azonosító (0 = jelenlegi)")
    # SEC-1: jelszó soha nem kerül a JSON fájlba (exclude=True)
    password: str = Field("", exclude=True, description="Jelszó – csak memóriában él, nem íródik lemezre")
    server: str = Field("", description="Bróker szerver (üres = jelenlegi)")


class SymbolConfig(BaseModel):
    """Szimbólum (arany) beállítások."""
    symbol: str = Field("XAUUSD", description="Kereskedett szimbólum (pl. XAUUSD, GOLD)")
    digits: int = Field(2, description="Tizedesjegyek (2 tipikus aranynál)")


class RiskConfig(BaseModel):
    """Kockázatkezelési paraméterek."""
    lot_size: float = Field(0.01, ge=0.01, le=100.0, description="Pozíció méret (lot)")
    max_lots: float = Field(1.0, ge=0.01, le=100.0, description="Max egy pozíció (lot)")
    stop_loss_pips: float = Field(50.0, ge=0.0, description="Stop loss (pip, 0 = kikapcsolt)")
    take_profit_pips: float = Field(100.0, ge=0.0, description="Take profit (pip, 0 = kikapcsolt)")
    max_daily_trades: int = Field(10, ge=0, description="Max napi ügylet (0 = nincs limit)")
    max_spread_pips: float = Field(30.0, ge=0.0, description="Max spread (pip) – ennél nagyobb spreadnél nem nyitunk")
    # SEC-3: slippage konfigurálható (pontban – aranynál 20 pt = 2.0 pip)
    max_slippage_points: int = Field(20, ge=0, description="Max slippage (pont) – deviation az order kérésben")
    # SEC-4: order kitöltési mód (IOC = azonnali vagy töröl, FOK = mindent vagy semmit, RETURN = részleges)
    order_filling: Literal["IOC", "FOK", "RETURN"] = Field("IOC", description="Order kitöltési mód (IOC ajánlott)")


class StrategyParams(BaseModel):
    """
    Stratégia paraméterek – később bővíthető a konkrét stratégiával.
    Ezek a felületen állíthatók, a stratégiád ezeket kapja majd.
    """
    enabled: bool = Field(True, description="Stratégia bekapcsolva")
    # Általános (minden stratégiához használható)
    timeframe_minutes: int = Field(15, description="Időkeret (perc): 1,5,15,30,60,240,1440")
    magic_number: int = Field(123456, description="Expert egyedi azonosító")
    # Placeholder paraméterek – később cserélhetők a saját stratégiára
    param_1: float = Field(14.0, description="Stratégia paraméter 1 (pl. RSI periódus)")
    param_2: float = Field(20.0, description="Stratégia paraméter 2")
    param_3: float = Field(0.02, description="Stratégia paraméter 3")
    comment: str = Field("GoldBot", description="Order megjegyzés")


class BotConfig(BaseModel):
    """Teljes bot konfiguráció – UI-ról töltődik."""
    mt5: MT5Config = Field(default_factory=MT5Config)
    symbol: SymbolConfig = Field(default_factory=SymbolConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyParams = Field(default_factory=StrategyParams)
