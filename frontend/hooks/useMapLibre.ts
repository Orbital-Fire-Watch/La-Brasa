import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import { useEffect, useState, type RefObject } from "react";
import { CONFIG } from "../lib/config";
import type { BBox } from "../lib/geo";

/** Creates a MapLibre map in `container` and returns it once the style is loaded. */
export function useMapLibre(container: RefObject<HTMLDivElement | null>, initialBbox: BBox, attribution: string): MlMap | null {
  const [map, setMap] = useState<MlMap | null>(null);

  useEffect(() => {
    if (!container.current) return;
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
      setMap(m);
    });
    return () => {
      setMap(null);
      m.remove();
    };
    // Created once per container; later bbox changes are handled with fitBounds by the caller.
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
