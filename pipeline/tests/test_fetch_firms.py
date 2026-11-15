"""fetch_firms.py without internet: conversion, area filter, merge and the archive/NRT update on temp files."""
import csv
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
import fetch_firms as ff  # noqa: E402

HEADER_NRT = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite", "instrument",
              "confidence", "version", "bright_t31", "frp", "daynight"]
HEADER_ARCH = HEADER_NRT + ["type"]
API_VIIRS = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
             "bright_ti5,frp,daynight\n")


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def row(lat, lon, d, t="1200", sat="SNPP", typ=None):
    r = {"latitude": f"{lat}", "longitude": f"{lon}", "brightness": "330", "scan": "0.4", "track": "0.4",
         "acq_date": d, "acq_time": t, "satellite": sat, "instrument": "VIIRS", "confidence": "n",
         "version": "2.0NRT", "bright_t31": "290", "frp": "5.0", "daynight": "D"}
    if typ is not None:
        r["type"] = typ
    return r


def test_api_rows_are_converted_to_the_download_layout():
    text = API_VIIRS + "40.1,-3.2,330.5,0.4,0.4,2026-11-14,138,N,VIIRS,n,2.0NRT,290.1,4.5,D\n"
    r = ff.to_download_rows(text, HEADER_NRT)[0]
    assert r["satellite"] == "SNPP" and r["acq_time"] == "0138"
    assert r["brightness"] == "330.5" and r["bright_t31"] == "290.1" and list(r) == HEADER_NRT


def test_unknown_satellite_code_fails_loudly():
    with pytest.raises(ff.FirmsError):
        ff.to_download_rows(API_VIIRS + "40.1,-3.2,330,0.4,0.4,2026-11-14,0138,X9,VIIRS,n,2.0NRT,290,4.5,D\n", HEADER_NRT)


def test_merge_keeps_duplicates_once_and_area_filter_only_hits_reference_satellites():
    a = [row(40.1, -3.2, "2026-11-01")]
    merged, added = ff.merge(a, [row(40.1, -3.2, "2026-11-01"), row(40.2, -3.2, "2026-11-01")])
    assert added == 1 and len(merged) == 2
    area = {ff.cell(row(40.1, -3.2, "x"))}
    kept = ff.keep_in_area([row(40.1, -3.2, "d"), row(44.7, 4.8, "d"), row(44.7, 4.8, "d", sat="N20")], area)
    assert [(r["satellite"], r["latitude"]) for r in kept] == [("SNPP", "40.1"), ("N20", "44.7")]


def test_update_pair_adds_archive_days_trims_nrt_and_adds_new_nrt(tmp_path, monkeypatch):
    arch, nrt = tmp_path / "a.csv", tmp_path / "n.csv"
    write(arch, HEADER_ARCH, [row(40.1, -3.2, "2026-07-31", typ="0")])
    write(nrt, HEADER_NRT, [row(40.1, -3.2, "2026-08-01"), row(40.1, -3.2, "2026-08-05"), row(40.1, -3.2, "2026-11-10")])
    archive_api = (API_VIIRS.strip() + ",type\n" + "40.1,-3.2,331,0.4,0.4,2026-08-01,1200,N,VIIRS,n,2,290,6,D,0\n")
    calls = []

    def fake_get(key, source, day_range, start, retries=3):
        calls.append((source, start))
        if source.endswith("_SP"):
            return archive_api if start == date(2026, 8, 1) else ""
        return API_VIIRS + "40.1,-3.2,330,0.4,0.4,2026-11-14,0138,N,VIIRS,n,2.0NRT,290,4.5,D\n"

    monkeypatch.setattr(ff, "get_csv", fake_get)
    rep = ff.update_pair("KEY", {"name": "snpp_archive", "path": arch}, {"name": "snpp_nrt", "path": nrt},
                         {ff.cell(row(40.1, -3.2, "x"))}, 5, date(2026, 11, 15), dry_run=False)
    assert rep["archive_added"] == 1 and rep["archive_end"] == "2026-08-01"
    assert rep["nrt_removed_now_in_archive"] == 1 and rep["nrt_added"] == 1 and rep["nrt_end"] == "2026-11-14"
    _, n_rows = ff.read_csv_file(nrt)
    assert [r["acq_date"] for r in n_rows] == ["2026-08-05", "2026-11-10", "2026-11-14"]
    assert (tmp_path / "n.csv.bak").exists() and (tmp_path / "a.csv.bak").exists()
    assert ("VIIRS_SNPP_SP", date(2026, 8, 6)) in calls         # second 5-day chunk asked, empty -> stop
    nrt_starts = [d for s_, d in calls if s_ == "VIIRS_SNPP_NRT"]
    assert nrt_starts[0] == date(2026, 11, 10) and nrt_starts[-1] <= date(2026, 11, 15)   # from the last NRT day


def test_archive_failure_does_not_stop_nrt(tmp_path, monkeypatch):
    arch, nrt = tmp_path / "a.csv", tmp_path / "n.csv"
    write(arch, HEADER_ARCH, [row(40.1, -3.2, "2026-07-31", typ="0")])
    write(nrt, HEADER_NRT, [row(40.1, -3.2, "2026-08-01")])

    def fake_get(key, source, day_range, start, retries=3):
        if source.endswith("_SP"):
            raise ff.FirmsError("Invalid source")
        return API_VIIRS + "40.1,-3.2,330,0.4,0.4,2026-11-14,0138,N,VIIRS,n,2.0NRT,290,4.5,D\n"

    monkeypatch.setattr(ff, "get_csv", fake_get)
    rep = ff.update_pair("KEY", {"name": "snpp_archive", "path": arch}, {"name": "snpp_nrt", "path": nrt},
                         set(), 5, date(2026, 11, 15), dry_run=True)
    assert "archive_error" in rep and rep["nrt_added"] == 0     # outside the (empty) reference area
