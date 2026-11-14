"""POST /api/sync and GET /api/sync: fetch the newest FIRMS data, harmonise it and reload the database.

The work is pipeline/sync_data.py (fetch_firms -> harmonisation/run_pipeline.py --incremental -> load_to_db
--incremental). It takes seconds up to a minute, longer than a request should take, so POST starts it in a
background thread and GET reports its status.
- One sync at a time: a POST while one runs returns the running one instead of starting a second.
- The status lives in this process. That is enough because uvicorn runs one worker (backend/Dockerfile); with
  several workers each would keep its own status and could start its own sync.
- After the load the event index is rebuilt before the status says "succeeded", so requests after that
  already get the new events.
"""
import datetime as dt
import logging
import sys
import threading
from types import ModuleType
from typing import Any

from core.config import PIPELINE_DIR, SYNC_AVAILABLE
from errors import ApiError
from services.events import refresh_index

log = logging.getLogger(__name__)

_lock = threading.Lock()
_status: dict[str, Any] = {"state": "idle", "step": None, "started_at": None, "finished_at": None,
                           "new_rows": None, "message": None}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _update(**fields: Any) -> None:
    with _lock:
        _status.update(fields)


def sync_status() -> dict[str, Any]:
    with _lock:
        return dict(_status)


def start_sync() -> dict[str, Any]:
    if not SYNC_AVAILABLE:
        raise ApiError(501, "NOT_IMPLEMENTED", "Data sync is not set up on this server (FIRMS_MAP_KEY or the pipeline is missing).")
    with _lock:
        if _status["state"] != "running":
            _status.update(state="running", step=None, started_at=_now(), finished_at=None, new_rows=None, message=None)
            threading.Thread(target=_run, name="data-sync", daemon=True).start()
        return dict(_status)


def _pipeline() -> ModuleType:
    """pipeline/sync_data.py imports its neighbours as top-level modules (load_to_db, ingestion), so its folder
    goes on the path. Imported only when a sync starts: the API itself does not need the pipeline packages."""
    if str(PIPELINE_DIR) not in sys.path:
        sys.path.insert(0, str(PIPELINE_DIR))
    import sync_data
    return sync_data


def _run() -> None:
    try:
        result = _pipeline().sync_data(on_step=lambda step: _update(step=step))
        refresh_index()
        _update(state="succeeded", finished_at=_now(), new_rows=result.new_rows)
    except Exception as err:  # whatever fails, the status has to leave "running" and say why
        log.exception("Data sync failed")
        _update(state="failed", finished_at=_now(), message=str(err) or type(err).__name__)
