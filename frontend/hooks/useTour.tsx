/**
 * State of the guided tutorial: which step is shown, and what the pages have to do for it (open a tile, show the
 * info boxes, zoom the map). Each step puts the app into its own complete state via the URL; at the end the user
 * is back on the start page with the selection they had before.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { clampDate } from "../lib/dates";
import type { BBox, Position } from "../lib/geo";
import {
  readTourStatus, returnSearch, shouldAutoStart, stepState, TOUR_DATE, TOUR_LOOKBACK, TOUR_REGION_ID, TOUR_REGION_NAME,
  TOUR_STEPS, tourRequested, tourSteps, writeTourStatus, zoomBox, type TourStatus, type TourStep, type TourStepId,
  type TourTarget,
} from "../lib/tour";
import { fireApi } from "../services/api/fireApi";
import { useAppData } from "./useAppData";
import { replaceAppSearch, useAppState } from "./useAppState";

/** Delay of the automatic start, so the map and the tiles are on screen first. */
const AUTO_START_DELAY_MS = 900;

interface TourFire {
  id: string;
  bbox: BBox;
  centroid: Position;
}

export interface TourValue {
  /** the "Tutorial" button is shown (real data, or ?tour=1) */
  available: boolean;
  active: boolean;
  index: number;
  total: number;
  step: TourStep | null;
  /** name of the test area and the (clamped) test date, for the texts */
  placeName: string;
  date: string;
  start: () => void;
  next: () => void;
  back: () => void;
  end: (status: TourStatus) => void;
  isTarget: (target: TourTarget) => boolean;
  /** map view the current step asks for; pages pass it to their map before their own fitTo */
  fit: { bbox: BBox; key: string } | null;
}

const INACTIVE: TourValue = {
  available: false, active: false, index: 0, total: TOUR_STEPS.length, step: null, placeName: TOUR_REGION_NAME, date: TOUR_DATE,
  start: () => undefined, next: () => undefined, back: () => undefined, end: () => undefined, isTarget: () => false, fit: null,
};

const TourContext = createContext<TourValue>(INACTIVE);

export const useTour = () => useContext(TourContext);

export function TourProvider({ children }: { children: ReactNode }) {
  const { meta, regions } = useAppData();
  const [, setState] = useAppState();
  const [requested] = useState(() => tourRequested(window.location.search));
  // The step is kept by id: the list can still lose a step while the cloud check below runs.
  const [run, setRun] = useState<{ id: TourStepId; returnTo: string } | null>(null);
  const [fire, setFire] = useState<TourFire | null>(null);
  /** cloud cover known for the test area; null until checked (the step stays in the list meanwhile) */
  const [clouds, setClouds] = useState<boolean | null>(null);
  const autoStarted = useRef(false);

  const region = useMemo(() => {
    const features = regions?.features ?? [];
    return features.find((f) => f.properties.id === TOUR_REGION_ID)
      ?? features.find((f) => f.properties.level === "region" && f.properties.name === TOUR_REGION_NAME)
      ?? null;
  }, [regions]);
  const regionId = region?.properties.id ?? null;
  const date = clampDate(TOUR_DATE, meta.first_date, meta.last_date);
  const active = run !== null;

  const steps = useMemo(() => tourSteps({
    forecast: !!meta.features.forecast,
    anomaly: !!(meta.features.anomaly && meta.features.anomaly_window),
    clouds: clouds !== false,
  }), [meta.features, clouds]);

  const start = useCallback(() => setRun({ id: TOUR_STEPS[0].id, returnTo: returnSearch(window.location.search) }), []);

  // First visit (or ?tour=1): start once the pages are there. Waits for the regions, the steps need the test area.
  useEffect(() => {
    if (autoStarted.current || !regions) return;
    if (!requested && !shouldAutoStart({ search: window.location.search, stored: readTourStatus() })) return;
    const id = window.setTimeout(() => {
      autoStarted.current = true;
      start();
    }, AUTO_START_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [regions, requested, start]);

  // The strongest fire of the test area: target of the zoom on the start page and selected on the analysis page.
  useEffect(() => {
    if (!active || !regionId) return;
    const ctrl = new AbortController();
    fireApi.events({ region_id: regionId, date, lookback_days: TOUR_LOOKBACK, sort: "frp_sum", limit: 1, min_confidence: "nominal" }, ctrl.signal)
      .then((res) => {
        const f = res.features[0];
        setFire(f ? { id: f.id, bbox: f.properties.bbox as BBox, centroid: f.properties.centroid as Position } : null);
      })
      // Without the fire the steps still work: no close-up, nothing selected.
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [active, regionId, date, meta.data_version]);

  // Cloud cover is optional (table cloud_daily): without it the time slider has no cloud strip, so the step is left out.
  useEffect(() => {
    if (!active || !regionId || clouds !== null) return;
    const ctrl = new AbortController();
    fireApi.daily({ region_id: regionId, min_confidence: "nominal" }, ctrl.signal)
      .then((res) => setClouds(!!res.cloud_day?.some((v) => v !== null)))
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [active, regionId, clouds]);

  const found = run ? steps.findIndex((s) => s.id === run.id) : -1;
  const index = found >= 0 ? found : 0;
  const step = run ? steps[index] : null;
  const eventId = fire?.id ?? null;
  useEffect(() => {
    if (step) setState(stepState(step, { regionId, date, eventId }), { replace: true });
  }, [step, regionId, date, eventId, setState]);

  const end = useCallback((status: TourStatus) => {
    if (!run) return;
    writeTourStatus(status);
    setRun(null);
    // Back to the start page with what the user had selected before the tutorial.
    replaceAppSearch(run.returnTo);
  }, [run]);
  const next = useCallback(() => {
    if (!run) return;
    if (index >= steps.length - 1) end("done");
    else setRun({ ...run, id: steps[index + 1].id });
  }, [run, index, steps, end]);
  const back = useCallback(() => {
    if (run && index > 0) setRun({ ...run, id: steps[index - 1].id });
  }, [run, index, steps]);

  const isTarget = useCallback((target: TourTarget) => !!step?.targets.includes(target), [step]);
  const fit = useMemo(() => {
    if (!step?.fit || !fire) return null;
    return step.fit === "zoom"
      ? { bbox: zoomBox(fire.centroid), key: `tour|zoom|${fire.id}` }
      : { bbox: fire.bbox, key: `tour|fire|${fire.id}` };
  }, [step, fire]);

  const value = useMemo<TourValue>(() => ({
    available: true, active, index, total: steps.length, step, placeName: region?.properties.name ?? TOUR_REGION_NAME, date,
    start, next, back, end, isTarget, fit,
  }), [active, index, steps.length, step, region, date, start, next, back, end, isTarget, fit]);

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}
