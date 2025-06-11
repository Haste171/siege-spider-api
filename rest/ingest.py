from database.handler import SessionLocal
from database.models import Match
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
router = APIRouter()

class IngestMatchModel(BaseModel):
    identifiers: List[Dict[str, int]]

@router.post("/ingest/match")
async def ingest_match(request: Request, match: IngestMatchModel):
    db = SessionLocal()

    new_match = Match(teams=match.identifiers, created_by_host=request.client.host)
    db.add(new_match)
    db.commit()
    db.refresh(new_match)
    return {"id": new_match.id, "teams": new_match.teams}
