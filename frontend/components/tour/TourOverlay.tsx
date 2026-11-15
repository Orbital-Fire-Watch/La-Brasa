/**
 * Overlay of the guided tutorial: the whole page is darkened except the elements the current step talks about
 * (found by their data-tour attribute), with a popup next to them (Back / Next / Skip).
 * Clicks on the page do nothing while the tutorial runs; the steps make every change themselves.
 */
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePrefs } from "../../hooks/usePrefs";
import { useTour } from "../../hooks/useTour";
import { useI18n } from "../../i18n/I18n";
import type { MessageKey } from "../../i18n/types";
import { placePopup, type Rect, type TourTarget, type TourTextVar } from "../../lib/tour";

/** Room around a highlighted element. */
const PAD = 6;
/** Below this width the popup is a sheet at the bottom of the screen. */
const NARROW_PX = 640;
/** Give up scrolling to a target that has not appeared after this long (e.g. a feature switched off). */
const TARGET_WAIT_MS = 3000;

interface Layout {
  holes: Rect[];
  vw: number;
  vh: number;
  pw: number;
  ph: number;
}

/** One rectangle per target (several elements with the same name are joined), padded and cut to the viewport. */
function measure(targets: readonly TourTarget[], vw: number, vh: number): Rect[] {
  const out: Rect[] = [];
  for (const id of targets) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    document.querySelectorAll(`[data-tour="${id}"]`).forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      x0 = Math.min(x0, r.left);
      y0 = Math.min(y0, r.top);
      x1 = Math.max(x1, r.right);
      y1 = Math.max(y1, r.bottom);
    });
    if (!Number.isFinite(x0)) continue;
    const left = Math.max(0, x0 - PAD), top = Math.max(0, y0 - PAD);
    const right = Math.min(vw, x1 + PAD), bottom = Math.min(vh, y1 + PAD);
    if (right - left >= 4 && bottom - top >= 4) out.push({ x: left, y: top, w: right - left, h: bottom - top });
  }
  return out;
}

const near = (a: Rect, b: Rect) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y) + Math.abs(a.w - b.w) + Math.abs(a.h - b.h) < 1;
const lerp = (a: Rect, b: Rect, k: number): Rect => ({ x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, w: a.w + (b.w - a.w) * k, h: a.h + (b.h - a.h) * k });
const sameLayout = (a: Layout, b: Layout) =>
  a.vw === b.vw && a.vh === b.vh && a.pw === b.pw && a.ph === b.ph && a.holes.length === b.holes.length && a.holes.every((h, i) => near(h, b.holes[i]));

/** Scrolls the target into view unless it is already completely visible (below the sticky header of the analysis page). */
function reveal(el: HTMLElement, vh: number, smooth: boolean) {
  const r = el.getBoundingClientRect();
  const head = document.querySelector(".ow-header:not(.ow-header--floating)")?.getBoundingClientRect().bottom ?? 0;
  if (r.top >= head && r.bottom <= vh) return;
  el.scrollIntoView({ block: r.height > (vh - head) * 0.8 ? "start" : "center", behavior: smooth ? "smooth" : "auto" });
}

export function TourOverlay() {
  const tour = useTour();
  const { motionOff } = usePrefs();
  const { t, f } = useI18n();
  const rawId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const maskId = `ow-tour-mask-${rawId}`;
  const titleId = `ow-tour-title-${rawId}`;
  const textId = `ow-tour-text-${rawId}`;
  const popRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const holesRef = useRef<Rect[]>([]);
  const [layout, setLayout] = useState<Layout>(() => ({ holes: [], vw: window.innerWidth, vh: window.innerHeight, pw: 320, ph: 220 }));
  const { active, step, index, total, next, back, end } = tour;

  // Follow the targets every frame: tiles load and grow, the map zooms, the page scrolls. The holes glide to a new
  // position (unless motion is reduced); React only re-renders when something actually changed.
  useEffect(() => {
    if (!step) return;
    const targets = step.targets;
    const startedAt = performance.now();
    let scrolled = targets.length === 0;
    let raf = 0;
    const frame = () => {
      const vw = document.documentElement.clientWidth;
      const vh = window.innerHeight;
      if (!scrolled) {
        const el = document.querySelector<HTMLElement>(`[data-tour="${targets[0]}"]`);
        if (el && el.getBoundingClientRect().height > 0) {
          scrolled = true;
          reveal(el, vh, !motionOff);
        } else if (performance.now() - startedAt > TARGET_WAIT_MS) scrolled = true;
      }
      const goal = measure(targets, vw, vh);
      const cur = holesRef.current;
      holesRef.current = motionOff || cur.length !== goal.length ? goal : cur.map((c, i) => (near(c, goal[i]) ? goal[i] : lerp(c, goal[i], 0.3)));
      const pop = popRef.current;
      const nextLayout: Layout = { holes: holesRef.current, vw, vh, pw: pop?.offsetWidth ?? 320, ph: pop?.offsetHeight ?? 220 };
      setLayout((prev) => (sameLayout(prev, nextLayout) ? prev : nextLayout));
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [step, motionOff]);

  // The page behind is not reachable with Tab or a screen reader while the tutorial runs.
  useEffect(() => {
    if (!active) return;
    const root = document.getElementById("root");
    if (!root) return;
    root.inert = true;
    return () => {
      root.inert = false;
    };
  }, [active]);

  useEffect(() => {
    if (active) primaryRef.current?.focus({ preventScroll: true });
  }, [active, index]);

  // Arrow keys and Esc belong to the tutorial; captured first, so Esc does not also leave the selected region.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") end("skipped");
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") back();
      else if (e.key === "Enter" && !(document.activeElement instanceof HTMLButtonElement)) next();
      else return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [active, next, back, end]);

  if (!active || !step) return null;

  const first = index === 0;
  const last = index === total - 1;
  const narrow = layout.vw < NARROW_PX;
  const pos = placePopup(layout.holes[0] ?? null, { w: layout.pw, h: layout.ph }, { w: layout.vw, h: layout.vh });
  // Labels of the app, so the texts name the buttons exactly as they read in the chosen language.
  const vars: Record<TourTextVar, string> = {
    place: tour.placeName, date: f.dateLong(tour.date), latest: t("settings.latest"), conf: t("conf.label"), method: t("settings.method"),
    draw: t("draw.label"), display: t("display.label"), compare: t("display.compare"), analysis: t("start.analysis"),
    satellite: t("map.satellite"), lookback: t("an.lookback"), unusual: t("an.unusual"), tutorial: t("tour.button"),
    fetch: t("sync.button"), compareWith: t("an.compareWith"), hideAnomalies: t("an.hideAnomalies"),
  };

  return createPortal(
    <div className="ow-tour">
      <svg className="ow-tour__dim" width={layout.vw} height={layout.vh} aria-hidden="true">
        <defs>
          <mask id={maskId}>
            <rect width="100%" height="100%" fill="white" />
            {layout.holes.map((r, i) => <rect key={i} x={r.x} y={r.y} width={r.w} height={r.h} rx={6} fill="black" />)}
          </mask>
        </defs>
        <rect className="ow-tour__shade" width="100%" height="100%" mask={`url(#${maskId})`} />
        {layout.holes.map((r, i) => <rect key={i} className="ow-tour__ring" x={r.x} y={r.y} width={r.w} height={r.h} rx={6} />)}
      </svg>

      <div ref={popRef} className="ow-tour__pop" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={textId}
        data-narrow={narrow || undefined} style={narrow ? undefined : { left: pos.left, top: pos.top }}>
        <div className="ow-tour__head">
          <p className="ow-tour__progress">{t("tour.progress", { current: index + 1, total })}</p>
          <button type="button" className="ow-tour__close" onClick={() => end("skipped")} aria-label={t("tour.close")} title={t("tour.close")}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
          </button>
        </div>
        <h2 id={titleId} className="ow-tour__title">{t(`tour.${step.id}.title` as MessageKey, vars)}</h2>
        <p id={textId} className="ow-tour__text">{t(`tour.${step.id}.text` as MessageKey, vars)}</p>
        <ol className="ow-tour__dots" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => <li key={i} data-state={i === index ? "on" : i < index ? "done" : undefined} />)}
        </ol>
        <div className="ow-tour__foot">
          {!last && <button type="button" className="ow-btn ow-btn--small ow-btn--ghost" onClick={() => end("skipped")}>{t("tour.skip")}</button>}
          <span className="ow-tour__spacer" />
          {!first && <button type="button" className="ow-btn ow-btn--small" onClick={back}>{t("tour.back")}</button>}
          <button ref={primaryRef} type="button" className="ow-btn ow-btn--small ow-btn--primary" onClick={next}>
            {t(first ? "tour.start" : last ? "tour.finish" : "tour.next")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
