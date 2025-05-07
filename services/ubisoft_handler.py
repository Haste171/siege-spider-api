from datetime import datetime
from dotenv import load_dotenv
from services.linked_account_parser import LinkedAccountParser
from services.siegeapipatched import SiegeAPIPatched, ExpiredAuthException
from services.twitch_handler import TwitchHandler
import aiohttp
import asyncio
import certifi
import logging
import os
import requests
import siegeapi
import ssl

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class UbisoftHandler:
    def __init__(self) -> None:
        self.auth = None
        self.linked_account_parser = LinkedAccountParser()
        self.twitch_handler = TwitchHandler()

    async def initialize(self, email: str, password: str) -> None:
        # Create SSL context & connector with certifi certificates inside an event loop
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        session = aiohttp.ClientSession(connector=connector)
        logger.info("Initiating Ubisoft API session...")
        self.auth = SiegeAPIPatched(email, password, session=session)

    async def convert_uplay_to_profile_id(self, uplay: str) -> str:
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")
        try:
            retries = 2
            while retries > 0:
                try:
                    player = await self.auth.get_player(name=uplay, platform="uplay")
                    break
                except ExpiredAuthException as e:
                    await self.initialize(
                        os.getenv("UBISOFT_EMAIL"),
                        os.getenv("UBISOFT_PASSWORD")
                    )
                    retries -= 1
                    if retries == 0:
                        raise e
                
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

    def format_profile(self, profile, add_risk_score=False):
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
            "risk_score": self.calculate_cheater_risk(profile) if add_risk_score else None
        }

    @staticmethod
    def calculate_cheater_risk(profile):
        """
        Calculate a risk score (0-100) indicating the likelihood that a player is cheating.

        Args:
            profile: Player profile object containing match statistics and rank information

        Returns:
            int: Risk score between 0-100, with higher values indicating higher suspicion
        """
        # 1. Basic calculations and data preparation
        total_matches = profile.wins + profile.losses + profile.abandons
        if total_matches < 5:
            return 15  # Minimum baseline for too few matches to make reliable assessment

        kd_ratio = profile.kills / max(1, profile.deaths)
        wl_ratio = profile.wins / max(1, profile.losses)

        # Extract rank category
        rank_categories = ["Copper", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Champions"]
        rank_category = profile.rank.split()[0] if hasattr(profile, 'rank') and profile.rank else "Gold"

        # 2. Match count confidence scaling
        # Low match counts reduce confidence in all suspicious patterns
        match_count_factor = min(1.0, (total_matches - 5) / 25)

        # 3. Performance Anomaly Detection
        # Base KD expectation is 1.0 across all ranks
        expected_kd = 1.0
        universal_ceiling = 2.2  # Universal suspicious ceiling

        # KD deviation thresholds by rank (how far above 1.0 is suspicious)
        kd_deviation_threshold = {
            "Copper": 1.5, "Bronze": 1.3, "Silver": 1.1, "Gold": 0.9,
            "Platinum": 0.7, "Emerald": 0.5, "Diamond": 0.3, "Champions": 0.2
        }.get(rank_category, 1.0)

        # Apply match count scaling to threshold (more lenient with fewer matches)
        adjusted_threshold = kd_deviation_threshold * (1.5 - (match_count_factor * 0.5))

        # Calculate KD anomaly score
        if kd_ratio <= expected_kd:
            kd_anomaly = 0.0  # Below average KD is never suspicious
        else:
            kd_anomaly = max(0, (kd_ratio - expected_kd) / adjusted_threshold)

        # Apply universal ceiling with match count consideration
        if kd_ratio > universal_ceiling and total_matches > 10:
            # Calculate how much player exceeds the universal ceiling
            ceiling_excess = (kd_ratio - universal_ceiling) / universal_ceiling
            # Scale ceiling_excess penalty by match count
            ceiling_excess *= match_count_factor
            # Add to anomaly score
            kd_anomaly += ceiling_excess * 2.0

        # Apply rank-sensitive scaling
        rank_sensitivity = {
            "Copper": 0.5, "Bronze": 0.6, "Silver": 0.8, "Gold": 1.0,
            "Platinum": 1.3, "Emerald": 1.5, "Diamond": 1.7, "Champions": 2.0
        }.get(rank_category, 1.0)

        # Apply rank sensitivity to anomaly calculation
        kd_anomaly *= rank_sensitivity

        # Factor in win-loss ratio (with rank sensitivity)
        expected_wl = 1.0
        performance_anomaly = kd_anomaly * (1 + max(0, wl_ratio - expected_wl) * 0.5)

        # 4. Match Experience Factor
        # More matches expected for higher ranks
        expected_matches = max(15, 20 + ((profile.rank_id * 4) - 40))

        if total_matches >= expected_matches:
            match_experience_factor = 0.0  # Not suspicious if they've played enough matches
        else:
            match_deficit_ratio = (expected_matches - total_matches) / expected_matches
            match_experience_factor = match_deficit_ratio * 0.7  # Scale down the impact

        # 5. Rank Efficiency - FIXED to prevent false positives for high ranks
        starting_points = 1000
        points_gained = profile.rank_points - starting_points
        points_per_match = points_gained / max(1, total_matches)

        # Improved expected points calculation that scales properly with rank
        base_expected_points = 25 + (5000 / (profile.rank_id + 50))
        rank_multiplier = 1.0 + (0.5 * (profile.rank_id / 40))  # Higher ranks can earn more per match
        expected_points = base_expected_points * rank_multiplier

        # Calculate rank efficiency and apply scaling to prevent extreme values
        if points_per_match <= expected_points:
            rank_efficiency = 0.0  # Not suspicious if not gaining points too quickly
        else:
            rank_efficiency = min(2.0, (points_per_match / expected_points) - 1.0) * 0.5

        # 6. Metric Consistency
        kd_win_alignment = abs((kd_ratio - expected_kd) - (wl_ratio - expected_wl))
        metric_consistency = min(1.0, kd_win_alignment / (1 + (total_matches / 50)))

        # 7. Calculate base risk score with appropriate weights
        # Normalized to be on a more controlled scale
        cheater_risk = (
                (performance_anomaly * 0.35) +
                (match_experience_factor * 0.25) +
                (rank_efficiency * 0.30) +
                (metric_consistency * 0.10)
        )

        # 8. Apply safeguards against false positives
        # Players with below average KD are extremely unlikely to be cheating
        if kd_ratio < 0.9 and total_matches > 20:
            cheater_risk *= 0.3  # Significant reduction for below-average KD
        elif kd_ratio < 1.0 and total_matches > 30:
            cheater_risk *= 0.5  # Moderate reduction for average KD

        # 9. Apply confidence factor based on match count
        confidence_factor = min(1.0, (total_matches / 30))

        # Scale down confidence more aggressively for very low match counts
        if total_matches < 10:
            confidence_factor *= 0.7

        adjusted_risk = cheater_risk * confidence_factor

        # 10. Scale to 0-100 range with better control to prevent maxing out
        # Divide by 1.5 to ensure normal values don't reach 100 too easily
        final_score = min(100, max(0, (adjusted_risk / 1.5) * 100))

        # 11. Final sanity check for edge cases
        # Normal players shouldn't exceed 50 unless extremely suspicious
        if kd_ratio < 1.3 and wl_ratio < 1.3 and total_matches > 50:
            final_score = min(final_score, 40)

        return int(final_score)

    def format_player(self, player: siegeapi.Player):
        return {
            "player": {
                "name": player.name,
                "profile_id": player.id,
                "uuid": player.uid,
                "profile_pic_url": player.profile_pic_url,
                "locker_link": f"https://siege.locker/view?uid={player.id}",
                "statscc_link": f"https://stats.cc/siege/{player.name}/{player.id}",
                "twitch_info": self.get_twitch_info(player.id),
                "current_platform_info": self.get_platform_info(player.id),
                "linked_accounts": [
                    {
                        "profile_id": acc.profile_id,
                        "user_id": acc.user_id,
                        "platform_type": acc.platform_type,
                        "id_on_platform": acc.id_on_platform,
                        "name_on_platform": acc.name_on_platform,
                        "info_link": self._get_info_link(acc),
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
                    mode: self.format_profile(
                        getattr(player, f"{mode}_profile"),
                        add_risk_score=True if mode == "ranked" else False
                    ) for mode in ["ranked", "standard", "casual", "event", "warmup"]
                }
            }
        }

    def get_platform_info(self, uuid: str):
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")

        R6_PLATFORMS = {
            'e3d5ea9e-50bd-43b7-88bf-39794f4e3d40': 'uplay',
            '6e3c99c9-6c3f-43f4-b4f6-f1a3143f2764': 'ps5',
            '76f580d5-7f50-47cc-bbc1-152d000bfe59': 'xbox_scarlett',
            '4008612d-3baf-49e4-957a-33066726a7bc': 'xbox_one',
            'fb4cc4c9-2063-461d-a1e8-84a7d36525fc': 'ps4',
        }

        PROFILE_IDS = [uuid]

        def get_last_used_app_per_profile(applications):
            latest_apps = {}
            for app in applications:
                profile_id = app["profileId"]
                session_date = datetime.fromisoformat(app["lastSessionDate"].replace("Z", "+00:00"))
                if profile_id not in latest_apps or session_date > latest_apps[profile_id][1]:
                    latest_apps[profile_id] = (app["applicationId"], session_date)

            return {
                "platform": R6_PLATFORMS.get(app_id, "Unknown")
                for profile_id, (app_id, _) in latest_apps.items()
            }

        app_ids = ",".join(R6_PLATFORMS.keys())
        url = (
            f"https://public-ubiservices.ubi.com/v3/profiles/applications"
            f"?profileIds={','.join(PROFILE_IDS)}&applicationIds={app_ids}"
        )

        headers = {
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
            "Content-Type": "application/json; charset=UTF-8",
            'Ubi-AppId': '2c2d31af-4ee4-4049-85dc-00dc74aef88f',
            "Ubi-SessionId": self.auth.get_session_id(),
            "Authorization": f"Ubi_v1 t={self.auth.key}"
        }

        response = requests.get(url, headers=headers)
        apps = response.json().get("applications", [])

        result = get_last_used_app_per_profile(apps)
        return result

    def get_twitch_info(self, uuid: str):
        if self.auth is None:
            raise Exception("UbisoftHandler.initialize() must be called before this method!")

        url = "https://public-ubiservices.ubi.com/v1/profiles/me/uplay/graphql"

        headers = {
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
            "Content-Type": "application/json; charset=UTF-8",
            "Ubi-AppId": self.auth.get_app_id(),
            "Ubi-SessionId": self.auth.get_session_id(),
            "Authorization": f"Ubi_v1 t={self.auth.key}"
        }

        payload = {
            "operationName": "GetMultipleUserProfiles",
            "variables": {
                "userIds": [uuid]
            },
            "query": """query GetMultipleUserProfiles($userIds: [String!]!) {
                users(userIds: $userIds) {
                    ...ProfileFragment
                }
            }
            fragment ProfileFragment on User {
                id
                userId
                avatarUrl
                name
                level
                onlineStatus
                games(filterBy: {isOwned: true}) { totalCount }
                lastPlayedGame {
                    node {
                        id
                        name
                        bannerUrl: backgroundUrl
                        platform {
                            id
                            applicationId
                            name
                            type
                        }
                    }
                }
                currentOnlineGame {
                    node {
                        id
                        name
                        bannerUrl: backgroundUrl
                        platform {
                            id
                            applicationId
                            name
                            type
                        }
                    }
                }
                networks {
                    edges {
                        node {
                            id
                            publicCodeName
                        }
                        meta {
                            id
                            name
                        }
                    }
                }
            }"""
        }

        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        networks = data.get("data").get("users")[0].get("networks").get("edges")
        if networks is None:
            return None

        for edge in networks:
            if edge.get("node").get("publicCodeName") == "TWITCH":
                twitch_username = edge.get("meta").get("name")
                return self.twitch_handler.check_stream_data(twitch_username)

        return None

    def _get_info_link(self, acc):
            if acc.platform_type == "steam":
                return f"https://steamid.pro/lookup/{self.linked_account_parser.resolve_steam_vanity_url(acc.id_on_platform)}"
            elif acc.platform_type == "xbl":
                return f"https://www.xbox.com/en-US/play/user/{acc.name_on_platform}"
            elif acc.platform_type == "psn":
                return f"https://www.psntools.com/psn/checker/{acc.name_on_platform}"
            elif acc.platform_type == "amazon":
                return f"https://www.amazon.com/gp/profile/{acc.name_on_platform}/ref=cm_cr_dp_d_gw_tr?ie=UTF8"
            else:
                return None

    @staticmethod
    def _get_locker_link( profile_id: str):
        return f"https://siege.locker/view?uid={profile_id}"

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
