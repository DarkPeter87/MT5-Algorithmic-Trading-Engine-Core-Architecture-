import requests
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_trade_alert(self, is_buy: bool, symbol: str, lot_size: float, entry_price: float, sl: float, tp: float):
        if not self.enabled:
            return
            
        if not self.token or not self.chat_id:
            logger.warning("Telegram token vagy chat_id hiányzik. Nincs üzenetküldés.")
            return

        direction_emoji = "🟢 BUY" if is_buy else "🔴 SELL"
        
        message = (
            f"<b>{direction_emoji} alert</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Lot size:</b> {lot_size:.2f}\n"
            f"<b>Entry Price:</b> {entry_price:.2f}\n"
            f"<b>SL:</b> {sl:.2f} | <b>TP:</b> {tp:.2f}\n"
        )
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            response = requests.post(self.base_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram üzenet sikeresen elküldve.")
        except Exception as e:
            logger.error("Hiba a Telegram üzenet küldésekor: %s", e)
