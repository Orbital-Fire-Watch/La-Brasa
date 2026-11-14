import type * as GeoJSON from "geojson";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef, useState, type RefObject } from "react";
import { CONFIG } from "../lib/config";
import type { BBox } from "../lib/geo";

// MapLibre 6 looks for its web worker next to its own file, which no longer exists once Vite bundles the
// library. Vite builds the worker itself (?worker&url) and MapLibre gets its URL.
maplibregl.setWorkerUrl(maplibreWorkerUrl);

/**
 * Creates a MapLibre map in `container` and returns it once the style is loaded and `setup` (sources, layers)
 * has run. The map is created once per container: later bbox changes are handled with fitBounds by the caller,
 * so only the first values of the other arguments count.
 */
export function useMapLibre(
  container: RefObject<HTMLDivElement | null>,
  initialBbox: BBox,
  attribution: string,
  setup?: (map: MlMap) => void,
): MlMap | null {
  const [map, setMap] = useState<MlMap | null>(null);
  const initial = useRef({ initialBbox, attribution, setup });

  useEffect(() => {
    if (!container.current) return;
    const { initialBbox, attribution, setup } = initial.current;
    const m = new maplibregl.Map({
      container: container.current,
      style: CONFIG.basemapStyleUrl,
      bounds: initialBbox,
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true, customAttribution: attribution },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxZoom: 16,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.on("load", () => {
      // Start with the attribution collapsed behind its (i) button – expanded it covers the map legend.
      // MapLibre does the same after the first drag anyway.
      m.getContainer().querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      setup?.(m);
      setMap(m);
    });
    return () => {
      setMap(null);
      m.remove();
    };
  }, [container]);

  return map;
}

export const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Keeps a GeoJSON source in sync with React data. */
export function useGeoJsonData(map: MlMap | null, sourceId: string, data: GeoJSON.FeatureCollection | null | undefined) {
  useEffect(() => {
    (map?.getSource(sourceId) as GeoJSONSource | undefined)?.setData(data ?? EMPTY_FC);
  }, [map, sourceId, data]);
}

export function mapBbox(map: MlMap): BBox {
  const b = map.getBounds();
  const r = (v: number) => Math.round(v * 1e4) / 1e4;
  return [r(Math.max(-180, b.getWest())), r(Math.max(-90, b.getSouth())), r(Math.min(180, b.getEast())), r(Math.min(90, b.getNorth()))];
}
