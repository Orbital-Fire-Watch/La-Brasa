/**
 * Analysis page: header blocks with year-to-date figures (EFFIS style), then collapsible tiles for the short-term analysis,
 * the map with time slider and fire list, the season curve and the year overview.
 */
import { useCallback, useMemo, useState } from "react";
import { RingCalendar } from "../components/charts/RingCalendar";
import { SeasonChart } from "../components/charts/SeasonChart";
import { YearHeatmap } from "../components/charts/YearHeatmap";
import { Segmented } from "../components/ui/Segmented";
import { useApiQuery } from "../hooks/useApiQuery";
import { useAppData } from "../hooks/useAppData";
import type { CompareSetting } from "../hooks/useAppState";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { usePlayback, usePlaybackClock } from "../hooks/usePlayback";
import { useSelection } from "../hooks/useSelection";
import { climatology, periodCells, seasonPhase, valueAt, windowAnomaly, type PeriodMode } from "../lib/analysis";
import { divergingScale } from "../lib/colors";
import { addDays, clampDate, daysBetween } from "../lib/dates";
import { cellsToUnits, eventsToUnits, type FireUnit } from "../lib/fireUnits";
import {
  EVENTS_COMPARABLE_FROM_YEAR, gridMetricFor, HOTSPOT_MIN_ZOOM, LOOKBACKS, METHODS, seriesKeyFor, SLIDER_RANGE_DAYS,
} from "../lib/methods";
import { ApiError } from "../services/api/errors";
import { exportCsvUrl, fireApi } from "../services/api/fireApi";
import { isGridAnomaly, isGridCount, type EventSort, type ExportQuery } from "../services/api/types";
import { ActiveCard, FireList, inSentence, SeasonCard, StrongestCard, TimeSlider, WeekCard } from "../components/analysis/AnalysisParts";
import { Header } from "../components/Header";
import { DisplaySwitch, ExitButton } from "../components/map/MapTools";
import { YearCompare } from "../components/analysis/YearCompare";
import { loadSensorDaily } from "../services/api/sensorDaily";
import { useSensorDaily } from "../hooks/useSensorDaily";
import { SensorCompare } from "../components/SensorCompare";
import { OrbitalMap, type MapView } from "../components/map/OrbitalMap";
import { Empty, ErrorNote, Loading, Spinner, Tile, Tip } from "../components/ui/Elements";
import { CLOUDY_THRESHOLD, fineResolutionForZoom } from "../lib/uiConfig";
import { cloudDays, probablyHiddenFire } from "../lib/clouds";
import { useI18n } from "../i18n/I18n";
import { anomalyCells, cellsByAge, eventShapes, hotspotPoints } from "../lib/mapFeatures";
import { useAppState } from "../hooks/useAppState";
import { ageColors } from "../lib/palette";
import { usePrefs } from "../hooks/usePrefs";
import { useRegionName, useSelectionInfo } from "../hooks/useSelectionInfo";
import { compareSensors } from "../lib/sensors";
import { useTour } from "../hooks/useTour";

const FALLBACK_RESOLUTION = 6;

/** Selected event on the shown day: in the list, not started yet, already over, outside the list, or not known. */
type EventPhase = "shown" | "upcoming" | "ended" | "outside" | "unknown";

const isEventGone = (q: { status: string; error?: unknown }) =>
  q.status === "error" && q.error instanceof ApiError && q.error.code === "EVENT_NOT_FOUND";
const MIN_ANOMALY_WINDOW_DAYS = 7;

export function AnalysisPage() {
  const { meta, regionById, regions } = useAppData();
  const [state, setState] = useAppState();
  const { prefs } = usePrefs();
  const { t, f } = useI18n();
  const regionName = useRegionName();
  const tour = useTour();
  const colors = ageColors(prefs.palette);
  const { selection, withArea } = useSelection(state, setState);
  const info = useSelectionInfo(selection);
  const { conf, lookback: L } = state;
  const eventsAvailable = meta.features.events;
  const method = state.metric === "events" && !eventsAvailable ? "fires" : state.metric;
  const seriesKey = seriesKeyFor(method);
  const gridMetric = gridMetricFor(method);
  const v = meta.data_version;
  const countries = useMemo(() => (regions?.features ?? []).filter((r) => r.properties.level === "country"), [regions]);
  const unitOf = (m: typeof method) => (m === "frp_sum" ? "MW" : t(m === "events" ? "unit.events" : "unit.hotspots"));

  // ---- dates: D₀ from the start page, D from the slider
  const D0 = clampDate(state.date ?? meta.last_date, meta.first_date, meta.last_date);
  const sliderMin = clampDate(addDays(D0, -SLIDER_RANGE_DAYS), meta.first_date, meta.last_date);
  const sliderMax = clampDate(addDays(D0, SLIDER_RANGE_DAYS), meta.first_date, meta.last_date);
  const D = clampDate(state.d ?? D0, sliderMin, sliderMax);
  // Playback steps one day at a time and waits for the data itself, so it skips the debounce meant for dragging.
  const playback = usePlayback();
  const debouncedD = useDebouncedValue(D, 300);
  const qD = playback.playing ? D : debouncedD;
  const qStart = clampDate(addDays(qD, -(L - 1)), meta.first_date, qD);
  // Labels and the export query are derived here, before the memos below: the React Compiler cannot tell that
  // these helpers leave their (string) arguments alone and would otherwise skip the memoised values.
  const D0Label = f.date(D0);
  const DLabel = f.date(D);
  const qDLabel = f.date(qD);
  const windowLabel = t("lookback", { count: L });
  // The raw MODIS / VIIRS comparison loads 30 days of raw hotspots (several MB) per day. During playback it stays on
  // the day shown when Play was pressed instead of loading every frame, and follows the slider again once paused.
  const [cmpPlayD, setCmpPlayD] = useState(qD);
  const cmpD = playback.playing ? cmpPlayD : qD;
  const cmpDLabel = f.date(cmpD);
  const cmpStart = clampDate(addDays(cmpD, -29), meta.first_date, cmpD);
  const exportQuery: ExportQuery | null = selection.kind === "area" && !selection.exportParams.area_id
    ? null
    : { ...selection.exportParams, start: addDays(D, -(L - 1)) < meta.first_date ? meta.first_date : addDays(D, -(L - 1)), end: D, min_confidence: conf };

  const daily = useApiQuery(`daily|${v}|${selection.key}|${conf}`, (signal) => withArea((sel) => fireApi.daily({ ...sel, min_confidence: conf }, signal)));
  const dailyData = daily.status === "success" ? daily.data : null;

  // ---- events or the H3 fallback
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
    const key = listSort as "frp_sum" | "duration_days" | "hotspots" | "last_seen";
    return cellsToUnits(g.cells, qD, qStart).sort((a, b) => (a[key] < b[key] ? 1 : a[key] > b[key] ? -1 : 0));
  }, [eventsAvailable, events.data, fallbackGrid.data, qD, qStart, listSort]);
  const unitsQuery = eventsAvailable ? events : fallbackGrid;
  const kind = eventsAvailable ? "event" : "cell";

  const nameOf = (u: FireUnit) => {
    if (u.kind === "cell") return t("fire.cell", { id: u.id.slice(0, 8) });
    const area = u.province_id ? regionById.get(u.province_id) : undefined;
    const place = area ? regionName(area) : u.province_id ?? "";
    return t(area?.properties.level === "province" ? "fire.near" : "fire.in", { place, date: f.dayMonth(u.first_seen) });
  };

  const selectedUnit = units.find((u) => u.id === state.event) ?? null;
  // The slider and playback can move to days before the selected event's start or after its end, where the backend
  // does not know it (EVENT_NOT_FOUND); its dates then tell which of the two it is. They come from the event as of the
  // last slider day (one request per event, also when it was opened from a link), else from the list.
  const lifespan = useApiQuery(
    eventsAvailable && state.event ? `event|${v}|${state.event}|${sliderMax}` : null,
    (signal) => fireApi.eventDetail(state.event as string, sliderMax, signal),
  );
  const lifespanUnit = useMemo(
    () => (lifespan.status === "success" && lifespan.data.id === state.event ? eventsToUnits([lifespan.data])[0] : null),
    [lifespan.status, lifespan.data, state.event],
  );
  const [lastSelected, setLastSelected] = useState<FireUnit | null>(null);
  if (selectedUnit && selectedUnit !== lastSelected) setLastSelected(selectedUnit);
  const knownUnit = lifespanUnit ?? selectedUnit ?? (lastSelected && lastSelected.id === state.event ? lastSelected : null);
  const eventPhase: EventPhase | null = !state.event ? null
    : selectedUnit ? "shown"
      : !knownUnit ? "unknown"
        : qD < knownUnit.first_seen ? "upcoming"
          : qD > knownUnit.last_seen ? "ended"
            : "outside";
  // Before its start and after its end the map shows the normal layers; the view stays on the event.
  const eventOnMap = eventsAvailable && (eventPhase === "shown" || eventPhase === "outside" || eventPhase === "unknown");
  const detail = useApiQuery(
    eventsAvailable && state.event && (eventPhase === "outside" || eventPhase === "unknown") ? `event|${v}|${state.event}|${qD}` : null,
    (signal) => fireApi.eventDetail(state.event as string, qD, signal),
  );
  const [fit, setFit] = useState<{ bbox: [number, number, number, number]; key: string } | null>(null);
  const selectUnit = (u: FireUnit | null, zoom = true) => {
    playback.stop();
    setState({ event: u?.id ?? null });
    if (u && zoom) setFit({ bbox: u.bbox, key: `${u.id}|${Date.now()}` });
  };

  // ---- raw MODIS / VIIRS, 30 days up to D (summed up from /api/hotspots, see sensors.ts)
  const raw = useApiQuery(`raw|${v}|${selection.key}|${conf}|${cmpStart}|${cmpD}`, (signal) =>
    withArea((sel) => fireApi.hotspots({ ...sel, start: cmpStart, end: cmpD, limit: meta.limits.hotspots_max, min_confidence: conf, raw: true }, signal)),
  );
  const comparison = useMemo(
    () => (raw.data ? compareSensors(raw.data.features, cmpStart, cmpD, meta, raw.data) : null),
    [raw.data, cmpStart, cmpD, meta],
  );

  // ---- short-term cards
  const week = useMemo(() => (dailyData ? windowAnomaly(dailyData, seriesKey, addDays(D, -6), D) : null), [dailyData, seriesKey, D]);
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
  const [view, setView] = useState<MapView | null>(null);
  const debView = useDebouncedValue(view, 300);
  const mapMode = !eventsAvailable ? "cells" : state.view;
  const showPoints = !!debView && debView.zoom >= HOTSPOT_MIN_ZOOM && !state.anomaly;
  const resolution = debView ? fineResolutionForZoom(debView.zoom, state.anomaly ? meta.limits.anomaly_resolution_max : 8) : 5;
  const bboxKey = debView?.bbox.join(",") ?? "";
  const anomalyLen = Math.max(L, MIN_ANOMALY_WINDOW_DAYS);
  const anomalyStart = clampDate(addDays(qD, -(anomalyLen - 1)), meta.first_date, qD);
  const anomalyAvailable = meta.features.anomaly && meta.features.anomaly_window;

  const mapGrid = useApiQuery(
    debView && !showPoints && (state.anomaly || mapMode === "cells")
      ? `grid|${v}|${selection.key}|${conf}|${state.anomaly ? `anomaly|${anomalyStart}|${state.compare}|${gridMetric}` : `count|${qStart}`}|${qD}|${resolution}|${bboxKey}`
      : null,
    (signal) => withArea((sel) => (state.anomaly
      ? fireApi.grid({ ...sel, mode: "anomaly", start: anomalyStart, end: qD, compare: state.compare, metric: gridMetric, bbox: debView?.bbox, resolution, min_confidence: conf }, signal)
      : fireApi.grid({ ...sel, mode: "count", start: qStart, end: qD, bbox: debView?.bbox, resolution, min_confidence: conf }, signal))),
  );
  const pointsQuery = useApiQuery(
    debView && (showPoints || eventOnMap) ? `hotspots|${v}|${selection.key}|${conf}|${qStart}|${qD}|${eventOnMap ? state.event : bboxKey}` : null,
    (signal) => withArea((sel) => fireApi.hotspots(
      eventOnMap && state.event
        ? { ...sel, start: qStart, end: qD, event_id: state.event, limit: meta.limits.hotspots_max, min_confidence: conf }
        : { ...sel, start: qStart, end: qD, bbox: debView?.bbox, limit: meta.limits.hotspots_default, min_confidence: conf },
      signal,
    )),
  );
  const cellsFc = useMemo(() => {
    const g = mapGrid.data;
    if (!g || showPoints) return null;
    if (state.anomaly && isGridAnomaly(g)) return anomalyCells(g.cells, g.max_abs_diff, gridMetric === "frp_sum" ? "MW" : t("unit.hotspots"), { t, f });
    if (!state.anomaly && isGridCount(g)) return cellsByAge(g.cells, gridMetric, g.max[gridMetric], qD, colors, { t, f });
    return null;
  }, [mapGrid.data, showPoints, state.anomaly, gridMetric, qD, colors, t, f]);
  const isHidden = useCallback((u: FireUnit) => probablyHiddenFire(u, CLOUDY_THRESHOLD), []);
  const hiddenFires = useMemo(() => units.filter(isHidden).length, [units, isHidden]);
  const shapes = useMemo(() => (mapMode === "events" && !state.anomaly ? eventShapes(units, colors, isHidden) : null), [mapMode, state.anomaly, units, colors, isHidden]);
  const pointsFc = useMemo(
    () => (pointsQuery.data ? hotspotPoints(pointsQuery.data.features, qD, (id) => regionById.get(id)?.properties.name ?? id, colors, eventsAvailable, { t, f }) : null),
    [pointsQuery.data, qD, regionById, colors, eventsAvailable, t, f],
  );
  const anomalyData = mapGrid.data && isGridAnomaly(mapGrid.data) ? mapGrid.data : null;
  const mapLoading = mapGrid.status === "loading" || pointsQuery.status === "loading" || unitsQuery.status === "loading";
  // A selected event missing on this day (e.g. merged into another one) is explained in the list, not a map error,
  // so it neither shows an error note nor stops playback.
  const detailGone = isEventGone(detail) || isEventGone(pointsQuery);
  const mapError = [mapGrid, pointsQuery, unitsQuery].find((q) => q.status === "error" && !isEventGone(q));
  usePlaybackClock({
    playing: playback.playing, stop: playback.stop, speed: playback.speed,
    value: D, max: sliderMax, ready: !mapLoading, failed: !!mapError, onStep: (d) => setState({ d }),
  });
  // Play runs over the whole slider: a new run starts at its first day, a paused run continues where it was.
  const togglePlayback = () => {
    if (playback.playing) return playback.pause();
    if (playback.status === "stopped" || D >= sliderMax) setState({ d: sliderMin });
    setCmpPlayD(qD);
    playback.play();
  };
  // Before its start and after its end the selected event stays in the list, with a note instead of an error.
  const shownUnit = eventPhase === "upcoming" || eventPhase === "ended" ? knownUnit : selectedUnit;
  const selectionFit = useMemo(() => (selection.bbox ? { bbox: selection.bbox, key: `sel|${selection.key}` } : null), [selection.bbox, selection.key]);

  // ---- season curve and year overview
  const [compareYears, setCompareYears] = useState<number[]>([]);
  const [heatMode, setHeatMode] = useState<PeriodMode>("week");
  const [heatShape, setHeatShape] = useState<"grid" | "ring">("grid");
  const heatCells = useMemo(() => (dailyData ? periodCells(dailyData, seriesKey, heatMode) : null), [dailyData, seriesKey, heatMode]);
  // Year overview with raw MODIS / VIIRS: loaded only when that view is chosen, cached per version, area and confidence.
  const yearDisplay = state.display;
  const rawYear = yearDisplay !== "harmonised";
  const sensorDaily = useSensorDaily(rawYear ? `sensors|${v}|${selection.key}|${conf}` : null, (signal, onProgress) =>
    withArea((sel) => loadSensorDaily(
      { ...sel, min_confidence: conf, start: meta.first_date, end: meta.last_date }, meta,
      (body, s) => fireApi.hotspots(body, s), signal, onProgress,
    )),
  );
  const minYear = method === "events" ? EVENTS_COMPARABLE_FROM_YEAR : undefined;
  const pickDate = (end: string) => {
    playback.stop();
    const d = end > meta.last_date ? meta.last_date : end;
    if (d < sliderMin || d > sliderMax) setState({ date: d, d: null, event: null });
    else setState({ d });
  };
  const sliderBars = useMemo(() => {
    if (!dailyData) return null;
    return Array.from({ length: daysBetween(sliderMin, sliderMax) + 1 }, (_, i) => valueAt(dailyData, seriesKey, addDays(sliderMin, i)));
  }, [dailyData, seriesKey, sliderMin, sliderMax]);
  const hidden = useApiQuery(
    eventsAvailable ? `hidden|${v}|${selection.key}|${conf}|${sliderMin}|${sliderMax}` : null,
    (signal) => withArea((sel) => fireApi.hiddenFires({ ...sel, start: sliderMin, end: sliderMax, min_confidence: conf }, signal)),
  );
  const hiddenCover = hidden.status === "success" ? hidden.data.cover : null;
  const sliderClouds = useMemo(
    () => (dailyData ? cloudDays(dailyData, sliderMin, sliderMax, CLOUDY_THRESHOLD, hiddenCover) : null),
    [dailyData, sliderMin, sliderMax, hiddenCover],
  );
  const fmt = (x: number) => f.method(method, x);
  const methodLong = t(`method.${method}.long`);
  const gridLong = t(`method.${gridMetric}.long`);
  const ageLegend = mapMode === "events" ? (["today", "recent", "older", "ended"] as const) : (["today", "recent", "older"] as const);

  return (
    <div className="ow-analysis">
      <Header>
        <dl className="ow-summary">
          <div><dt>{t("an.area")}</dt><dd>{info.name} <span className="ow-muted">{info.detail}</span></dd></div>
          <div><dt>{t("an.refDate")}</dt><dd>{D0Label}</dd></div>
          <div><dt>{t("an.conf")}</dt><dd>{t(`conf.${conf}`)}</dd></div>
        </dl>
      </Header>

      <div className="ow-toolbar">
        <div className="ow-toolbar__group">
          <Segmented label={t("settings.method")} value={method} onChange={(m) => setState({ metric: m })} size="small"
            options={METHODS.map((m) => ({ value: m, label: t(`method.${m}`), disabled: m === "events" && !eventsAvailable }))} />
          <Tip text={METHODS.map((m) => `${t(`method.${m}`)}: ${t(`method.${m}.help`)}`).join("\n\n")} label={t("settings.aboutMethods")} />
        </div>
        <div className="ow-toolbar__group">
          {info.parentCountry && (
            <button type="button" className="ow-btn" onClick={() => setState({ region: info.parentCountry?.properties.id ?? null, area: null, event: null })}>
              {t("sel.backTo", { country: regionName(info.parentCountry) })}
            </button>
          )}
          <ExportButton query={exportQuery} title={t("an.exportTitle", { window: windowLabel, date: DLabel })} />
          <button type="button" className="ow-btn ow-btn--primary" onClick={() => setState({ page: "select", d: null, event: null }, { push: true })}>
            {t("an.edit")}
          </button>
        </div>
      </div>

      {daily.status === "error" && <div className="ow-content"><ErrorNote error={daily.error} onRetry={daily.reload} /></div>}

      <main className="ow-content">
        <Tile title={t("an.short", { date: DLabel })} tour="short">
          <div className="ow-cards">
            <WeekCard anomaly={week} method={method} unit={unitOf(method)} loading={daily.status === "loading"} />
            <ActiveCard active={active} previous={previous} fresh={fresh} kind={kind} loading={unitsQuery.status === "loading"} />
            <SeasonCard phase={phase} date={D} loading={daily.status === "loading"} curve={clim?.median ?? null} />
            <StrongestCard unit={strongest} name={strongest ? nameOf(strongest) : ""} loading={unitsQuery.status === "loading"}
              onShow={() => strongest && selectUnit(strongest)} />
          </div>
        </Tile>

        <Tile title={t("an.mapTitle", { window: windowLabel, date: qDLabel })} tour="maptile"
          aside={
            <div className="ow-tile__controls">
              <Segmented label={t("an.lookback")} value={L} size="small" onChange={(l) => setState({ lookback: l })}
                options={LOOKBACKS.map((l) => ({ value: l, label: t("lookback", { count: l }) }))} />
              <Segmented label={t("an.show")} value={mapMode} size="small" onChange={(m) => setState({ view: m })}
                options={[{ value: "events", label: t("an.events"), disabled: !eventsAvailable }, { value: "cells", label: t("an.cells") }]} />
              <label className="ow-switch" title={anomalyAvailable ? t("an.unusualTitle") : t("an.notAvailable")}>
                <input type="checkbox" checked={state.anomaly} disabled={!anomalyAvailable} onChange={(e) => setState({ anomaly: e.target.checked })} />
                <span>{t("an.unusual")}</span>
              </label>
              {state.anomaly && (
                <label className="ow-field ow-field--inline">
                  <span className="ow-small ow-muted">{t("an.compareWith")}</span>
                  <select className="ow-input ow-input--small" value={String(state.compare)}
                    onChange={(e) => setState({ compare: (e.target.value === "all" ? "all" : Number(e.target.value)) as CompareSetting })}>
                    <option value="all">{t("an.allYears")}</option>
                    <option value="10">{t("an.last10")}</option>
                    <option value="5">{t("an.last5")}</option>
                  </select>
                </label>
              )}
            </div>
          }>
          <div className="ow-maplayout">
            <div className="ow-maplayout__map">
              <OrbitalMap
                fullscreen="map"
                initialBbox={selection.bbox ?? meta.bbox}
                attribution={meta.attribution}
                ariaLabel={t("an.mapAria")}
                countries={countries}
                selection={selection.kind === "all" ? null : selection.geometry}
                fitTo={tour.fit ?? fit ?? selectionFit}
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
                <div className="ow-exitslot ow-exitslot--inmap">
                  <ExitButton info={info} isArea={selection.kind === "area"} escapeEnabled
                    onExit={(target) => setState({ ...target, event: null })} />
                </div>
                <section className="ow-legend ow-legend--inmap" aria-label={t("legend.aria")}>
                  <h3 className="ow-legend__title">
                    {state.anomaly ? t("legend.unusual", { metric: gridLong })
                      : showPoints || eventOnMap ? t("legend.byAge")
                        : t(mapMode === "events" ? "legend.eventsByAge" : "legend.cellsByAge")}
                    <Tip label={t("legend.about")}
                      text={state.anomaly
                        ? t("legend.anomalyTip", { days: MIN_ANOMALY_WINDOW_DAYS, res: meta.limits.anomaly_resolution_max })
                        : t("legend.ageTip", { zoom: HOTSPOT_MIN_ZOOM })} />
                    {mapLoading && <Spinner label={t("legend.loading")} />}
                  </h3>
                  {state.anomaly ? (
                    <AnomalyLegend max={anomalyData?.max_abs_diff ?? 0} unit={gridMetric === "frp_sum" ? "MW" : t("unit.hotspots")} years={anomalyData ? anomalyData.years_compared : null} />
                  ) : (
                    <ul className="ow-agelegend">
                      {ageLegend.map((a) => <li key={a}><span className="ow-swatch" style={{ background: colors[a] }} />{t(`age.${a}`)}</li>)}
                      {shapes && !showPoints && !eventOnMap && units.some((u) => u.extensionGeometry) && (
                        <li><span className="ow-swatch ow-swatch--extension" style={{ color: colors.today }} />{t("legend.extension")}</li>
                      )}
                      {hiddenFires > 0 && <li><span className="ow-swatch ow-swatch--hidden" />{t("legend.hidden")}</li>}
                    </ul>
                  )}
                  {pointsQuery.data?.truncated && <p className="ow-small">{t("legend.truncated", { returned: pointsQuery.data.returned, total: pointsQuery.data.total })}</p>}
                  {mapError && mapError.status === "error" && <ErrorNote error={mapError.error} onRetry={mapError.reload} />}
                </section>
              </OrbitalMap>
              <TimeSlider value={D} anchor={D0} min={sliderMin} max={sliderMax} onChange={(d) => { playback.stop(); setState({ d }); }}
                bars={sliderBars} barsLabel={methodLong} clouds={sliderClouds} hiddenFires={hiddenFires}
                playback={{ playing: playback.playing, onToggle: togglePlayback, speed: playback.speed, onSpeed: playback.setSpeed }} />
            </div>

            <aside className="ow-maplayout__list" aria-labelledby="ow-list-title">
              <h3 id="ow-list-title" className="ow-subtitle">
                {t(kind === "event" ? "list.events" : "list.cells")}
                <Tip text={t(kind === "event" ? "list.helpEvents" : "list.helpCells")} />
              </h3>
              {shownUnit && (
                <div className="ow-selected">
                  <p className="ow-selected__name">{nameOf(shownUnit)}</p>
                  <p className="ow-small ow-muted">
                    {t("list.selected", { start: f.date(shownUnit.first_seen), end: f.date(shownUnit.last_seen), frp: f.compact(shownUnit.frp_sum) })}
                  </p>
                  {(eventPhase === "upcoming" || eventPhase === "ended") && (
                    <p className="ow-small ow-selected__phase" role="status">
                      {eventPhase === "upcoming"
                        ? t("list.upcoming", { date: f.date(shownUnit.first_seen) })
                        : t("list.ended", { date: f.date(shownUnit.last_seen) })}
                    </p>
                  )}
                  <div className="ow-selected__actions">
                    <button type="button" className="ow-btn ow-btn--small" onClick={() => setFit({ bbox: shownUnit.bbox, key: `${shownUnit.id}|${Date.now()}` })}>{t("list.zoom")}</button>
                    <button type="button" className="ow-btn ow-btn--small ow-btn--ghost" onClick={() => selectUnit(null)}>{t("list.close")}</button>
                  </div>
                </div>
              )}
              {state.event && !shownUnit && unitsQuery.status === "success" && (
                <Empty>
                  {t(detailGone ? "list.gone" : "list.notInWindow")}{" "}
                  <button type="button" className="ow-btn ow-btn--small" onClick={() => selectUnit(null)}>{t("list.clear")}</button>
                </Empty>
              )}
              {unitsQuery.status === "loading" && units.length === 0 && <Loading />}
              {unitsQuery.status === "error" && <ErrorNote error={unitsQuery.error} onRetry={unitsQuery.reload} />}
              {unitsQuery.status === "success" && units.length === 0 && <Empty>{t("list.empty", { window: windowLabel, date: qDLabel })}</Empty>}
              {units.length > 0 && (
                <FireList units={units} kind={kind} sort={listSort} onSort={setSort} selectedId={state.event}
                  onSelect={(u) => selectUnit(u.id === state.event ? null : u)} nameOf={nameOf}
                  total={eventsAvailable ? events.data?.total ?? units.length : units.length}
                  truncated={eventsAvailable ? events.data?.truncated ?? false : false} />
              )}
            </aside>
          </div>
        </Tile>

        <Tile title={t("cmp.analysisTitle", { date: cmpDLabel })}
          aside={playback.playing ? <span className="ow-small ow-muted">{t("cmp.playbackNote")}</span> : undefined}>
          <SensorCompare data={comparison} loading={raw.status === "loading"} error={raw.status === "error" ? raw.error : null} onRetry={raw.reload} />
        </Tile>

        <Tile title={t("an.seasonTitle", { metric: methodLong })} tour="season" aside={<Tip text={t("an.seasonHelp")} label={t("an.aboutSeason")} />}>
          {method === "events" && <p className="ow-note">{t("an.eventsNote", { year: String(EVENTS_COMPARABLE_FROM_YEAR) })}</p>}
          {daily.status === "loading" && <Loading height={260} />}
          {dailyData && (
            <div className="ow-chart">
              <SeasonChart daily={dailyData} seriesKey={seriesKey} date={D} compareYears={compareYears} onCompareYears={setCompareYears}
                formatValue={fmt} unitLabel={unitOf(method)} minYear={minYear} />
            </div>
          )}
        </Tile>

        <Tile tour="year" title={t(heatMode === "week" ? "an.yearTitleWeek" : "an.yearTitleMonth", {
          metric: rawYear ? (yearDisplay === "compare" ? t("cmp.title") : t(`display.${yearDisplay}`)) : methodLong,
        })}
          aside={
            <div className="ow-tile__controls">
              <Segmented label={t("an.columns")} value={heatMode} onChange={setHeatMode} size="small" options={[{ value: "week", label: t("an.weeks") }, { value: "month", label: t("an.months") }]} />
              <Segmented label={t("an.shape")} value={heatShape} onChange={setHeatShape} size="small" options={[{ value: "grid", label: t("an.heatmap") }, { value: "ring", label: t("an.ring"), disabled: rawYear, title: rawYear ? t("year.ringRaw") : undefined }]} />
            </div>
          }>
          <div className="ow-yc__switch">
            <DisplaySwitch value={yearDisplay} onChange={(d) => setState({ display: d })} help={t("year.helpDisplay")} />
          </div>
          {rawYear && sensorDaily.status === "loading" && (
            <Loading height={220} label={t("year.loading", { done: sensorDaily.progress.done, total: sensorDaily.progress.total })} />
          )}
          {rawYear && sensorDaily.status === "error" && <ErrorNote error={sensorDaily.error} onRetry={sensorDaily.retry} />}
          {yearDisplay !== "harmonised" && sensorDaily.status === "success" && (
            <YearCompare result={sensorDaily.result} view={yearDisplay} mode={heatMode} selectedDate={D} onSelect={pickDate} />
          )}
          {!rawYear && daily.status === "loading" && <Loading height={220} />}
          {!rawYear && heatCells && (
            <div className="ow-chart">
              {heatShape === "grid" || rawYear ? (
                <YearHeatmap cells={heatCells} mode={heatMode} selectedDate={D} onSelect={(c) => pickDate(c.end)} formatValue={fmt}
                  unitLabel={unitOf(method)} minYear={minYear} ariaLabel={t("an.heatAria", { metric: inSentence(methodLong) })} />
              ) : (
                <RingCalendar cells={heatCells} mode={heatMode} selectedDate={D} onSelect={(c) => pickDate(c.end)} formatValue={fmt}
                  unitLabel={unitOf(method)} minYear={minYear} ariaLabel={t("an.ringAria", { metric: inSentence(methodLong) })} />
              )}
            </div>
          )}
        </Tile>
      </main>

      <footer className="ow-footer">
        <span>{t("footer.asOf", { date: f.date(meta.last_date) })}</span>
        <span>data_version {meta.data_version}</span>
        <span>weight_version {meta.weight_version}</span>
        <span>{meta.attribution}</span>
      </footer>
    </div>
  );
}

function AnomalyLegend({ max, unit, years }: { max: number; unit: string; years: number | null }) {
  const { t, f } = useI18n();
  const color = divergingScale(max);
  const stops = [-1, -0.5, -0.15, 0, 0.15, 0.5, 1].map((s, i, a) => `${color(Math.sign(s) * max * s * s)} ${(i / (a.length - 1)) * 100}%`);
  return (
    <div>
      <div className="ow-ramp">
        <span>{f.signed(-max)}</span>
        <span className="ow-ramp__bar" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} />
        <span>{f.signed(max)} {unit}</span>
      </div>
      <p className="ow-small ow-muted">{years !== null ? t("anomaly.note", { count: years }) : t("anomaly.noteNoYears")}</p>
    </div>
  );
}

/** CSV of all hotspots in the look-back window: a link against the backend. */
function ExportButton({ query, title }: { query: ExportQuery | null; title: string }) {
  const { t } = useI18n();
  if (query) return <a className="ow-btn" href={exportCsvUrl(query)} title={title}>{t("an.download")}</a>;
  return <button type="button" className="ow-btn" disabled title={t("an.noExport")}>{t("an.download")}</button>;
}
