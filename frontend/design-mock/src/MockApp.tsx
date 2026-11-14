/** Root of the design mock: loads meta and regions through the same fireApi as the app, then shows a page. */
import { useMemo } from "react";
import { useApiQuery } from "../../hooks/useApiQuery";
import { AppDataContext, type AppData } from "../../hooks/useAppData";
import { CONFIG } from "../../lib/config";
import { finestRegions } from "../../lib/regions";
import { fireApi } from "../../services/api/fireApi";
import { Logo } from "./components/Header";
import { ErrorNote, Spinner } from "./components/ui";
import { I18nProvider, useI18n } from "./i18n/I18n";
import { useMockState } from "./mockState";
import { AnalysisPage } from "./pages/AnalysisPage";
import { StartPage } from "./pages/StartPage";
import { PrefsProvider } from "./prefs";
import { SyncContextProvider, useSyncController } from "./sync";

function Pages() {
  const [state] = useMockState();
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
          <p className="ow-splash__text"><Spinner /> {t(CONFIG.apiMode === "mock" ? "splash.mock" : "splash.live")}</p>
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

export function MockApp() {
  return (
    <PrefsProvider>
      <I18nProvider>
        <Pages />
      </I18nProvider>
    </PrefsProvider>
  );
}
