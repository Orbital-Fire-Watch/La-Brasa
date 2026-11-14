/**
 * MapLibre map of the mock, used on both pages. Same layers and data flow as components/map/FireMap, with
 * the mock's layout: "Map / Satellite" sits directly above the +/− buttons, a fullscreen button below them,
 * English popups, brand colours, and movestart/moveend callbacks for the sliding info boxes.
 */
import type * as GeoJSON from "geojson";
import * as maplibregl from "maplibre-gl";
import type { Map as MlMap, MapGeoJSONFeature } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useBasemap, type Basemap } from "../../hooks/useBasemap";
import { DRAW_SOURCE, useDrawTool, type DrawMode } from "../../hooks/useDrawTool";
import { EMPTY_FC, mapBbox, useGeoJsonData } from "../../hooks/useMapLibre";
import { CONFIG } from "../../lib/config";
import { worldWithout, type AreaGeometry, type BBox, type PolygonGeometry } from "../../lib/geo";
import type { RegionFeature } from "../../services/api/types";
import { useI18n } from "../../i18n/I18n";
import type { PopupData } from "../../lib/mapFeatures";

export interface MapView {
  bbox: BBox;
  zoom: number;
}

interface OrbitalMapProps {
  initialBbox: BBox;
  attribution: string;
  ariaLabel: string;
  /** "page" = the browser fullscreen shows the whole page (start page), "map" = only this map */
  fullscreen: "page" | "map";
  /** room kept free around fitted areas, e.g. for the floating sidebar */
  fitPadding?: maplibregl.PaddingOptions;
  countries: RegionFeature[];
  regions?: RegionFeature[] | null;
  onRegionClick?: (id: string) => void;
  selection?: AreaGeometry | null;
  fitTo?: { bbox: BBox; key: string } | null;
  cells?: GeoJSON.FeatureCollection | null;
  events?: GeoJSON.FeatureCollection | null;
  eventPoints?: GeoJSON.FeatureCollection | null;
  hotspots?: GeoJSON.FeatureCollection | null;
  selectedEventId?: string | null;
  onEventClick?: (id: string) => void;
  onView?: (view: MapView) => void;
  onMoveStart?: () => void;
  onMoveEnd?: () => void;
  drawMode?: DrawMode;
  maxVertices?: number;
  onDrawComplete?: (g: PolygonGeometry) => void;
  onDrawCancel?: () => void;
  className?: string;
  /** gets the MapLibre instance once it is ready (used to keep the two comparison maps in step) */
  onMap?: (map: MlMap | null) => void;
  children?: ReactNode;
}

const BLUE = "#2f8cff";

const BASEMAP_PAINT: Record<Basemap, { maskOpacity: number; line: string; selection: string }> = {
  map: { maskOpacity: 0.35, line: "#3b4452", selection: "#0b1220" },
  satellite: { maskOpacity: 0.55, line: "#ffffff", selection: "#ffffff" },
};

function maskOutside(geometries: AreaGeometry[]): GeoJSON.FeatureCollection {
  if (geometries.length === 0) return EMPTY_FC;
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: worldWithout(geometries) }] };
}

function addLayers(map: MlMap) {
  const labels = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  const src = (id: string, promoteId?: string) => map.addSource(id, { type: "geojson", data: EMPTY_FC, ...(promoteId ? { promoteId } : {}) });

  map.addSource("satellite", {
    type: "raster", tiles: [CONFIG.satelliteTilesUrl], tileSize: 256, maxzoom: 19, attribution: CONFIG.satelliteAttribution,
  });
  map.addLayer({ id: "satellite", type: "raster", source: "satellite", layout: { visibility: "none" } }, labels);
  for (const id of ["coverage", "mask", "selection", "cells", "hotspots", DRAW_SOURCE]) src(id);
  src("regions", "id");
  src("events", "id");
  src("event-points", "id");

  map.addLayer({ id: "coverage-mask", type: "fill", source: "coverage", paint: { "fill-color": "#05080f", "fill-opacity": 0.35 } }, labels);
  map.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#05080f", "fill-opacity": 0.22 } }, labels);
  map.addLayer({
    id: "regions-fill", type: "fill", source: "regions",
    paint: { "fill-color": BLUE, "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.14, 0] },
  }, labels);
  map.addLayer({
    id: "regions-line", type: "line", source: "regions",
    paint: { "line-color": "#3b4452", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.3, 9, 1], "line-opacity": 0.5 },
  }, labels);
  map.addLayer({
    id: "coverage-line", type: "line", source: "coverage",
    paint: { "line-color": "#3b4452", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 9, 1.6], "line-opacity": 0.8 },
  }, labels);
  map.addLayer({
    id: "cells-fill", type: "fill", source: "cells",
    paint: { "fill-color": ["get", "color"], "fill-opacity": ["coalesce", ["get", "opacity"], 0.8] },
  }, labels);
  map.addLayer({
    id: "cells-line", type: "line", source: "cells", minzoom: 6,
    paint: { "line-color": "#ffffff", "line-width": 0.4, "line-opacity": 0.55 },
  }, labels);
  map.addLayer({ id: "selection-line", type: "line", source: "selection", paint: { "line-color": "#0b1220", "line-width": 2 } });
  map.addLayer({
    id: "events-fill", type: "fill", source: "events",
    paint: { "fill-color": ["get", "color"], "fill-opacity": ["coalesce", ["get", "opacity"], 0.55] },
  }, labels);
  map.addLayer({
    id: "events-line", type: "line", source: "events",
    paint: { "line-color": ["get", "stroke"], "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, 1.5] },
  });
  map.addLayer({
    id: "event-points", type: "circle", source: "event-points", maxzoom: 10,
    paint: {
      "circle-color": ["get", "color"], "circle-radius": ["get", "radius"], "circle-opacity": ["coalesce", ["get", "opacity"], 0.85],
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 1,
    },
  });
  map.addLayer({ id: "events-selected", type: "line", source: "events", filter: ["==", ["get", "id"], ""], paint: { "line-color": BLUE, "line-width": 3 } });
  map.addLayer({
    id: "event-points-selected", type: "circle", source: "event-points", maxzoom: 10, filter: ["==", ["get", "id"], ""],
    paint: { "circle-color": "rgba(0,0,0,0)", "circle-radius": ["+", ["get", "radius"], 4], "circle-stroke-color": BLUE, "circle-stroke-width": 3 },
  });
  map.addLayer({
    id: "hotspots", type: "circle", source: "hotspots",
    paint: {
      "circle-color": ["get", "color"], "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 2, 11, 4, 15, 7],
      "circle-stroke-color": "#1a0d05", "circle-stroke-width": 0.6,
    },
  });
  map.addLayer({ id: "draw-fill", type: "fill", source: DRAW_SOURCE, filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": BLUE, "fill-opacity": 0.15 } });
  map.addLayer({ id: "draw-line", type: "line", source: DRAW_SOURCE, paint: { "line-color": BLUE, "line-width": 2, "line-dasharray": [2, 1] } });
  map.addLayer({
    id: "draw-points", type: "circle", source: DRAW_SOURCE, filter: ["==", ["geometry-type"], "Point"],
    paint: { "circle-color": BLUE, "circle-radius": 4, "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
  });
}

/** Map instance with the mock's control order; created once per container. */
function useOrbitalMapInstance(
  container: RefObject<HTMLDivElement | null>,
  initialBbox: BBox,
  attribution: string,
  fullscreen: "page" | "map",
  fitPadding?: maplibregl.PaddingOptions,
): { map: MlMap | null; basemapSlot: HTMLElement | null } {
  const [ready, setReady] = useState<{ map: MlMap; basemapSlot: HTMLElement } | null>(null);
  const initial = useRef({ initialBbox, attribution, fullscreen, fitPadding });

  useEffect(() => {
    if (!container.current) return;
    const { initialBbox, attribution, fullscreen, fitPadding } = initial.current;
    const m = new maplibregl.Map({
      container: container.current,
      style: CONFIG.basemapStyleUrl,
      bounds: initialBbox,
      fitBoundsOptions: { padding: fitPadding ?? 24 },
      attributionControl: { compact: true, customAttribution: attribution },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxZoom: 16,
    });
    m.touchZoomRotate.disableRotation();
    // Order in the top-right corner: Map/Satellite, then +/−, then fullscreen (spec: toggle above the +/− buttons).
    const slot = document.createElement("div");
    slot.className = "maplibregl-ctrl ow-basemap";
    m.addControl({ onAdd: () => slot, onRemove: () => slot.remove() }, "top-right");
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.FullscreenControl(fullscreen === "page" ? { container: document.documentElement } : {}), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.on("load", () => {
      m.getContainer().querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      addLayers(m);
      setReady({ map: m, basemapSlot: slot });
    });
    return () => {
      setReady(null);
      m.remove();
    };
  }, [container]);

  return { map: ready?.map ?? null, basemapSlot: ready?.basemapSlot ?? null };
}

function popupNode(data: PopupData, eventLabel: string, onEvent?: (id: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "ow-popup";
  const h = document.createElement("strong");
  h.textContent = data.title;
  const dl = document.createElement("dl");
  for (const [k, v] of data.rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  root.append(h, dl);
  if (data.eventId && onEvent) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ow-btn ow-btn--small";
    btn.textContent = eventLabel;
    const id = data.eventId;
    btn.addEventListener("click", () => onEvent(id));
    root.append(btn);
  }
  return root;
}

function parsePopup(f: MapGeoJSONFeature): PopupData | null {
  const raw = f.properties?.popup;
  if (typeof raw !== "string") return null;
  try {
    return JSON.parse(raw) as PopupData;
  } catch {
    return null;
  }
}

export function OrbitalMap(props: OrbitalMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const [basemap, setBasemap] = useBasemap();
  const { t } = useI18n();
  const { map, basemapSlot } = useOrbitalMapInstance(container, props.initialBbox, props.attribution, props.fullscreen, props.fitPadding);
  const latest = useRef({ ...props, eventLabel: "" });
  const eventLabel = t("map.showEvent");
  useEffect(() => {
    latest.current = { ...props, eventLabel };
  });

  useEffect(() => {
    latest.current.onMap?.(map);
  }, [map]);

  useEffect(() => {
    if (!map) return;
    let hoverId: string | number | undefined;
    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px", className: "ow-maplibre-popup" });
    const isDrawing = () => (latest.current.drawMode ?? "none") !== "none";
    const report = () => latest.current.onView?.({ bbox: mapBbox(map), zoom: map.getZoom() });
    const onMoveStart = () => latest.current.onMoveStart?.();
    const onMoveEnd = () => {
      report();
      latest.current.onMoveEnd?.();
    };
    map.on("movestart", onMoveStart);
    map.on("moveend", onMoveEnd);
    report();

    map.on("mousemove", "regions-fill", (e) => {
      if (!latest.current.onRegionClick || isDrawing()) return;
      const id = e.features?.[0]?.id;
      if (hoverId !== undefined) map.setFeatureState({ source: "regions", id: hoverId }, { hover: false });
      hoverId = id;
      if (id !== undefined) map.setFeatureState({ source: "regions", id }, { hover: true });
    });
    map.on("mouseleave", "regions-fill", () => {
      if (hoverId !== undefined) map.setFeatureState({ source: "regions", id: hoverId }, { hover: false });
      hoverId = undefined;
    });
    for (const layer of ["cells-fill", "hotspots", "events-fill", "event-points"]) {
      map.on("mouseenter", layer, () => {
        if (!isDrawing()) map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        if (!isDrawing()) map.getCanvas().style.cursor = "";
      });
    }
    map.on("click", (e) => {
      if (isDrawing()) return;
      const top = map.queryRenderedFeatures(e.point, { layers: ["hotspots", "event-points", "events-fill", "cells-fill", "regions-fill"] })[0];
      if (!top) return;
      const layer = top.layer.id;
      if ((layer === "events-fill" || layer === "event-points") && latest.current.onEventClick) {
        latest.current.onEventClick(String(top.properties?.id));
        return;
      }
      if (layer === "hotspots" || layer === "cells-fill") {
        const data = parsePopup(top);
        if (data) {
          popup.setLngLat(e.lngLat).setDOMContent(popupNode(data, latest.current.eventLabel, (id) => {
            popup.remove();
            latest.current.onEventClick?.(id);
          })).addTo(map);
        }
        return;
      }
      if (layer === "regions-fill" && latest.current.onRegionClick) latest.current.onRegionClick(String(top.properties?.id));
    });
    return () => {
      map.off("movestart", onMoveStart);
      map.off("moveend", onMoveEnd);
      popup.remove();
    };
  }, [map]);

  const outlines = useMemo<GeoJSON.FeatureCollection | null>(
    () => (props.regions ? { type: "FeatureCollection", features: props.regions } : null),
    [props.regions],
  );
  const selectionFc = useMemo<GeoJSON.FeatureCollection | null>(
    () => (props.selection ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: props.selection }] } : null),
    [props.selection],
  );
  const mask = useMemo(() => maskOutside(props.selection ? [props.selection] : []), [props.selection]);
  const coverage = useMemo(() => maskOutside(props.countries.map((f) => f.geometry)), [props.countries]);

  useGeoJsonData(map, "regions", outlines);
  useGeoJsonData(map, "selection", selectionFc);
  useGeoJsonData(map, "mask", mask);
  useGeoJsonData(map, "coverage", coverage);
  useGeoJsonData(map, "cells", props.cells);
  useGeoJsonData(map, "events", props.events);
  useGeoJsonData(map, "event-points", props.eventPoints);
  useGeoJsonData(map, "hotspots", props.hotspots);

  useEffect(() => {
    if (!map) return;
    const filter = ["==", ["get", "id"], props.selectedEventId ?? ""] as maplibregl.FilterSpecification;
    map.setFilter("events-selected", filter);
    map.setFilter("event-points-selected", filter);
  }, [map, props.selectedEventId]);

  useEffect(() => {
    if (!map) return;
    map.setLayoutProperty("satellite", "visibility", basemap === "satellite" ? "visible" : "none");
    const paint = BASEMAP_PAINT[basemap];
    map.setPaintProperty("coverage-mask", "fill-opacity", paint.maskOpacity);
    map.setPaintProperty("coverage-line", "line-color", paint.line);
    map.setPaintProperty("regions-line", "line-color", paint.line);
    map.setPaintProperty("selection-line", "line-color", paint.selection);
  }, [map, basemap]);

  const fitKey = props.fitTo?.key;
  useEffect(() => {
    const { fitTo, fitPadding } = latest.current;
    if (!map || !fitTo) return;
    const [x0, y0, x1, y1] = fitTo.bbox;
    if (![x0, y0, x1, y1].every(Number.isFinite)) return;
    map.fitBounds([[x0, y0], [x1, y1]], { padding: fitPadding ?? 40, maxZoom: 12, duration: 600 });
  }, [map, fitKey]);

  useDrawTool(map, props.drawMode ?? "none", props.maxVertices ?? 1000, {
    onComplete: (g) => props.onDrawComplete?.(g),
    onCancel: () => props.onDrawCancel?.(),
    onHint: () => undefined,
  });

  return (
    <div className={`ow-map ${props.className ?? ""}`}>
      <div ref={container} className="ow-map__canvas" role="region" aria-label={props.ariaLabel} />
      {props.children}
      {/* Rendered into MapLibre's top-right control stack, so it always sits directly above the +/− buttons. */}
      {basemapSlot && createPortal(
        <div role="group" aria-label={t("map.background")} className="ow-basemap__group">
          {(["map", "satellite"] as const).map((b) => (
            <button key={b} type="button" aria-pressed={basemap === b} onClick={() => setBasemap(b)}>
              {t(b === "map" ? "map.map" : "map.satellite")}
            </button>
          ))}
        </div>,
        basemapSlot,
      )}
    </div>
  );
}
