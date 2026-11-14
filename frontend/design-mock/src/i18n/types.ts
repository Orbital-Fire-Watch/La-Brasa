/** Types of the translation files. The English file is the reference for all keys. */
import type { en } from "./messages/en";

/** Plural forms as in Intl.PluralRules; `other` is always required. */
export interface PluralForms {
  zero?: string;
  one?: string;
  two?: string;
  few?: string;
  many?: string;
  other: string;
}

export type Message = string | PluralForms;
export type MessageKey = keyof typeof en;

/** A complete translation. Use Partial<Messages> for a draft language; missing keys fall back to English. */
export type Messages = Record<MessageKey, Message>;

export type Vars = Record<string, string | number>;
