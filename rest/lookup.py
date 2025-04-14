from database.handler import get_db
from database.models import SiegeBan, SiegeBanMetadata
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from pydantic import BaseModel
from services.user.token import get_current_user
from services.webhook_exception_handler import WebhookExceptionHandler
from sqlalchemy.orm import Session
from typing import List, Dict
import logging
import siegeapi

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
router = APIRouter()

@router.get("/lookup/uplay/{uplay}")
async def lookup_profile_id(request: Request, uplay: str, current_user = Depends(get_current_user)):
    try:
        ubisoft_handler = request.app.state.ubisoft_handler

        player: siegeapi.Player = await ubisoft_handler.lookup_via_uplay(uplay)

        await player.load_linked_accounts()
        await player.load_persona()
        await player.load_playtime()
        await player.load_progress()
        await player.load_ranked_v2()

        return ubisoft_handler.format_player(player)
    except siegeapi.InvalidRequest as e:
        if "no results" in str(e).lower():
            return HTTPException(status_code=404, detail="Player not found for the provided Uplay username.")
        elif "missing resource" in str(e).lower():
            return HTTPException(status_code=404, detail="Player not found for the provided Uplay username.")
        else:
            e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
            logger.error(f"Error [Uplay Lookup]: {e_str}")
            WebhookExceptionHandler().send_exception_alert(
                title="Error [Uplay Lookup]",
                e_str=e_str
            )
            raise Exception(e_str)
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Lookup: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{uplay}/uplay")
async def lookup_bans_uplay(request: Request, uplay: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        bans = db.query(SiegeBan).filter(SiegeBan.uplay.ilike(uplay.lower())).all()
        if not bans or len(bans) == 0:
            return HTTPException(status_code=404, detail="No bans found for the provided uplay username.")
        return {"bans": bans}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Ban Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Ban Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{uplay}/uplay/metadata")
async def lookup_bans_metadata_uplay(request: Request, uplay: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # Query the SiegeBans table to retrieve the ban ID(s) for the given Uplay username.
        ban_ids = db.query(SiegeBan.id).filter(SiegeBan.uplay.ilike(uplay.lower())).all()

        if not ban_ids:
            return HTTPException(status_code=404, detail="No bans found for the provided Uplay username.")
        # Extract the Ban IDs from the result
        ban_ids = [ban_id[0] for ban_id in ban_ids]
        # Query the SiegeBanMetadata table to retrieve metadata for the retrieved Ban IDs.
        metadata = db.query(SiegeBanMetadata).filter(SiegeBanMetadata.ban_id.in_(ban_ids)).all()
        if not metadata:
            return HTTPException(status_code=404, detail="No metadata found for the provided Uplay username.")
        return {"metadata": metadata}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Uplay Ban Metadata Lookup]: {e}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Uplay Ban Metadata Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/profile_id/{profile_id}")
async def lookup_profile_id(request: Request, profile_id: str, current_user = Depends(get_current_user)):
    try:
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
    except siegeapi.InvalidRequest as e:
        if "no results" in str(e).lower():
            return HTTPException(status_code=404, detail="Player not found for the provided profile ID.")
        elif "missing resource" in str(e).lower():
            return HTTPException(status_code=404, detail="Player not found for the provided profile ID.")
        else:
            e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
            logger.error(f"Error [Profile ID Lookup]: {e_str}")
            WebhookExceptionHandler().send_exception_alert(
                title="Error [Profile ID Lookup]",
                e_str=e_str
            )
            raise e
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Profile ID Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{profile_id}/profile_id")
async def lookup_bans_profile_id(request: Request, profile_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # Clean up profile_id (e.g., remove spaces, ensure proper matching) -- avoids wildcards
        profile_id = profile_id.strip()

        # Query the database using ilike (case-insensitive comparison)
        bans = db.query(SiegeBan).filter(SiegeBan.profile_id.ilike(profile_id)).all()

        # If no bans are found, raise 404 exception
        if not bans or len(bans) == 0:
            return HTTPException(
                status_code=404,
                detail=f"No bans found for the provided profile ID: {profile_id}"
            )

        # Return results
        return {"bans": bans}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Unexpected error occurred: {e}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Ban Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/lookup/bans/{profile_id}/profile_id/metadata")
async def lookup_bans_metadata_profile_id(request: Request, profile_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    try:
        # will need to get ban id from siege bans table then use that id to get corresponding metadata:
        # Query the SiegeBans table to retrieve the ban ID(s) for the given profile ID.
        ban_ids = db.query(SiegeBan.id).filter(SiegeBan.profile_id.ilike(profile_id)).all()

        if not ban_ids:
            return HTTPException(status_code=404, detail="No bans found for the provided profile ID.")
        # Extract the Ban IDs from the result
        ban_ids = [ban_id[0] for ban_id in ban_ids]
        # Query the SiegeBanMetadata table to retrieve metadata for the retrieved Ban IDs.
        metadata = db.query(SiegeBanMetadata).filter(SiegeBanMetadata.ban_id.in_(ban_ids)).all()
        if not metadata:
            return HTTPException(status_code=404, detail="No metadata found for the provided profile ID.")
        return {"metadata": metadata}
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Profile ID Ban Metadata Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Profile ID Ban Metadata Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

class PlayerIdentifier(BaseModel):
    identifiers: List[Dict[str, int]]

@router.post("/lookup/match")
async def lookup_match_players(
        request: Request,
        data: PlayerIdentifier,
        db: Session = Depends(get_db)
):
    try:
        ubisoft_handler = request.app.state.ubisoft_handler
        players = []
        for item in data.identifiers:
            for key, value in item.items():
                player: siegeapi.Player = await ubisoft_handler.lookup_via_profile_id(key)
                await player.load_linked_accounts()
                await player.load_persona()
                await player.load_playtime()
                await player.load_progress()
                await player.load_ranked_v2()
                data_to_add = ubisoft_handler.format_player(player)
                data_to_add["team"] = value
                players.append(data_to_add)
        return players
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Match Lookup]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Match Lookup]",
            e_str=e_str
        )
        raise Exception(e_str)

@router.get("/bans")
async def get_all_bans(
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
        page: int = 1,
        limit: int = 25,
):
    try:
        # Calculate offset based on page and limit
        offset = (page - 1) * limit

        # Get total count for pagination info
        total_bans = db.query(SiegeBan).count()

        # Get paginated bans
        bans = db.query(SiegeBan).offset(offset).limit(limit).all()

        # If no bans are found, return empty list but not an error
        if not bans:
            return {
                "bans": [],
                "pagination": {
                    "total": total_bans,
                    "page": page,
                    "limit": limit,
                    "pages": (total_bans + limit - 1) // limit  # Ceiling division
                }
            }

        return {
            "bans": bans,
            "pagination": {
                "total": total_bans,
                "page": page,
                "limit": limit,
                "pages": (total_bans + limit - 1) // limit  # Ceiling division
            }
        }
    except Exception as e:
        e_str = f"Exception: {str(e)}\n\nRequest data: {request.url}\nMethod: {request.method}\nHeaders: {dict(request.headers)}\nClient: {request.client}"
        logger.error(f"Error [Get All Bans]: {e_str}")
        WebhookExceptionHandler().send_exception_alert(
            title="Error [Get All Bans]",
            e_str=e_str
        )
        raise Exception(e_str)
