import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

DEFAULT_BOT_TOKEN = "8950289524:AAGBA4jWhlNhdIVGLhD8G0spuATqdPLX2l4"
DEFAULT_CHAT_ID = "8989112896"

def send_telegram_notification(text: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN)
    chat_id = os.getenv("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID)
    if not bot_token or not chat_id:
        logger.warning("Telegram notification skipped: credentials not set.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        # If Markdown parsing failed (e.g. unescaped markdown chars), retry as plain text
        try:
            payload.pop("parse_mode", None)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as retry_e:
            logger.error(f"Failed to dispatch Telegram message retry: {retry_e}")
            return False
    except Exception as e:
        logger.error(f"Failed to dispatch Telegram notification: {e}")
        return False
