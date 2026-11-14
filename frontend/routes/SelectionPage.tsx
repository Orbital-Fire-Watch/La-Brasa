/**
 * Seite 1 – Auswahl: area (predefined or drawn), reference day, confidence and method.
 * Left: predefined areas and the calendar heatmap of the selected area. Right: map with H3 activity.
 */
import { cellToBoundary } from "h3-js";
import { useMemo, useState } from "react";
import { Brand } from "../components/Brand";
import { YearHeatmap } from "../components/charts/YearHeatmap";
import { FireMap, type MapView } from "../components/map/FireMap";
import { CoordinateDialog } from "../components/selection/CoordinateDialog";
import { DrawToolbar } from "../components/selection/DrawToolbar";
import { FrequentAreas } from "../components/selection/FrequentAreas";
import { RegionPicker } from "../components/selection/RegionPicker";
import { SettingsBar } from "../components/selection/SettingsBar";
import { HeatLegend } from "../components/charts/HeatLegend";
import { EmptyBlock, ErrorBlock, LoadingBlock, Spinner } from "../components/ui/Status";
import { useApiQuery } from "../hooks/useApiQuery";
import { useAppData } from "../hooks/useAppData";
import { useAppState } from "../hooks/useAppState";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { DrawMode } from "../hooks/useDrawTool";
import { registerArea, useSelection } from "../hooks/useSelection";
import { periodCells, type PeriodCell } from "../lib/analysis";
import { sequentialScale } from "../lib/colors";
import { addDays, clampDate, daysInMonth, formatDate, isoFromParts } from "../lib/dates";
import { bboxOf, type PolygonGeometry, type Position } from "../lib/geo";
import { cellsByValue, hotspotPoints } from "../lib/mapFeatures";
import { gridMetricFor, HOTSPOT_MIN_ZOOM, METHOD_LONG, resolutionForZoom } from "../lib/methods";
import { formatMethodValue, METHOD_UNIT } from "../lib/units";
import { userMessage } from "../services/api/errors";
import { fireApi } from "../services/api/fireApi";
import { isGridCount, type CalendarMonth } from "../services/api/types";

/** Window of the activity map on page 1. */
const MAP_WINDOW_DAYS = 30;

function calendarToCells(months: CalendarMonth[], metric: "fires" | "frp_sum"): PeriodCell[] {
  const present = new Map(months.map((m) => [`${m.year}:${m.month - 1}`, m]));
  const years = [...new Set(months.map((m) => m.year))];
  return years.flatMap((year) =>
    Array.from({ length: 12 }, (_, col) => {
      const m = present.get(`${year}:${col}`);
      const start = isoFromParts(year, col + 1, 1);
      const end = isoFromParts(year, col + 1, daysInMonth(year, col + 1));
      return m
        ? { year, col, start, end, value: m[metric], status: m.status }
        : { year, col, start, end, value: null, status: "nodata" as const };
    }),
  );
}

export function SelectionPage() {
  const { meta, regions, regionById, finestRegions } = useAppData();
  const [state, setState] = useAppState();
  const { selection, withArea } = useSelection(state, setState);
  const date = clampDate(state.date ?? meta.last_date, meta.first_date, meta.last_date);
  const { conf, metric } = state;
  const eventsAvailable = meta.features.events && meta.features.daily;
  const method = metric === "events" && !eventsAvailable ? "fires" : metric;
  const gridMetric = gridMetricFor(method);

  // ---- calendar heatmap (calendar for hotspots/FRP, daily for events: monthly sum of events_new)
  const calendar = useApiQuery(
    method !== "events" ? `calendar|${meta.data_version}|${selection.key}|${conf}` : null,
    (signal) => withArea((sel) => fireApi.calendar({ ...sel, min_confidence: conf }, signal)),
  );
  const daily = useApiQuery(
    method === "events" ? `daily|${meta.data_version}|${selection.key}|${conf}` : null,
    (signal) => withArea((sel) => fireApi.daily({ ...sel, min_confidence: conf }, signal)),
  );
  const heatQuery = method === "events" ? daily : calendar;
  const heatCells = useMemo<PeriodCell[] | null>(() => {
    if (method === "events") return daily.status === "success" ? periodCells(daily.data, "events_new", "month") : null;
    return calendar.status === "success" ? calendarToCells(calendar.data.data, method) : null;
  }, [method, daily, calendar]);

  // ---- map
  const [view, setView] = useState<MapView | null>(null);
  const debView = useDebouncedValue(view, 300);
  const windowStart = clampDate(addDays(date, -(MAP_WINDOW_DAYS - 1)), meta.first_date, date);
  const showPoints = !!debView && debView.zoom >= HOTSPOT_MIN_ZOOM;
  const resolution = debView ? resolutionForZoom(debView.zoom) : 4;
  const bboxKey = debView?.bbox.join(",") ?? "";

  const grid = useApiQuery(
    debView && !showPoints ? `grid|${meta.data_version}|${selection.key}|${conf}|${windowStart}|${date}|${resolution}|${bboxKey}` : null,
    (signal) =>
      withArea((sel) =>
        fireApi.grid({ ...sel, mode: "count", start: windowStart, end: date, bbox: debView?.bbox, resolution, min_confidence: conf }, signal),
      ),
  );
  const hotspots = useApiQuery(
    debView && showPoints ? `hotspots|${meta.data_version}|${selection.key}|${conf}|${windowStart}|${date}|${bboxKey}` : null,
    (signal) =>
      withArea((sel) =>
        fireApi.hotspots({ ...sel, start: windowStart, end: date, bbox: debView?.bbox, limit: meta.limits.hotspots_default, min_confidence: conf }, signal),
      ),
  );

  const gridData = grid.data && isGridCount(grid.data) ? grid.data : null;
  const cellsFc = useMemo(
    () => (gridData && !showPoints ? cellsByValue(gridData.cells, gridMetric, gridData.max[gridMetric]) : null),
    [gridData, gridMetric, showPoints],
  );
  const pointsFc = useMemo(
    () =>
      hotspots.data && showPoints
        ? hotspotPoints(hotspots.data.features, date, (id) => regionById.get(id)?.properties.name ?? id, meta.features.events)
        : null,
    [hotspots.data, showPoints, date, regionById, meta.features.events],
  );

  // ---- drawing
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [coordsOpen, setCoordsOpen] = useState(false);

  const applyGeometry = async (g: PolygonGeometry) => {
    setDrawMode("none");
    setCoordsOpen(false);
    setAreaError(null);
    setBusy(true);
    try {
      const { id } = await registerArea(g, meta.features.areas);
      setState({ area: id, region: null });
    } catch (e) {
      setAreaError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const pickCell = (cell: string) => {
    const ring = cellToBoundary(cell, true) as Position[];
    void applyGeometry({ type: "Polygon", coordinates: [ring] });
  };

  const fitTo = useMemo(
    () => (selection.bbox ? { bbox: selection.bbox, key: selection.key } : selection.geometry ? { bbox: bboxOf(selection.geometry), key: selection.key } : null),
    [selection],
  );

  const mapLoading = grid.status === "loading" || hotspots.status === "loading";
  const mapError = grid.status === "error" ? grid.error : hotspots.status === "error" ? hotspots.error : null;
  const legendMax = gridData?.max[gridMetric] ?? 0;

  return (
    <div className="page page--select">
      <header className="topbar">
        <Brand />
        <SettingsBar
          date={date} minDate={meta.first_date} maxDate={meta.last_date} onDate={(d) => setState({ date: d, d: null })}
          conf={conf} onConf={(c) => setState({ conf: c })}
          metric={method} onMetric={(m) => setState({ metric: m })} eventsAvailable={eventsAvailable}
        />
      </header>

      <aside className="sidebar">
        <RegionPicker regions={regions} selectedId={state.region} onSelect={(id) => setState({ region: id, area: null })} />
        <FrequentAreas metric={gridMetric} conf={conf} onPick={pickCell} />
        <section className="panel" aria-labelledby="calendar-title">
          <h2 id="calendar-title" className="panel__title">
            Kalender: {METHOD_LONG[method]} pro Monat
          </h2>
          <p className="muted small">{selection.label} · Klick auf einen Monat setzt den Stichtag.</p>
          {heatQuery.status === "loading" && <LoadingBlock height={220} />}
          {heatQuery.status === "error" && <ErrorBlock error={heatQuery.error} onRetry={heatQuery.reload} />}
          {heatCells && heatQuery.status === "success" && (
            <YearHeatmap
              cells={heatCells}
              mode="month"
              selectedDate={date}
              onSelect={(c) => setState({ date: c.end > meta.last_date ? meta.last_date : c.end, d: null })}
              formatValue={(v) => formatMethodValue(method, v)}
              unitLabel={METHOD_UNIT[method]}
              minYear={method === "events" ? 2012 : undefined}
              ariaLabel={`Kalender-Heatmap ${METHOD_LONG[method]} pro Monat für ${selection.label}`}
            />
          )}
          {method === "events" && <p className="note">Ereignisse erst ab 2012: Die Anzahl hängt von der Satellitenflotte ab.</p>}
        </section>
      </aside>

      <main className="main">
        <div className="selection-bar">
          <div>
            <span className="selection-bar__label">Gebiet</span>
            <strong>{selection.label}</strong> <span className="muted">· {selection.detail}</span>
          </div>
          {(state.region || state.area) && (
            <button type="button" className="btn btn--small" onClick={() => setState({ region: null, area: null })}>
              Auswahl aufheben
            </button>
          )}
        </div>
        {areaError && <p className="form-error" role="alert">{areaError}</p>}

        <FireMap
          initialBbox={meta.bbox}
          attribution={meta.attribution}
          ariaLabel="Karte: Feueraktivität und Gebietsauswahl"
          regions={finestRegions}
          onRegionClick={(id) => setState({ region: id, area: null })}
          selection={selection.kind === "all" ? null : selection.geometry}
          fitTo={fitTo}
          cells={cellsFc}
          hotspots={pointsFc}
          onView={setView}
          drawMode={drawMode}
          maxVertices={meta.limits.geometry_max_vertices}
          onDrawComplete={(g) => void applyGeometry(g)}
          onDrawCancel={() => setDrawMode("none")}
          onDrawHint={setHint}
        >
          <DrawToolbar mode={drawMode} onMode={setDrawMode} onCoordinates={() => setCoordsOpen(true)}
            onClear={state.area ? () => setState({ area: null }) : null} hint={hint} busy={busy} />
          <div className="map-legend">
            <div className="map-legend__title">
              {showPoints ? "Hotspots" : `${METHOD_LONG[gridMetric]} pro H3-Zelle`} · {MAP_WINDOW_DAYS} Tage bis {formatDate(date)}
              {mapLoading && <Spinner />}
            </div>
            {!showPoints && <HeatLegend max={legendMax} color={sequentialScale(legendMax)} formatValue={(v) => formatMethodValue(gridMetric, v)}
              unitLabel={METHOD_UNIT[gridMetric]} showStatus={false} />}
            {showPoints && hotspots.data?.truncated && (
              <p className="small">{hotspots.data.returned} von {hotspots.data.total} Punkten (stärkste FRP)</p>
            )}
            {!showPoints && <p className="small muted">Ab Zoomstufe {HOTSPOT_MIN_ZOOM}: einzelne Hotspots</p>}
            {mapError !== null && <ErrorBlock error={mapError} onRetry={showPoints ? hotspots.reload : grid.reload} />}
            {grid.status === "success" && gridData?.cells.length === 0 && <EmptyBlock>Keine Feuer in diesem Zeitraum und Ausschnitt.</EmptyBlock>}
          </div>
        </FireMap>

        <div className="actions">
          <p className="muted small">
            {selection.label} · Stichtag {formatDate(date)} · {METHOD_LONG[method]}
          </p>
          <button type="button" className="btn btn--primary btn--large" onClick={() => setState({ page: "analysis", date, d: null }, { push: true })}>
            Auswertung →
          </button>
        </div>
      </main>

      <CoordinateDialog open={coordsOpen} onClose={() => setCoordsOpen(false)} onSubmit={(g) => void applyGeometry(g)}
        maxVertices={meta.limits.geometry_max_vertices} />
    </div>
  );
}
