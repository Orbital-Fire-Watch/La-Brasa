/**
 * The MapLibre map used on both pages. All data layers are optional; each page passes the GeoJSON it needs.
 * Features carry their colour in `properties.color` (computed with the same scales as the legends) and their
 * popup content in `properties.popup` (JSON with title + rows), so this component stays free of domain logic.
 */
import maplibregl, { type Map as MlMap, type MapGeoJSONFeature } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DRAW_SOURCE, useDrawTool, type DrawMode } from "../../hooks/useDrawTool";
import { useAppData } from "../../hooks/useAppData";
import { useBasemap, type Basemap } from "../../hooks/useBasemap";
import { EMPTY_FC, mapBbox, useGeoJsonData, useMapLibre } from "../../hooks/useMapLibre";
import { CONFIG } from "../../lib/config";
import { worldWithout, type AreaGeometry, type BBox, type PolygonGeometry } from "../../lib/geo";
import type { RegionsResponse } from "../../services/api/types";
import { Segmented } from "../ui/Segmented";

export interface MapView {
  bbox: BBox;
  zoom: number;
}

export interface PopupData {
  title: string;
  rows: [string, string][];
  eventId?: string | null;
}

interface FireMapProps {
  initialBbox: BBox;
  attribution: string;
  ariaLabel: string;
  regions?: RegionsResponse | null;
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
  drawMode?: DrawMode;
  maxVertices?: number;
  onDrawComplete?: (g: PolygonGeometry) => void;
  onDrawCancel?: () => void;
  onDrawHint?: (text: string) => void;
  children?: ReactNode;
}

/** Darkening fill for everything outside the given areas. */
function maskOutside(geometries: AreaGeometry[]): GeoJSON.FeatureCollection {
  if (geometries.length === 0) return EMPTY_FC;
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: worldWithout(geometries) }] };
}

const BASEMAP_OPTIONS = [
  { value: "map", label: "Karte" },
  { value: "satellite", label: "Satellit" },
] as const;

/** Paint values that depend on the background: dark lines on the light map, light lines on imagery. */
const BASEMAP_PAINT: Record<Basemap, [layer: string, property: string, value: unknown][]> = {
  map: [
    ["coverage-mask", "fill-opacity", 0.3],
    ["coverage-line", "line-color", "#44403c"],
    ["regions-line", "line-color", "#57534e"],
    ["selection-line", "line-color", "#1c1917"],
  ],
  satellite: [
    ["coverage-mask", "fill-opacity", 0.55],
    ["coverage-line", "line-color", "#ffffff"],
    ["regions-line", "line-color", "#ffffff"],
    ["selection-line", "line-color", "#ffffff"],
  ],
};

function addLayers(map: MlMap) {
  // Area fills go below the basemap labels, outlines and points on top.
  const labels = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  const src = (id: string, promoteId?: string) =>
    map.addSource(id, { type: "geojson", data: EMPTY_FC, ...(promoteId ? { promoteId } : {}) });

  // Satellite imagery covers the basemap's areas and roads but stays below its labels and all data layers.
  // Hidden layers load no tiles, so the imagery is only fetched once the user switches to it.
  map.addSource("satellite", {
    type: "raster", tiles: [CONFIG.satelliteTilesUrl], tileSize: 256, maxzoom: 19, attribution: CONFIG.satelliteAttribution,
  });
  map.addLayer({ id: "satellite", type: "raster", source: "satellite", layout: { visibility: "none" } }, labels);

  src("coverage");
  src("regions", "id");
  src("mask");
  src("selection");
  src("cells");
  src("events", "id");
  src("event-points", "id");
  src("hotspots");
  src(DRAW_SOURCE);

  // Only Spain and Portugal are covered: every other country is clearly darker.
  map.addLayer({ id: "coverage-mask", type: "fill", source: "coverage", paint: { "fill-color": "#1c1917", "fill-opacity": 0.3 } }, labels);
  map.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#1c1917", "fill-opacity": 0.18 } }, labels);
  map.addLayer({
    id: "regions-fill", type: "fill", source: "regions",
    paint: { "fill-color": "#d9480f", "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.12, 0] },
  }, labels);
  map.addLayer({
    id: "regions-line", type: "line", source: "regions",
    paint: { "line-color": "#57534e", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.3, 9, 1], "line-opacity": 0.55 },
  }, labels);
  map.addLayer({
    id: "coverage-line", type: "line", source: "coverage",
    paint: { "line-color": "#44403c", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 9, 1.6], "line-opacity": 0.75 },
  }, labels);
  map.addLayer({
    id: "cells-fill", type: "fill", source: "cells",
    paint: { "fill-color": ["get", "color"], "fill-opacity": ["coalesce", ["get", "opacity"], 0.78] },
  }, labels);
  map.addLayer({
    id: "cells-line", type: "line", source: "cells", minzoom: 6,
    paint: { "line-color": "#ffffff", "line-width": 0.5, "line-opacity": 0.6 },
  }, labels);
  map.addLayer({ id: "selection-line", type: "line", source: "selection", paint: { "line-color": "#1c1917", "line-width": 2 } });
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
      "circle-color": ["get", "color"],
      "circle-radius": ["get", "radius"],
      "circle-opacity": ["coalesce", ["get", "opacity"], 0.85],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
    },
  });
  map.addLayer({
    id: "events-selected", type: "line", source: "events", filter: ["==", ["get", "id"], ""],
    paint: { "line-color": "#0b4f8a", "line-width": 3 },
  });
  map.addLayer({
    id: "event-points-selected", type: "circle", source: "event-points", maxzoom: 10, filter: ["==", ["get", "id"], ""],
    paint: { "circle-color": "rgba(0,0,0,0)", "circle-radius": ["+", ["get", "radius"], 4], "circle-stroke-color": "#0b4f8a", "circle-stroke-width": 3 },
  });
  map.addLayer({
    id: "hotspots", type: "circle", source: "hotspots",
    paint: {
      "circle-color": ["get", "color"],
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 2, 11, 4, 15, 7],
      "circle-stroke-color": "#3f1d0b",
      "circle-stroke-width": 0.6,
    },
  });
  map.addLayer({
    id: "draw-fill", type: "fill", source: DRAW_SOURCE, filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "fill-color": "#0b4f8a", "fill-opacity": 0.15 },
  });
  map.addLayer({
    id: "draw-line", type: "line", source: DRAW_SOURCE,
    paint: { "line-color": "#0b4f8a", "line-width": 2, "line-dasharray": [2, 1] },
  });
  map.addLayer({
    id: "draw-points", type: "circle", source: DRAW_SOURCE, filter: ["==", ["geometry-type"], "Point"],
    paint: { "circle-color": "#0b4f8a", "circle-radius": 4, "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
  });
}

function popupNode(data: PopupData, onEvent?: (id: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "popup";
  const h = document.createElement("strong");
  h.textContent = data.title;
  root.append(h);
  const dl = document.createElement("dl");
  for (const [k, v] of data.rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  root.append(dl);
  if (data.eventId && onEvent) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn--small";
    btn.textContent = "Ereignis anzeigen";
    btn.addEventListener("click", () => onEvent(data.eventId as string));
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

export function FireMap(props: FireMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const { regions: allRegions } = useAppData();
  const [basemap, setBasemap] = useBasemap();
  const map = useMapLibre(container, props.initialBbox, props.attribution);
  const [ready, setReady] = useState<MlMap | null>(null);
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  useEffect(() => {
    if (!map) return;
    addLayers(map);
    setReady(map);
    let hoverId: string | number | undefined;
    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "280px" });

    const report = () => latest.current.onView?.({ bbox: mapBbox(map), zoom: map.getZoom() });
    map.on("moveend", report);
    report();

    const isDrawing = () => (latest.current.drawMode ?? "none") !== "none";

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
      const hit = map.queryRenderedFeatures(e.point, { layers: ["hotspots", "event-points", "events-fill", "cells-fill", "regions-fill"] });
      const top = hit[0];
      if (!top) return;
      const layer = top.layer.id;
      if ((layer === "events-fill" || layer === "event-points") && latest.current.onEventClick) {
        latest.current.onEventClick(String(top.properties?.id));
        return;
      }
      if (layer === "hotspots" || layer === "cells-fill") {
        const data = parsePopup(top);
        if (data) {
          popup.setLngLat(e.lngLat).setDOMContent(popupNode(data, (id) => {
            popup.remove();
            latest.current.onEventClick?.(id);
          })).addTo(map);
        }
        return;
      }
      if (layer === "regions-fill" && latest.current.onRegionClick) latest.current.onRegionClick(String(top.properties?.id));
    });

    return () => {
      popup.remove();
    };
  }, [map]);

  const regionsData = useMemo(() => (props.regions ? (props.regions as unknown as GeoJSON.FeatureCollection) : null), [props.regions]);
  const provinces = useMemo<GeoJSON.FeatureCollection | null>(
    () =>
      regionsData && {
        type: "FeatureCollection",
        features: regionsData.features.filter((f) => f.properties?.level === "province"),
      },
    [regionsData],
  );
  const selectionFc = useMemo<GeoJSON.FeatureCollection | null>(
    () => (props.selection ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: props.selection }] } : null),
    [props.selection],
  );
  const mask = useMemo(() => maskOutside(props.selection ? [props.selection] : []), [props.selection]);
  const coverage = useMemo(
    () =>
      maskOutside(
        (allRegions?.features ?? []).filter((f) => f.properties.level === "country").map((f) => f.geometry),
      ),
    [allRegions],
  );

  useGeoJsonData(ready, "regions", provinces);
  useGeoJsonData(ready, "selection", selectionFc);
  useGeoJsonData(ready, "mask", mask);
  useGeoJsonData(ready, "coverage", coverage);
  useGeoJsonData(ready, "cells", props.cells);
  useGeoJsonData(ready, "events", props.events);
  useGeoJsonData(ready, "event-points", props.eventPoints);
  useGeoJsonData(ready, "hotspots", props.hotspots);

  useEffect(() => {
    if (!ready) return;
    const filter = ["==", ["get", "id"], props.selectedEventId ?? ""] as maplibregl.FilterSpecification;
    ready.setFilter("events-selected", filter);
    ready.setFilter("event-points-selected", filter);
  }, [ready, props.selectedEventId]);

  useEffect(() => {
    if (!ready) return;
    ready.setLayoutProperty("satellite", "visibility", basemap === "satellite" ? "visible" : "none");
    for (const [layer, property, value] of BASEMAP_PAINT[basemap]) ready.setPaintProperty(layer, property, value);
  }, [ready, basemap]);

  const fitKey = props.fitTo?.key;
  useEffect(() => {
    if (!ready || !props.fitTo) return;
    const [x0, y0, x1, y1] = props.fitTo.bbox;
    if (![x0, y0, x1, y1].every(Number.isFinite)) return;
    ready.fitBounds([[x0, y0], [x1, y1]], { padding: 40, maxZoom: 12, duration: 600 });
    // Only when the key changes, not on every new bbox array.
  }, [ready, fitKey]);

  useDrawTool(ready, props.drawMode ?? "none", props.maxVertices ?? 1000, {
    onComplete: (g) => props.onDrawComplete?.(g),
    onCancel: () => props.onDrawCancel?.(),
    onHint: (t) => props.onDrawHint?.(t),
  });

  return (
    <div className="map">
      <div ref={container} className="map__canvas" role="region" aria-label={props.ariaLabel} />
      {props.children}
      <div className="map-basemap">
        <Segmented label="Hintergrund" hideLabel size="small" value={basemap} options={BASEMAP_OPTIONS} onChange={setBasemap} />
      </div>
    </div>
  );
}
