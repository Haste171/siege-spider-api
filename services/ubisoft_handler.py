from dotenv import load_dotenv
import aiohttp
import asyncio
import certifi
import logging
import os
import siegeapi
import ssl

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class UbisoftHandler:
    def __init__(self) -> None:
        self.auth = None

    async def initialize(self, email: str, password: str) -> None:
        # Create SSL context & connector with certifi certificates inside an event loop
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        session = aiohttp.ClientSession(connector=connector)
        logger.info("Initiating Ubisoft API session...")
        self.auth = siegeapi.Auth(email, password, session=session)

    async def convert_uplay_to_profile_id(self, uplay: str) -> str:
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")
        try:
            player = await self.auth.get_player(name=uplay, platform="uplay")
        except siegeapi.FailedToConnect as e:
            logger.error("Invalid credentials passed to UbisoftHandler.initialize()!")
            raise Exception(f"Siege API Error: {e}")

        return player.uid

    async def lookup_via_profile_id(self, profile_id: str) -> siegeapi.Player:
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")

        try:
            player = await self.auth.get_player(uid=profile_id)
        except siegeapi.FailedToConnect as e:
            logger.error("Invalid credentials passed to UbisoftHandler.initialize()!")
            raise Exception(f"Siege API Error: {e}")

        return player

    async def lookup_via_uplay(self, uplay: str) -> siegeapi.Player:
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")

        try:
            player = await self.auth.get_player(name=uplay, platform="uplay")
        except siegeapi.FailedToConnect as e:
            logger.error("Invalid credentials passed to UbisoftHandler.initialize()!")
            raise Exception(f"Siege API Error: {e}")

        return player

    @staticmethod
    def format_profile(profile):
        return {
            "max_rank_id": profile.max_rank_id,
            "max_rank": profile.max_rank,
            "max_rank_points": profile.max_rank_points,
            "rank_id": profile.rank_id,
            "rank": profile.rank,
            "rank_points": profile.rank_points,
            "prev_rank_points": profile.prev_rank_points,
            "next_rank_points": profile.next_rank_points,
            "top_rank_position": profile.top_rank_position,
            "season_id": profile.season_id,
            "season_code": profile.season_code,
            "kills": profile.kills,
            "deaths": profile.deaths,
            "kill_death_ratio": profile.kills / profile.deaths if profile.deaths != 0 else 0.0,
            "wins": profile.wins,
            "losses": profile.losses,
            "win_loss_ratio": profile.wins / profile.losses if profile.losses != 0 else 0.0,
            "abandons": profile.abandons,
        }

    @staticmethod
    def format_player(player: siegeapi.Player):
        return {
            "player": {
                "name": player.name,
                "profile_id": player.id,
                "uuid": player.uid,
                "profile_pic_url": player.profile_pic_url,
                "linked_accounts": [
                    {
                        "profile_id": acc.profile_id,
                        "user_id": acc.user_id,
                        "platform_type": acc.platform_type,
                        "id_on_platform": acc.id_on_platform,
                        "name_on_platform": acc.name_on_platform
                    }
                    for acc in player.linked_accounts
                ],
                "persona": {
                    "tag": player.persona.nickname,
                    "enabled": player.persona.enabled,
                    "nickname": player.persona.nickname,
                },
                "playtime": {
                    "pvp_time_played": player.pvp_time_played,
                    "pve_time_played": player.pve_time_played,
                    "total_time_played": player.total_time_played,
                    "total_time_played_hours": player.total_time_played_hours
                },
                "progress": {
                    "level": player.level,
                    "xp": player.xp,
                    "total_xp": player.total_xp,
                    "xp_to_level_up": player.xp_to_level_up,
                },
                "stats": {
                    mode: UbisoftHandler.format_profile(getattr(player, f"{mode}_profile"))
                    for mode in ["ranked", "standard", "casual", "event", "warmup"]
                }
            }
        }

    async def close(self):
        if self.auth is None:
            return
        await self.auth.close()

async def main():
    ubisoft_email = os.getenv("UBISOFT_EMAIL")
    ubisoft_password = os.getenv("UBISOFT_PASSWORD")
    ubi_handler = UbisoftHandler()

    await ubi_handler.initialize(ubisoft_email, ubisoft_password)

    uid = await ubi_handler.convert_uplay_to_profile_id("Vertigo.._")
    print(f"Player UID: {uid}")

    player = await ubi_handler.lookup_via_profile_id(uid)
    print(f"Player name: {player.name}")

    await ubi_handler.close()

if __name__ == "__main__":
    asyncio.run(main())
