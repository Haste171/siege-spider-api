from database.handler import SessionLocal
from database.models import Match
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime, timedelta
from sqlalchemy import and_
import hashlib
import json
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
router = APIRouter()

class IngestMatchModel(BaseModel):
    identifiers: List[Dict[str, int]]

def generate_match_signature(identifiers: List[Dict[str, int]], time_window_hours: int = 1) -> str:
    """
    Generate a unique signature for a match based on the 10 players and time window.

    Args:
        identifiers: List of player dictionaries with profile_id and team (always 10)
        time_window_hours: Hour window for considering matches as the same (default: 1)

    Returns:
        A hash string representing the match signature
    """
    # Extract all player IDs and sort them (ignore team assignments)
    player_ids = []
    for player_dict in identifiers:
        for player_id in player_dict.keys():
            player_ids.append(player_id)

    # Verify we have exactly 10 players
    if len(player_ids) != 10:
        logger.warning(f"Expected 10 players, got {len(player_ids)}")

    # Sort player IDs to ensure consistent ordering
    player_ids.sort()

    # Create time bucket (round down to nearest hour window)
    current_time = datetime.utcnow()
    hours_since_epoch = int(current_time.timestamp() / 3600)
    bucket_hours = (hours_since_epoch // time_window_hours) * time_window_hours

    # Create signature data
    signature_data = {
        "player_ids": player_ids,
        "time_bucket": bucket_hours
    }

    # Generate hash
    signature_string = json.dumps(signature_data, sort_keys=True)
    signature_hash = hashlib.sha256(signature_string.encode()).hexdigest()

    return signature_hash

@router.post("/ingest/match")
async def ingest_match(request: Request, match: IngestMatchModel):
    """
    Ingest a match with automatic deduplication.
    If the same 10 players are in a match within the time window, return the existing match.
    """
    db = SessionLocal()

    try:
        # Validate we have exactly 10 players
        player_count = len(match.identifiers)
        if player_count != 10:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid player count: {player_count}. Expected exactly 10 players."
            )

        # Generate signature for this match
        match_signature = generate_match_signature(match.identifiers)

        # Look for existing match with same signature in the last 2 hours
        # (2 hours gives buffer for the 1-hour time window)
        time_threshold = datetime.utcnow() - timedelta(hours=2)

        existing_match = db.query(Match).filter(
            and_(
                Match.signature == match_signature,
                Match.created_at >= time_threshold
            )
        ).first()

        if existing_match:
            logger.info(
                f"Duplicate match detected. Returning existing match {existing_match.id} "
                f"(originally created by {existing_match.created_by_host})"
            )

            return {
                "id": existing_match.id,
                "teams": existing_match.teams,
                "is_duplicate": True,
                "message": "Match already exists (created by another client in the same game)",
                "original_created_at": existing_match.created_at.isoformat(),
                "created_by_host": existing_match.created_by_host,
                "current_request_host": request.client.host
            }

        # No existing match found, create new one
        new_match = Match(
            teams=match.identifiers,
            created_by_host=request.client.host,
            signature=match_signature
        )

        db.add(new_match)
        db.commit()
        db.refresh(new_match)

        logger.info(
            f"Created new match {new_match.id} with signature {match_signature} "
            f"by host {request.client.host}"
        )

        return {
            "id": new_match.id,
            "teams": new_match.teams,
            "is_duplicate": False,
            "message": "New match created successfully",
            "created_at": new_match.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error ingesting match: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()