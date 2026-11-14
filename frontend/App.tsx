import { useMemo, useRef } from "react";
import { Brand } from "./components/Brand";
import { ErrorBlock, Spinner } from "./components/ui/Status";
import { clearQueryCache, useApiQuery } from "./hooks/useApiQuery";
import { AppDataContext, type AppData } from "./hooks/useAppData";
import { useAppState } from "./hooks/useAppState";
import { CONFIG } from "./lib/config";
import { AnalysisPage } from "./routes/AnalysisPage";
import { SelectionPage } from "./routes/SelectionPage";
import { fireApi } from "./services/api/fireApi";

export function App() {
  const [state] = useAppState();
  const meta = useApiQuery("meta", (signal) => fireApi.meta(signal));
  const version = meta.status === "success" ? meta.data.data_version : null;
  const regions = useApiQuery(version ? `regions|${version}` : null, (signal) => fireApi.regions(signal));

  // A new data_version means a new import: cached answers are outdated (spec §6.1).
  const lastVersion = useRef<string | null>(null);
  if (version && lastVersion.current && lastVersion.current !== version) clearQueryCache();
  if (version) lastVersion.current = version;

  const data = useMemo<AppData | null>(() => {
    if (meta.status !== "success") return null;
    const r = regions.status === "success" ? regions.data : null;
    return { meta: meta.data, regions: r, regionById: new Map((r?.features ?? []).map((f) => [f.properties.id, f])) };
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
      {state.page === "analysis" ? <AnalysisPage /> : <SelectionPage />}
    </AppDataContext.Provider>
  );
}
