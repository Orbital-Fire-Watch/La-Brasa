"""Meteomatics Weather API client: point time series as tidy DataFrames, cached on disk.

Request format (https://www.meteomatics.com/en/api/request/):
    https://api.meteomatics.com/<validdatetime>/<parameters>/<location>/<format>?<optionals>
    validdatetime: <start>--<end>:P1D      parameters: comma-separated, e.g. t_2m:C,precip_24h:mm
    location:      lat,lon+lat,lon+...     (more than 10 points needs the "area requests" option)
    format:        csv (semicolon-separated)

Credentials come from METEOMATICS_USERNAME / METEOMATICS_PASSWORD (environment or La-Brasa/.env)
and are sent with HTTP basic auth, never in the URL. They are never logged.
"""
from __future__ import annotations

import hashlib
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests


# Placeholders Meteomatics uses for "no value" (invalid / not available).
MISSING_VALUES = (-999.0, -666.0)


class MeteomaticsError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class MeteomaticsAuthError(MeteomaticsError):
    pass


def load_env_file(path: Path) -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE lines, # comments). Does not override real env vars."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def credentials(env_file: Path) -> tuple[str, str]:
    file_values = load_env_file(env_file)
    user = os.environ.get("METEOMATICS_USERNAME") or file_values.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD") or file_values.get("METEOMATICS_PASSWORD")
    if not user or not password:
        raise MeteomaticsAuthError(
            f"METEOMATICS_USERNAME / METEOMATICS_PASSWORD missing (environment or {env_file}).")
    return user, password


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def day_chunks(start: date, end: date, chunk_days: int) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=chunk_days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def parse_csv(text: str, points: list[tuple[float, float]]) -> pd.DataFrame:
    """Parse a Meteomatics CSV into columns lat, lon, validdate, <parameters>.

    Multi-point responses carry lat;lon columns; single-point responses only validdate.
    """
    df = pd.read_csv(io.StringIO(text), sep=";")
    if "validdate" not in df.columns:
        raise MeteomaticsError(f"Unexpected CSV header: {list(df.columns)[:6]}")
    if "lat" not in df.columns:
        if len(points) != 1:
            raise MeteomaticsError("CSV without lat/lon for a multi-point request.")
        df.insert(0, "lat", points[0][0])
        df.insert(1, "lon", points[0][1])
    df["validdate"] = pd.to_datetime(df["validdate"], utc=True)
    value_cols = [c for c in df.columns if c not in ("lat", "lon", "validdate")]
    df[value_cols] = df[value_cols].apply(pd.to_numeric, errors="coerce")
    df[value_cols] = df[value_cols].mask(df[value_cols].isin(MISSING_VALUES))
    return df


@dataclass
class MeteomaticsClient:
    username: str
    password: str
    cache_dir: Path
    base_url: str = "https://api.meteomatics.com"
    model: str = "mix"
    max_points_per_request: int = 10
    chunk_days: int = 366
    timeout_s: float = 120
    max_retries: int = 4
    pause_between_requests_s: float = 0.5
    parallel_requests: int = 1
    progress: bool = False
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.session = self.session or requests.Session()
        self.session.auth = (self.username, self.password)

    # --- low level -------------------------------------------------------------------------
    def build_path(self, start: datetime, end: datetime, step: str, parameters: list[str],
                   points: list[tuple[float, float]], fmt: str = "csv") -> str:
        location = "+".join(f"{lat:.4f},{lon:.4f}" for lat, lon in points)
        return f"/{iso(start)}--{iso(end)}:{step}/{','.join(parameters)}/{location}/{fmt}"

    def _get(self, path: str, params: dict[str, str] | None = None) -> requests.Response:
        url = self.base_url.rstrip("/") + path
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
            except requests.RequestException as exc:  # network error: retry
                if attempt == self.max_retries:
                    raise MeteomaticsError(f"Network error for {path}: {exc}") from exc
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (401, 403):
                raise MeteomaticsAuthError(
                    f"HTTP {resp.status_code}: credentials rejected or request not covered by the account. "
                    f"{resp.text[:300]}")
            if resp.status_code in (408, 429) or resp.status_code >= 500:   # 408 = server-side query timeout
                if attempt == self.max_retries:
                    raise MeteomaticsError(f"HTTP {resp.status_code} for {path}: {resp.text[:300]}",
                                           status=resp.status_code)
                time.sleep(2 ** attempt * 2)
                continue
            if resp.status_code != 200:
                raise MeteomaticsError(f"HTTP {resp.status_code} for {path}: {resp.text[:500]}")
            return resp
        raise MeteomaticsError("unreachable")

    def user_stats(self) -> dict:
        return self._get("/user_stats_json").json()

    # --- cached time series ----------------------------------------------------------------
    def _cache_file(self, path: str, query: dict[str, str]) -> Path:
        key = hashlib.sha1((path + "?" + "&".join(f"{k}={v}" for k, v in sorted(query.items()))).encode())
        return self.cache_dir / f"{key.hexdigest()[:20]}.parquet"

    def fetch_once(self, start: datetime, end: datetime, step: str, parameters: list[str],
                   points: list[tuple[float, float]], use_cache: bool = True, **optionals: str) -> pd.DataFrame:
        """One request (no chunking). Cached as Parquet, keyed by the URL path and optionals."""
        query = {"model": self.model, **optionals}
        path = self.build_path(start, end, step, parameters, points)
        cache_file = self._cache_file(path, query)
        if use_cache and cache_file.exists():
            return pd.read_parquet(cache_file)
        resp = self._get(path, params=query)
        df = parse_csv(resp.text, points)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(cache_file)  # atomic: an interrupted run never leaves a half-written cache file
        if self.pause_between_requests_s:
            time.sleep(self.pause_between_requests_s)
        return df

    def daily_series(self, start: date, end: date, parameters: list[str], points: list[tuple[float, float]],
                     valid_hour_utc: int = 12, use_cache: bool = True, **optionals: str) -> pd.DataFrame:
        """Daily values at valid_hour_utc for all points, split into allowed request sizes.

        Requests run in parallel (parallel_requests, keep below the account's parallel limit).
        """
        tasks = []
        for pts in chunk(points, self.max_points_per_request):
            for d0, d1 in day_chunks(start, end, self.chunk_days):
                t0 = datetime(d0.year, d0.month, d0.day, valid_hour_utc, tzinfo=timezone.utc)
                t1 = datetime(d1.year, d1.month, d1.day, valid_hour_utc, tzinfo=timezone.utc)
                tasks.append((t0, t1, pts))

        def run(task):
            t0, t1, pts = task
            try:
                return self.fetch_once(t0, t1, "P1D", parameters, pts, use_cache=use_cache, **optionals)
            except MeteomaticsError as exc:
                # a request that keeps timing out on the server is split into two halves of the points
                if exc.status == 408 and len(pts) > 1:
                    half = len(pts) // 2
                    return pd.concat([run((t0, t1, pts[:half])), run((t0, t1, pts[half:]))], ignore_index=True)
                raise

        frames = []
        with ThreadPoolExecutor(max_workers=max(1, self.parallel_requests)) as pool:
            futures = [pool.submit(run, t) for t in tasks]
            for i, fut in enumerate(as_completed(futures), 1):
                frames.append(fut.result())
                if self.progress and len(tasks) > 1:
                    print(f"    {i}/{len(tasks)} requests done", flush=True)
        out = pd.concat(frames, ignore_index=True)
        return out.drop_duplicates(["lat", "lon", "validdate"]).sort_values(["lat", "lon", "validdate"]).reset_index(drop=True)
