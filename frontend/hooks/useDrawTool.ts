/**
 * Drawing on the map without an extra library: rectangle, circle and freehand by dragging,
 * polygon by clicking. Results follow spec §6.3 (circle with 64 steps, freehand simplified to ≤ 1000 points).
 */
import type { GeoJSONSource, Map as MlMap, MapMouseEvent, MapTouchEvent } from "maplibre-gl";
import { useEffect, useRef } from "react";
import { formatOne } from "../lib/format";
import {
  circlePolygon, closeRing, distanceKm, rectanglePolygon, roundPosition, simplifyToMaxVertices,
  type PolygonGeometry, type Position,
} from "../lib/geo";

export type DrawMode = "none" | "rectangle" | "circle" | "polygon" | "freehand";

export const DRAW_SOURCE = "draw-preview";

interface Callbacks {
  onComplete: (g: PolygonGeometry) => void;
  onCancel: () => void;
  onHint: (text: string) => void;
}

const MIN_FREEHAND_STEP_PX = 3;

function setPreview(map: MlMap, features: GeoJSON.Feature[]) {
  (map.getSource(DRAW_SOURCE) as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features });
}

const polygonFeature = (g: PolygonGeometry): GeoJSON.Feature => ({ type: "Feature", properties: {}, geometry: g });
const lineFeature = (coords: Position[]): GeoJSON.Feature => ({
  type: "Feature",
  properties: {},
  geometry: { type: "LineString", coordinates: coords },
});
const pointFeatures = (coords: Position[]): GeoJSON.Feature[] =>
  coords.map((c) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: c } }));

export function useDrawTool(map: MlMap | null, mode: DrawMode, maxVertices: number, callbacks: Callbacks) {
  const cb = useRef(callbacks);
  useEffect(() => {
    cb.current = callbacks;
  });

  useEffect(() => {
    if (!map || mode === "none") return;
    const canvas = map.getCanvas();
    canvas.style.cursor = "crosshair";
    const pos = (e: MapMouseEvent | MapTouchEvent): Position => roundPosition([e.lngLat.lng, e.lngLat.lat]);
    const offs: (() => void)[] = [];
    const on = <K extends "mousedown" | "mousemove" | "mouseup" | "click" | "dblclick" | "touchstart" | "touchmove" | "touchend">(
      type: K,
      fn: (e: MapMouseEvent | MapTouchEvent) => void,
    ) => {
      map.on(type, fn as never);
      offs.push(() => map.off(type, fn as never));
    };

    const finish = (g: PolygonGeometry) => {
      setPreview(map, []);
      cb.current.onComplete(g);
    };

    if (mode === "polygon") {
      const points: Position[] = [];
      map.doubleClickZoom.disable();
      cb.current.onHint("Klicken setzt Eckpunkte · Doppelklick oder Enter schließt · Esc bricht ab");
      const render = (cursor?: Position) => {
        const line = cursor ? [...points, cursor] : points;
        setPreview(map, [
          ...(line.length >= 3 ? [polygonFeature({ type: "Polygon", coordinates: [closeRing(line)] })] : []),
          ...(line.length >= 2 ? [lineFeature(line)] : []),
          ...pointFeatures(points),
        ]);
      };
      const complete = () => {
        if (points.length >= 3) finish({ type: "Polygon", coordinates: [closeRing(points)] });
      };
      on("click", (e) => {
        points.push(pos(e));
        render();
      });
      on("mousemove", (e) => render(pos(e)));
      on("dblclick", (e) => {
        e.preventDefault();
        complete();
      });
      const onKey = (e: KeyboardEvent) => {
        if (e.key === "Enter") complete();
        if (e.key === "Backspace" && points.length) {
          points.pop();
          render();
        }
      };
      window.addEventListener("keydown", onKey);
      offs.push(() => window.removeEventListener("keydown", onKey));
      offs.push(() => map.doubleClickZoom.enable());
    } else {
      let start: Position | null = null;
      let path: Position[] = [];
      let lastPixel: [number, number] | null = null;
      map.dragPan.disable();
      cb.current.onHint(
        mode === "rectangle" ? "Ziehen: Rechteck aufspannen" : mode === "circle" ? "Ziehen: vom Mittelpunkt aus den Radius festlegen" : "Ziehen: Gebiet frei umfahren",
      );
      const shape = (end: Position): PolygonGeometry | null => {
        if (!start) return null;
        if (mode === "rectangle") return rectanglePolygon(start, end);
        if (mode === "circle") return circlePolygon(start, Math.max(0.1, distanceKm(start, end)));
        return path.length >= 3 ? { type: "Polygon", coordinates: [closeRing(path)] } : null;
      };
      const down = (e: MapMouseEvent | MapTouchEvent) => {
        e.preventDefault();
        start = pos(e);
        path = [start];
        lastPixel = [e.point.x, e.point.y];
      };
      const move = (e: MapMouseEvent | MapTouchEvent) => {
        if (!start) return;
        const p = pos(e);
        if (mode === "freehand" && lastPixel) {
          if (Math.hypot(e.point.x - lastPixel[0], e.point.y - lastPixel[1]) < MIN_FREEHAND_STEP_PX) return;
          lastPixel = [e.point.x, e.point.y];
          path.push(p);
          setPreview(map, [lineFeature(path)]);
          return;
        }
        const g = shape(p);
        if (g) setPreview(map, [polygonFeature(g)]);
        if (mode === "circle") cb.current.onHint(`Radius: ${formatOne(distanceKm(start, p))} km`);
      };
      const up = (e: MapMouseEvent | MapTouchEvent) => {
        if (!start) return;
        const end = mode === "freehand" || !e.lngLat ? path[path.length - 1] : pos(e);
        const g = shape(end);
        start = null;
        if (!g) return setPreview(map, []);
        if (mode === "freehand") g.coordinates = [simplifyToMaxVertices(g.coordinates[0], maxVertices)];
        finish(g);
      };
      on("mousedown", down);
      on("mousemove", move);
      on("mouseup", up);
      on("touchstart", down);
      on("touchmove", move);
      on("touchend", up);
      offs.push(() => map.dragPan.enable());
    }

    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") cb.current.onCancel();
    };
    window.addEventListener("keydown", onEsc);
    offs.push(() => window.removeEventListener("keydown", onEsc));

    return () => {
      offs.forEach((off) => off());
      canvas.style.cursor = "";
      setPreview(map, []);
      cb.current.onHint("");
    };
  }, [map, mode, maxVertices]);
}
