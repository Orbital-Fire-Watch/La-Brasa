/** Info boxes on the start page: hidden while the map moves, back after a pause. */
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Visible `initialDelay` ms after mount; hidden as soon as the map starts moving; visible again
 * `idleDelay` ms after the last movement ended.
 */
export function useIdleReveal(initialDelay: number, idleDelay: number) {
  const [visible, setVisible] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    timer.current = window.setTimeout(() => setVisible(true), initialDelay);
    return () => window.clearTimeout(timer.current);
  }, [initialDelay]);

  const onMoveStart = useCallback(() => {
    window.clearTimeout(timer.current);
    setVisible(false);
  }, []);
  const onMoveEnd = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setVisible(true), idleDelay);
  }, [idleDelay]);

  return { visible, onMoveStart, onMoveEnd };
}
