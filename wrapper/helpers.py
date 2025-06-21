from typing import List, Dict, Optional, Union, Tuple
import re

#############################################################
################## PROGRESS HELPER METHODS ##################
#############################################################
def get_xp_to_next_lvl(lvl: int) -> int:
    if lvl > 37:
        return (lvl - 18) * 500
    if lvl == 0:
        return 500
    if lvl == 1:
        return 1_500
    if lvl in (2, 3):
        return 3_500
    if lvl in (4, 5):
        return 4_000
    if lvl in (6, 7, 8):
        return 4_500
    if lvl in (9, 10):
        return 5_500
    if lvl in (11, 12, 13):
        return 6_000
    if lvl in (14, 15, 16):
        return 6_500
    if lvl in (17, 18, 19):
        return 7_000
    if lvl in (20, 21, 22):
        return 7_500
    if lvl in (23, 24, 25):
        return 8_000
    if lvl in (26, 27, 28):
        return 8_500
    if lvl in (29, 30, 31):
        return 9_000
    if lvl in (32, 33, 34):
        return 9_500
    if lvl in (35, 36, 37):
        return 10_000
    raise ValueError(f"Level {lvl} is not a valid level.")

def get_total_xp(lvl: int, current_xp: int) -> int:
    total = 0
    for level in range(1, lvl):
        total += get_xp_to_next_lvl(level)
    return total + current_xp

#############################################################
################ RANKED DATA HELPER METHODS #################
#############################################################

from wrapper.constants import (
    ranks_v1,
    ranks_v2,
    ranks_v3,
    ranks_v4,
    ranks_v5,
    ranks_v6
)

def season_id_to_code(season_id: int) -> Optional[str]:
    yr = (season_id - 1) // 4 + 1
    ssn = (season_id - 1) % 4 + 1
    return f"Y{yr}S{ssn}"


def season_code_to_id(season_code: str) -> int:
    if not re.match(r'Y\d+S\d+', season_code):
        raise ValueError(f"Season code {season_code} does not match the expected format 'YXSX' where X is a number.")

    code_split = season_code.split('S')
    return (int(code_split[0][1:]) - 1) * 4 + int(code_split[1])


def get_rank_constants(season_number: int = -1) -> List[Dict[str, Union[str, int]]]:
    if 1 <= season_number <= 3:
        return ranks_v1
    if 4 == season_number:
        return ranks_v2
    if 5 <= season_number <= 14:
        return ranks_v3
    if 15 <= season_number <= 22:
        return ranks_v4
    if 23 <= season_number <= 27:
        return ranks_v5
    if 28 <= season_number:
        return ranks_v6
    return ranks_v6


def get_rank_from_mmr(mmr: int | float, season: int = -1) -> Tuple[str, int, int, int]:
    for rank_id, r in enumerate(get_rank_constants(season)):
        if int(r["min_mmr"]) <= int(mmr) <= int(r["max_mmr"]):
            return str(r["name"]), int(r["min_mmr"]), int(r["max_mmr"])+1, int(rank_id)
    return "Unranked", 0, 0, 0

from dataclasses import asdict, is_dataclass
from typing import Any
from wrapper.models import Player, LinkedAccount, FullProfile, Persona, CurrentPlatformInfo

def serialize(obj: Any) -> Any:
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    elif is_dataclass(obj):
        return {k: serialize(v) for k, v in asdict(obj).items()}
    return obj

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
    )