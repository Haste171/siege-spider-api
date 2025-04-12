import os
from dotenv import load_dotenv
from services.webhook_agent import DiscordWebhookAgent
from typing import List, Dict

load_dotenv()

class WebhookExceptionHandler:
    def __init__(self):
        self.webhook_agent = DiscordWebhookAgent(os.getenv("EXCEPTION_HANDLER_WEBHOOK"))

    def send_exception_alert(self, title: str,  exception: Exception = None, e_str: str = None):
        if e_str and not exception:
            exception = e_str
        self.webhook_agent.send_notification(
            [
                {
                    "title": f"{title}",
                    "description": f"```python\n{exception}```",
                    "color": 16734310
                }
            ]
        )