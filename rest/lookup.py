from database.handler import get_db
from database.models import SiegeBan, SiegeBanMetadata
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session
import siegeapi
router = APIRouter()

@router.get("/lookup/profile_id/{profile_id}")
async def lookup_profile_id(request: Request, profile_id: str):
    ubisoft_handler = request.app.state.ubisoft_handler

    player: siegeapi.Player = await ubisoft_handler.lookup_via_profile_id(profile_id)
    await player.load_linked_accounts()
    await player.load_persona()
    await player.load_playtime()
    await player.load_progress()
    await player.load_ranked_v2()
    # await player.load_operators(op_about=False)
    # await player.load_skill_records()
    # await player.load_summaries()
    # await player.load_trends()
    # await player.load_weapons()

    return ubisoft_handler.format_player(player)

@router.get("/lookup/uplay/{uplay}")
async def lookup_profile_id(request: Request, uplay: str):
    ubisoft_handler = request.app.state.ubisoft_handler

    player: siegeapi.Player = await ubisoft_handler.lookup_via_uplay(uplay)
    await player.load_linked_accounts()
    await player.load_persona()
    await player.load_playtime()
    await player.load_progress()
    await player.load_ranked_v2()
    # await player.load_operators(op_about=False)
    # await player.load_skill_records()
    # await player.load_summaries()
    # await player.load_trends()
    # await player.load_weapons()

    return ubisoft_handler.format_player(player)

@router.get("/lookup/bans/{uplay}/uplay")
async def lookup_bans_uplay(uplay: str, db: Session = Depends(get_db)):
    bans = db.query(SiegeBan).filter(SiegeBan.uplay == uplay).all()
    if not bans:
        raise HTTPException(status_code=404, detail="No bans found for the provided uplay username.")
    return {"bans": bans}


@router.get("/lookup/bans/{profile_id}/profile_id")
async def lookup_bans_profile_id(profile_id: str, db: Session = Depends(get_db)):
    bans = db.query(SiegeBan).filter(SiegeBan.profile_id == profile_id).all()
    if not bans:
        raise HTTPException(status_code=404, detail="No bans found for the provided profile ID.")
    return {"bans": bans}