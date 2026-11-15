import { useEffect, useRef, useState } from "react";
import { addDays } from "../lib/dates";

/** Playback speeds of the time slider animation and the minimum time each day stays on screen. */
export const PLAYBACK_SPEEDS = [0.5, 1, 2] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];
const FRAME_MS_AT_1X = 600;

/**
 * stopped: no run (initially, at the end, after an error or after the user moved the date) - Play starts from the beginning.
 * paused: a run was paused with the button or by hiding the tab - Play continues from the current day.
 */
export type PlaybackStatus = "stopped" | "playing" | "paused";

/**
 * State of the time slider animation. Kept apart from the clock (usePlaybackClock) because the page needs
 * `playing` early (to skip the slider debounce) but knows only later whether the map data has loaded.
 */
export function usePlayback() {
  const [status, setStatus] = useState<PlaybackStatus>("stopped");
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const playing = status === "playing";

  // A background tab should not keep loading data: pause, so Play continues where it was.
  useEffect(() => {
    if (!playing) return;
    const onVisibility = () => {
      if (document.hidden) setStatus("paused");
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [playing]);

  return {
    status,
    playing,
    speed,
    setSpeed,
    play: () => setStatus("playing"),
    pause: () => setStatus("paused"),
    /** ends the run, e.g. when the user picks a date */
    stop: () => setStatus("stopped"),
  };
}

/**
 * Advances `value` by one day while playing. A step happens only when the data for the current day is shown
 * (`ready`) and the day has been on screen for at least the frame time, so a slow backend makes the animation
 * wait instead of skipping days. Stops at `max`, and also on a failed request (`failed`), so errors are seen.
 */
export function usePlaybackClock({ playing, stop, speed, value, max, ready, failed, onStep }: {
  playing: boolean;
  stop: () => void;
  speed: PlaybackSpeed;
  value: string;
  max: string;
  ready: boolean;
  failed: boolean;
  onStep: (d: string) => void;
}) {
  // Time of the last step: the frame time counts from when the day was set, not from when its data arrived.
  const steppedAt = useRef(0);
  const callbacks = useRef({ stop, onStep });
  useEffect(() => {
    callbacks.current = { stop, onStep };
  });

  // The first day of a run gets its full frame time too.
  useEffect(() => {
    if (playing) steppedAt.current = performance.now();
  }, [playing]);

  useEffect(() => {
    if (!playing || !ready) return;
    const frameMs = FRAME_MS_AT_1X / speed;
    const wait = Math.max(0, frameMs - (performance.now() - steppedAt.current));
    const timer = setTimeout(() => {
      if (failed || value >= max) {
        callbacks.current.stop();
        return;
      }
      steppedAt.current = performance.now();
      callbacks.current.onStep(addDays(value, 1));
    }, wait);
    return () => clearTimeout(timer);
  }, [playing, ready, failed, value, max, speed]);
}
