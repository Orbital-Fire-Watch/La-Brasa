/** Controls on the map and in the header: sync, exit from the selected area, data view switch. */
import { useEffect } from "react";
import { useI18n } from "../../i18n/I18n";
import { DISPLAY_MODES, type DisplayMode } from "../../hooks/useAppState";
import type { SelectionInfo } from "../../hooks/useSelectionInfo";
import { useRegionName } from "../../hooks/useSelectionInfo";
import { useSync } from "../../hooks/useSync";
import { Spinner, Tip } from "../ui/Elements";

// ------------------------------------------------------------------ sync (header)

export function SyncButton() {
  const { state, run, dataVersion } = useSync();
  const { t, f } = useI18n();
  const running = state.status === "running";
  let status: string | null = null;
  if (state.status === "done") {
    status = state.result === "completed"
      ? t("sync.done", { time: f.time(state.at), count: state.newHotspots })
      : t("sync.upToDate", { time: f.time(state.at) });
  } else if (state.status === "failed") status = t("sync.failed");
  return (
    <div className="ow-sync">
      <button type="button" className="ow-headbtn" onClick={run} disabled={running} aria-busy={running}
        title={`${t("sync.title")}\n${t("sync.version", { version: dataVersion })}`}>
        {running ? <Spinner label={t("sync.running")} /> : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 11a8 8 0 0 0-14.3-4.6M4 13a8 8 0 0 0 14.3 4.6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            <path d="M5.5 2.8v3.8h3.8M18.5 21.2v-3.8h-3.8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        <span>{t(running ? "sync.running" : "sync.button")}</span>
      </button>
      <span className="ow-sync__status" role="status" aria-live="polite" data-failed={state.status === "failed" || undefined}>
        {status}
        {state.status === "done" && state.result === "reload_only" && <Tip text={t("sync.reloadOnly")} />}
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ exit from the selected region (on the map)

/**
 * "Exit Extremadura": one level up (region → country → all) and the map zooms out to it. Esc does the same while
 * the focus is on the map (or nowhere) and no drawing tool is active.
 */
export function ExitButton({ info, isArea, onExit, escapeEnabled }: {
  info: SelectionInfo; isArea: boolean; onExit: (target: { region: string | null; area: null }) => void; escapeEnabled: boolean;
}) {
  const { t } = useI18n();
  const name = useRegionName();
  const current = info.path[info.path.length - 1];
  const visible = isArea || !!current;
  const parentId = info.path.length >= 2 ? info.path[info.path.length - 2].properties.id : null;
  const label = isArea ? t("area.drawn") : current ? name(current) : "";

  useEffect(() => {
    if (!visible || !escapeEnabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const el = document.activeElement;
      const onMap = !el || el === document.body || !!el.closest(".ow-map");
      if (onMap) onExit({ region: parentId, area: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, escapeEnabled, parentId, onExit]);

  if (!visible) return null;
  return (
    <button type="button" className="ow-exit" onClick={() => onExit({ region: parentId, area: null })} title={t("exit.hint")}>
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M8 5 3 10l5 5M3.5 10H13a4 4 0 0 1 4 4v1" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{t("exit.button", { name: label })}</span>
    </button>
  );
}

// ------------------------------------------------------------------ data view switch (harmonised / raw / compare)

export function DisplaySwitch({ value, onChange, help }: { value: DisplayMode; onChange: (d: DisplayMode) => void; help?: string }) {
  const { t } = useI18n();
  return (
    <div className="ow-display" role="group" aria-label={t("display.label")} data-tour="display">
      <span className="ow-display__label">{t("display.label")}</span>
      {DISPLAY_MODES.map((d) => (
        <button key={d} type="button" className="ow-display__btn" aria-pressed={value === d} onClick={() => onChange(d)}>
          {d === "compare" && (
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4h6v12H3zM11 4h6v12h-6z" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
          )}
          {t(`display.${d}`)}
        </button>
      ))}
      <Tip text={help ?? t("display.help")} />
    </div>
  );
}
