/** The selected area (spec §2 "Gebiets-Angabe") with everything the views need to show and query it. */
import { useCallback, useMemo } from "react";
import { bboxOf, geometryAreaKm2, type BBox } from "../lib/geo";
import { formatKm2 } from "../lib/format";
import { shortHash } from "../lib/hash";
import { ApiError } from "../services/api/errors";
import { fireApi } from "../services/api/fireApi";
import type { AreaSelector, Geometry, RegionLevel } from "../services/api/types";
import { LOCAL_AREA_ID, loadAreaGeometry, saveAreaGeometry } from "../services/areaStore";
import { useAppData } from "./useAppData";
import type { AppState, SetAppState } from "./useAppState";

export const LEVEL_LABEL: Record<RegionLevel, string> = { country: "Land", region: "Region", province: "Provinz" };

export interface Selection {
  kind: "all" | "region" | "area";
  label: string;
  detail: string;
  selector: AreaSelector;
  geometry: Geometry | null;
  bbox: BBox | null;
  /** part of every query key */
  key: string;
  /** for the CSV file and export query */
  exportParams: { region_id?: string; area_id?: string };
}

/**
 * Registers a drawn area (POST /api/areas) or keeps it locally when the backend has no /areas yet
 * (then the requests send `geometry`, spec §2). Returns the value for the `area` URL parameter.
 */
export async function registerArea(geometry: Geometry, areasAvailable: boolean): Promise<{ id: string; geometry: Geometry }> {
  if (!areasAvailable) {
    saveAreaGeometry(LOCAL_AREA_ID, geometry);
    return { id: LOCAL_AREA_ID, geometry };
  }
  const res = await fireApi.areas({ geometry });
  saveAreaGeometry(res.area_id, res.geometry);
  return { id: res.area_id, geometry: res.geometry };
}

export function useSelection(state: AppState, setState: SetAppState) {
  const { regionById, meta } = useAppData();

  const selection = useMemo<Selection>(() => {
    if (state.region) {
      const f = regionById.get(state.region);
      const name = f?.properties.name ?? state.region;
      return {
        kind: "region",
        label: name,
        detail: f ? LEVEL_LABEL[f.properties.level] : "Region",
        selector: { region_id: state.region },
        geometry: f?.geometry ?? null,
        bbox: f?.properties.bbox ?? null,
        key: `r:${state.region}`,
        exportParams: { region_id: state.region },
      };
    }
    if (state.area) {
      const geometry = loadAreaGeometry(state.area);
      const local = state.area === LOCAL_AREA_ID;
      const selector: AreaSelector = local && geometry ? { geometry } : local ? {} : { area_id: state.area };
      return {
        kind: "area",
        label: "Gezeichnetes Gebiet",
        detail: geometry ? `ca. ${formatKm2(geometryAreaKm2(geometry))}` : "Umriss nicht mehr verfügbar",
        selector,
        geometry,
        bbox: geometry ? bboxOf(geometry) : null,
        key: local ? `g:${geometry ? shortHash(JSON.stringify(geometry)) : "none"}` : `a:${state.area}`,
        exportParams: local ? {} : { area_id: state.area },
      };
    }
    return {
      kind: "all",
      label: "Spanien + Portugal",
      detail: "Festland und Balearen",
      selector: {},
      geometry: null,
      bbox: meta.bbox,
      key: "all",
      exportParams: {},
    };
  }, [state.region, state.area, regionById, meta.bbox]);

  /**
   * Runs a request with the current area. On AREA_NOT_FOUND the drawn area is registered again and the
   * request repeated once (spec §6.3).
   */
  const withArea = useCallback(
    async <T>(request: (selector: AreaSelector) => Promise<T>): Promise<T> => {
      try {
        return await request(selection.selector);
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "AREA_NOT_FOUND" && selection.geometry)) throw e;
        const { id } = await registerArea(selection.geometry, meta.features.areas);
        if (id !== state.area) setState({ area: id });
        return request(id === LOCAL_AREA_ID ? { geometry: selection.geometry } : { area_id: id });
      }
    },
    [selection, meta.features.areas, setState, state.area],
  );

  return { selection, withArea };
}
