from database.models import Client
from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from database.handler import SessionLocal
from pydantic import BaseModel
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
router = APIRouter()

class IngestMatchModel(BaseModel):
    identifiers: List[Dict[str, int]]

@router.get("/client/version")
async def get_client_version():
    db = SessionLocal()

    client = db.query(Client).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client version not found")

    return {"current_version": client.current_version, "download_url": client.download_url}