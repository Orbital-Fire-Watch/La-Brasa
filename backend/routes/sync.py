"""Data sync: POST /api/sync starts fetch FIRMS -> harmonise -> load into the database, GET /api/sync reports it."""
from fastapi import APIRouter

from dtos import SyncStatus
from errors import ERRORS_DOC
from services.sync import start_sync, sync_status

router = APIRouter(prefix="/api")


@router.post("/sync", status_code=202, response_model=SyncStatus, responses=ERRORS_DOC, tags=["Sync"])
def start():
    return start_sync()


@router.get("/sync", response_model=SyncStatus, responses=ERRORS_DOC, tags=["Sync"])
def status():
    return sync_status()
