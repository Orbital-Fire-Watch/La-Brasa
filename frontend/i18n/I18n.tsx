/**
 * Translation and formatting for the mock. `t(key, vars)` picks the text of the current language (falling back to
 * English), chooses the plural form from `vars.count` and fills in {placeholders}. All number, date, month,
 * relative-time and country formatting comes from Intl, so a new language needs no formatting code.
 */
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import type { Method } from "../lib/methods";
import { ApiError } from "../services/api/errors";
import { usePrefs } from "../hooks/usePrefs";
import { LOCALES, type Locale } from "./locales";
import { en } from "./messages/en";
import type { Message, MessageKey, Vars } from "./types";

export interface Fmt {
  int: (v: number) => string;
  one: (v: number) => string;
  compact: (v: number) => string;
  signed: (v: number) => string;
  /** ratio → signed percent, 0.25 → "+25 %" */
  pctChange: (ratio: number) => string;
  factor: (v: number) => string;
  km2: (v: number) => string;
  date: (iso: string) => string;
  dateLong: (iso: string) => string;
  dayMonth: (iso: string) => string;
  monthNarrow: (m: number) => string;
  monthShort: (m: number) => string;
  monthLong: (m: number) => string;
  /** days in the past → "yesterday", "3 days ago" */
  daysAgo: (days: number) => string;
  /** local clock time of an ISO timestamp, e.g. "14:32" */
  time: (iso: string) => string;
  method: (method: Method, v: number) => string;
  country: (code: string) => string;
}

export type Translate = (key: MessageKey, vars?: Vars) => string;

interface I18nValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: Translate;
  f: Fmt;
}

const I18nContext = createContext<I18nValue | null>(null);

const utc = (iso: string) => new Date(`${iso}T00:00:00Z`);
const monthDate = (m: number) => new Date(Date.UTC(2001, m - 1, 15));

function makeFmt(tag: string): Fmt {
  const n0 = new Intl.NumberFormat(tag, { maximumFractionDigits: 0 });
  const n1 = new Intl.NumberFormat(tag, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nFactor = new Intl.NumberFormat(tag, { maximumFractionDigits: 1 });
  const big = new Intl.NumberFormat(tag, { notation: "compact", maximumFractionDigits: 1 });
  const pct = new Intl.NumberFormat(tag, { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" });
  const d = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const dLong = new Intl.DateTimeFormat(tag, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const dm = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", timeZone: "UTC" });
  const mNarrow = new Intl.DateTimeFormat(tag, { month: "narrow", timeZone: "UTC" });
  const mShort = new Intl.DateTimeFormat(tag, { month: "short", timeZone: "UTC" });
  const mLong = new Intl.DateTimeFormat(tag, { month: "long", timeZone: "UTC" });
  const rel = new Intl.RelativeTimeFormat(tag, { numeric: "auto" });
  const clock = new Intl.DateTimeFormat(tag, { hour: "2-digit", minute: "2-digit" });
  const regions = new Intl.DisplayNames([tag], { type: "region" });
  const compact = (v: number) => (Math.abs(v) >= 1e6 ? big.format(v) : Math.abs(v) >= 100 ? n0.format(v) : n1.format(v));
  return {
    int: (v) => n0.format(Math.round(v)),
    one: (v) => n1.format(v),
    compact,
    signed: (v) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${compact(Math.abs(v))}`,
    pctChange: (r) => pct.format(r),
    factor: (v) => nFactor.format(v),
    km2: (v) => `${v < 10 ? n1.format(v) : n0.format(v)} km²`,
    date: (iso) => d.format(utc(iso)),
    dateLong: (iso) => dLong.format(utc(iso)),
    dayMonth: (iso) => dm.format(utc(iso)),
    monthNarrow: (m) => mNarrow.format(monthDate(m)),
    monthShort: (m) => mShort.format(monthDate(m)),
    monthLong: (m) => mLong.format(monthDate(m)),
    daysAgo: (days) => rel.format(-days, "day"),
    time: (iso) => clock.format(new Date(iso)),
    method: (method, v) => (method === "events" ? n0.format(Math.round(v)) : v >= 100 ? compact(v) : n1.format(v)),
    country: (code) => regions.of(code) ?? code,
  };
}

function makeT(locale: Locale, f: Fmt): Translate {
  const messages = LOCALES[locale].messages as Partial<Record<MessageKey, Message>>;
  const plural = new Intl.PluralRules(LOCALES[locale].intl);
  return (key, vars) => {
    const msg: Message = messages[key] ?? en[key];
    let text: string;
    if (typeof msg === "string") text = msg;
    else {
      const rule = plural.select(Number(vars?.count ?? 0));
      text = msg[rule] ?? msg.other;
    }
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (all, name: string) => {
      const v = vars[name];
      if (v === undefined) return all;
      return typeof v === "number" ? f.int(v) : v;
    });
  };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const { prefs, setPrefs } = usePrefs();
  const locale = prefs.lang;
  const value = useMemo<I18nValue>(() => {
    const f = makeFmt(LOCALES[locale].intl);
    return { locale, setLocale: (lang) => setPrefs({ lang }), t: makeT(locale, f), f };
  }, [locale, setPrefs]);

  useEffect(() => {
    document.documentElement.lang = LOCALES[locale].intl;
    document.documentElement.dir = LOCALES[locale].dir;
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** User-facing text for an API error. */
export function errorMessage(e: unknown, t: Translate): string {
  if (!(e instanceof ApiError)) return t("error.network");
  const key = `error.${e.code}` as MessageKey;
  return key in en ? t(key) : t("error.generic", { code: e.code });
}
