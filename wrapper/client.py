from wrapper.models import (
    AuthModel,
    Player,
    LinkedAccount,
    Persona,
    Playtime,
    Progress,
    FullProfile,
    CurrentPlatformInfo,
    RankedProfiles
)
from wrapper.helpers import (
    get_total_xp,
    get_xp_to_next_lvl,
    get_rank_constants,
    get_rank_from_mmr,
    season_id_to_code,
    deserialize_player,
    serialize
)
from wrapper.constants import (
    BASIC_APP_ID,
    ADVANCED_RANKED_APP_ID,
    PLATFORM_GROUP_MAP,
    R6_PLATFORMS
)
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import List, Optional, Literal
import aiohttp
import asyncio
import base64
import dataclasses
from dataclasses import asdict, is_dataclass
import json
import os
import hashlib
from urllib import parse

load_dotenv()

class UbisoftClient:
    def __init__(self, email: str, password: str, redis_client: Optional = None):
        self.email = email
        self.password = password
        self.session = aiohttp.ClientSession()
        self.redis = redis_client
        self.creds_path: str = f"{os.getcwd()}/creds/"

    def get_basic_token(self) -> str:
        auth_str = f"{self.email}:{self.password}"
        return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    def load_creds(self, appid: str) -> AuthModel | None:
        token = self.get_basic_token()
        creds_file_path = os.path.join(self.creds_path, f"{token}/{appid}.json")

        if not os.path.exists(creds_file_path):
            return None

        with open(creds_file_path, "r") as f:
            data = json.load(f)

            if not data:
                return None

            auth_data = AuthModel(**data)

            expiration = datetime.fromisoformat(auth_data.expiration.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            if expiration < now:
                return None

            return auth_data

    def save_creds(self, auth_model: AuthModel) -> None:
        token = self.get_basic_token()
        creds_file_path = os.path.join(self.creds_path, f"{token}/{auth_model.appid}.json")

        if not os.path.exists(os.path.dirname(creds_file_path)):
            os.makedirs(os.path.dirname(creds_file_path))

        with open(creds_file_path, "w") as f:
            json.dump(dataclasses.asdict(auth_model), f)

    async def fetch_auth_model_basic(self, appid: str) -> AuthModel:
        token = self.get_basic_token()

        if creds := self.load_creds(appid):
            return creds

        async with self.session.post(
                "https://public-ubiservices.ubi.com/v3/profiles/sessions",
                headers={
                    "Authorization": f"Basic {token}",
                    "Ubi-AppId": appid,
                    "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
                    "Content-Type": "application/json"
                },
                json={"rememberMe": True}
        ) as resp:
            data = await resp.json()
            model = AuthModel(
                ticket=data["ticket"],
                session_id=data["sessionId"],
                user_id=data["userId"],
                expiration=data["expiration"],
                appid=appid,
                xplay_spaceid="0d2ae42d-4c27-4cb7-af6c-2099062302bb"
            )
            self.save_creds(model)
            return model

    async def fetch_auth_model_advanced(self, appid: str) -> AuthModel:
        if creds := self.load_creds(appid):
            return creds

        basic_auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

        async with self.session.post(
                "https://public-ubiservices.ubi.com/v3/profiles/sessions",
                headers={
                    "Authorization": f"Ubi_v1 t={basic_auth.ticket}",
                    "Ubi-AppId": appid,
                    "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
                    "Content-Type": "application/json"
                },
                json={"rememberMe": True}
        ) as resp:
            data = await resp.json()
            model = AuthModel(
                ticket=data["ticket"],
                session_id=data["sessionId"],
                user_id=data["userId"],
                expiration=data["expiration"],
                appid=appid,
                xplay_spaceid="0d2ae42d-4c27-4cb7-af6c-2099062302bb"
            )
            self.save_creds(model)
            return model

    async def get_player(self,
         name: Optional[str] = None,
         uid: Optional[str] = None,
         platform: Literal["uplay", "xbl", "psn"] = "uplay",
         get_twitch: bool = True,
         get_current_platform: bool = True
    ) -> Player:

        # Build cache key
        key = None
        if self.redis:
            if uid:
                key_data = {
                    "uid": uid,
                }
            elif name:
                key_data = {
                    "name": name,
                }
            key = "player:" + hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

            # Try Redis cache
            cached = self.redis.cache_for_key(key, lambda: None)
            if cached:
                print(f"Cache hit on {uid}")
                return deserialize_player(cached)

        # Not cached, make the full request
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)
        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        if name:
            url = f"https://public-ubiservices.ubi.com/v3/profiles?nameOnPlatform={parse.quote(name)}&platformType={parse.quote(platform)}"
        elif uid:
            url = f"https://public-ubiservices.ubi.com/v3/users/{uid}/profiles?platformType={parse.quote(platform)}"
        else:
            raise Exception("Please input a name or uid to search for a player.")

        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()
            profile_id = data.get("profiles")[0].get("profileId")
            linked_account_data = await self.get_linked_accounts(profile_id, get_twitch)
            persona_data = await self.get_persona(profile_id)
            playtime_data = await self.get_playtime(profile_id)
            progress_data = await self.get_progress(profile_id)
            ranked_profiles_data = await self.get_ranked_profiles(profile_id, platform)
            current_platform_info = None
            if get_current_platform:
                current_platform_info = await self.get_current_platform_info(profile_id)

            model = Player(
                id=profile_id,
                uid=profile_id,
                profile_pic_url_146=f"https://ubisoft-avatars.akamaized.net/{profile_id}/default_146_146.png",
                profile_pic_url_256=f"https://ubisoft-avatars.akamaized.net/{profile_id}/default_256_256.png",
                profile_pic_url_500=f"https://ubisoft-avatars.akamaized.net/{profile_id}/default_tall.png",
                profile_pic_url=f"https://ubisoft-avatars.akamaized.net/{profile_id}/default_256_256.png",
                linked_accounts=linked_account_data,
                name=data.get("profiles")[0].get("nameOnPlatform"),
                persona=persona_data,
                level=playtime_data.level,
                xp=progress_data.xp,
                total_xp=progress_data.total_xp,
                xp_to_level_up=progress_data.xp_to_level_up,
                total_time_played=playtime_data.total_time_played,
                total_time_played_hours=playtime_data.total_time_played_hours,
                pvp_time_played=playtime_data.pvp_time_played,
                pve_time_played=playtime_data.pve_time_played,
                standard_profile=ranked_profiles_data.standard_profile,
                unranked_profile=ranked_profiles_data.unranked_profile,
                ranked_profile=ranked_profiles_data.ranked_profile,
                casual_profile=ranked_profiles_data.casual_profile,
                warmup_profile=ranked_profiles_data.warmup_profile,
                event_profile=ranked_profiles_data.event_profile,
                current_platform_info=current_platform_info
            )

            if self.redis and key:
                try:
                    self.redis.redis.setex(key, 900, json.dumps(serialize(model)))
                except Exception as e:
                    print(e)
                    pass  # silent fail on cache store

            return model

    @staticmethod
    def serialize(obj):
        if isinstance(obj, list):
            return [serialize(item) for item in obj]
        elif is_dataclass(obj):
            return {k: serialize(v) for k, v in asdict(obj).items()}
        return obj

    @staticmethod
    def deserialize_player(data: dict) -> Player:
        return Player(
            id=data["id"],
            uid=data["uid"],
            profile_pic_url_146=data["profile_pic_url_146"],
            profile_pic_url_256=data["profile_pic_url_256"],
            profile_pic_url_500=data["profile_pic_url_500"],
            profile_pic_url=data["profile_pic_url"],
            linked_accounts=[LinkedAccount(**a) for a in data["linked_accounts"]],
            name=data["name"],
            persona=Persona(**data["persona"]) if data["persona"] else None,
            level=data["level"],
            xp=data["xp"],
            total_xp=data["total_xp"],
            xp_to_level_up=data["xp_to_level_up"],
            total_time_played=data["total_time_played"],
            total_time_played_hours=data["total_time_played_hours"],
            pvp_time_played=data["pvp_time_played"],
            pve_time_played=data["pve_time_played"],
            standard_profile=FullProfile(**data["standard_profile"]) if data["standard_profile"] else None,
            unranked_profile=FullProfile(**data["unranked_profile"]) if data["unranked_profile"] else None,
            ranked_profile=FullProfile(**data["ranked_profile"]) if data["ranked_profile"] else None,
            casual_profile=FullProfile(**data["casual_profile"]) if data["casual_profile"] else None,
            warmup_profile=FullProfile(**data["warmup_profile"]) if data["warmup_profile"] else None,
            event_profile=FullProfile(**data["event_profile"]) if data["event_profile"] else None,
            current_platform_info=CurrentPlatformInfo(**data["current_platform_info"]) if data["current_platform_info"] else None,
        )


    async def get_linked_accounts(self, profile_id: str, get_twitch=True) -> List[LinkedAccount]:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)
        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        url = f"https://public-ubiservices.ubi.com/v3/profiles?userId={profile_id}"
        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()

            linked_accounts = []
            if "profiles" in data:
                for profile_data in data["profiles"]:
                    linked_account = LinkedAccount(
                        profile_id=profile_data.get("profileId", ""),
                        user_id=profile_data.get("userId", ""),
                        platform_type=profile_data.get("platformType", ""),
                        id_on_platform=profile_data.get("idOnPlatform", ""),
                        name_on_platform=profile_data.get("nameOnPlatform", "")
                    )
                    linked_accounts.append(linked_account)

            if get_twitch:
                twitch_info = await self._get_twitch_info(profile_id)
                if twitch_info is not None:
                    linked_accounts.append(twitch_info)

            return linked_accounts

    async def get_persona(self, profile_id: str) -> Persona:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        url = f"https://public-ubiservices.ubi.com/v1/profiles/{profile_id}/persona?spaceId={auth.xplay_spaceid}"
        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()

            obj_data = data.get('obj', {})
            enabled = obj_data.get('Enabled', False) if obj_data else False

            persona = Persona(
                tag=data.get('personaTag', ''),
                enabled=enabled,
                nickname=data.get('nickname', '')
            )

            return persona

    async def get_playtime(self, profile_id: str) -> Playtime:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        url = (
            f"https://public-ubiservices.ubi.com/v1/profiles/stats?"
            f"profileIds={profile_id}&"
            f"spaceId={auth.xplay_spaceid}&"
            f"statNames=PPvPTimePlayed,PPvETimePlayed,PTotalTimePlayed,PClearanceLevel"
        )
        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()

            if not isinstance(data, dict):
                raise ValueError(f"Failed to load playtime. Response: {data}")

            profiles = data.get("profiles", [])
            if not profiles:
                raise ValueError("No profile data found in playtime response")

            stats = profiles[0].get("stats", {})

            level = int(stats.get("PClearanceLevel", {}).get("value", 0))
            pvp_time_played = int(stats.get("PPvPTimePlayed", {}).get("value", 0))
            pve_time_played = int(stats.get("PPvETimePlayed", {}).get("value", 0))
            total_time_played = int(stats.get("PTotalTimePlayed", {}).get("value", 0))
            total_time_played_hours = total_time_played // 3600 if total_time_played else 0

            playtime = Playtime(
                level=level,
                pvp_time_played=pvp_time_played,
                pve_time_played=pve_time_played,
                total_time_played=total_time_played,
                total_time_played_hours=total_time_played_hours
            )

            return playtime

    async def get_progress(self, profile_id: str) -> Progress | dict:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": "83564d31-7cd7-4bc0-a763-6524e78d1a7f",
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        url = f"https://public-ubiservices.ubi.com/v1/profiles/{profile_id}/global/ubiconnect/economy/api/metaprogression"

        async with self.session.get(url, headers=headers) as resp:
            try:
                data = await resp.json()

                if not isinstance(data, dict):
                    raise ValueError(f"Failed to load progress. Response: {data}")

                level = int(data.get("level", 0))
                xp = int(data.get("xp", 0))
                total_xp = get_total_xp(level, xp)
                xp_to_level_up = get_xp_to_next_lvl(level) - xp

                progress = Progress(
                    level=level,
                    xp=xp,
                    total_xp=total_xp,
                    xp_to_level_up=xp_to_level_up
                )

                return progress

            except aiohttp.ContentTypeError:
                text = await resp.text()
                return {
                    "error": "Non-JSON response",
                    "status": resp.status,
                    "reason": resp.reason,
                    "text": text
                }

    async def get_ranked_profiles(self, profile_id: str, platform_group: str) -> RankedProfiles | dict:
        auth = await self.fetch_auth_model_advanced(ADVANCED_RANKED_APP_ID)

        platform_group_value = PLATFORM_GROUP_MAP.get(platform_group.lower(), platform_group.lower())

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": "e3d5ea9e-50bd-43b7-88bf-39794f4e3d40",
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
        }

        url = (
            f"https://public-ubiservices.ubi.com/v2/spaces/{auth.xplay_spaceid}/title/r6s/skill/full_profiles?"
            f"profile_ids={profile_id}"
            f"&platform_families={platform_group_value}"
        )
        async with self.session.get(url, headers=headers) as resp:
            try:
                data = await resp.json()

                if not isinstance(data, dict):
                    raise ValueError(f"Failed to load full profiles. Response: {data}")

                standard_profile = None
                unranked_profile = None
                ranked_profile = None
                casual_profile = None
                warmup_profile = None
                event_profile = None

                boards = data.get('platform_families_full_profiles', [])[0].get('board_ids_full_profiles', [])

                for board in boards:
                    board_id = board.get('board_id')
                    full_profiles = board.get('full_profiles', [])

                    if not full_profiles:
                        continue

                    profile_data = full_profiles[0]
                    profile = profile_data.get("profile", {})
                    season_stats = profile_data.get("season_statistics", {})
                    match_outcomes = season_stats.get("match_outcomes", {})

                    max_rank_id = profile.get("max_rank", 0)
                    max_rank_points = profile.get("max_rank_points", 0)
                    rank_id = profile.get("rank", 0)
                    rank_points = profile.get("rank_points", 0)
                    top_rank_position = profile.get("top_rank_position", 0)
                    season_id = profile.get("season_id", 0)

                    rank_constants = get_rank_constants(season_id)
                    rank_name, min_mmr, max_mmr, _ = get_rank_from_mmr(rank_points, season_id)
                    max_rank_name = rank_constants[max_rank_id].get("name", '') if max_rank_id < len(rank_constants) else ''
                    season_code = season_id_to_code(season_id)

                    kills = season_stats.get("kills", 0)
                    deaths = season_stats.get("deaths", 0)
                    abandons = match_outcomes.get("abandons", 0)
                    losses = match_outcomes.get("losses", 0)
                    wins = match_outcomes.get("wins", 0)

                    full_profile = FullProfile(
                        max_rank_id=max_rank_id,
                        max_rank_points=max_rank_points,
                        rank_id=rank_id,
                        rank_points=rank_points,
                        top_rank_position=top_rank_position,
                        season_id=season_id,
                        max_rank=max_rank_name,
                        rank=rank_name,
                        prev_rank_points=min_mmr,
                        next_rank_points=max_mmr,
                        season_code=season_code,
                        kills=kills,
                        deaths=deaths,
                        abandons=abandons,
                        losses=losses,
                        wins=wins
                    )

                    if board_id == 'standard':
                        standard_profile = full_profile
                    elif board_id == 'unranked':
                        unranked_profile = full_profile
                    elif board_id == 'ranked':
                        ranked_profile = full_profile
                    elif board_id == 'casual':
                        casual_profile = full_profile
                    elif board_id == 'warmup':
                        warmup_profile = full_profile
                    elif board_id == 'event':
                        event_profile = full_profile

                ranked_profiles = RankedProfiles(
                    standard_profile=standard_profile,
                    unranked_profile=unranked_profile,
                    ranked_profile=ranked_profile,
                    casual_profile=casual_profile,
                    warmup_profile=warmup_profile,
                    event_profile=event_profile
                )

                return ranked_profiles

            except aiohttp.ContentTypeError:
                text = await resp.text()
                return {
                    "error": "Non-JSON response",
                    "status": resp.status,
                    "reason": resp.reason,
                    "text": text
                }

    async def get_current_platform_info(self, uuid: str) -> CurrentPlatformInfo:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

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
            f"?profileIds={','.join([uuid])}&applicationIds={app_ids}"
        )

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
            "Content-Type": "application/json; charset=UTF-8"
        }

        async with self.session.get(url, headers=headers) as resp:
            data = await resp.json()
            apps = data.get("applications", [])
            result = get_last_used_app_per_profile(apps)
            return CurrentPlatformInfo(
                result.get("platform", "Unknown"),
            )

    async def _get_twitch_info(self, uuid: str) -> Optional[LinkedAccount]:
        auth = await self.fetch_auth_model_basic(BASIC_APP_ID)

        url = "https://public-ubiservices.ubi.com/v1/profiles/me/uplay/graphql"

        headers = {
            "Authorization": f"Ubi_v1 t={auth.ticket}",
            "Ubi-AppId": auth.appid,
            "Ubi-SessionId": auth.session_id,
            "User-Agent": "UbiServices_SDK_2020.Release.58_PC64_ansi_static",
            "Content-Type": "application/json; charset=UTF-8"
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

        async with self.session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()

            if not data.get("data") or not data.get("data").get("users"):
                return None

            networks = data.get("data").get("users")[0].get("networks", {}).get("edges")
            if networks is None:
                return None

            for edge in networks:
                if edge.get("node", {}).get("publicCodeName") == "TWITCH":
                    twitch_username = edge.get("meta", {}).get("name")
                    twitch_id = edge.get("meta", {}).get("id")
                    return LinkedAccount(
                        profile_id=uuid,
                        user_id=uuid,
                        platform_type="twitch",
                        id_on_platform=twitch_id,
                        name_on_platform=twitch_username
                    )

            return None

    async def close(self):
        await self.session.close()

async def main():
    # Examples
    ubisoft_email = os.getenv("UBISOFT_EMAIL")
    ubisoft_password = os.getenv("UBISOFT_PASSWORD")
    client = UbisoftClient(email=ubisoft_email, password=ubisoft_password, redis_client=None)
    profile_id = "adb38455-fb57-47cb-9c7b-720a4f19e834"

    player = await client.get_player(name="Ext", platform="uplay")
    player2 = await client.get_player(uid=profile_id, platform="uplay")
    print(player)
    print(player2)

    linked = await client.get_linked_accounts(profile_id)
    persona = await client.get_persona(profile_id)
    playtime = await client.get_playtime(profile_id)
    progress = await client.get_progress(profile_id)
    ranked_data = await client.get_ranked_profiles(profile_id, "uplay")
    print(linked)
    print(persona)
    print(playtime)
    print(progress)
    print(ranked_data)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
