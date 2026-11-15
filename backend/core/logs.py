"""Logging for the API: one format for our own loggers and uvicorn's, written to stderr (Docker collects it).

LOG_LEVEL sets the level of our own loggers (default INFO); uvicorn's are set with its --log-level option.
Errors are logged in one place, the error handlers in errors.py, together with the request that caused them.
"""
import logging

from core.config import LOG_LEVEL

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class _SkipDuplicateTraceback(logging.Filter):
    """errors.py logs an unhandled error with its request. Starlette re-raises it afterwards, and uvicorn would log
    the same traceback a second time, without the request."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Exception in ASGI application")


def setup_logging() -> None:
    logging.basicConfig(level=LOG_LEVEL, format=FORMAT)
    # uvicorn brings its own handlers and format; route its records through ours instead
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.error").addFilter(_SkipDuplicateTraceback())
