/** "Gebiete, in denen es oft brennt" (could-have, spec §4): top H3 cells over the whole period, resolution 5. */
import { cellToLatLng } from "h3-js";
import { useMemo, useState } from "react";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useAppData } from "../../hooks/useAppData";
import { formatCompact } from "../../lib/format";
import { pointInGeometry } from "../../lib/geo";
import { fireApi } from "../../services/api/fireApi";
import { isGridCount } from "../../services/api/types";
import { ErrorBlock, LoadingBlock } from "../ui/Status";

const TOP_N = 8;
const RESOLUTION = 5;

interface FrequentAreasProps {
  metric: "fires" | "frp_sum";
  conf: "nominal" | "high";
  onPick: (cell: string) => void;
}

export function FrequentAreas({ metric, conf, onPick }: FrequentAreasProps) {
  const { meta, regions } = useAppData();
  const [open, setOpen] = useState(false);
  const key = open ? `frequent|${meta.data_version}|${conf}` : null;
  const q = useApiQuery(key, (signal) =>
    fireApi.grid({ mode: "count", start: meta.first_date, end: meta.last_date, resolution: RESOLUTION, min_confidence: conf }, signal),
  );

  const top = useMemo(() => {
    if (q.status !== "success" || !isGridCount(q.data)) return [];
    const provinces = regions?.features.filter((f) => f.properties.level === "province") ?? [];
    return [...q.data.cells]
      .sort((a, b) => b[metric] - a[metric])
      .slice(0, TOP_N)
      .map((c) => {
        const [lat, lon] = cellToLatLng(c.cell);
        const province = provinces.find((p) => pointInGeometry([lon, lat], p.geometry));
        return { ...c, name: province?.properties.name ?? "Grenzgebiet" };
      });
  }, [q, metric, regions]);

  return (
    <section className="panel" aria-labelledby="frequent-title">
      <div className="panel__head">
        <h2 id="frequent-title" className="panel__title">Gebiete, in denen es oft brennt</h2>
        <button type="button" className="btn btn--small" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Ausblenden" : "Anzeigen"}
        </button>
      </div>
      {open && q.status === "loading" && <LoadingBlock label="Wird berechnet …" />}
      {open && q.status === "error" && <ErrorBlock error={q.error} onRetry={q.reload} />}
      {open && top.length > 0 && (
        <ol className="frequent">
          {top.map((c) => (
            <li key={c.cell}>
              <button type="button" className="frequent__item" onClick={() => onPick(c.cell)}>
                <span>{c.name}</span>
                <span className="muted">
                  {formatCompact(c[metric])} {metric === "fires" ? "Hotspots" : "MW"} seit {meta.first_date.slice(0, 4)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
