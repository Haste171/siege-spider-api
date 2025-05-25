from logging import exception

from database.handler import SessionLocal
from database.models import SiegeBan, SiegeBanMetadata
from datetime import datetime
from dotenv import load_dotenv
from services.ubisoft_handler import UbisoftHandler
from services.webhook_agent import DiscordWebhookAgent
from services.webhook_exception_handler import WebhookExceptionHandler
import asyncio
import json
import logging
import os
import requests
import ssl
import websockets

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class UbisoftBanListener:
    def __init__(self, email: str, password: str, ubisoft_handler) -> None:
        session_id, ticket = self.get_auth(
            os.getenv("UBISOFT_BAN_R6_APP_ID"),
            email,
            password
        )
        self.session_id = session_id
        self.ticket = ticket
        self.webhook_agent = DiscordWebhookAgent(os.getenv("UBISOFT_BAN_DISCORD_WEBHOOK"))
        self.webhook_exception_handler = WebhookExceptionHandler()
        self.ubisoft_handler = ubisoft_handler

    @staticmethod
    def get_auth(r6_app_id: str, email: str, password: str) -> tuple[str, str]:
        response = requests.post(
            "https://public-ubiservices.ubi.com/v3/profiles/sessions",
            auth=(email, password),
            headers={
                "Ubi-AppId": r6_app_id,
                "Content-Type": "application/json",
                "User-Agent": "PostmanRuntime/7.39.0",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            },
            json={"rememberMe": False},
            allow_redirects=True,
        )
        response = response.json()
        session_id = response["sessionId"]
        ticket = f"Ubi_v1 t={response['ticket']}"
        return session_id, ticket

    async def connect_to_ban_websocket(self):
        websocket_server_link = os.getenv("UBISOFT_BAN_WEBSOCKET")
        try:
            ubi_headers = {
                "Ubi-AppId": os.getenv("UBISOFT_BAN_R6_APP_ID"),
                "Ubi-SessionId": self.session_id,
                "Authorization": self.ticket,
            }

            # Create SSL context directly in this function
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Connect to websocket directly without nesting a function or running a new event loop
            async with websockets.connect(
                    websocket_server_link,
                    additional_headers=ubi_headers,
                    ssl=ssl_context
            ) as ws:
                logger.info("Connected to Ubisoft WebSocket")
                while True:
                    response = await ws.recv()
                    await self._ban_alerts_parser(json.loads(response))

        except Exception as e:
            logger.error(f"Error occurred: {e}")
            self.webhook_exception_handler.send_exception_alert(
                title="Error [Ban Alert Websocket Listener]",
                exception=e
            )
        finally:
            await self.ubisoft_handler.close()

    async def _ban_alerts_parser(self, websocket_output: dict) -> dict:
        reason_map = {
            0: "battleye", # maybe
            1: "toxicity",
            2: "boosting", # maybe
            3: "ddosing",
            4: "cheating",
            5: "botting",
            6: "tos_breach"
        }
        parsed_players = []
        for player in websocket_output.get("content").get("PlayerNamesCrossplay"):
            if player.get("uplay"):
                parsed_players.append(
                    {
                        "uplay": player.get("uplay"),
                        "psn": player.get("psn"),
                        "xbl": player.get("xbl"),
                        "profile_id": await self.ubisoft_handler.convert_uplay_to_profile_id(player.get("uplay"))
                    }
                )

        reformatted_dict = {
            "players": parsed_players,
            "ban_reason_id": websocket_output.get("content").get("BanReason"),
            "ban_reason": reason_map.get(websocket_output.get("content").get("BanReason"), "Unknown"),
            "notification_type": websocket_output.get("notificationType"),
            "source_application_id": websocket_output.get("sourceApplicationId"),
            "date_posted": websocket_output.get("datePosted"),
            "space_id": websocket_output.get("spaceId"),
        }
        logger.info(f"Ban Alerts [{len(reformatted_dict.get('players'))}]: {reformatted_dict.get('ban_reason')}")
        self.webhook_agent.send_notification(
            [
                {
                    "title":"Ban Alert",
                    "description": f"**Ban Reason:** `{reformatted_dict.get('ban_reason').capitalize()} ({reformatted_dict.get('ban_reason_id')})`\n**Date Posted:** `{reformatted_dict.get('date_posted')}`\n**Notification Type:** `{reformatted_dict.get('notification_type')}`\n**Space ID:** `{reformatted_dict.get('space_id')}`\n**Source Application ID:** `{reformatted_dict.get('source_application_id')}`",
                    "color": 5814783
                }
            ]
        )
        self.webhook_agent.send_notification(
            [
                {
                    "title": player.get('uplay'),
                    "author": {
                        "name": "click here for stats",
                        "url": f"https://stats.cc/siege/{player.get('uplay')}/{player.get('profile_id')}",
                        "icon_url": "https://pbs.twimg.com/profile_images/1767303330252853249/2j_BC5NF_400x400.jpg"
                    },
                    "thumbnail": {
                        "url": f"https://ubisoft-avatars.akamaized.net/{player.get('profile_id')}/default_256_256.png"
                    },
                    "color": 5814783
                } for player in reformatted_dict.get("players")
            ]
        )
        await self._send_to_db(reformatted_dict)
        return reformatted_dict

    async def _send_to_db(self, ban_data: dict):
        session = SessionLocal()
        try:
            for player in ban_data["players"]:
                ban = SiegeBan(
                    profile_id=player["profile_id"],
                    uplay=player["uplay"],
                    xbl=player["xbl"],
                    psn=player["psn"],
                    ban_reason=ban_data["ban_reason_id"],
                )
                session.add(ban)
                session.flush()  # ensures ban.id is populated

                metadata = SiegeBanMetadata(
                    ban_id=ban.id,  # link to parent
                    notification_type=ban_data["notification_type"],
                    source_application_id=ban_data["source_application_id"],
                    date_posted=self._convert_datestr_to_datetime(ban_data["date_posted"]),
                    space_id=ban_data["space_id"],
                )
                session.add(metadata)

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB insert error: {e}")
        finally:
            session.close()

    @staticmethod
    def _convert_datestr_to_datetime(date_str: str) -> datetime:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")

async def run(ubisoft_handler):
    try:
        logger.info("Starting Ubisoft Ban Alert Websocket Listener...")
        email = os.getenv("UBISOFT_BAN_EMAIL")
        password = os.getenv("UBISOFT_BAN_PASSWORD")

        ban_listener = UbisoftBanListener(email, password, ubisoft_handler)

        # Simply await the connect_to_ban_websocket method instead of trying to run a new event loop
        # await ban_listener.connect_to_ban_websocket()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        WebhookExceptionHandler().send_exception_alert(
            title="Startup Error [Ban Alert Websocket Listener]",
            exception=e
        )
        raise e

async def main():
    ubisoft_handler = UbisoftHandler()
    await ubisoft_handler.initialize(
        os.getenv("UBISOFT_EMAIL"),
        os.getenv("UBISOFT_PASSWORD")
    )
    await run(ubisoft_handler)

if __name__ == "__main__":
    asyncio.run(main())