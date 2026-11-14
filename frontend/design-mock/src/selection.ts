/** Name, detail line and country of the current selection (hooks/useSelection has German labels). */
import { useAppData } from "../../hooks/useAppData";
import type { Selection } from "../../hooks/useSelection";
import { geometryAreaKm2 } from "../../lib/geo";
import type { RegionFeature } from "../../services/api/types";
import { useI18n } from "./i18n/I18n";

export interface SelectionInfo {
  name: string;
  detail: string;
  /** from the country down to the selected region; empty for "all" and drawn areas */
  path: RegionFeature[];
  /** the country above the selected region, or null when the country itself (or nothing) is selected */
  parentCountry: RegionFeature | null;
}

export function useSelectionInfo(selection: Selection): SelectionInfo {
  const { regionById, regions } = useAppData();
  const { t, f } = useI18n();
  const regionName = useRegionName();

  if (selection.kind === "region") {
    const id = selection.exportParams.region_id ?? "";
    const path: RegionFeature[] = [];
    for (let cur = regionById.get(id); cur; cur = cur.properties.parent ? regionById.get(cur.properties.parent) : undefined) path.unshift(cur);
    const selected = path[path.length - 1];
    const country = path[0]?.properties.level === "country" ? path[0] : null;
    return {
      name: selected ? regionName(selected) : id,
      detail: selected ? t(`level.${selected.properties.level}`) : t("level.region"),
      path,
      parentCountry: country && country !== selected ? country : null,
    };
  }
  if (selection.kind === "area") {
    return {
      name: t("area.drawn"),
      detail: selection.geometry ? t("area.approx", { area: f.km2(geometryAreaKm2(selection.geometry)) }) : t("area.outlineGone"),
      path: [],
      parentCountry: null,
    };
  }
  const islands = regions?.features.some((r) => /balear/i.test(r.properties.name));
  return { name: t("area.allName"), detail: t(islands ? "area.mainlandIslands" : "area.mainland"), path: [], parentCountry: null };
}

/** Countries in the user's language (Intl.DisplayNames); regions keep their official names. */
export function useRegionName(): (f: RegionFeature) => string {
  const { f } = useI18n();
  return (r) => (r.properties.level === "country" ? f.country(r.properties.id) : r.properties.name);
}
