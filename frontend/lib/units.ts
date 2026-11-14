/** Value formatting per method, shared by charts, cards and legends. */
import { formatCompact, formatOne } from "./format";
import type { Method } from "./methods";

export const METHOD_UNIT: Record<Method, string> = {
  fires: "Hotspots (harm.)",
  frp_sum: "MW",
  events: "Ereignisse",
};

export function formatMethodValue(method: Method, v: number): string {
  if (method === "events") return Math.round(v).toLocaleString("de-DE");
  return v >= 100 ? formatCompact(v) : formatOne(v);
}
