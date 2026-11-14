/** Small building blocks of the mock: collapsible tile, viewport-safe tooltip, status blocks, flags. */
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { errorMessage, useI18n } from "../i18n/I18n";

/** Collapsible tile with a heading (EFFIS-style). No shadow, quiet metal surface (mock.css). */
export function Tile({ title, children, defaultOpen = true, aside, className }: {
  title: string; children: ReactNode; defaultOpen?: boolean; aside?: ReactNode; className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  return (
    <section className={`ow-tile ${className ?? ""}`} data-open={open}>
      <header className="ow-tile__head">
        <h2 className="ow-tile__title">
          <button type="button" className="ow-tile__toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
            <svg viewBox="0 0 12 12" aria-hidden="true" className="ow-tile__chevron"><path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
            {title}
          </button>
        </h2>
        {aside}
      </header>
      <div id={bodyId} className="ow-tile__body" hidden={!open}>
        {children}
      </div>
    </section>
  );
}

const MARGIN = 8;
const GAP = 6;

/**
 * "i" button with an explanation. The text is rendered into <body> with position: fixed and kept inside the
 * viewport (8 px margin); it opens below the button and flips above when there is no room.
 */
export function Tip({ text, label }: { text: string; label?: string }) {
  const { t } = useI18n();
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useLayoutEffect(() => {
    const b = button.current?.getBoundingClientRect();
    const el = bubble.current;
    if (!open || !b || !el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    const left = Math.max(MARGIN, Math.min(b.left + b.width / 2 - w / 2, vw - w - MARGIN));
    const below = b.bottom + GAP;
    const top = below + h > vh - MARGIN ? Math.max(MARGIN, b.top - GAP - h) : below;
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
    el.style.visibility = "visible";
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span className="ow-tip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button ref={button} type="button" className="ow-tip__button" aria-label={label ?? t("ui.moreInfo")} aria-describedby={open ? id : undefined}
        aria-expanded={open} onClick={() => setOpen((o) => !o)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.3" /><path d="M8 7v4.5M8 4.6v.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
      </button>
      {open && createPortal(
        <div ref={bubble} id={id} role="tooltip" className="ow-tip__bubble" style={{ visibility: "hidden" }}>
          {text}
        </div>,
        document.body,
      )}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <span className="ow-spinner" role="status">
      <span className="ow-spinner__ring" aria-hidden="true" />
      <span className="visually-hidden">{label ?? t("ui.loading")}</span>
    </span>
  );
}

export function Loading({ label, height }: { label?: string; height?: number }) {
  const { t } = useI18n();
  const text = label ?? t("ui.loadingData");
  return (
    <div className="ow-status ow-status--loading" style={height ? { minHeight: height } : undefined}>
      <Spinner label={text} />
      <span>{text}</span>
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="ow-status ow-status--error" role="alert">
      <span>{errorMessage(error, t)}</span>
      {onRetry && <button type="button" className="ow-btn ow-btn--small" onClick={onRetry}>{t("ui.retry")}</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="ow-status ow-status--empty">{children}</div>;
}

/** Small inline flags (SVG, because Windows does not render flag emoji). */
export function Flag({ country }: { country: string }) {
  const { t, f } = useI18n();
  const label = t("ui.flagOf", { country: f.country(country) });
  if (country === "ES") {
    return (
      <svg className="ow-flag" viewBox="0 0 30 20" role="img" aria-label={label}>
        <rect width="30" height="20" fill="#aa151b" />
        <rect y="5" width="30" height="10" fill="#f1bf00" />
      </svg>
    );
  }
  if (country === "PT") {
    return (
      <svg className="ow-flag" viewBox="0 0 30 20" role="img" aria-label={label}>
        <rect width="30" height="20" fill="#da291c" />
        <rect width="12" height="20" fill="#046a38" />
        <circle cx="12" cy="10" r="4" fill="#ffe900" stroke="#ffffff" strokeWidth="0.8" />
      </svg>
    );
  }
  return null;
}
