import { useCallback, useState } from "react";

export type Basemap = "map" | "satellite";

const STORAGE_KEY = "la-brasa:basemap";

function stored(): Basemap {
  try {
    return localStorage.getItem(STORAGE_KEY) === "satellite" ? "satellite" : "map";
  } catch {
    return "map";
  }
}

/** Map or satellite background; remembered per browser so both pages open with the last choice. */
export function useBasemap(): [Basemap, (b: Basemap) => void] {
  const [basemap, setBasemap] = useState<Basemap>(stored);
  const set = useCallback((b: Basemap) => {
    setBasemap(b);
    try {
      localStorage.setItem(STORAGE_KEY, b);
    } catch {
      // Private mode or blocked storage: the choice just is not remembered.
    }
  }, []);
  return [basemap, set];
}
