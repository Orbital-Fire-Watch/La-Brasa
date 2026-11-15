/** Root of the app: loads meta and regions, keeps the sync state, then shows the start or the analysis page. */
import { useMemo } from "react";
import { useApiQuery } from "./hooks/useApiQuery";
import { AppDataContext, type AppData } from "./hooks/useAppData";
import { finestRegions } from "./lib/regions";
import { fireApi } from "./services/api/fireApi";
import { Logo } from "./components/Header";
import { ErrorNote, Spinner } from "./components/ui/Elements";
import { I18nProvider, useI18n } from "./i18n/I18n";
import { useAppState } from "./hooks/useAppState";
import { AnalysisPage } from "./routes/AnalysisPage";
import { StartPage } from "./routes/StartPage";
import { PrefsProvider } from "./hooks/usePrefs";
import { SyncContextProvider, useSyncController } from "./hooks/useSync";

function Pages() {
  const [state] = useAppState();
  const { t } = useI18n();
  const meta = useApiQuery("meta", (signal) => fireApi.meta(signal));
  // While /api/meta reloads after a sync, keep the previous answer: the pages (and the map) stay mounted.
  const { effectiveMeta, value: sync } = useSyncController(meta.data ?? null, meta.reload);
  const version = effectiveMeta?.data_version ?? null;
  const regions = useApiQuery(version ? `regions|${version}` : null, (signal) => fireApi.regions(signal));

  const regionsData = regions.data ?? null;
  const data = useMemo<AppData | null>(() => {
    if (!effectiveMeta) return null;
    const r = regionsData;
    return { meta: effectiveMeta, regions: r, regionById: new Map((r?.features ?? []).map((f) => [f.properties.id, f])), finestRegions: finestRegions(r) };
  }, [effectiveMeta, regionsData]);

  if (!data || !sync) {
    return (
      <div className="ow-splash">
        <Logo size="large" />
        {meta.status === "error" ? (
          <ErrorNote error={meta.error} onRetry={meta.reload} />
        ) : (
          <p className="ow-splash__text"><Spinner /> {t("splash.live")}</p>
        )}
      </div>
    );
  }
  return (
    <SyncContextProvider value={sync}>
      <AppDataContext.Provider value={data}>
        {state.page === "analysis" ? <AnalysisPage /> : <StartPage />}
      </AppDataContext.Provider>
    </SyncContextProvider>
  );
}

export function App() {
  return (
    <PrefsProvider>
      <I18nProvider>
        <Pages />
      </I18nProvider>
    </PrefsProvider>
  );
}
