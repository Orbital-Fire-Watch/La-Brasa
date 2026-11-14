/**
 * Settings from the menus top right: language, theme, data palette, text size, motion.
 * Stored per browser (a viewer convenience) and applied as data attributes on <html>, where mock.css reads them.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { browserLocale, isLocale, type Locale } from "../i18n/locales";

export type Theme = "dark" | "light" | "contrast";
export type Palette = "standard" | "cvd";
export type TextSize = "100" | "115" | "130";

export interface Prefs {
  theme: Theme;
  palette: Palette;
  textSize: TextSize;
  reduceMotion: boolean;
  lang: Locale;
}

const DEFAULT_PREFS: Omit<Prefs, "lang"> = { theme: "dark", palette: "standard", textSize: "100", reduceMotion: false };
const STORAGE_KEY = "la-brasa:prefs";

function load(): Prefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFS, lang: browserLocale() };
    const p = JSON.parse(raw) as Partial<Prefs>;
    return {
      theme: p.theme === "light" || p.theme === "contrast" ? p.theme : "dark",
      palette: p.palette === "cvd" ? "cvd" : "standard",
      textSize: p.textSize === "115" || p.textSize === "130" ? p.textSize : "100",
      reduceMotion: p.reduceMotion === true,
      lang: isLocale(p.lang) ? p.lang : browserLocale(),
    };
  } catch {
    return { ...DEFAULT_PREFS, lang: "en" };
  }
}

interface PrefsContextValue {
  prefs: Prefs;
  setPrefs: (patch: Partial<Prefs>) => void;
  reset: () => void;
  /** reduceMotion from the menu or from the operating system */
  motionOff: boolean;
}

const PrefsContext = createContext<PrefsContextValue | null>(null);

function useSystemReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setState] = useState<Prefs>(load);
  const systemReduced = useSystemReducedMotion();

  useEffect(() => {
    const el = document.documentElement;
    el.dataset.theme = prefs.theme;
    el.dataset.palette = prefs.palette;
    el.dataset.text = prefs.textSize;
    el.dataset.motion = prefs.reduceMotion ? "reduced" : "full";
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Blocked storage: the settings just are not remembered.
    }
  }, [prefs]);

  const setPrefs = useCallback((patch: Partial<Prefs>) => setState((p) => ({ ...p, ...patch })), []);
  // Reset keeps the language: it is not an accessibility setting.
  const reset = useCallback(() => setState((p) => ({ ...DEFAULT_PREFS, lang: p.lang })), []);
  const value = useMemo(
    () => ({ prefs, setPrefs, reset, motionOff: prefs.reduceMotion || systemReduced }),
    [prefs, setPrefs, reset, systemReduced],
  );
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): PrefsContextValue {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs must be used inside <PrefsProvider>");
  return ctx;
}
