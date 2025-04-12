import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class DiscordWebhookAgent:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_notification(self, embeds: List[Dict]):
        data = {
            "embeds": embeds
        }

        response = requests.post(self.webhook_url, json=data)

        if response.status_code == 204:
            logger.info("Webhook sent successfully.")
        else:
            logger.error(f"Failed to send webhook: {response.status_code}, {response.text}")
