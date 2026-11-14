"""Events (spec 5.6, 6.9, 6.10): hotspots that belong together in space and time, most likely the same fire.

How it works
- Points: every hotspot of Spain + Portugal with confidence nominal or high that is part of the series
  (in_series_n), i.e. exactly the points /api/hotspots returns.
- Clustering (spec section 10): union-find over nodes (day, H3 cell of resolution 8), day by day. Two nodes
  belong together if their cells are equal or direct neighbours (h3.grid_disk(cell, 1), centres about 0.9 km
  apart) and at most GAP_DAYS days lie between them. The rule is transitive. The root of a group is its
  earliest node; the id is 'e_' + sha256(start day, start cell)[:12], stable as long as the start is.
- When a fire grows across two existing events they merge and the older one keeps its id (spec 5.6). The
  clustering remembers the day of every merge and, for every point, its group on its own day.
- "As of D" (spec 5.6): an answer for day D must not know anything after D. Events that merge only after D
  are split again into their groups as of D (a small local clustering of their points up to D). The younger
  group has its own id until the merge; afterwards that id is gone (EVENT_NOT_FOUND).
- Everything is kept in memory as numpy arrays (no table, no schema change). The index is built in the
  background when the backend starts and again when the data_version changes (checked every 30 s at most,
  right away after a data sync: refresh_index).
"""
import datetime as dt
import hashlib
import logging
import threading
import time
from dataclasses import dataclass

import h3
import numpy as np
from psycopg.rows import tuple_row

from core.config import API_COUNTRIES
from core.db import connect
from errors import ApiError
from services.areas import contains, inline_area, stored_area
from services.meta import data_version
from services.scope import SENSOR_SQL, region_exists

log = logging.getLogger(__name__)

GAP_DAYS = 2                     # spec 5.6: at most 2 days between two hotspots of one event
RING = 1                         # direct neighbour cells at resolution 8
VERSION_CHECK_SECONDS = 30       # how often a request may check whether the data was reloaded
STATE_CACHE_SIZE = 50_000        # event states "as of D" (slider steps reuse them)
TREND_DAYS = 3                   # spec 6.9: fires of the last 3 days against the 3 days before
TREND_MIN_DURATION = 4
TREND_GROWING, TREND_SHRINKING = 1.25, 0.8
BBOX_PAD_DEG = 0.005             # about half a cell: an outline reaches a bit beyond its points
COORD_DIGITS = 4

POINTS_SQL = f"""
SELECT h.hotspot_id, h.obs_date, h.h3_cell, h.longitude, h.latitude,
       COALESCE(h.weight_n, 0) AS fires, COALESCE(h.frp * h.weight_frp, 0) AS frp_h, h.frp,
       h.confidence_class = 'high' AS high, COALESCE(h.region_id, h.country) AS region, h.country,
       {SENSOR_SQL} AS sensor
FROM hotspots_harmonised h
WHERE h.in_series_n AND h.confidence_class IN ('nominal', 'high') AND h.country = ANY(%(countries)s)
"""

Node = tuple[int, str]           # (day as ordinal, H3 cell)


# ---------------------------------------------------------------------------- clustering

@dataclass
class Clusters:
    final: dict[Node, Node]          # node -> root of its event at the end
    own_day: dict[Node, Node]        # node -> root of its event on the node's own day
    merges: list[tuple[int, Node]]   # (day, a root) for every day on which two existing events grew together


def cluster(cells_by_day: dict[int, set[str]]) -> Clusters:
    """Union-find over (day, cell), in the order of the days (spec section 10)."""
    parent: dict[Node, Node] = {}
    merges: list[tuple[int, Node]] = []
    own_day: dict[Node, Node] = {}

    def find(x: Node) -> Node:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Node, b: Node, day: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra[0] < day and rb[0] < day:          # both events existed before today: they merge
                merges.append((day, min(ra, rb)))
            parent[max(ra, rb)] = min(ra, rb)        # the older root wins -> stable id

    last_seen: dict[str, Node] = {}                  # cell -> its latest node so far
    for day in sorted(cells_by_day):
        cells = cells_by_day[day]
        for c in cells:
            parent[(day, c)] = (day, c)
        for c in cells:
            for n in h3.grid_disk(c, RING):          # contains c itself
                if n in cells:
                    union((day, c), (day, n), day)
                prev = last_seen.get(n)
                if prev is not None and day - prev[0] <= GAP_DAYS:
                    union((day, c), prev, day)
        for c in cells:
            last_seen[c] = (day, c)
            own_day[(day, c)] = find((day, c))
    return Clusters({node: find(node) for node in parent}, own_day, [(d, find(r)) for d, r in merges])


def event_id(root: Node) -> str:
    day, cell = root
    return "e_" + hashlib.sha256(f"{dt.date.fromordinal(day).isoformat()}|{cell}".encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------- index

def _encode(values) -> tuple[list, np.ndarray]:
    table: dict = {}
    codes = np.fromiter((table.setdefault(v, len(table)) for v in values), dtype=np.int32, count=len(values))
    return list(table), codes


@dataclass
class EventIndex:
    """Points sorted by (final event, node); final event e owns the points offset[e]:offset[e+1].
    Nodes are numbered in the order (day, cell), so the root of a group (its earliest node) is its smallest number."""
    version: str
    node_day: np.ndarray         # per node
    node_cell: np.ndarray
    root: np.ndarray             # per final event: root node
    offset: np.ndarray
    last_merge: np.ndarray       # per final event: last day two of its parts grew together (-1 = never)
    group_ids: dict[int, str]    # root node -> id, for every group that exists on some day
    group_by_id: dict[str, int]
    event_of_root: dict[int, int]
    day: np.ndarray              # per point ...
    event: np.ndarray
    node: np.ndarray
    own: np.ndarray              # root node of the point's group on its own day
    cell: np.ndarray
    region: np.ndarray
    country: np.ndarray
    high: np.ndarray
    fires: np.ndarray
    frp_h: np.ndarray
    frp_raw: np.ndarray          # NaN where FRP is missing
    lon: np.ndarray
    lat: np.ndarray
    sensor: np.ndarray
    day_order: np.ndarray        # point indices sorted by day, for windows
    day_sorted: np.ndarray
    hid_sorted: np.ndarray       # hotspot_id as uint64 (16 hex digits), sorted ...
    hid_point: np.ndarray        # ... and the point it belongs to
    hid: np.ndarray
    cell_names: list[str]
    cell_area: np.ndarray
    region_names: list[str]
    country_names: list[str]
    sensor_names: list[str]
    states: dict


def build_index(conn, version: str) -> EventIndex:
    t0 = time.monotonic()
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(POINTS_SQL, {"countries": list(API_COUNTRIES)})
        rows = cur.fetchall()
    hid, obs, cells, lon, lat, fires, frp_h, frp, high, region, country, sensor = zip(*rows) if rows else ([],) * 12
    n = len(rows)
    days = [d.toordinal() for d in obs]

    cells_by_day: dict[int, set[str]] = {}
    for d, c in zip(days, cells):
        cells_by_day.setdefault(d, set()).add(c)
    clusters = cluster(cells_by_day)
    nodes = sorted(clusters.final)
    number = {nd: i for i, nd in enumerate(nodes)}
    node = np.fromiter((number[nd] for nd in zip(days, cells)), dtype=np.int32, count=n)
    final = np.fromiter((number[clusters.final[nd]] for nd in nodes), dtype=np.int32, count=len(nodes))
    own_of_node = np.fromiter((number[clusters.own_day[nd]] for nd in nodes), dtype=np.int32, count=len(nodes))
    roots = np.unique(final)
    event_of_root_node = np.full(len(nodes), -1, dtype=np.int32)
    event_of_root_node[roots] = np.arange(len(roots), dtype=np.int32)
    last_merge = np.full(len(roots), -1, dtype=np.int32)
    for day, r in clusters.merges:
        e = event_of_root_node[number[r]]
        last_merge[e] = max(last_merge[e], day)

    cell_names, cell = _encode(cells)
    region_names, region_codes = _encode(region)
    country_names, country_codes = _encode(country)
    sensor_names, sensor_codes = _encode(sensor)
    columns = {
        "day": np.array(days, dtype=np.int32), "event": event_of_root_node[final[node]], "node": node,
        "own": own_of_node[node], "cell": cell, "region": region_codes, "country": country_codes,
        "high": np.array(high, dtype=bool), "fires": np.array(fires, dtype=float), "frp_h": np.array(frp_h, dtype=float),
        "frp_raw": np.array([np.nan if v is None else v for v in frp], dtype=float),
        "lon": np.array(lon, dtype=float), "lat": np.array(lat, dtype=float), "sensor": sensor_codes,
        "hid": np.fromiter((int(h, 16) for h in hid), dtype=np.uint64, count=n),
    }
    order = np.lexsort((columns["node"], columns["event"]))
    columns = {k: v[order] for k, v in columns.items()}
    hid_order = np.argsort(columns["hid"])
    day_order = np.argsort(columns["day"], kind="stable")

    # every group that is an event on some day: the final roots and the roots on each point's own day
    group_roots = np.unique(np.concatenate([roots, own_of_node]))
    group_ids = {int(r): event_id(nodes[r]) for r in group_roots}
    event_of_group = event_of_root_node[final[group_roots]]
    cell_number = {c: i for i, c in enumerate(cell_names)}
    index = EventIndex(
        version=version,
        node_day=np.fromiter((nd[0] for nd in nodes), dtype=np.int32, count=len(nodes)),
        node_cell=np.fromiter((cell_number[nd[1]] for nd in nodes), dtype=np.int32, count=len(nodes)),
        root=roots, offset=np.concatenate([[0], np.cumsum(np.bincount(columns["event"], minlength=len(roots)))]),
        last_merge=last_merge, group_ids=group_ids, group_by_id={v: k for k, v in group_ids.items()},
        event_of_root={int(r): int(e) for r, e in zip(group_roots, event_of_group)},
        **columns, day_order=day_order, day_sorted=columns["day"][day_order],
        hid_sorted=columns["hid"][hid_order], hid_point=hid_order,
        cell_names=cell_names, cell_area=np.array([h3.cell_area(c, "km^2") for c in cell_names]),
        region_names=region_names, country_names=country_names, sensor_names=sensor_names, states={},
    )
    log.info("Event index %s: %d points, %d events, %d merges in %.1f s",
             version, n, len(roots), len(clusters.merges), time.monotonic() - t0)
    return index


class _IndexHolder:
    """The one index of this process. Requests wait while it is (re)built."""

    def __init__(self):
        self._index: EventIndex | None = None
        self._checked = 0.0
        self._lock = threading.Lock()

    def get(self, conn) -> EventIndex:
        with self._lock:
            now = time.monotonic()
            if self._index is None or now - self._checked > VERSION_CHECK_SECONDS:
                version = data_version(conn)
                if self._index is None or self._index.version != version:
                    self._index = build_index(conn, version)
                self._checked = now
            return self._index

    def expire(self) -> None:
        """The next get() checks the data_version, however recently it last did."""
        with self._lock:
            self._checked = float("-inf")


_holder = _IndexHolder()


def get_index(conn) -> EventIndex:
    return _holder.get(conn)


def warm_up() -> None:
    """Started in a thread when the backend starts, so the first request does not wait for the clustering."""
    try:
        with connect() as conn:
            get_index(conn)
    except Exception:
        log.exception("Building the event index failed; the next events request tries again.")


def refresh_index() -> None:
    """After a data sync (services/sync.py): rebuild now, so later requests do not get the old events."""
    _holder.expire()
    warm_up()


# ---------------------------------------------------------------------------- events as of day D

@dataclass
class Groups:
    """The events as of day d among the points of some final events. Group g owns
    points[bounds[g]:bounds[g + 1]], sorted by node (so by day); roots[g] is its root node."""
    points: np.ndarray
    bounds: np.ndarray
    roots: np.ndarray

    def members(self, g: int) -> np.ndarray:
        return self.points[self.bounds[g]:self.bounds[g + 1]]


def _split(ix: EventIndex, e: int, d: int) -> tuple[np.ndarray, np.ndarray]:
    """Points of final event e up to d and their group root as of d (the event merges only after d)."""
    s, t = int(ix.offset[e]), int(ix.offset[e + 1])
    pts = np.arange(s, s + int(np.searchsorted(ix.day[s:t], d, side="right")))
    by_key: dict[Node, int] = {}
    cells_by_day: dict[int, set[str]] = {}
    for nd in np.unique(ix.node[pts]).tolist():
        key = (int(ix.node_day[nd]), ix.cell_names[ix.node_cell[nd]])
        by_key[key] = nd
        cells_by_day.setdefault(key[0], set()).add(key[1])
    roots = {by_key[k]: by_key[r] for k, r in cluster(cells_by_day).final.items()}
    return pts, np.fromiter((roots[nd] for nd in ix.node[pts].tolist()), dtype=np.int64, count=len(pts))


def groups_as_of(ix: EventIndex, events: np.ndarray, d: int) -> Groups:
    """Split the given final events into their events as of day d, from their points up to d only."""
    pts = np.flatnonzero(np.isin(ix.event, events) & (ix.day <= d))
    labels = ix.root[ix.event[pts]].astype(np.int64)
    for e in events[ix.last_merge[events] > d]:                 # rare: parts that grow together only after d
        part, part_labels = _split(ix, int(e), d)
        labels[np.searchsorted(pts, part)] = part_labels
    order = np.lexsort((ix.node[pts], labels))
    pts, labels = pts[order], labels[order]
    starts = np.flatnonzero(np.r_[True, labels[1:] != labels[:-1]]) if len(pts) else np.zeros(0, dtype=int)
    return Groups(pts, np.r_[starts, len(pts)], labels[starts])


def _events_on(ix: EventIndex, first: int, last: int) -> np.ndarray:
    """Final events with at least one point in [first, last]."""
    lo = np.searchsorted(ix.day_sorted, first, side="left")
    hi = np.searchsorted(ix.day_sorted, last, side="right")
    return np.unique(ix.event[ix.day_order[lo:hi]])


@dataclass
class GroupTable:
    """Values of all groups at once (for filtering and sorting, without outlines)."""
    start: np.ndarray
    last: np.ndarray
    hotspots: np.ndarray
    frp_sum: np.ndarray
    area_km2: np.ndarray
    in_area: np.ndarray
    has_high: np.ndarray
    west: np.ndarray
    east: np.ndarray
    south: np.ndarray
    north: np.ndarray


def _table(ix: EventIndex, g: Groups, mask: np.ndarray | None) -> GroupTable:
    p, starts = g.points, g.bounds[:-1]
    if len(starts) == 0:
        empty = np.zeros(0)
        return GroupTable(*(empty for _ in range(11)))
    counts = np.diff(g.bounds)
    group_of_point = np.repeat(np.arange(len(starts)), counts)
    pairs = np.unique(group_of_point.astype(np.int64) * len(ix.cell_names) + ix.cell[p])
    lon, lat = ix.lon[p], ix.lat[p]
    return GroupTable(
        start=ix.day[p[starts]].astype(np.int64), last=ix.day[p[g.bounds[1:] - 1]].astype(np.int64), hotspots=counts,
        frp_sum=np.add.reduceat(ix.frp_h[p], starts),
        area_km2=np.bincount(pairs // len(ix.cell_names), weights=ix.cell_area[pairs % len(ix.cell_names)],
                             minlength=len(starts)),
        in_area=np.ones(len(starts), dtype=bool) if mask is None else np.add.reduceat(mask[p].astype(int), starts) > 0,
        has_high=np.add.reduceat(ix.high[p].astype(int), starts) > 0,
        west=np.minimum.reduceat(lon, starts), east=np.maximum.reduceat(lon, starts),
        south=np.minimum.reduceat(lat, starts), north=np.maximum.reduceat(lat, starts),
    )


# ---------------------------------------------------------------------------- one event as of D

@dataclass(frozen=True)
class EventState:
    start: int
    last: int
    days: np.ndarray             # days with points
    hotspots: np.ndarray         # per day ...
    fires: np.ndarray
    frp_sum: np.ndarray
    new_cells: np.ndarray
    frp_max: float | None
    cells: int
    area_km2: float
    geometry: dict
    bbox: tuple[float, float, float, float]
    centroid: tuple[float, float]
    province_id: str
    sensors: list[str]


def _geometry(cells: list[str]) -> tuple[dict, tuple[float, float, float, float]]:
    """Outline = union of the cells (spec 6.9), as a GeoJSON MultiPolygon with rounded coordinates."""
    g = h3.cells_to_geo(cells)
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    coords = [[[[round(x, COORD_DIGITS), round(y, COORD_DIGITS)] for x, y in ring] for ring in poly] for poly in polys]
    xs = [x for p in coords for x, _ in p[0]]
    ys = [y for p in coords for _, y in p[0]]
    return {"type": "MultiPolygon", "coordinates": coords}, (min(xs), min(ys), max(xs), max(ys))


def state(ix: EventIndex, root: int, pts: np.ndarray) -> EventState:
    """The event with this root from its points (all up to D, sorted by day). A group only grows over time,
    so root + number of points identify its state; moving the slider reuses most of them."""
    key = (root, len(pts))
    cached = ix.states.get(key)
    if cached is not None:
        return cached
    days, inverse = np.unique(ix.day[pts], return_inverse=True)
    unique_cells, first = np.unique(ix.cell[pts], return_index=True)
    geometry, bbox = _geometry([ix.cell_names[c] for c in unique_cells])
    frp_raw = ix.frp_raw[pts]
    st = EventState(
        start=int(days[0]), last=int(days[-1]), days=days,
        hotspots=np.bincount(inverse, minlength=len(days)),
        fires=np.bincount(inverse, weights=ix.fires[pts], minlength=len(days)),
        frp_sum=np.bincount(inverse, weights=ix.frp_h[pts], minlength=len(days)),
        new_cells=np.bincount(inverse[first], minlength=len(days)),
        frp_max=float(np.nanmax(frp_raw)) if np.isfinite(frp_raw).any() else None,
        cells=len(unique_cells), area_km2=float(ix.cell_area[unique_cells].sum()),
        geometry=geometry, bbox=bbox,
        centroid=(round(float(ix.lon[pts].mean()), COORD_DIGITS), round(float(ix.lat[pts].mean()), COORD_DIGITS)),
        province_id=ix.region_names[int(np.bincount(ix.region[pts]).argmax())],
        sensors=sorted({ix.sensor_names[i] for i in np.unique(ix.sensor[pts])}),
    )
    if len(ix.states) >= STATE_CACHE_SIZE:
        ix.states.clear()
    ix.states[key] = st
    return st


def _trend(st: EventState, d: int) -> str | None:
    duration = st.last - st.start + 1
    if duration < TREND_MIN_DURATION or d - st.last > GAP_DAYS:
        return None
    recent = st.fires[(st.days > d - TREND_DAYS) & (st.days <= d)].sum()
    before = st.fires[(st.days > d - 2 * TREND_DAYS) & (st.days <= d - TREND_DAYS)].sum()
    if before == 0:
        return "growing" if recent > 0 else "stable"
    ratio = recent / before
    return "growing" if ratio > TREND_GROWING else "shrinking" if ratio < TREND_SHRINKING else "stable"


def feature(ix: EventIndex, root: int, st: EventState, d: int) -> dict:
    since = d - st.last
    return {
        "type": "Feature", "id": ix.group_ids[root], "geometry": st.geometry,
        "properties": {
            "start": dt.date.fromordinal(st.start), "last_seen": dt.date.fromordinal(st.last),
            "duration_days": st.last - st.start + 1, "days_since_last": since,
            "active": since == 0, "new": st.start == d, "ended": since > GAP_DAYS,
            "hotspots": int(st.hotspots.sum()), "fires": round(float(st.fires.sum()), 1),
            "frp_sum": round(float(st.frp_sum.sum()), 1),
            "frp_max": None if st.frp_max is None else round(st.frp_max, 1),
            "area_km2": round(st.area_km2, 1), "cells": st.cells, "centroid": st.centroid, "bbox": st.bbox,
            "province_id": st.province_id, "sensors": st.sensors, "trend": _trend(st, d), "landcover": None,
        },
    }


# ---------------------------------------------------------------------------- area

def scope_mask(conn, ix: EventIndex, body) -> np.ndarray | None:
    """Points in the requested area (region, country, registered or inline area); None = all of ES + PT."""
    region_id = getattr(body, "region_id", None)
    if region_id is not None:
        if region_id in API_COUNTRIES:
            return ix.country == (ix.country_names.index(region_id) if region_id in ix.country_names else -1)
        if not region_exists(conn, region_id):
            raise ApiError(404, "REGION_NOT_FOUND", f"Unknown region '{region_id}'.")
        return ix.region == (ix.region_names.index(region_id) if region_id in ix.region_names else -1)
    if getattr(body, "area_id", None) is not None:
        return contains(stored_area(conn, body.area_id), ix.lon, ix.lat)
    if getattr(body, "geometry", None) is not None:
        return contains(inline_area(body.geometry.model_dump()), ix.lon, ix.lat)
    return None


# ---------------------------------------------------------------------------- endpoints

def _selected(table: GroupTable, first: int, high_only: bool) -> np.ndarray:
    """Spec 6.9: last_seen in the window, at least one point up to D in the area, with 'high' a high point."""
    keep = (table.last >= first) & table.in_area
    return keep & table.has_high if high_only else keep


def list_events(conn, body) -> dict:
    """POST /api/events (spec 6.9)."""
    ix = get_index(conn)
    mask = scope_mask(conn, ix, body)
    d, lookback, high_only = body.date.toordinal(), body.lookback_days, body.min_confidence == "high"
    first = d - lookback + 1

    groups = groups_as_of(ix, _events_on(ix, first, d), d)
    table = _table(ix, groups, mask)
    found = np.flatnonzero(_selected(table, first, high_only))
    yesterday = groups_as_of(ix, _events_on(ix, d - 1, d - 1), d - 1)
    summary = {"active": int((table.last[found] == d).sum()), "new": int((table.start[found] == d).sum()),
               "active_previous_day": int(_selected(_table(ix, yesterday, mask), d - 1, high_only).sum())}

    shown = found
    if body.bbox is not None:
        w, s, e, n = body.bbox
        shown = found[(table.west[found] - BBOX_PAD_DEG <= e) & (table.east[found] + BBOX_PAD_DEG >= w)
                      & (table.south[found] - BBOX_PAD_DEG <= n) & (table.north[found] + BBOX_PAD_DEG >= s)]
    if len(shown):
        values = {"frp_sum": table.frp_sum, "area_km2": table.area_km2, "hotspots": table.hotspots,
                  "duration_days": table.last - table.start + 1, "start": table.start, "last_seen": table.last}[body.sort]
        ids = np.array([ix.group_ids[int(groups.roots[g])] for g in shown])
        shown = shown[np.lexsort((ids, -values[shown]))]                # always descending, ties by id
    top = shown[: body.limit]
    features = [feature(ix, int(groups.roots[g]), state(ix, int(groups.roots[g]), groups.members(int(g))), d) for g in top]
    return {"type": "FeatureCollection", "date": body.date, "lookback_days": lookback, "features": features,
            "summary": summary, "total": len(shown), "returned": len(features), "truncated": len(shown) > len(features)}


def _group(ix: EventIndex, event: str, d: int) -> tuple[int, np.ndarray]:
    """Root and points (up to d) of the event with this id as of day d."""
    root = ix.group_by_id.get(event)
    if root is not None and ix.node_day[root] <= d:
        groups = groups_as_of(ix, np.array([ix.event_of_root[root]]), d)
        hit = np.flatnonzero(groups.roots == root)
        if len(hit):
            return root, groups.members(int(hit[0]))
    # unknown, not started yet on d, or merged into an older event by d (spec 5.6)
    raise ApiError(404, "EVENT_NOT_FOUND", f"Event '{event}' does not exist on {dt.date.fromordinal(d).isoformat()}.")


def event_detail(conn, event: str, date: dt.date) -> dict:
    """GET /api/events/{id} (spec 6.10): the feature plus its gapless daily course up to D."""
    ix = get_index(conn)
    d = date.toordinal()
    root, pts = _group(ix, event, d)
    st = state(ix, root, pts)
    by_day = {int(day): i for i, day in enumerate(st.days)}
    daily = []
    for day in range(st.start, st.last + 1):
        i = by_day.get(day)
        daily.append({"date": dt.date.fromordinal(day),
                      "hotspots": 0 if i is None else int(st.hotspots[i]),
                      "fires": 0.0 if i is None else round(float(st.fires[i]), 1),
                      "frp_sum": 0.0 if i is None else round(float(st.frp_sum[i]), 1),
                      "new_cells": 0 if i is None else int(st.new_cells[i])})
    return {**feature(ix, root, st, d), "daily": daily}


def daily_event_counts(conn, body, first: dt.date, last: dt.date, no_data: list[bool]) -> dict:
    """events_active / events_new for /api/daily (spec 6.5): events with a point on that day in the area, each
    day seen as of that day; new = the event started that day. With 'high' only events with a high point that day."""
    ix = get_index(conn)
    mask = scope_mask(conn, ix, body)
    sel = (ix.day >= first.toordinal()) & (ix.day <= last.toordinal())
    if mask is not None:
        sel &= mask
    if body.min_confidence == "high":
        sel &= ix.high
    pairs = np.unique(ix.own[sel].astype(np.int64) * 2**20 + (ix.day[sel] - first.toordinal()))
    group, offset = pairs // 2**20, pairs % 2**20
    n = (last - first).days + 1
    active = np.bincount(offset, minlength=n)
    new = np.bincount(offset[ix.node_day[group] == offset + first.toordinal()], minlength=n)
    return {"events_active": [None if gap else int(v) for v, gap in zip(active, no_data)],
            "events_new": [None if gap else int(v) for v, gap in zip(new, no_data)]}


def events_of(ix: EventIndex, hotspot_ids: list[str], end: dt.date) -> list[str | None]:
    """Event id of each hotspot as of day `end` (None for points that are not in the index)."""
    if not hotspot_ids:
        return []
    keys = np.fromiter((int(h, 16) for h in hotspot_ids), dtype=np.uint64, count=len(hotspot_ids))
    pos = np.clip(np.searchsorted(ix.hid_sorted, keys), 0, max(len(ix.hid_sorted) - 1, 0))
    found = ix.hid_sorted[pos] == keys
    pts = ix.hid_point[pos]
    roots = ix.root[ix.event[pts]].astype(np.int64)
    d = end.toordinal()
    events = np.unique(ix.event[pts[found]])
    late = events[ix.last_merge[events] > d]
    if len(late):                                          # parts that grow together only after `end`
        groups = groups_as_of(ix, late, d)
        root_of_point = dict(zip(groups.points.tolist(), np.repeat(groups.roots, np.diff(groups.bounds)).tolist()))
        roots = np.array([root_of_point.get(int(p), int(r)) for p, r in zip(pts, roots)], dtype=np.int64)
    return [ix.group_ids[int(r)] if ok else None for r, ok in zip(roots, found)]


def hotspots_of_event(ix: EventIndex, event: str, end: dt.date) -> list[str]:
    """hotspot_ids of an event as of `end`, up to and including `end` (filter event_id)."""
    _, pts = _group(ix, event, end.toordinal())
    return [f"{int(h):016x}" for h in ix.hid[pts]]
