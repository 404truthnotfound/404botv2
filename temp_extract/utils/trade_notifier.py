import logging
import requests

class TradeNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_message(self, message):
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'Markdown'  # Optional: Use Markdown for formatting
        }
        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()  # Raise an error for bad responses
        except Exception as e:
            logging.error(f"Failed to send message: {str(e)}")

    def notify_trade(self, trade_data, success=True):
        status = "Successful" if success else "Unsuccessful"
        message = f"Trade Status: {status}\nDetails: {trade_data}"
        self.send_message(message)
