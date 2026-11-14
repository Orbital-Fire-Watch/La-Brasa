import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { Brand } from "./components/Brand";
import { ErrorBlock, Spinner } from "./components/ui/Status";
import { clearQueryCache, useApiQuery } from "./hooks/useApiQuery";
import { AppDataContext, type AppData } from "./hooks/useAppData";
import { useAppState } from "./hooks/useAppState";
import { CONFIG } from "./lib/config";
import { finestRegions, localizeRegions } from "./lib/regions";
import { fireApi } from "./services/api/fireApi";

// Each page is loaded when it is first shown, so the first page does not wait for the code of the second.
const SelectionPage = lazy(() => import("./routes/SelectionPage").then((m) => ({ default: m.SelectionPage })));
const AnalysisPage = lazy(() => import("./routes/AnalysisPage").then((m) => ({ default: m.AnalysisPage })));

export function App() {
  const [state] = useAppState();
  const meta = useApiQuery("meta", (signal) => fireApi.meta(signal));
  const version = meta.status === "success" ? meta.data.data_version : null;
  const regions = useApiQuery(version ? `regions|${version}` : null, async (signal) => localizeRegions(await fireApi.regions(signal)));

  // A new data_version means a new import: cached answers are outdated (spec §6.1).
  // Every query key contains the data_version, so this only frees the memory of the old answers.
  const lastVersion = useRef<string | null>(null);
  useEffect(() => {
    if (version && lastVersion.current && lastVersion.current !== version) clearQueryCache();
    if (version) lastVersion.current = version;
  }, [version]);

  const data = useMemo<AppData | null>(() => {
    if (meta.status !== "success") return null;
    const r = regions.status === "success" ? regions.data : null;
    return {
      meta: meta.data,
      regions: r,
      regionById: new Map((r?.features ?? []).map((f) => [f.properties.id, f])),
      finestRegions: finestRegions(r),
    };
  }, [meta, regions]);

  if (!data) {
    return (
      <div className="splash">
        <Brand />
        {meta.status === "error" ? (
          <ErrorBlock error={meta.error} onRetry={meta.reload} />
        ) : (
          <p className="splash__text">
            <Spinner /> {CONFIG.apiMode === "mock" ? "Mock-Daten werden erzeugt …" : "Verbindung zur Fire-API …"}
          </p>
        )}
      </div>
    );
  }

  return (
    <AppDataContext.Provider value={data}>
      <Suspense fallback={<div className="splash"><Brand /><p className="splash__text"><Spinner /> Seite wird geladen …</p></div>}>
        {state.page === "analysis" ? <AnalysisPage /> : <SelectionPage />}
      </Suspense>
    </AppDataContext.Provider>
  );
}
