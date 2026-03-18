"""
MT5 Aranykereskedő Bot – asztali alkalmazás.
PC-re telepíthető, felhasználóbarát egyablakos program.
Futtatás: python desktop_app.py
"""
import json
import logging
import sys
from pathlib import Path

# CustomTkinter és tk
import customtkinter as ctk
from tkinter import messagebox

# Projekt modulok
from src.config import BotConfig, MT5Config, SymbolConfig, RiskConfig, StrategyParams
from src.mt5_client import MT5Client

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

def _config_path() -> Path:
    """Konfig fájl mappája: futáskori mappa (exe mellett) vagy script mappája."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config_saved.json"
    return Path(__file__).resolve().parent / "config_saved.json"


CONFIG_FILE = _config_path()
# Ablak kinézete
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def load_config() -> BotConfig | None:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return BotConfig.model_validate(data)
        except Exception as e:
            LOG.warning("Konfig betöltése sikertelen: %s", e)
    return None


def save_config(config: BotConfig) -> None:
    CONFIG_FILE.write_text(config.model_dump_json(indent=2), encoding="utf-8")


class GoldTraderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MT5 Aranykereskedő Bot")
        self.geometry("900x620")
        self.minsize(700, 500)

        self.mt5_client: MT5Client | None = None
        self.config = load_config() or BotConfig()
        self._poll_id: str | None = None  # MEM-1: after() handle a törléshez

        self._build_ui()
        self._load_config_into_ui()
        self._refresh_status()

    def _build_ui(self):
        # Felső sáv: MT5 kapcsolat
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(top, text="MT5 kapcsolat", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(top, text="Terminal:").pack(side="left", padx=(0, 4))
        self.entry_path = ctk.CTkEntry(top, width=280, placeholder_text="Üres = alapértelmezett")
        self.entry_path.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(top, text="Login:").pack(side="left", padx=(8, 4))
        self.entry_login = ctk.CTkEntry(top, width=80)
        self.entry_login.insert(0, "0")
        self.entry_login.pack(side="left", padx=(0, 8))
        self.btn_connect = ctk.CTkButton(top, text="Kapcsolódás", command=self._on_connect, width=100)
        self.btn_connect.pack(side="left", padx=8)
        self.btn_disconnect = ctk.CTkButton(top, text="Kapcsolat bontása", command=self._on_disconnect, width=120, state="disabled")
        self.btn_disconnect.pack(side="left", padx=4)
        self.label_status = ctk.CTkLabel(top, text="Nincs kapcsolat", text_color="gray")
        self.label_status.pack(side="left", padx=12)

        # Lapok
        self.tabs = ctk.CTkTabview(self, width=860)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tabs.add("Szimbólum")
        self.tabs.add("Kockázat")
        self.tabs.add("Stratégia")
        self.tabs.add("Státusz")
        self.tabs.add("Műveletek")

        self._build_tab_symbol()
        self._build_tab_risk()
        self._build_tab_strategy()
        self._build_tab_status()
        self._build_tab_actions()

    def _build_tab_symbol(self):
        f = self.tabs.tab("Szimbólum")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=8)
        ctk.CTkLabel(row, text="Szimbólum (pl. XAUUSD):").pack(side="left", padx=(0, 8))
        self.entry_symbol = ctk.CTkEntry(row, width=120)
        self.entry_symbol.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row, text="Tizedesjegyek:").pack(side="left", padx=(0, 8))
        self.entry_digits = ctk.CTkEntry(row, width=60)
        self.entry_digits.insert(0, "2")
        self.entry_digits.pack(side="left")

    def _build_tab_risk(self):
        f = self.tabs.tab("Kockázat")
        row1 = ctk.CTkFrame(f, fg_color="transparent")
        row1.pack(fill="x", pady=6)
        ctk.CTkLabel(row1, text="Lot méret:").pack(side="left", padx=(0, 8))
        self.entry_lot = ctk.CTkEntry(row1, width=80)
        self.entry_lot.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row1, text="Max lot / pozíció:").pack(side="left", padx=(0, 8))
        self.entry_max_lots = ctk.CTkEntry(row1, width=80)
        self.entry_max_lots.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row1, text="Stop loss (pip):").pack(side="left", padx=(0, 8))
        self.entry_sl = ctk.CTkEntry(row1, width=80)
        self.entry_sl.pack(side="left")

        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", pady=6)
        ctk.CTkLabel(row2, text="Take profit (pip):").pack(side="left", padx=(0, 8))
        self.entry_tp = ctk.CTkEntry(row2, width=80)
        self.entry_tp.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row2, text="Max napi ügylet:").pack(side="left", padx=(0, 8))
        self.entry_max_trades = ctk.CTkEntry(row2, width=80)
        self.entry_max_trades.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row2, text="Max spread (pip):").pack(side="left", padx=(0, 8))
        self.entry_max_spread = ctk.CTkEntry(row2, width=80)
        self.entry_max_spread.pack(side="left")

    def _build_tab_strategy(self):
        f = self.tabs.tab("Stratégia")
        self.var_strategy_on = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(f, text="Stratégia bekapcsolva", variable=self.var_strategy_on).pack(anchor="w", pady=4)
        row1 = ctk.CTkFrame(f, fg_color="transparent")
        row1.pack(fill="x", pady=6)
        ctk.CTkLabel(row1, text="Időkeret (perc):").pack(side="left", padx=(0, 8))
        self.combo_timeframe = ctk.CTkComboBox(row1, values=["1", "5", "15", "30", "60", "240", "1440"], width=80)
        self.combo_timeframe.set("15")
        self.combo_timeframe.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row1, text="Magic number:").pack(side="left", padx=(0, 8))
        self.entry_magic = ctk.CTkEntry(row1, width=80)
        self.entry_magic.insert(0, "123456")
        self.entry_magic.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row1, text="Order megjegyzés:").pack(side="left", padx=(0, 8))
        self.entry_comment = ctk.CTkEntry(row1, width=120)
        self.entry_comment.insert(0, "GoldBot")
        self.entry_comment.pack(side="left")

        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", pady=12)
        ctk.CTkLabel(row2, text="Paraméter 1:").pack(side="left", padx=(0, 8))
        self.entry_param1 = ctk.CTkEntry(row2, width=80)
        self.entry_param1.insert(0, "14.0")
        self.entry_param1.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row2, text="Paraméter 2:").pack(side="left", padx=(0, 8))
        self.entry_param2 = ctk.CTkEntry(row2, width=80)
        self.entry_param2.insert(0, "20.0")
        self.entry_param2.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row2, text="Paraméter 3:").pack(side="left", padx=(0, 8))
        self.entry_param3 = ctk.CTkEntry(row2, width=80)
        self.entry_param3.insert(0, "0.02")
        self.entry_param3.pack(side="left")

    def _build_tab_status(self):
        self.frame_status = self.tabs.tab("Státusz")
        self.label_bid = ctk.CTkLabel(self.frame_status, text="Bid: -", font=ctk.CTkFont(size=14))
        self.label_bid.pack(anchor="w", pady=4)
        self.label_ask = ctk.CTkLabel(self.frame_status, text="Ask: -", font=ctk.CTkFont(size=14))
        self.label_ask.pack(anchor="w", pady=4)
        self.label_spread = ctk.CTkLabel(self.frame_status, text="Spread: - pip", font=ctk.CTkFont(size=14))
        self.label_spread.pack(anchor="w", pady=4)
        self.label_positions = ctk.CTkLabel(self.frame_status, text="Nyitott pozíciók: 0", font=ctk.CTkFont(size=14))
        self.label_positions.pack(anchor="w", pady=4)
        self.text_positions = ctk.CTkTextbox(self.frame_status, height=180, state="disabled")
        self.text_positions.pack(fill="x", pady=8)
        ctk.CTkButton(self.frame_status, text="Frissítés", command=self._refresh_status, width=100).pack(anchor="w", pady=4)

    def _build_tab_actions(self):
        f = self.tabs.tab("Műveletek")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=8)
        ctk.CTkButton(row, text="Konfiguráció mentése", command=self._save_config_click, width=160).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Manuális VÉTEL (teszt)", command=self._manual_buy, width=160, fg_color="green").pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Manuális ELADÁS (teszt)", command=self._manual_sell, width=160, fg_color="crimson").pack(side="left", padx=(0, 8))
        self.label_action_msg = ctk.CTkLabel(f, text="", text_color="gray")
        self.label_action_msg.pack(anchor="w", pady=12)

    def _get_config_from_ui(self) -> BotConfig:
        def num(s: str, default: float) -> float:
            try:
                return float(s.strip() or default)
            except ValueError:
                return default

        def int_num(s: str, default: int) -> int:
            try:
                return int(s.strip() or default)
            except ValueError:
                return default

        return BotConfig(
            mt5=MT5Config(
                terminal_path=self.entry_path.get().strip(),
                login=int_num(self.entry_login.get(), 0),
                # QUAL-2: megőrizzük a betöltött jelszót (UI-on nincs mező hozzá)
                password=self.config.mt5.password,
                server="",
            ),
            symbol=SymbolConfig(
                symbol=self.entry_symbol.get().strip() or "XAUUSD",
                digits=int_num(self.entry_digits.get(), 2),
            ),
            risk=RiskConfig(
                lot_size=num(self.entry_lot.get(), 0.01),
                max_lots=num(self.entry_max_lots.get(), 1.0),
                stop_loss_pips=num(self.entry_sl.get(), 50.0),
                take_profit_pips=num(self.entry_tp.get(), 100.0),
                max_daily_trades=int_num(self.entry_max_trades.get(), 10),
                max_spread_pips=num(self.entry_max_spread.get(), 30.0),
            ),
            strategy=StrategyParams(
                enabled=self.var_strategy_on.get(),
                timeframe_minutes=int_num(self.combo_timeframe.get(), 15),
                magic_number=int_num(self.entry_magic.get(), 123456),
                param_1=num(self.entry_param1.get(), 14.0),
                param_2=num(self.entry_param2.get(), 20.0),
                param_3=num(self.entry_param3.get(), 0.02),
                comment=self.entry_comment.get().strip() or "GoldBot",
            ),
        )

    def _load_config_into_ui(self):
        c = self.config
        self.entry_path.delete(0, "end")
        self.entry_path.insert(0, c.mt5.terminal_path or "")
        self.entry_login.delete(0, "end")
        self.entry_login.insert(0, str(c.mt5.login))
        self.entry_symbol.delete(0, "end")
        self.entry_symbol.insert(0, c.symbol.symbol)
        self.entry_digits.delete(0, "end")
        self.entry_digits.insert(0, str(c.symbol.digits))
        self.entry_lot.delete(0, "end")
        self.entry_lot.insert(0, str(c.risk.lot_size))
        self.entry_max_lots.delete(0, "end")
        self.entry_max_lots.insert(0, str(c.risk.max_lots))
        self.entry_sl.delete(0, "end")
        self.entry_sl.insert(0, str(c.risk.stop_loss_pips))
        self.entry_tp.delete(0, "end")
        self.entry_tp.insert(0, str(c.risk.take_profit_pips))
        self.entry_max_trades.delete(0, "end")
        self.entry_max_trades.insert(0, str(c.risk.max_daily_trades))
        self.entry_max_spread.delete(0, "end")
        self.entry_max_spread.insert(0, str(c.risk.max_spread_pips))
        self.var_strategy_on.set(c.strategy.enabled)
        self.combo_timeframe.set(str(c.strategy.timeframe_minutes))
        self.entry_magic.delete(0, "end")
        self.entry_magic.insert(0, str(c.strategy.magic_number))
        self.entry_comment.delete(0, "end")
        self.entry_comment.insert(0, c.strategy.comment or "GoldBot")
        self.entry_param1.delete(0, "end")
        self.entry_param1.insert(0, str(c.strategy.param_1))
        self.entry_param2.delete(0, "end")
        self.entry_param2.insert(0, str(c.strategy.param_2))
        self.entry_param3.delete(0, "end")
        self.entry_param3.insert(0, str(c.strategy.param_3))

    def _on_connect(self):
        self.config = self._get_config_from_ui()
        self.mt5_client = MT5Client(self.config)
        path = self.config.mt5.terminal_path or ""
        ok = self.mt5_client.connect(
            path=path,
            login=self.config.mt5.login,
            password=self.config.mt5.password,
            server=self.config.mt5.server,
        )
        if ok:
            self.label_status.configure(text="Online", text_color="lime")
            self.btn_connect.configure(state="disabled")
            self.btn_disconnect.configure(state="normal")
            self._refresh_status()
        else:
            messagebox.showerror("Hiba", "MT5 kapcsolódás sikertelen.\nIndítsd el az MT5 terminált, és próbáld újra.")

    def _on_disconnect(self):
        if self.mt5_client:
            self.mt5_client.disconnect()
            self.mt5_client = None
        self.label_status.configure(text="Nincs kapcsolat", text_color="gray")
        self.btn_connect.configure(state="normal")
        self.btn_disconnect.configure(state="disabled")
        self.label_bid.configure(text="Bid: -")
        self.label_ask.configure(text="Ask: -")
        self.label_spread.configure(text="Spread: - pip")
        self.label_positions.configure(text="Nyitott pozíciók: 0")
        self.text_positions.configure(state="normal")
        self.text_positions.delete("1.0", "end")
        self.text_positions.configure(state="disabled")

    def _refresh_status(self):
        if not self.mt5_client or not self.mt5_client.is_connected:
            return
        self.config = self._get_config_from_ui()
        self.mt5_client.config = self.config
        price = self.mt5_client.current_price()
        if price:
            bid, ask, last = price
            self.label_bid.configure(text=f"Bid: {bid:.2f}")
            self.label_ask.configure(text=f"Ask: {ask:.2f}")
            self.label_spread.configure(text=f"Spread: {self.mt5_client.spread_pips():.1f} pip")
        positions = self.mt5_client.positions_open()
        self.label_positions.configure(text=f"Nyitott pozíciók: {len(positions)}")
        self.text_positions.configure(state="normal")
        self.text_positions.delete("1.0", "end")
        if positions:
            lines = []
            for p in positions:
                typ = "Buy" if p.type == 0 else "Sell"
                lines.append(f"#{p.ticket}  {typ}  {p.volume} lot  nyitás: {p.price_open}  SL: {p.sl}  TP: {p.tp}")
            self.text_positions.insert("1.0", "\n".join(lines))
        else:
            self.text_positions.insert("1.0", "Nincs nyitott pozíció.")
        self.text_positions.configure(state="disabled")

    def _save_config_click(self):
        self.config = self._get_config_from_ui()
        save_config(self.config)
        self.label_action_msg.configure(text=f"Konfiguráció mentve: {CONFIG_FILE}")
        messagebox.showinfo("Mentve", "Beállítások mentve.")

    def _manual_buy(self):
        if not self.mt5_client or not self.mt5_client.is_connected:
            messagebox.showwarning("Figyelmeztetés", "Előbb kapcsolódj az MT5-höz.")
            return
        self.config = self._get_config_from_ui()
        self.mt5_client.config = self.config
        # QUAL-3: spread egyszer lekérve, kétszer használva
        current_spread = self.mt5_client.spread_pips()
        if current_spread > self.config.risk.max_spread_pips:
            messagebox.showwarning("Figyelmeztetés", f"Spread túl magas ({current_spread:.1f} > {self.config.risk.max_spread_pips})")
            return
        r = self.mt5_client.buy(comment=self.config.strategy.comment)
        if r.success:
            self.label_action_msg.configure(text=f"Vétel leadva, ticket: {r.order_ticket}", text_color="lime")
            messagebox.showinfo("Siker", f"Vétel leadva.\nTicket: {r.order_ticket}")
            self._refresh_status()
        else:
            self.label_action_msg.configure(text=r.message, text_color="red")
            messagebox.showerror("Hiba", r.message)

    def _manual_sell(self):
        if not self.mt5_client or not self.mt5_client.is_connected:
            messagebox.showwarning("Figyelmeztetés", "Előbb kapcsolódj az MT5-höz.")
            return
        self.config = self._get_config_from_ui()
        self.mt5_client.config = self.config
        # QUAL-3: spread egyszer lekérve, kétszer használva
        current_spread = self.mt5_client.spread_pips()
        if current_spread > self.config.risk.max_spread_pips:
            messagebox.showwarning("Figyelmeztetés", f"Spread túl magas ({current_spread:.1f} > {self.config.risk.max_spread_pips})")
            return
        r = self.mt5_client.sell(comment=self.config.strategy.comment)
        if r.success:
            self.label_action_msg.configure(text=f"Eladás leadva, ticket: {r.order_ticket}", text_color="lime")
            messagebox.showinfo("Siker", f"Eladás leadva.\nTicket: {r.order_ticket}")
            self._refresh_status()
        else:
            self.label_action_msg.configure(text=r.message, text_color="red")
            messagebox.showerror("Hiba", r.message)

    def on_closing(self):
        # MEM-1: after() callback visszavonása – zombie process védelem
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if self.mt5_client:
            self.mt5_client.disconnect()
        self.destroy()
        sys.exit(0)


def main():
    app = GoldTraderApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
