import { createContext, useContext } from "react";
import type { MetaResponse, RegionFeature, RegionsResponse } from "../services/api/types";

/** Data loaded once on start (spec §4: meta and regions on page load). */
export interface AppData {
  meta: MetaResponse;
  regions: RegionsResponse | null;
  regionById: Map<string, RegionFeature>;
  /** most detailed predefined areas (provinces, or regions while the API has no provinces) */
  finestRegions: RegionFeature[];
}

export const AppDataContext = createContext<AppData | null>(null);

export function useAppData(): AppData {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error("useAppData must be used inside <AppDataContext.Provider>");
  return ctx;
}
