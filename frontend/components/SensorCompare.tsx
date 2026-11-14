/** "MODIS vs VIIRS": raw detections of both instrument families side by side (table, daily bars, caveats). */
import { useI18n } from "../i18n/I18n";
import { FAMILIES, FAMILY_COLOR, FAMILY_NAME, PIXEL_SIZE, SENSOR_NAME, type SensorComparison } from "../lib/sensors";
import { ErrorNote, Loading } from "./ui/Elements";

interface SensorCompareProps {
  data: SensorComparison | null;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}

function DailyBars({ data }: { data: SensorComparison }) {
  const { t, f } = useI18n();
  const n = data.daily.length;
  const max = Math.max(1, ...data.daily.map((d) => Math.max(d.modis, d.viirs)));
  const W = 300;
  const H = 70;
  const slot = W / Math.max(1, n);
  const bar = Math.max(0.6, slot / 2 - 0.4);
  return (
    <figure className="ow-cmp__chart">
      <figcaption className="ow-cmp__caption">
        {t("cmp.perDay")}
        <span className="ow-cmp__legend">
          {FAMILIES.map((fam) => (
            <span key={fam}><span className="ow-swatch" style={{ background: FAMILY_COLOR[fam] }} />{FAMILY_NAME[fam]}</span>
          ))}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H + 12}`} role="img" aria-label={t("cmp.dailyAria")}>
        <line x1={0} x2={W} y1={H} y2={H} className="ow-cmp__axis" />
        {data.daily.map((d, i) => (
          <g key={d.date}>
            <title>{`${f.date(d.date)}: MODIS ${f.int(d.modis)}, VIIRS ${f.int(d.viirs)}`}</title>
            <rect x={i * slot} y={H - (H * d.modis) / max} width={bar} height={(H * d.modis) / max} fill={FAMILY_COLOR.modis} />
            <rect x={i * slot + bar} y={H - (H * d.viirs) / max} width={bar} height={(H * d.viirs) / max} fill={FAMILY_COLOR.viirs} />
          </g>
        ))}
        <text x={0} y={H + 11} className="ow-cmp__tick">{f.dayMonth(data.start)}</text>
        <text x={W} y={H + 11} textAnchor="end" className="ow-cmp__tick">{f.dayMonth(data.end)}</text>
      </svg>
    </figure>
  );
}

export function SensorCompare({ data, loading, error, onRetry }: SensorCompareProps) {
  const { t, f } = useI18n();
  if (error) return <ErrorNote error={error} onRetry={onRetry} />;
  if (!data) return loading ? <Loading height={160} /> : null;
  const { modis, viirs } = data.stats;
  const total = modis.detections + viirs.detections;
  const share = (v: number) => (total > 0 ? f.pctChange(v / total).replace(/^\+/, "") : "–");
  const noViirs = viirs.satellites.length === 0;
  const cell = (fam: "modis" | "viirs", v: string) => (fam === "viirs" && noViirs ? <td className="ow-muted">{t("status.nodata")}</td> : <td>{v}</td>);
  const rows: { label: string; value: (fam: "modis" | "viirs") => string }[] = [
    { label: t("cmp.detections"), value: (fam) => f.int(data.stats[fam].detections) },
    { label: t("cmp.share"), value: (fam) => share(data.stats[fam].detections) },
    { label: t("cmp.frpSum"), value: (fam) => `${f.compact(data.stats[fam].frpSum)} MW` },
    { label: t("cmp.meanFrp"), value: (fam) => (data.stats[fam].meanFrp === null ? "–" : `${f.one(data.stats[fam].meanFrp ?? 0)} MW`) },
    { label: t("cmp.activeDays"), value: (fam) => `${f.int(data.stats[fam].activeDays)} / ${f.int(data.daily.length)}` },
    {
      label: t("cmp.satellites"),
      value: (fam) => data.stats[fam].satellites.map((s) => `${SENSOR_NAME[s]} (${f.int(data.stats[fam].bySensor[s] ?? 0)})`).join(", ") || t("cmp.none"),
    },
    { label: t("cmp.pixel"), value: (fam) => PIXEL_SIZE[fam] },
  ];
  return (
    <div className="ow-cmp">
      <p className="ow-small ow-muted">{t("cmp.window", { start: f.date(data.start), end: f.date(data.end) })}</p>
      <table className="ow-cmp__table">
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">{t("cmp.title")}</span></th>
            {FAMILIES.map((fam) => (
              <th key={fam} scope="col"><span className="ow-swatch" style={{ background: FAMILY_COLOR[fam] }} />{FAMILY_NAME[fam]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              {cell("modis", r.value("modis"))}
              {cell("viirs", r.value("viirs"))}
            </tr>
          ))}
        </tbody>
      </table>
      <DailyBars data={data} />
      <p className="ow-cmp__ratio">
        {noViirs ? t("cmp.noViirs") : modis.detections > 0 ? t("cmp.ratio", { ratio: f.factor(viirs.detections / modis.detections) }) : t("cmp.ratioNoModis")}
      </p>
      <p className="ow-small ow-muted">{t("cmp.caveat")}</p>
      {data.truncated && <p className="ow-cmp__warning" role="note">{t("cmp.truncated", { returned: data.returned, total: data.total })}</p>}
    </div>
  );
}
