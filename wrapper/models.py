from dataclasses import dataclass
from typing import List, Optional

@dataclass
class AuthModel:
    ticket: str
    session_id: str
    user_id: str
    expiration: str
    appid: str
    xplay_spaceid: str

@dataclass
class LinkedAccount:
    profile_id: str
    user_id: str
    platform_type: str
    id_on_platform: str
    name_on_platform: str

@dataclass
class Persona:
    tag: str
    enabled: bool
    nickname: str

@dataclass
class Playtime:
    level: int
    pvp_time_played: int
    pve_time_played: int
    total_time_played: int
    total_time_played_hours: int

@dataclass
class Progress:
    level: int
    xp: int
    total_xp: int
    xp_to_level_up: int

@dataclass
class FullProfile:
    max_rank_id: int
    max_rank_points: int
    rank_id: int
    rank_points: int
    top_rank_position: int
    season_id: int
    max_rank: str
    rank: str
    prev_rank_points: int
    next_rank_points: int
    season_code: str
    kills: int
    deaths: int
    abandons: int
    losses: int
    wins: int

@dataclass
class CurrentPlatformInfo:
    platform: str

@dataclass
class RankedProfiles:
    standard_profile: Optional[FullProfile]
    unranked_profile: Optional[FullProfile]
    ranked_profile: Optional[FullProfile]
    casual_profile: Optional[FullProfile]
    warmup_profile: Optional[FullProfile]
    event_profile: Optional[FullProfile]


@dataclass
class Player:
    id: str
    uid: str

    profile_pic_url_146: str
    profile_pic_url_256: str
    profile_pic_url_500: str
    profile_pic_url: str
    linked_accounts: List[LinkedAccount]

    name: str
    persona: Optional[Persona]
    level: int
    xp: int
    total_xp: int
    xp_to_level_up: int

    total_time_played: int
    total_time_played_hours: int
    pvp_time_played: int
    pve_time_played: int

    standard_profile: Optional[FullProfile]
    unranked_profile: Optional[FullProfile]
    ranked_profile: Optional[FullProfile]
    casual_profile: Optional[FullProfile]
    warmup_profile: Optional[FullProfile]
    event_profile: Optional[FullProfile]

