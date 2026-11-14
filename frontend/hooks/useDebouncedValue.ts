import { useEffect, useState } from "react";

/** Value that follows `value` only after it stopped changing for `ms` (spec §4: 300 ms for slider and map). */
export function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
