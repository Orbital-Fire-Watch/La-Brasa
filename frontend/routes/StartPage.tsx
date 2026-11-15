/**
 * Start page of the mock: fullscreen map, floating tiles on the left (settings first), info boxes that slide in
 * after 2 s and hide while the map moves, drawing tools at the bottom, "Analysis" bottom right.
 */
import { cellToBoundary } from "h3-js";
import type { Map as MlMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiQuery } from "../hooks/useApiQuery";
import { useAppData } from "../hooks/useAppData";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { DrawMode } from "../hooks/useDrawTool";
import { registerArea, useSelection } from "../hooks/useSelection";
import { periodCells, windowAnomaly, type PeriodCell } from "../lib/analysis";
import { addDays, clampDate, daysInMonth, isoFromParts } from "../lib/dates";
import { bboxOf, type PolygonGeometry, type Position } from "../lib/geo";
import { gridMetricFor, HOTSPOT_MIN_ZOOM } from "../lib/methods";
import { fireApi } from "../services/api/fireApi";
import { isGridCount, type CalendarMonth } from "../services/api/types";
import { fineResolutionForZoom, INFO_IDLE_DELAY_MS, INFO_INITIAL_DELAY_MS, MAP_WINDOW_DAYS } from "../lib/uiConfig";
import { Header } from "../components/Header";
import { MonthGrid } from "../components/start/MonthGrid";
import { OrbitalMap, type MapView } from "../components/map/OrbitalMap";
import { DisplaySwitch, ExitButton } from "../components/map/MapTools";
import { SensorCompare } from "../components/SensorCompare";
import { DrawBar, FrequentTile, InfoBoxes, RegionTile, SettingsTile, type InfoBox } from "../components/start/StartTiles";
import { Empty, ErrorNote, Loading, Spinner, Tile, Tip } from "../components/ui/Elements";
import { useIdleReveal } from "../hooks/useIdleReveal";
import { errorMessage, useI18n } from "../i18n/I18n";
import { cellsByValue, hotspotPoints, rawCells } from "../lib/mapFeatures";
import { useAppState } from "../hooks/useAppState";
import { ageColors, valueScale } from "../lib/palette";
import { usePrefs } from "../hooks/usePrefs";
import { useRegionName, useSelectionInfo } from "../hooks/useSelectionInfo";
import { compareSensors, FAMILY_NAME, familyCells, familyFeatures, type SensorFamily } from "../lib/sensors";
import { ytdStat } from "../lib/ytd";

/** Room for the floating sidebar and the bottom elements when the map zooms to an area. */
const FIT_PADDING = { left: 380, right: 80, top: 150, bottom: 160 };
/** The comparison maps are narrower: less room around fitted areas. */
const FIT_PADDING_COMPARE = { left: 30, right: 30, top: 110, bottom: 130 };

function calendarToCells(months: CalendarMonth[], metric: "fires" | "frp_sum"): PeriodCell[] {
  const present = new Map(months.map((m) => [`${m.year}:${m.month - 1}`, m]));
  const years = [...new Set(months.map((m) => m.year))];
  return years.flatMap((year) =>
    Array.from({ length: 12 }, (_, col) => {
      const m = present.get(`${year}:${col}`);
      const start = isoFromParts(year, col + 1, 1);
      const end = isoFromParts(year, col + 1, daysInMonth(year, col + 1));
      return m ? { year, col, start, end, value: m[metric], status: m.status } : { year, col, start, end, value: null, status: "nodata" as const };
    }),
  );
}

export function StartPage() {
  const { meta, regions, regionById, finestRegions } = useAppData();
  const [state, setState] = useAppState();
  const { prefs } = usePrefs();
  const { t, f } = useI18n();
  const regionName = useRegionName();
  const { selection, withArea } = useSelection(state, setState);
  const info = useSelectionInfo(selection);
  const date = clampDate(state.date ?? meta.last_date, meta.first_date, meta.last_date);
  const { conf, metric } = state;
  const eventsAvailable = meta.features.events && meta.features.daily;
  const method = metric === "events" && !eventsAvailable ? "fires" : metric;
  const gridMetric = gridMetricFor(method);
  const countries = useMemo(() => (regions?.features ?? []).filter((r) => r.properties.level === "country"), [regions]);
  const selectRegion = (id: string | null) => setState({ region: id, area: null });
  const display = state.display;
  const compare = display === "compare";
  const rawFamily: SensorFamily | null = display === "modis" || display === "viirs" ? display : null;

  // ---- daily series of the selection: info boxes and the events calendar
  const daily = useApiQuery(`daily|${meta.data_version}|${selection.key}|${conf}`, (signal) =>
    withArea((sel) => fireApi.daily({ ...sel, min_confidence: conf }, signal)),
  );
  const calendar = useApiQuery(
    method !== "events" ? `calendar|${meta.data_version}|${selection.key}|${conf}` : null,
    (signal) => withArea((sel) => fireApi.calendar({ ...sel, min_confidence: conf }, signal)),
  );
  const heatQuery = method === "events" ? daily : calendar;
  const heatCells = useMemo<PeriodCell[] | null>(() => {
    if (method === "events") return daily.status === "success" ? periodCells(daily.data, "events_new", "month") : null;
    return calendar.status === "success" ? calendarToCells(calendar.data.data, method) : null;
  }, [method, daily, calendar]);

  // ---- info boxes
  const reveal = useIdleReveal(INFO_INITIAL_DELAY_MS, INFO_IDLE_DELAY_MS);
  const windowStart = clampDate(addDays(date, -(MAP_WINDOW_DAYS - 1)), meta.first_date, date);
  const boxes = useMemo<InfoBox[]>(() => {
    if (daily.status !== "success") return [];
    const d = daily.data;
    const fires = windowAnomaly(d, "fires", windowStart, date);
    const frp = windowAnomaly(d, "frp_sum", windowStart, date);
    const ytd = ytdStat(d, "fires", date);
    const usual = (a: typeof fires) => (a?.factor != null ? t("box.usual", { factor: f.factor(a.factor) }) : t("box.noCompare"));
    const ytdNote = ytd.value !== null && ytd.lastYear
      ? t(ytd.value >= ytd.lastYear.value ? "box.above" : "box.below", { value: f.compact(ytd.lastYear.value), date: f.date(ytd.lastYear.date) })
      : t("box.noCompare");
    const value = (v: number | null | undefined) => (v == null ? t("ui.na") : f.compact(v));
    return [
      { id: "fires", value: value(fires?.value), unit: t("unit.hotspots"), label: t("box.last", { days: MAP_WINDOW_DAYS }), note: usual(fires) },
      { id: "frp", value: value(frp?.value), unit: "MW", label: t("box.frpLast", { days: MAP_WINDOW_DAYS }), note: usual(frp) },
      { id: "ytd", value: value(ytd.value), unit: t("unit.hotspots"), label: t("box.since", { date: f.date(`${date.slice(0, 4)}-01-01`) }), note: ytdNote },
    ];
  }, [daily, windowStart, date, t, f]);

  // ---- map
  const [view, setView] = useState<MapView | null>(null);
  const debView = useDebouncedValue(view, 300);
  const showPoints = !!debView && debView.zoom >= HOTSPOT_MIN_ZOOM;
  const resolution = debView ? fineResolutionForZoom(debView.zoom) : 4;
  const bboxKey = debView?.bbox.join(",") ?? "";
  const grid = useApiQuery(
    debView && !showPoints && display === "harmonised" ? `grid|${meta.data_version}|${selection.key}|${conf}|${windowStart}|${date}|${resolution}|${bboxKey}` : null,
    (signal) => withArea((sel) => fireApi.grid({ ...sel, mode: "count", start: windowStart, end: date, bbox: debView?.bbox, resolution, min_confidence: conf }, signal)),
  );
  const hotspots = useApiQuery(
    debView && showPoints && display === "harmonised" ? `hotspots|${meta.data_version}|${selection.key}|${conf}|${windowStart}|${date}|${bboxKey}` : null,
    (signal) => withArea((sel) => fireApi.hotspots({ ...sel, start: windowStart, end: date, bbox: debView?.bbox, limit: meta.limits.hotspots_default, min_confidence: conf }, signal)),
  );
  const gridData = grid.data && isGridCount(grid.data) ? grid.data : null;
  const legendMax = gridData?.max[gridMetric] ?? 0;
  const cellsFc = useMemo(
    () => (gridData && !showPoints ? cellsByValue(gridData.cells, gridMetric, valueScale(prefs.palette, gridData.max[gridMetric]), { t, f }) : null),
    [gridData, gridMetric, showPoints, prefs.palette, t, f],
  );
  const pointsFc = useMemo(
    () => (hotspots.data && showPoints
      ? hotspotPoints(hotspots.data.features, date, (id) => regionById.get(id)?.properties.name ?? id, ageColors(prefs.palette), meta.features.events, { t, f })
      : null),
    [hotspots.data, showPoints, date, regionById, prefs.palette, meta.features.events, t, f],
  );
  const mapLoading = grid.status === "loading" || hotspots.status === "loading";
  const mapError = grid.status === "error" ? grid.error : hotspots.status === "error" ? hotspots.error : null;

  // ---- raw MODIS / VIIRS (summed up in the browser from /api/hotspots, which has every point with its sensor)
  const [cmpMaps, setCmpMaps] = useState<{ modis: MlMap | null; viirs: MlMap | null }>({ modis: null, viirs: null });
  const onModisMap = useCallback((m: MlMap | null) => setCmpMaps((p) => ({ ...p, modis: m })), []);
  const onViirsMap = useCallback((m: MlMap | null) => setCmpMaps((p) => ({ ...p, viirs: m })), []);
  const [cmpView, setCmpView] = useState<MapView | null>(null);
  const debCmpView = useDebouncedValue(cmpView, 300);
  const rawZoom = compare ? debCmpView?.zoom : debView?.zoom;
  const rawResolution = rawZoom !== undefined ? fineResolutionForZoom(rawZoom) : 4;
  const rawPoints = rawZoom !== undefined && rawZoom >= HOTSPOT_MIN_ZOOM;
  const raw = useApiQuery(
    display !== "harmonised" ? `raw|${meta.data_version}|${selection.key}|${conf}|${windowStart}|${date}` : null,
    (signal) => withArea((sel) => fireApi.hotspots({ ...sel, start: windowStart, end: date, limit: meta.limits.hotspots_max, min_confidence: conf, raw: true }, signal)),
  );
  const comparison = useMemo(
    () => (raw.data ? compareSensors(raw.data.features, windowStart, date, meta, raw.data) : null),
    [raw.data, windowStart, date, meta],
  );
  const rawLayers = useMemo(() => {
    if (!raw.data || display === "harmonised") return null;
    const features = raw.data.features;
    const families: SensorFamily[] = compare ? ["modis", "viirs"] : rawFamily ? [rawFamily] : [];
    const cells = Object.fromEntries(families.map((fam) => [fam, familyCells(features, fam, rawResolution)])) as Partial<Record<SensorFamily, ReturnType<typeof familyCells>>>;
    // One shared scale for both comparison maps, so the same colour means the same number.
    const max = Math.max(1, ...families.flatMap((fam) => (cells[fam] ?? []).map((c) => c.count)));
    const color = valueScale(prefs.palette, max);
    const layers: Partial<Record<SensorFamily, { cells: GeoJSON.FeatureCollection | null; points: GeoJSON.FeatureCollection | null }>> = {};
    for (const fam of families) {
      layers[fam] = rawPoints
        ? { cells: null, points: hotspotPoints(familyFeatures(features, fam), date, (id) => regionById.get(id)?.properties.name ?? id, ageColors(prefs.palette), false, { t, f }) }
        : { cells: rawCells(cells[fam] ?? [], color, t("cmp.cellTitle", { family: FAMILY_NAME[fam] }), { t, f }), points: null };
    }
    return { layers, max, color };
  }, [raw.data, display, compare, rawFamily, rawResolution, rawPoints, prefs.palette, date, regionById, t, f]);

  // Keep the two comparison maps in step. The MODIS map leads (it also does the zoom to the selected area) and the
  // VIIRS map follows every move; moves the user makes on the VIIRS map are passed back. jumpTo has no
  // originalEvent, so the echo stops after one step.
  useEffect(() => {
    const { modis, viirs } = cmpMaps;
    if (!compare || !modis || !viirs) return;
    const a = () => viirs.jumpTo({ center: modis.getCenter(), zoom: modis.getZoom() });
    const b = (e: { originalEvent?: unknown }) => {
      if (e.originalEvent) modis.jumpTo({ center: viirs.getCenter(), zoom: viirs.getZoom() });
    };
    modis.on("move", a);
    viirs.on("move", b);
    viirs.jumpTo({ center: modis.getCenter(), zoom: modis.getZoom() });
    return () => {
      modis.off("move", a);
      viirs.off("move", b);
    };
  }, [cmpMaps, compare]);

  // ---- drawing
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [busy, setBusy] = useState(false);
  const [areaError, setAreaError] = useState<string | null>(null);
  const applyGeometry = async (g: PolygonGeometry) => {
    setDrawMode("none");
    setAreaError(null);
    setBusy(true);
    try {
      const { id } = await registerArea(g, meta.features.areas);
      setState({ area: id, region: null });
    } catch (e) {
      setAreaError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };
  const pickCell = (cell: string) => void applyGeometry({ type: "Polygon", coordinates: [cellToBoundary(cell, true) as Position[]] });

  const fitTo = useMemo(
    () => (selection.bbox ? { bbox: selection.bbox, key: selection.key } : selection.geometry ? { bbox: bboxOf(selection.geometry), key: selection.key } : null),
    [selection],
  );
  const ramp = valueScale(prefs.palette, legendMax);
  const methodLong = t(`method.${method}.long`);
  const gridLong = t(`method.${gridMetric}.long`);

  return (
    <div className="ow-start">
      <OrbitalMap
        className="ow-map--full"
        fullscreen="page"
        fitPadding={FIT_PADDING}
        initialBbox={meta.bbox}
        attribution={meta.attribution}
        ariaLabel={t("start.mapAria")}
        countries={countries}
        regions={finestRegions}
        onRegionClick={(id) => selectRegion(id)}
        selection={selection.kind === "all" ? null : selection.geometry}
        fitTo={fitTo}
        cells={rawFamily ? rawLayers?.layers[rawFamily]?.cells ?? null : cellsFc}
        hotspots={rawFamily ? rawLayers?.layers[rawFamily]?.points ?? null : pointsFc}
        onView={setView}
        onMoveStart={reveal.onMoveStart}
        onMoveEnd={reveal.onMoveEnd}
        drawMode={drawMode}
        maxVertices={meta.limits.geometry_max_vertices}
        onDrawComplete={(g) => void applyGeometry(g)}
        onDrawCancel={() => setDrawMode("none")}
      />

      {compare && (
        <div className="ow-compare">
          {(["modis", "viirs"] as const).map((fam) => (
            <OrbitalMap key={fam} className="ow-compare__map" fullscreen="map" fitPadding={FIT_PADDING_COMPARE}
              initialBbox={selection.bbox ?? meta.bbox} attribution={meta.attribution} ariaLabel={t("cmp.mapAria", { family: FAMILY_NAME[fam] })}
              countries={countries} regions={finestRegions} onRegionClick={(id) => selectRegion(id)}
              selection={selection.kind === "all" ? null : selection.geometry} fitTo={fam === "modis" ? fitTo : null}
              cells={rawLayers?.layers[fam]?.cells ?? null} hotspots={rawLayers?.layers[fam]?.points ?? null}
              onView={fam === "modis" ? setCmpView : undefined} onMap={fam === "modis" ? onModisMap : onViirsMap}>
              <p className="ow-compare__label" data-family={fam}>{t(`cmp.mapLabel.${fam}`)}</p>
            </OrbitalMap>
          ))}
        </div>
      )}

      <div className="ow-exitslot">
        <ExitButton info={info} isArea={selection.kind === "area"} escapeEnabled={drawMode === "none"}
          onExit={(target) => setState(target)} />
      </div>

      <Header floating />

      <aside className="ow-sidebar" aria-label={t("start.sidebarAria")}>
        {display !== "harmonised" && (
          <Tile title={t("cmp.title")}>
            <SensorCompare data={comparison} loading={raw.status === "loading"} error={raw.status === "error" ? raw.error : null} onRetry={raw.reload} />
          </Tile>
        )}
        <SettingsTile date={date} minDate={meta.first_date} maxDate={meta.last_date} onDate={(d) => setState({ date: d, d: null })}
          conf={conf} onConf={(c) => setState({ conf: c })} method={method} onMethod={(m) => setState({ metric: m })} eventsAvailable={eventsAvailable} />
        <RegionTile regions={regions} selectedId={state.region} path={info.path} onSelect={selectRegion} />
        <Tile title={t("cal.title")}>
          <p className="ow-small ow-muted ow-tile__lead">{t("cal.perMonth", { method: methodLong })}</p>
          {heatQuery.status === "loading" && <Loading height={180} />}
          {heatQuery.status === "error" && <ErrorNote error={heatQuery.error} onRetry={heatQuery.reload} />}
          {heatCells && heatQuery.status === "success" && (
            <MonthGrid cells={heatCells} selectedDate={date} unit={method === "frp_sum" ? "MW" : t(method === "events" ? "unit.events" : "unit.hotspots")}
              formatValue={(v) => f.method(method, v)} minYear={method === "events" ? 2012 : undefined}
              onSelect={(c) => setState({ date: c.end > meta.last_date ? meta.last_date : c.end, d: null })} />
          )}
          {method === "events" && <p className="ow-note">{t("cal.eventsNote")}</p>}
        </Tile>
        <FrequentTile metric={gridMetric} conf={conf} onPick={pickCell} />
      </aside>

      <InfoBoxes boxes={boxes} visible={reveal.visible && boxes.length > 0 && !compare} />

      <div className="ow-bottom">
        <DisplaySwitch value={display} onChange={(d) => setState({ display: d })} />
        {!compare && <DrawBar mode={drawMode} onMode={setDrawMode} busy={busy} onClear={state.area ? () => setState({ area: null }) : null} />}
      </div>

      <div className="ow-corner">
        {display !== "harmonised" ? (
          <section className="ow-legend" aria-label={t("legend.aria")}>
            <h2 className="ow-legend__title">
              {rawPoints ? t("legend.byAge") : compare ? t("cmp.legend") : t("cmp.legendFamily", { family: FAMILY_NAME[rawFamily ?? "modis"] })}
              <Tip text={t("legend.tip", { zoom: HOTSPOT_MIN_ZOOM, res: rawResolution })} label={t("legend.about")} />
              {raw.status === "loading" && <Spinner label={t("legend.loading")} />}
            </h2>
            <p className="ow-legend__sub">{t("legend.window", { days: MAP_WINDOW_DAYS, date: f.date(date) })}</p>
            {!rawPoints && rawLayers && (
              <div className="ow-ramp">
                <span>0</span>
                <span className="ow-ramp__bar" style={{ background: `linear-gradient(to right, ${[0, 0.1, 0.3, 0.6, 1].map((v) => rawLayers.color(rawLayers.max * v * v)).join(", ")})` }} />
                <span>{f.int(rawLayers.max)} {t("cmp.detections")}</span>
              </div>
            )}
            {raw.data?.truncated && <p className="ow-small">{t("cmp.truncated", { returned: raw.data.returned, total: raw.data.total })}</p>}
          </section>
        ) : (
        <section className="ow-legend" aria-label={t("legend.aria")}>
          <h2 className="ow-legend__title">
            {showPoints ? t("legend.byAge") : t("legend.perCell", { metric: gridLong })}
            <Tip text={t("legend.tip", { zoom: HOTSPOT_MIN_ZOOM, res: resolution })} label={t("legend.about")} />
            {mapLoading && <Spinner label={t("legend.loading")} />}
          </h2>
          <p className="ow-legend__sub">{t("legend.window", { days: MAP_WINDOW_DAYS, date: f.date(date) })}</p>
          {!showPoints && (
            <div className="ow-ramp">
              <span>0</span>
              <span className="ow-ramp__bar" style={{ background: `linear-gradient(to right, ${[0, 0.1, 0.3, 0.6, 1].map((s) => ramp(legendMax * s * s)).join(", ")})` }} />
              <span>{f.method(gridMetric, legendMax)} {gridMetric === "fires" ? t("unit.hotspots") : "MW"}</span>
            </div>
          )}
          {showPoints && hotspots.data?.truncated && (
            <p className="ow-small">{t("legend.truncated", { returned: hotspots.data.returned, total: hotspots.data.total })}</p>
          )}
          {mapError !== null && <ErrorNote error={mapError} onRetry={showPoints ? hotspots.reload : grid.reload} />}
          {grid.status === "success" && gridData?.cells.length === 0 && <Empty>{t("legend.empty")}</Empty>}
        </section>
        )}

        <section className="ow-selection" aria-label={t("sel.title")}>
          <p className="ow-selection__label">{t("sel.title")}</p>
          <p className="ow-selection__name">{info.name}</p>
          <p className="ow-selection__detail">{info.detail}</p>
          {(info.parentCountry || state.region || state.area) && (
            <div className="ow-selection__actions">
              {info.parentCountry && (
                <button type="button" className="ow-btn ow-btn--small" onClick={() => selectRegion(info.parentCountry?.properties.id ?? null)}>
                  {t("sel.backTo", { country: regionName(info.parentCountry) })}
                </button>
              )}
              <button type="button" className="ow-btn ow-btn--small ow-btn--ghost" onClick={() => selectRegion(null)}>{t("sel.clear")}</button>
            </div>
          )}
          {areaError && <p className="ow-error" role="alert">{areaError}</p>}
        </section>

        <button type="button" className="ow-btn ow-btn--primary ow-btn--block" onClick={() => setState({ page: "analysis", date, d: null }, { push: true })}>
          {t("start.analysis")}
        </button>
      </div>
    </div>
  );
}
