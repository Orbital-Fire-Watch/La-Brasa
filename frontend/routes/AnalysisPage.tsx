/**
 * Seite 2 – Auswertung: summary, short-term analysis, map + list with time slider, season curve, year heatmap.
 * /api/daily is loaded once per area and confidence; everything derived from it reacts to the slider without
 * a request. Events, grid and hotspots follow the slider with a 300 ms debounce (spec §4).
 */
import { useMemo, useState } from "react";
import { ActiveCard, SeasonCard, StrongestCard, WeekCard } from "../components/analysis/KpiCards";
import { SummaryBar } from "../components/analysis/SummaryBar";
import { TimeSlider } from "../components/analysis/TimeSlider";
import { UnitDetail } from "../components/analysis/UnitDetail";
import { UnitList } from "../components/analysis/UnitList";
import { RingCalendar } from "../components/charts/RingCalendar";
import { SeasonChart } from "../components/charts/SeasonChart";
import { YearHeatmap } from "../components/charts/YearHeatmap";
import { FireMap, type MapView as MapViewport } from "../components/map/FireMap";
import { InfoTip } from "../components/ui/InfoTip";
import { Segmented } from "../components/ui/Segmented";
import { EmptyBlock, ErrorBlock, LoadingBlock, Spinner } from "../components/ui/Status";
import { useApiQuery } from "../hooks/useApiQuery";
import { useAppData } from "../hooks/useAppData";
import { useAppState, type CompareSetting } from "../hooks/useAppState";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useSelection } from "../hooks/useSelection";
import {
  climatology, periodCells, seasonPhase, valueAt, windowAnomaly, type PeriodMode,
} from "../lib/analysis";
import { AGE_COLOR, AGE_LABEL, divergingScale, type AgeClass } from "../lib/colors";
import { addDays, clampDate, daysBetween, formatDate, yearOf } from "../lib/dates";
import { cellsToUnits, eventsToUnits, type FireUnit } from "../lib/fireUnits";
import { formatSigned } from "../lib/format";
import { anomalyCells, cellsByAge, eventShapes, hotspotPoints } from "../lib/mapFeatures";
import {
  EVENTS_COMPARABLE_FROM_YEAR, gridMetricFor, HOTSPOT_MIN_ZOOM, LOOKBACKS, lookbackLabel, METHOD_LONG, resolutionForZoom,
  seriesKeyFor, SLIDER_RANGE_DAYS,
} from "../lib/methods";
import { formatMethodValue, METHOD_UNIT } from "../lib/units";
import { ApiError } from "../services/api/errors";
import { fireApi } from "../services/api/fireApi";
import { isGridAnomaly, isGridCount, type EventSort } from "../services/api/types";

const FALLBACK_RESOLUTION = 6;
const MIN_ANOMALY_WINDOW_DAYS = 7;

export function AnalysisPage() {
  const { meta, regionById } = useAppData();
  const [state, setState] = useAppState();
  const { selection, withArea } = useSelection(state, setState);
  const { conf, lookback: L } = state;
  const eventsAvailable = meta.features.events;
  const method = state.metric === "events" && !eventsAvailable ? "fires" : state.metric;
  const seriesKey = seriesKeyFor(method);
  const gridMetric = gridMetricFor(method);
  const v = meta.data_version;

  // ---- dates: D₀ from page 1, D from the slider (D₀ ± 60 days within the data)
  const D0 = clampDate(state.date ?? meta.last_date, meta.first_date, meta.last_date);
  const sliderMin = clampDate(addDays(D0, -SLIDER_RANGE_DAYS), meta.first_date, meta.last_date);
  const sliderMax = clampDate(addDays(D0, SLIDER_RANGE_DAYS), meta.first_date, meta.last_date);
  const D = clampDate(state.d ?? D0, sliderMin, sliderMax);
  const qD = useDebouncedValue(D, 300);
  const qStart = clampDate(addDays(qD, -(L - 1)), meta.first_date, qD);
  const setD = (d: string) => setState({ d });

  // ---- /api/daily: once per area + confidence
  const daily = useApiQuery(`daily|${v}|${selection.key}|${conf}`, (signal) =>
    withArea((sel) => fireApi.daily({ ...sel, min_confidence: conf }, signal)),
  );
  const dailyData = daily.status === "success" ? daily.data : null;

  // ---- events (or the H3 fallback, spec §7.6)
  const [sort, setSort] = useState<EventSort>("frp_sum");
  const listSort: EventSort = !eventsAvailable && (sort === "area_km2" || sort === "start") ? "frp_sum" : sort;
  const events = useApiQuery(
    eventsAvailable ? `events|${v}|${selection.key}|${conf}|${qD}|${L}|${listSort}` : null,
    (signal) => withArea((sel) => fireApi.events({ ...sel, date: qD, lookback_days: L, sort: listSort, limit: meta.limits.events_default, min_confidence: conf }, signal)),
  );
  const strongestQuery = useApiQuery(
    eventsAvailable && listSort !== "frp_sum" ? `events|${v}|${selection.key}|${conf}|${qD}|${L}|frp_sum|1` : null,
    (signal) => withArea((sel) => fireApi.events({ ...sel, date: qD, lookback_days: L, sort: "frp_sum", limit: 1, min_confidence: conf }, signal)),
  );
  const fallbackGrid = useApiQuery(
    !eventsAvailable ? `grid|${v}|${selection.key}|${conf}|${qStart}|${qD}|${FALLBACK_RESOLUTION}|area` : null,
    (signal) => withArea((sel) => fireApi.grid({ ...sel, mode: "count", start: qStart, end: qD, resolution: FALLBACK_RESOLUTION, min_confidence: conf }, signal)),
  );
  const prevStart = clampDate(addDays(qD, -L), meta.first_date, qD);
  const fallbackPrev = useApiQuery(
    !eventsAvailable && qD > meta.first_date ? `grid|${v}|${selection.key}|${conf}|${prevStart}|${addDays(qD, -1)}|${FALLBACK_RESOLUTION}|area` : null,
    (signal) => withArea((sel) => fireApi.grid({ ...sel, mode: "count", start: prevStart, end: addDays(qD, -1), resolution: FALLBACK_RESOLUTION, min_confidence: conf }, signal)),
  );

  const units = useMemo<FireUnit[]>(() => {
    if (eventsAvailable) return events.data ? eventsToUnits(events.data.features) : [];
    const g = fallbackGrid.data;
    if (!g || !isGridCount(g)) return [];
    const list = cellsToUnits(g.cells, qD, qStart);
    const key = listSort as "frp_sum" | "duration_days" | "hotspots" | "last_seen";
    return list.sort((a, b) => (a[key] < b[key] ? 1 : a[key] > b[key] ? -1 : 0));
  }, [eventsAvailable, events.data, fallbackGrid.data, qD, qStart, listSort]);
  const unitsQuery = eventsAvailable ? events : fallbackGrid;
  const kind = eventsAvailable ? "event" : "cell";

  const nameOf = (u: FireUnit) => {
    if (u.kind === "cell") return `Gebiet ${u.id.slice(0, 8)}… (ca. 36 km²)`;
    const area = u.province_id ? regionById.get(u.province_id) : undefined;
    const name = area?.properties.name ?? u.province_id ?? "";
    // "bei Ourense" for a province, "in Galicia" for a whole region (the API has no provinces yet)
    const preposition = area?.properties.level === "province" ? "bei" : "in";
    return `Feuer ${preposition} ${name} · ${formatDate(u.first_seen).replace(/ \d{4}$/, "")}`;
  };

  // ---- selected event / cell
  const selectedUnit = units.find((u) => u.id === state.event) ?? null;
  const detail = useApiQuery(
    eventsAvailable && state.event ? `event|${v}|${state.event}|${qD}` : null,
    (signal) => fireApi.eventDetail(state.event as string, qD, signal),
  );
  const detailGone = detail.status === "error" && detail.error instanceof ApiError && detail.error.code === "EVENT_NOT_FOUND";
  const [fit, setFit] = useState<{ bbox: [number, number, number, number]; key: string } | null>(null);
  const selectUnit = (u: FireUnit | null, zoom = true) => {
    setState({ event: u?.id ?? null });
    if (u && zoom) setFit({ bbox: u.bbox, key: `${u.id}|${Date.now()}` });
  };

  // ---- KPI cards
  const week = useMemo(
    () => (dailyData ? windowAnomaly(dailyData, seriesKey, addDays(D, -6), D) : null),
    [dailyData, seriesKey, D],
  );
  const clim = useMemo(
    () => (dailyData ? climatology(dailyData, seriesKey, method === "events" ? EVENTS_COMPARABLE_FROM_YEAR : undefined) : null),
    [dailyData, seriesKey, method],
  );
  const phase = clim ? seasonPhase(clim.median, D) : null;

  let active: number | null = null;
  let previous: number | null = null;
  let fresh: number | null = null;
  if (eventsAvailable && events.data) {
    active = events.data.summary.active;
    previous = events.data.summary.active_previous_day;
    fresh = events.data.summary.new;
  } else if (!eventsAvailable && fallbackGrid.data && isGridCount(fallbackGrid.data)) {
    active = fallbackGrid.data.cells.filter((c) => c.last_seen === qD).length;
    fresh = fallbackGrid.data.cells.filter((c) => c.first_seen === qD).length;
    const p = fallbackPrev.data;
    previous = p && isGridCount(p) ? p.cells.filter((c) => c.last_seen === addDays(qD, -1)).length : null;
  }
  const strongest: FireUnit | null = useMemo(() => {
    if (eventsAvailable) {
      const src = listSort === "frp_sum" ? events.data : strongestQuery.data;
      return src?.features[0] ? eventsToUnits([src.features[0]])[0] : null;
    }
    return units.reduce<FireUnit | null>((best, u) => (!best || u.frp_sum > best.frp_sum ? u : best), null);
  }, [eventsAvailable, listSort, events.data, strongestQuery.data, units]);

  // ---- map
  const [view, setView] = useState<MapViewport | null>(null);
  const debView = useDebouncedValue(view, 300);
  const mapMode = !eventsAvailable ? "cells" : state.view;
  const showPoints = !!debView && debView.zoom >= HOTSPOT_MIN_ZOOM && !state.anomaly;
  const resolution = debView ? resolutionForZoom(debView.zoom, state.anomaly ? meta.limits.anomaly_resolution_max : 8) : 5;
  const bboxKey = debView?.bbox.join(",") ?? "";
  const anomalyLen = Math.max(L, MIN_ANOMALY_WINDOW_DAYS);
  const anomalyStart = clampDate(addDays(qD, -(anomalyLen - 1)), meta.first_date, qD);
  const anomalyAvailable = meta.features.anomaly && meta.features.anomaly_window;

  const mapGrid = useApiQuery(
    debView && !showPoints && (state.anomaly || mapMode === "cells")
      ? `grid|${v}|${selection.key}|${conf}|${state.anomaly ? `anomaly|${anomalyStart}|${state.compare}|${gridMetric}` : `count|${qStart}`}|${qD}|${resolution}|${bboxKey}`
      : null,
    (signal) =>
      withArea((sel) =>
        state.anomaly
          ? fireApi.grid({ ...sel, mode: "anomaly", start: anomalyStart, end: qD, compare: state.compare, metric: gridMetric, bbox: debView?.bbox, resolution, min_confidence: conf }, signal)
          : fireApi.grid({ ...sel, mode: "count", start: qStart, end: qD, bbox: debView?.bbox, resolution, min_confidence: conf }, signal),
      ),
    { debounceMs: 0 },
  );
  const pointsQuery = useApiQuery(
    debView && (showPoints || (eventsAvailable && state.event))
      ? `hotspots|${v}|${selection.key}|${conf}|${qStart}|${qD}|${state.event ?? bboxKey}`
      : null,
    (signal) =>
      withArea((sel) =>
        fireApi.hotspots(
          state.event && eventsAvailable
            ? { ...sel, start: qStart, end: qD, event_id: state.event, limit: meta.limits.hotspots_max, min_confidence: conf }
            : { ...sel, start: qStart, end: qD, bbox: debView?.bbox, limit: meta.limits.hotspots_default, min_confidence: conf },
          signal,
        ),
      ),
  );

  const cellsFc = useMemo(() => {
    const g = mapGrid.data;
    if (!g || showPoints) return null;
    if (state.anomaly && isGridAnomaly(g)) return anomalyCells(g.cells, g.max_abs_diff, METHOD_UNIT[gridMetric]);
    if (!state.anomaly && isGridCount(g)) return cellsByAge(g.cells, gridMetric, g.max[gridMetric], qD);
    return null;
  }, [mapGrid.data, showPoints, state.anomaly, gridMetric, qD]);
  const shapes = useMemo(() => (mapMode === "events" && !state.anomaly ? eventShapes(units) : null), [mapMode, state.anomaly, units]);
  const pointsFc = useMemo(
    () =>
      pointsQuery.data
        ? hotspotPoints(pointsQuery.data.features, qD, (id) => regionById.get(id)?.properties.name ?? id, eventsAvailable)
        : null,
    [pointsQuery.data, qD, regionById, eventsAvailable],
  );
  const anomalyData = mapGrid.data && isGridAnomaly(mapGrid.data) ? mapGrid.data : null;
  const mapLoading = mapGrid.status === "loading" || pointsQuery.status === "loading" || unitsQuery.status === "loading";
  const mapError = [mapGrid, pointsQuery, unitsQuery].find((q) => q.status === "error");

  const selectionFit = useMemo(
    () => (selection.bbox ? { bbox: selection.bbox, key: `sel|${selection.key}` } : null),
    [selection.bbox, selection.key],
  );

  // ---- season curve + year heatmap
  const [compareYears, setCompareYears] = useState<number[]>([]);
  const [heatMode, setHeatMode] = useState<PeriodMode>("week");
  const [heatShape, setHeatShape] = useState<"grid" | "ring">("grid");
  const heatCells = useMemo(() => (dailyData ? periodCells(dailyData, seriesKey, heatMode) : null), [dailyData, seriesKey, heatMode]);
  const minYear = method === "events" ? EVENTS_COMPARABLE_FROM_YEAR : undefined;
  const pickDate = (end: string) => {
    const d = end > meta.last_date ? meta.last_date : end;
    if (d < sliderMin || d > sliderMax) setState({ date: d, d: null, event: null });
    else setState({ d });
  };
  const sliderBars = useMemo(() => {
    if (!dailyData) return null;
    return Array.from({ length: daysBetween(sliderMin, sliderMax) + 1 }, (_, i) => valueAt(dailyData, seriesKey, addDays(sliderMin, i)));
  }, [dailyData, seriesKey, sliderMin, sliderMax]);

  const exportQuery = selection.kind === "area" && !selection.exportParams.area_id
    ? null
    : { ...selection.exportParams, start: addDays(D, -(L - 1)) < meta.first_date ? meta.first_date : addDays(D, -(L - 1)), end: D, min_confidence: conf };

  const fmt = (x: number) => formatMethodValue(method, x);
  const ageLegend: AgeClass[] = mapMode === "events" ? ["today", "recent", "older", "ended"] : ["today", "recent", "older"];

  return (
    <div className="page page--analysis">
      <SummaryBar
        areaLabel={selection.label} areaDetail={selection.detail} date={D0} conf={conf}
        metric={method} onMetric={(m) => setState({ metric: m })} eventsAvailable={eventsAvailable}
        onEdit={() => setState({ page: "select", d: null, event: null }, { push: true })}
        exportQuery={exportQuery}
        exportLabel={`Alle Hotspots im Fenster ${lookbackLabel(L)} bis ${formatDate(D)} als CSV`}
      />

      <section className="section" aria-labelledby="kpi-title">
        <div className="section__head">
          <h2 id="kpi-title" className="section__title">Kurzzeitanalyse · {formatDate(D)}</h2>
          {daily.status === "error" && <ErrorBlock error={daily.error} onRetry={daily.reload} />}
        </div>
        <div className="kpis">
          <WeekCard anomaly={week} method={method} loading={daily.status === "loading"} />
          <ActiveCard active={active} previous={previous} fresh={fresh} kind={kind} loading={unitsQuery.status === "loading"} />
          <SeasonCard phase={phase} date={D} loading={daily.status === "loading"} curve={clim?.median ?? null} />
          <StrongestCard unit={strongest} name={strongest ? nameOf(strongest) : ""} loading={unitsQuery.status === "loading"}
            onShow={() => strongest && selectUnit(strongest)} />
        </div>
      </section>

      <section className="section section--map" aria-labelledby="map-title">
        <div className="section__head">
          <h2 id="map-title" className="section__title">Karte · {lookbackLabel(L)} bis {formatDate(qD)}</h2>
          <div className="map-controls">
            <Segmented label="Rückblick" value={L} size="small" onChange={(l) => setState({ lookback: l })}
              options={LOOKBACKS.map((l) => ({ value: l, label: lookbackLabel(l) }))} />
            <Segmented label="Darstellung" value={mapMode} size="small" onChange={(m) => setState({ view: m })}
              options={[
                { value: "events", label: "Ereignisse", disabled: !eventsAvailable, title: eventsAvailable ? undefined : "Noch nicht verfügbar" },
                { value: "cells", label: "H3-Zellen" },
              ]} />
            <label className="switch" title={anomalyAvailable ? "Abweichung vom selben Fenster in anderen Jahren" : "Noch nicht verfügbar"}>
              <input type="checkbox" checked={state.anomaly} disabled={!anomalyAvailable} onChange={(e) => setState({ anomaly: e.target.checked })} />
              <span>Ungewöhnlich</span>
            </label>
            {state.anomaly && (
              <label className="field field--inline">
                <span className="field__label">Vergleich</span>
                <select className="input input--small" value={String(state.compare)}
                  onChange={(e) => setState({ compare: (e.target.value === "all" ? "all" : Number(e.target.value)) as CompareSetting })}>
                  <option value="all">alle Jahre</option>
                  <option value="10">letzte 10 Jahre</option>
                  <option value="5">letzte 5 Jahre</option>
                </select>
              </label>
            )}
          </div>
        </div>

        <div className="map-layout">
          <div className="map-layout__map">
            <FireMap
              initialBbox={selection.bbox ?? meta.bbox}
              attribution={meta.attribution}
              ariaLabel="Karte der Feuer im Rückblick-Fenster"
              selection={selection.kind === "all" ? null : selection.geometry}
              fitTo={fit ?? selectionFit}
              cells={cellsFc}
              events={shapes?.polygons}
              eventPoints={shapes?.points}
              hotspots={pointsFc}
              selectedEventId={state.event}
              onEventClick={(id) => {
                const u = units.find((x) => x.id === id);
                if (u) selectUnit(u, false);
                else setState({ event: id });
              }}
              onView={setView}
            >
              <div className="map-legend">
                <div className="map-legend__title">
                  {state.anomaly
                    ? `Ungewöhnlich: ${METHOD_LONG[gridMetric]}, ${formatDate(anomalyStart)} – ${formatDate(qD)}`
                    : showPoints || state.event
                      ? "Hotspots nach Alter"
                      : mapMode === "events"
                        ? "Ereignisse nach Alter"
                        : "H3-Zellen nach Alter (Deckkraft = Menge)"}
                  {mapLoading && <Spinner />}
                </div>
                {state.anomaly ? (
                  <AnomalyLegend max={anomalyData?.max_abs_diff ?? 0} unit={METHOD_UNIT[gridMetric]}
                    years={anomalyData ? anomalyData.years_compared : null} />
                ) : (
                  <ul className="legend legend--list">
                    {ageLegend.map((a) => (
                      <li key={a}><span className="legend__swatch" style={{ background: AGE_COLOR[a] }} />{AGE_LABEL[a]}</li>
                    ))}
                  </ul>
                )}
                {!state.anomaly && !showPoints && <p className="small muted">Ab Zoomstufe {HOTSPOT_MIN_ZOOM}: einzelne Hotspots</p>}
                {state.anomaly && <p className="small muted">Fenster mindestens {MIN_ANOMALY_WINDOW_DAYS} Tage, Auflösung höchstens {meta.limits.anomaly_resolution_max}</p>}
                {pointsQuery.data?.truncated && (
                  <p className="small">{pointsQuery.data.returned} von {pointsQuery.data.total} Punkten (stärkste FRP)</p>
                )}
                {mapError && mapError.status === "error" && <ErrorBlock error={mapError.error} onRetry={mapError.reload} />}
              </div>
            </FireMap>
            <TimeSlider value={D} anchor={D0} min={sliderMin} max={sliderMax} onChange={setD}
              bars={sliderBars} barsLabel={METHOD_LONG[method]} />
          </div>

          <aside className="map-layout__list" aria-labelledby="list-title">
            <h3 id="list-title" className="panel__title">
              {kind === "event" ? "Ereignisse" : "Aktive Gebiete (H3-Zellen)"}
              <InfoTip text={kind === "event"
                ? "Ereignis = Hotspots, die räumlich (benachbarte H3-Zellen) und zeitlich (Lücke ≤ 2 Tage) zusammenhängen, wahrscheinlich derselbe Brand. Gezeigt werden alle, die im Rückblick-Fenster aktiv waren."
                : "Ereignisse sind im Backend noch nicht verfügbar. Ersatzweise werden H3-Zellen (ca. 36 km²) mit Hotspots im Rückblick-Fenster gezeigt."} />
            </h3>
            {selectedUnit && (
              <UnitDetail unit={selectedUnit} name={nameOf(selectedUnit)} metric={gridMetric}
                detail={eventsAvailable ? detail : null}
                onClose={() => selectUnit(null)}
                onZoom={() => setFit({ bbox: selectedUnit.bbox, key: `${selectedUnit.id}|${Date.now()}` })} />
            )}
            {state.event && !selectedUnit && unitsQuery.status === "success" && (
              <EmptyBlock>
                {detailGone ? "Dieses Ereignis gibt es nicht mehr." : "Das gewählte Ereignis ist an diesem Tag nicht im Rückblick-Fenster."}{" "}
                <button type="button" className="btn btn--small" onClick={() => selectUnit(null)}>Auswahl aufheben</button>
              </EmptyBlock>
            )}
            {unitsQuery.status === "loading" && units.length === 0 && <LoadingBlock />}
            {unitsQuery.status === "error" && <ErrorBlock error={unitsQuery.error} onRetry={unitsQuery.reload} />}
            {unitsQuery.status === "success" && units.length === 0 && (
              <EmptyBlock>Keine Feuer in den {lookbackLabel(L)} bis {formatDate(qD)}.</EmptyBlock>
            )}
            {units.length > 0 && (
              <UnitList units={units} kind={kind} sort={listSort} onSort={setSort} selectedId={state.event}
                onSelect={(u) => selectUnit(u.id === state.event ? null : u)} nameOf={nameOf}
                total={eventsAvailable ? events.data?.total ?? units.length : units.length}
                truncated={eventsAvailable ? events.data?.truncated ?? false : false} />
            )}
          </aside>
        </div>
      </section>

      <section className="section" aria-labelledby="season-title">
        <div className="section__head">
          <h2 id="season-title" className="section__title">Saisonkurve: {METHOD_LONG[method]} pro Tag</h2>
          <InfoTip text="Vergleich des gewählten Jahres mit anderen Jahren und dem typischen Verlauf. Der Punkt ist der Stichtag und wandert mit dem Zeitschieber." />
        </div>
        {method === "events" && <p className="note">Ereignisse erst ab {EVENTS_COMPARABLE_FROM_YEAR}: Anzahl hängt von der Satellitenflotte ab, Jahre nur eingeschränkt vergleichbar.</p>}
        {daily.status === "loading" && <LoadingBlock height={280} />}
        {daily.status === "error" && <ErrorBlock error={daily.error} onRetry={daily.reload} />}
        {dailyData && (
          <SeasonChart daily={dailyData} seriesKey={seriesKey} date={D} compareYears={compareYears} onCompareYears={setCompareYears}
            formatValue={fmt} unitLabel={METHOD_UNIT[method]} minYear={minYear} />
        )}
      </section>

      <section className="section" aria-labelledby="heat-title">
        <div className="section__head">
          <h2 id="heat-title" className="section__title">Jahresübersicht: {METHOD_LONG[method]} pro {heatMode === "week" ? "Woche" : "Monat"}</h2>
          <div className="map-controls">
            <Segmented label="Spalten" value={heatMode} onChange={setHeatMode} size="small"
              options={[{ value: "week", label: "Wochen" }, { value: "month", label: "Monate" }]} />
            <Segmented label="Form" value={heatShape} onChange={setHeatShape} size="small"
              options={[{ value: "grid", label: "Heatmap" }, { value: "ring", label: "Ringkalender" }]} />
          </div>
        </div>
        {daily.status === "loading" && <LoadingBlock height={240} />}
        {heatCells && heatShape === "grid" && (
          <YearHeatmap cells={heatCells} mode={heatMode} selectedDate={D} onSelect={(c) => pickDate(c.end)} formatValue={fmt}
            unitLabel={METHOD_UNIT[method]} minYear={minYear}
            ariaLabel={`Jahres-Heatmap ${METHOD_LONG[method]}, Zeilen Jahre, Spalten ${heatMode === "week" ? "Wochen" : "Monate"}`} />
        )}
        {heatCells && heatShape === "ring" && (
          <RingCalendar cells={heatCells} mode={heatMode} selectedDate={D} onSelect={(c) => pickDate(c.end)} formatValue={fmt}
            unitLabel={METHOD_UNIT[method]} minYear={minYear}
            ariaLabel={`Ringkalender ${METHOD_LONG[method]}: Jahre als Ringe von ${yearOf(meta.first_date)} innen bis ${yearOf(meta.last_date)} außen`} />
        )}
      </section>

      <footer className="footer small muted">
        Datenstand {formatDate(meta.last_date)} · data_version {meta.data_version} · weight_version {meta.weight_version} · {meta.attribution}
      </footer>
    </div>
  );
}

function AnomalyLegend({ max, unit, years }: { max: number; unit: string; years: number | null }) {
  const color = divergingScale(max);
  const stops = [-1, -0.5, -0.15, 0, 0.15, 0.5, 1].map((t, i, a) => `${color(Math.sign(t) * max * t * t)} ${(i / (a.length - 1)) * 100}%`);
  return (
    <div>
      <div className="legend">
        <span className="legend__label">{formatSigned(-max)}</span>
        <span className="legend__ramp" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} aria-hidden="true" />
        <span className="legend__label">{formatSigned(max)} {unit}</span>
      </div>
      <p className="small muted">blau = weniger, rot = mehr als der Median{years !== null ? ` von ${years} Vergleichsjahren` : ""}</p>
    </div>
  );
}
