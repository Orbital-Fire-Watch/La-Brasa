/**
 * Available languages. Adding one = one file in messages/ plus one entry here; components stay unchanged.
 * `intl` is the BCP 47 tag used for numbers, dates, plurals and country names.
 */
import { en } from "./messages/en";
import { es } from "./messages/es";
import { pt } from "./messages/pt";
import type { Messages } from "./types";

export interface LocaleInfo {
  /** native name, shown in the language menu */
  name: string;
  intl: string;
  dir: "ltr" | "rtl";
  messages: Messages | Partial<Messages>;
}

export const LOCALES = {
  en: { name: "English", intl: "en-GB", dir: "ltr", messages: en },
  es: { name: "Español", intl: "es-ES", dir: "ltr", messages: es },
  pt: { name: "Português", intl: "pt-PT", dir: "ltr", messages: pt },
} as const satisfies Record<string, LocaleInfo>;

export type Locale = keyof typeof LOCALES;
export const LOCALE_CODES = Object.keys(LOCALES) as Locale[];

export const isLocale = (v: unknown): v is Locale => typeof v === "string" && v in LOCALES;

/** First supported language from the browser settings, else English. */
export function browserLocale(): Locale {
  for (const tag of navigator.languages ?? [navigator.language]) {
    const base = tag.toLowerCase().split("-")[0];
    if (isLocale(base)) return base;
  }
  return "en";
}
