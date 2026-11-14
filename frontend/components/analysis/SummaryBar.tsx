/** Top of page 2: short summary of the page 1 settings, "Bearbeiten" and the CSV download. */
import { useState } from "react";
import { formatDate } from "../../lib/dates";
import { CONFIDENCE_LABEL, METHOD_HELP, METHOD_LABEL, METHODS, type ConfidenceLevel, type Method } from "../../lib/methods";
import { userMessage } from "../../services/api/errors";
import { downloadMockCsv, exportCsvUrl } from "../../services/api/fireApi";
import type { ExportQuery } from "../../services/api/types";
import { Brand } from "../Brand";
import { Segmented } from "../ui/Segmented";

interface SummaryBarProps {
  areaLabel: string;
  areaDetail: string;
  date: string;
  conf: ConfidenceLevel;
  metric: Method;
  onMetric: (m: Method) => void;
  eventsAvailable: boolean;
  onEdit: () => void;
  /** null when the area cannot be exported (locally drawn area without /api/areas) */
  exportQuery: ExportQuery | null;
  exportLabel: string;
}

export function SummaryBar(p: SummaryBarProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const href = p.exportQuery ? exportCsvUrl(p.exportQuery) : null;

  const download = async () => {
    if (!p.exportQuery) return;
    setError(null);
    setDownloading(true);
    try {
      await downloadMockCsv(p.exportQuery);
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <header className="topbar topbar--summary">
      <Brand />
      <dl className="summary">
        <div>
          <dt>Gebiet</dt>
          <dd>
            {p.areaLabel} <span className="muted">· {p.areaDetail}</span>
          </dd>
        </div>
        <div>
          <dt>Stichtag</dt>
          <dd>{formatDate(p.date)}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{CONFIDENCE_LABEL[p.conf]}</dd>
        </div>
      </dl>
      <Segmented label="Methode" value={p.metric} onChange={p.onMetric} size="small"
        options={METHODS.map((m) => ({ value: m, label: METHOD_LABEL[m], title: METHOD_HELP[m], disabled: m === "events" && !p.eventsAvailable }))} />
      <div className="topbar__actions">
        {href ? (
          <a className="btn" href={href} title={p.exportLabel}>CSV-Download</a>
        ) : (
          <button type="button" className="btn" onClick={() => void download()} disabled={!p.exportQuery || downloading}
            title={p.exportQuery ? p.exportLabel : "Für lokal gezeichnete Gebiete ist kein Export möglich."}>
            {downloading ? "Export läuft …" : "CSV-Download"}
          </button>
        )}
        <button type="button" className="btn btn--primary" onClick={p.onEdit}>Bearbeiten</button>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </header>
  );
}
