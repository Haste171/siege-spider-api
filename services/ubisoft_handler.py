from dotenv import load_dotenv
from services.linked_account_parser import LinkedAccountParser
from services.twitch_handler import TwitchHandler
from typing import List
from wrapper.client import UbisoftClient
from wrapper.models import LinkedAccount, Player
from services.statscc_handler import StatsCCHandler
from services.redis_client import RedisClient
import asyncio
import logging
import os
import json

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class UbisoftHandler:
    def __init__(self) -> None:
        self.linked_account_parser = LinkedAccountParser()
        self.twitch_handler = TwitchHandler()
        self.statscc_handler = StatsCCHandler()
        ubisoft_email = os.getenv("UBISOFT_EMAIL")
        ubisoft_password = os.getenv("UBISOFT_PASSWORD")
        self.redis_client = RedisClient()
        self.client = None

    async def initialize(self, email: str, password: str):
        self.client = UbisoftClient(email=email, password=password, redis_client=self.redis_client)

    async def lookup_via_profile_id(self, profile_id: str) -> Player:
        player = await self.client.get_player(uid=profile_id, platform="uplay")
        return player

    async def lookup_via_uplay(self, uplay: str) -> Player:
        player = await self.client.get_player(name=uplay, platform="uplay")
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

    def format_player(self, player: Player):
        return {
            "player": {
                "name": player.name,
                "profile_id": player.id,
                "uuid": player.uid,
                "profile_pic_url": player.profile_pic_url,
                "reputation_gg_status": self.get_rep_gg_status(player.id),
                "r6_tracker_link": f"https://r6.tracker.network/r6siege/profile/ubi/{player.name}/overview",
                "statscc_link": f"https://stats.cc/siege/{player.name}/{player.id}",
                "twitch_info": self.get_twitch_info(player.linked_accounts),
                "current_platform_info": player.current_platform_info,
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
                    ) for mode in ["ranked", "standard", "casual", "event", "warmup"] if getattr(player, f"{mode}_profile") is not None
                }
            }
        }

    def get_rep_gg_status(self, profile_id: str):
        key = f"repgg:{profile_id}"

        if self.redis_client:
            cached = self.redis_client.cache_for_key(key, lambda: None)
            if cached:
                logger.info(f"[repgg] Cache hit on {profile_id}")
                if cached.get("profileBans"):
                    result = cached["profileBans"][0]
                    return result

        try:
            response = self.statscc_handler.fetch_by_profile_id(profile_id)
            if self.redis_client:
                self.redis_client.redis.setex(key, 900, json.dumps(response))
            if response.get("profileBans"):
                result = response["profileBans"][0]
                return result
        except Exception as e:
            logger.error(f"Encountered exception when attempting to fetch info from stats.cc (profile id: {profile_id}). Error: \n\n{e}")

    def get_twitch_info(self, linked_accounts: List[LinkedAccount]):
        if not linked_accounts:
            return None

        twitch_users = [acc.name_on_platform for acc in linked_accounts if acc.platform_type == "twitch"]
        if not twitch_users:
            return None

        twitch_username = twitch_users[0]
        stream_key = f"twitch:stream_data:{twitch_username}"

        # Check stream cache
        if self.redis_client:
            cached_stream = self.redis_client.cache_for_key(stream_key, lambda: None)
            if cached_stream:
                return cached_stream

        try:
            # Fetch live data
            response = self.twitch_handler.check_stream_data(twitch_username)

            if self.redis_client:
                # Cache stream data
                self.redis_client.redis.setex(stream_key, 900, json.dumps(response))

            return response
        except Exception as e:
            logger.error(f"Error fetching Twitch stream data for {twitch_username}: {e}")
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
        await self.client.close()

async def main():

    ubi_handler = UbisoftHandler()

    player = await ubi_handler.lookup_via_uplay("Vertigo.._")
    print(f"Player name: {player.name}")

    await ubi_handler.close()

if __name__ == "__main__":
    asyncio.run(main())
