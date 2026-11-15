"""Errors are logged with the request that caused them. Needs no database:  pytest tests/test_logging.py -q"""
import logging
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from errors import ApiError, install_error_handlers  # noqa: E402

app = FastAPI()
install_error_handlers(app)


@app.get("/crash")
def crash():
    raise RuntimeError("boom")


@app.get("/misconfigured")
def misconfigured():
    raise ApiError(500, "INTERNAL_ERROR", "Region boundaries file is missing on the server.")


@app.get("/slow")
def slow():
    raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")


@app.get("/missing")
def missing():
    raise ApiError(404, "REGION_NOT_FOUND", "Unknown region 'ES-XX'.")


@app.get("/limit")
def limit(n: int):
    return n


# Starlette re-raises unexpected errors after the handler; the server (uvicorn) would swallow them, the test client must too
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.DEBUG, logger="api.errors")
    return caplog


def _only(logs) -> logging.LogRecord:
    records = [r for r in logs.records if r.name == "api.errors"]
    assert len(records) == 1
    return records[0]


def test_unexpected_error_is_logged_with_traceback_and_request(logs):
    res = client.get("/crash?x=1")
    assert res.status_code == 500
    assert "boom" not in res.text                   # the client sees no internals
    rec = _only(logs)
    assert rec.levelno == logging.ERROR
    assert "GET /crash?x=1" in rec.getMessage()
    assert rec.exc_info and isinstance(rec.exc_info[1], RuntimeError)


def test_server_setup_error_is_logged_as_error(logs):
    assert client.get("/misconfigured").status_code == 500
    rec = _only(logs)
    assert rec.levelno == logging.ERROR
    assert "boundaries file is missing" in rec.getMessage()


def test_query_timeout_is_logged_as_warning(logs):
    assert client.get("/slow").status_code == 504
    rec = _only(logs)
    assert rec.levelno == logging.WARNING
    assert "QUERY_TIMEOUT on GET /slow" in rec.getMessage()


@pytest.mark.parametrize("path, status, code", [("/missing", 404, "REGION_NOT_FOUND"),
                                                ("/limit?n=abc", 400, "INVALID_REQUEST")])
def test_client_errors_are_logged_as_info(logs, path, status, code):
    assert client.get(path).status_code == status
    rec = _only(logs)
    assert rec.levelno == logging.INFO
    assert code in rec.getMessage()
