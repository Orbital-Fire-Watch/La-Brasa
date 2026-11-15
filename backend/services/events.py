"""Events (spec 5.6, 6.9, 6.10): hotspots that belong together in space and time, most likely the same fire.

How it works
- Points: every hotspot of Spain + Portugal with confidence nominal or high that is part of the series
  (in_series_n), i.e. exactly the points /api/hotspots returns.
- Clustering (spec section 10): union-find over nodes (day, H3 cell of resolution 8), day by day. Two nodes
  belong together if their cells are at most RING = 2 cells apart (h3.grid_disk(cell, 2), centres up to about
  1.8 km apart; a MODIS pixel is 1 km) and at most GAP_DAYS days lie between them. The rule is transitive. The root of a group is its
  earliest node; the id is 'e_' + sha256(start day, start cell)[:12], stable as long as the start is.
- An event bundles several hotspots: a group counts as an event only from the day on which it has at least
  MIN_HOTSPOTS points (event_day). A lone hotspot is no event, its event_id is null. The start stays the day
  of the first point; "new" on D means the group became an event on D.
- When a fire grows across two existing events they merge and the older one keeps its id (spec 5.6). The
  clustering remembers the day of every merge and, for every point, its group on its own day.
- "As of D" (spec 5.6): an answer for day D must not know anything after D. Events that merge only after D
  are split again into their groups as of D (a small local clustering of their points up to D). The younger
  group has its own id until the merge; afterwards that id is gone (EVENT_NOT_FOUND).
- Core and extension: inside an event as of D the points are grouped once more with CORE_RING = 1 (equal or
  direct neighbour cells). The largest of these groups is the core; cells joined only through the wider ring
  are the extension (core_geometry / extension_geometry, both null when there is no extension).
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
from services.clouds import cell_of, cells_on_day, lower_pass
from services.meta import data_version
from services.scope import SENSOR_SQL, region_exists

log = logging.getLogger(__name__)

GAP_DAYS = 2                     # spec 5.6: at most 2 days between two hotspots of one event
MIN_HOTSPOTS = 2                 # a group of fewer points is a lone hotspot, not an event
NEVER = np.iinfo(np.int32).max   # event_day of a group that never reaches MIN_HOTSPOTS
RING = 2                         # cells up to 2 apart at resolution 8 belong to one event
CORE_RING = 1                    # direct neighbours: the dense core of an event, the rest is its extension
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
    event_day: dict[Node, int]       # root -> first day at whose end its group has >= MIN_HOTSPOTS points


def cluster(cells_by_day: dict[int, set[str]], points: dict[Node, int] | None = None, ring: int = RING) -> Clusters:
    """Union-find over (day, cell), in the order of the days (spec section 10). `points` = hotspots per node
    (default 1 each). A root stays the root of a growing group, so its size only grows and event_day is the
    first day on which the group is an event."""
    parent: dict[Node, Node] = {}
    size: dict[Node, int] = {}                       # root -> points of its group so far
    merges: list[tuple[int, Node]] = []
    own_day: dict[Node, Node] = {}
    event_day: dict[Node, int] = {}

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
            size[min(ra, rb)] += size.pop(max(ra, rb))

    last_seen: dict[str, Node] = {}                  # cell -> its latest node so far
    for day in sorted(cells_by_day):
        cells = cells_by_day[day]
        for c in cells:
            parent[(day, c)] = (day, c)
            size[(day, c)] = 1 if points is None else points[(day, c)]
        for c in cells:
            for n in h3.grid_disk(c, ring):          # contains c itself
                if n in cells:
                    union((day, c), (day, n), day)
                prev = last_seen.get(n)
                if prev is not None and day - prev[0] <= GAP_DAYS:
                    union((day, c), prev, day)
        for c in cells:
            last_seen[c] = (day, c)
            root = own_day[(day, c)] = find((day, c))
            if root not in event_day and size[root] >= MIN_HOTSPOTS:
                event_day[root] = day
    return Clusters({node: find(node) for node in parent}, own_day, [(d, find(r)) for d, r in merges], event_day)


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
    event_day: np.ndarray        # per node: day on which the group with this root became an event (NEVER)
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
    points: dict[Node, int] = {}
    for d, c in zip(days, cells):
        cells_by_day.setdefault(d, set()).add(c)
        points[(d, c)] = points.get((d, c), 0) + 1
    clusters = cluster(cells_by_day, points)
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
        last_merge=last_merge,
        event_day=np.fromiter((clusters.event_day.get(nd, NEVER) for nd in nodes), dtype=np.int32, count=len(nodes)),
        group_ids=group_ids, group_by_id={v: k for k, v in group_ids.items()},
        event_of_root={int(r): int(e) for r, e in zip(group_roots, event_of_group)},
        **columns, day_order=day_order, day_sorted=columns["day"][day_order],
        hid_sorted=columns["hid"][hid_order], hid_point=hid_order,
        cell_names=cell_names, cell_area=np.array([h3.cell_area(c, "km^2") for c in cell_names]),
        region_names=region_names, country_names=country_names, sensor_names=sensor_names, states={},
    )
    log.info("Event index %s: %d points, %d events (%d groups below %d hotspots), %d merges in %.1f s",
             version, n, int((index.event_day[roots] != NEVER).sum()), int((index.event_day[roots] == NEVER).sum()),
             MIN_HOTSPOTS, len(clusters.merges), time.monotonic() - t0)
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
        # No events (e.g. a day without any hotspot). The dtypes must match the filled case: _selected() combines
        # last and in_area with `&`, which fails on float arrays.
        no_int, no_float, no_bool = np.zeros(0, np.int64), np.zeros(0), np.zeros(0, bool)
        return GroupTable(start=no_int, last=no_int, hotspots=no_int, frp_sum=no_float, area_km2=no_float,
                          in_area=no_bool, has_high=no_bool, west=no_float, east=no_float, south=no_float, north=no_float)
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
    core_geometry: dict | None   # None: no extension, the core is the whole event
    extension_geometry: dict | None
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


def core_cells(points: dict[Node, int]) -> set[str]:
    """Cells of the core of one event (points = hotspots per node): the largest group of its points under
    CORE_RING, ties go to the earliest group. The other cells are the extension."""
    cells_by_day: dict[int, set[str]] = {}
    for day, cell in points:
        cells_by_day.setdefault(day, set()).add(cell)
    groups: dict[Node, int] = {}
    final = cluster(cells_by_day, points, ring=CORE_RING).final
    for key, r in final.items():
        groups[r] = groups.get(r, 0) + points[key]
    core = min(groups, key=lambda r: (-groups[r], r))
    return {key[1] for key, r in final.items() if r == core}


def state(ix: EventIndex, root: int, pts: np.ndarray) -> EventState:
    """The event with this root from its points (all up to D, sorted by day). A group only grows over time,
    so root + number of points identify its state; moving the slider reuses most of them."""
    key = (root, len(pts))
    cached = ix.states.get(key)
    if cached is not None:
        return cached
    days, inverse = np.unique(ix.day[pts], return_inverse=True)
    unique_cells, first = np.unique(ix.cell[pts], return_index=True)
    names = [ix.cell_names[c] for c in unique_cells]
    geometry, bbox = _geometry(names)
    nodes, counts = np.unique(ix.node[pts], return_counts=True)
    core = core_cells({(int(ix.node_day[nd]), ix.cell_names[ix.node_cell[nd]]): int(k) for nd, k in zip(nodes, counts)})
    extension = [c for c in names if c not in core]
    core_geometry = _geometry([c for c in names if c in core])[0] if extension else None
    extension_geometry = _geometry(extension)[0] if extension else None
    frp_raw = ix.frp_raw[pts]
    st = EventState(
        start=int(days[0]), last=int(days[-1]), days=days,
        hotspots=np.bincount(inverse, minlength=len(days)),
        fires=np.bincount(inverse, weights=ix.fires[pts], minlength=len(days)),
        frp_sum=np.bincount(inverse, weights=ix.frp_h[pts], minlength=len(days)),
        new_cells=np.bincount(inverse[first], minlength=len(days)),
        frp_max=float(np.nanmax(frp_raw)) if np.isfinite(frp_raw).any() else None,
        cells=len(unique_cells), area_km2=float(ix.cell_area[unique_cells].sum()),
        geometry=geometry, core_geometry=core_geometry, extension_geometry=extension_geometry, bbox=bbox,
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
            "active": since == 0, "new": int(ix.event_day[root]) == d, "ended": since > GAP_DAYS,
            "hotspots": int(st.hotspots.sum()), "fires": round(float(st.fires.sum()), 1),
            "frp_sum": round(float(st.frp_sum.sum()), 1),
            "frp_max": None if st.frp_max is None else round(st.frp_max, 1),
            "area_km2": round(st.area_km2, 1), "cells": st.cells, "centroid": st.centroid, "bbox": st.bbox,
            "province_id": st.province_id, "sensors": st.sensors, "trend": _trend(st, d), "landcover": None,
            "core_geometry": st.core_geometry, "extension_geometry": st.extension_geometry,
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
    """Spec 6.9: last_seen in the window, at least one point up to D in the area, with 'high' a high point.
    Groups below MIN_HOTSPOTS points (as of D) are lone hotspots, not events."""
    keep = (table.last >= first) & table.in_area & (table.hotspots >= MIN_HOTSPOTS)
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
    summary = {"active": int((table.last[found] == d).sum()), "new": int((ix.event_day[groups.roots[found]] == d).sum()),
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
    add_cloud_check(conn, ix, groups, top, d, features)
    return {"type": "FeatureCollection", "date": body.date, "lookback_days": lookback, "features": features,
            "summary": summary, "total": len(shown), "returned": len(features), "truncated": len(shown) > len(features)}


def _next_day_cells(ix: EventIndex, d: int) -> set[str] | None:
    """H3 cells with points on d + 1; None when d is the newest day (no day after it yet)."""
    if len(ix.day) == 0 or d + 1 > int(ix.day.max()):
        return None
    return {ix.cell_names[c] for c in np.unique(ix.cell[ix.day == d + 1])}


def add_cloud_check(conn, ix: EventIndex, groups, top: np.ndarray, d: int, features: list[dict]) -> None:
    """For events last seen the day before D: cloud cover at the event on D (0.25° cell of its centroid) and
    whether it was seen again on D + 1 (a point in one of its cells or a direct neighbour, the clustering rule).
    The frontend calls such an event "probably hidden under clouds" when D was cloudy (frontend/lib/clouds.ts)."""
    gap = [(g, f) for g, f in zip(top, features) if f["properties"]["days_since_last"] == 1]
    if not gap:
        return
    next_cells = _next_day_cells(ix, d)
    clouds = cells_on_day(conn, dt.date.fromordinal(d), sorted({cell_of(*f["properties"]["centroid"]) for _, f in gap}))
    for g, f in gap:
        props = f["properties"]
        props["cloud_day"], props["cloud_night"] = clouds.get(cell_of(*props["centroid"]), (None, None))
        if next_cells is not None:
            props["seen_next_day"] = _seen_again(ix, groups.members(int(g)), next_cells)


def _seen_again(ix: EventIndex, pts: np.ndarray, next_cells: set[str]) -> bool:
    """A point on the next day in one of the event's cells or a direct neighbour (the clustering rule)."""
    cells = {ix.cell_names[c] for c in np.unique(ix.cell[pts])}
    return any(n in next_cells for c in cells for n in h3.grid_disk(c, RING))


def hidden_fires(conn, body) -> dict:
    """POST /api/events/hidden: for every day from start to end, the fires the map draws dashed on that day
    (add_cloud_check: last seen the day before, seen again the day after), reduced to the cloud cover of the most
    covered one. One value per day, so the time slider can mark the days without asking /api/events for each."""
    ix = get_index(conn)
    mask = scope_mask(conn, ix, body)
    high_only = body.min_confidence == "high"
    first, last = body.start.toordinal(), body.end.toordinal()
    candidates: list[tuple[dt.date, str]] = []
    for d in range(first, last + 1):
        next_cells = _next_day_cells(ix, d)
        if next_cells is None:
            continue
        groups = groups_as_of(ix, _events_on(ix, d - 1, d - 1), d)
        table = _table(ix, groups, mask)
        for g in np.flatnonzero(_selected(table, d - 1, high_only) & (table.last == d - 1)):
            pts = groups.members(int(g))
            if _seen_again(ix, pts, next_cells):
                centroid = (round(float(ix.lon[pts].mean()), COORD_DIGITS), round(float(ix.lat[pts].mean()), COORD_DIGITS))
                candidates.append((dt.date.fromordinal(d), cell_of(*centroid)))
    low = lower_pass(conn, sorted(set(candidates)))
    cover: dict[dt.date, float] = {}
    for key in candidates:
        if key in low:
            cover[key[0]] = max(cover.get(key[0], 0.0), low[key])
    days = [body.start + dt.timedelta(days=i) for i in range(last - first + 1)]
    return {"start": body.start, "end": body.end, "cover": [None if d not in cover else round(cover[d], 2) for d in days]}


def _group(ix: EventIndex, event: str, d: int) -> tuple[int, np.ndarray]:
    """Root and points (up to d) of the event with this id as of day d."""
    root = ix.group_by_id.get(event)
    if root is not None and ix.event_day[root] <= d:
        groups = groups_as_of(ix, np.array([ix.event_of_root[root]]), d)
        hit = np.flatnonzero(groups.roots == root)
        if len(hit):
            return root, groups.members(int(hit[0]))
    # unknown, not an event yet on d (too few hotspots), or merged into an older event by d (spec 5.6)
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
    day seen as of that day; new = the group became an event that day. With 'high' only events with a high point
    that day. Groups below MIN_HOTSPOTS points on that day are not counted."""
    ix = get_index(conn)
    mask = scope_mask(conn, ix, body)
    sel = (ix.day >= first.toordinal()) & (ix.day <= last.toordinal())
    if mask is not None:
        sel &= mask
    if body.min_confidence == "high":
        sel &= ix.high
    sel &= ix.event_day[ix.own] <= ix.day                      # the point's group is an event on its day
    pairs = np.unique(ix.own[sel].astype(np.int64) * 2**20 + (ix.day[sel] - first.toordinal()))
    group, offset = pairs // 2**20, pairs % 2**20
    n = (last - first).days + 1
    active = np.bincount(offset, minlength=n)
    new = np.bincount(offset[ix.event_day[group] == offset + first.toordinal()], minlength=n)
    return {"events_active": [None if gap else int(v) for v, gap in zip(active, no_data)],
            "events_new": [None if gap else int(v) for v, gap in zip(new, no_data)]}


def events_of(ix: EventIndex, hotspot_ids: list[str], end: dt.date) -> list[str | None]:
    """Event id of each hotspot as of day `end` (None for points that are not in the index and for lone
    hotspots whose group has fewer than MIN_HOTSPOTS points up to `end`)."""
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
    return [ix.group_ids[int(r)] if ok and ix.event_day[r] <= d else None for r, ok in zip(roots, found)]


def hotspots_of_event(ix: EventIndex, event: str, end: dt.date) -> list[str]:
    """hotspot_ids of an event as of `end`, up to and including `end` (filter event_id)."""
    _, pts = _group(ix, event, end.toordinal())
    return [f"{int(h):016x}" for h in ix.hid[pts]]
