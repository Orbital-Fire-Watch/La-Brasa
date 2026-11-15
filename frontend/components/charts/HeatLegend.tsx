import { useI18n } from "../../i18n/I18n";

interface HeatLegendProps {
  max: number;
  color: (v: number) => string;
  formatValue: (v: number) => string;
  unitLabel: string;
  showStatus?: boolean;
}

/** Colour legend for sequential (log-like) scales plus the markers for incomplete and running periods. */
export function HeatLegend({ max, color, formatValue, unitLabel, showStatus = true }: HeatLegendProps) {
  const { t } = useI18n();
  const stops = Array.from({ length: 9 }, (_, i) => {
    const v = max * ((Math.pow(10, i / 8) - 1) / 9);
    return `${color(v)} ${(i / 8) * 100}%`;
  });
  return (
    <div className="legend">
      <span className="legend__label">0</span>
      <span className="legend__ramp" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} aria-hidden="true" />
      <span className="legend__label">
        {formatValue(max)} {unitLabel}
      </span>
      {showStatus && (
        <>
          <span className="legend__swatch legend__swatch--hatch" aria-hidden="true" />
          <span className="legend__label">{t("status.incomplete")}</span>
          <span className="legend__swatch legend__swatch--running" aria-hidden="true" />
          <span className="legend__label">{t("status.running")}</span>
        </>
      )}
    </div>
  );
}
