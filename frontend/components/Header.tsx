/** Top bar of both pages: logo top left; language, info page and accessibility menu top right. */
import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { BRAND, INFO_PAGE_URL } from "../lib/uiConfig";
import { useI18n } from "../i18n/I18n";
import { LOCALE_CODES, LOCALES, type Locale } from "../i18n/locales";
import type { MessageKey } from "../i18n/types";
import { usePrefs, type Palette, type TextSize, type Theme } from "../hooks/usePrefs";
import { goHome, useAppState } from "../hooks/useAppState";
import { useTour } from "../hooks/useTour";
import { SyncButton } from "./map/MapTools";

export function Logo({ size = "normal" }: { size?: "normal" | "large" }) {
  return (
    <div className={`ow-logo ow-logo--${size}`}>
      <img className="ow-logo__img" src={BRAND.logoUrl} alt="" />
      <span className="ow-logo__name">{BRAND.name}</span>
    </div>
  );
}

const THEMES: Theme[] = ["dark", "light", "contrast"];
const PALETTES: Palette[] = ["standard", "cvd"];
const TEXT_SIZES: { value: TextSize; label: string }[] = [
  { value: "100", label: "A" },
  { value: "115", label: "A+" },
  { value: "130", label: "A++" },
];

function Choice<T extends string>({ legend, value, options, onChange }: {
  legend: string; value: T; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className="ow-choice">
      <legend className="ow-choice__legend">{legend}</legend>
      {options.map((o) => (
        <label key={o.value} className="ow-choice__option">
          <input type="radio" name={name} checked={o.value === value} onChange={() => onChange(o.value)} />
          <span>
            {o.label}
            {o.hint && <small>{o.hint}</small>}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

/** Closes on outside click and Escape. */
function usePopover() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, root };
}

function AccessibilityMenu() {
  const { prefs, setPrefs, reset } = usePrefs();
  const { t } = useI18n();
  const { open, setOpen, root } = usePopover();
  const menuId = useId();

  return (
    <div className="ow-menu" ref={root}>
      <button type="button" className="ow-headbtn" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((o) => !o)}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="4.5" r="2" fill="currentColor" />
          <path d="M4 8.5l8 1.5 8-1.5M12 10v5m0 0l-3.5 6.5M12 15l3.5 6.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        <span>{t("header.accessibility")}</span>
      </button>
      {open && (
        <div id={menuId} className="ow-menu__panel" role="dialog" aria-label={t("a11y.dialog")}>
          <Choice legend={t("a11y.theme")} value={prefs.theme} onChange={(theme) => setPrefs({ theme })}
            options={THEMES.map((v) => ({ value: v, label: t(`a11y.theme.${v}`), hint: t(`a11y.theme.${v}.hint` as MessageKey) }))} />
          <Choice legend={t("a11y.palette")} value={prefs.palette} onChange={(palette) => setPrefs({ palette })}
            options={PALETTES.map((v) => ({ value: v, label: t(`a11y.palette.${v}`), hint: t(`a11y.palette.${v}.hint` as MessageKey) }))} />
          <fieldset className="ow-choice ow-choice--row">
            <legend className="ow-choice__legend">{t("a11y.text")}</legend>
            {TEXT_SIZES.map((s) => (
              <label key={s.value} className="ow-choice__pill">
                <input type="radio" name={`${menuId}-text`} checked={prefs.textSize === s.value} onChange={() => setPrefs({ textSize: s.value })} />
                <span>{s.label}</span>
              </label>
            ))}
          </fieldset>
          <label className="ow-switch">
            <input type="checkbox" checked={prefs.reduceMotion} onChange={(e) => setPrefs({ reduceMotion: e.target.checked })} />
            <span>{t("a11y.motion")}</span>
          </label>
          <button type="button" className="ow-btn ow-btn--small" onClick={reset}>{t("a11y.reset")}</button>
        </div>
      )}
    </div>
  );
}

function LanguageSelect() {
  const { locale, setLocale, t } = useI18n();
  return (
    <label className="ow-lang">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9M12 3C9.5 5.6 8.2 8.6 8.2 12s1.3 6.4 3.8 9" fill="none" stroke="currentColor" strokeWidth="1.6" />
      </svg>
      <span className="visually-hidden">{t("header.language")}</span>
      <select value={locale} onChange={(e) => setLocale(e.target.value as Locale)}>
        {LOCALE_CODES.map((code) => (
          <option key={code} value={code} lang={LOCALES[code].intl}>{LOCALES[code].name}</option>
        ))}
      </select>
    </label>
  );
}

/** Opens the guided tutorial again; only on the start page, where the tutorial begins. */
function TutorialButton() {
  const { t } = useI18n();
  const tour = useTour();
  const [state] = useAppState();
  if (!tour.available || state.page !== "select") return null;
  return (
    <button type="button" className="ow-headbtn" onClick={tour.start} aria-haspopup="dialog">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M9.5 9.3a2.6 2.6 0 0 1 5 .9c0 1.8-2.5 2.2-2.5 3.9M12 16.8v.3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <span>{t("tour.button")}</span>
    </button>
  );
}

/** The logo as a link back to the start page (empty query); a plain link still works with modifier keys. */
function HomeLink() {
  const { t } = useI18n();
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    goHome();
  };
  return (
    <a className="ow-home" href={window.location.pathname} aria-label={t("header.home")} onClick={onClick} data-tour="home">
      <Logo />
    </a>
  );
}

export function Header({ children, floating = false }: { children?: ReactNode; floating?: boolean }) {
  const { t } = useI18n();
  return (
    <header className={`ow-header ${floating ? "ow-header--floating" : ""}`}>
      <HomeLink />
      <div className="ow-header__middle">{children}</div>
      <nav className="ow-header__actions" aria-label={t("header.nav")}>
        <SyncButton />
        <TutorialButton />
        <LanguageSelect />
        <a className="ow-headbtn" href={INFO_PAGE_URL}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path d="M12 10.5v6M12 7.2v.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span>{t("header.info")}</span>
        </a>
        <AccessibilityMenu />
      </nav>
    </header>
  );
}
