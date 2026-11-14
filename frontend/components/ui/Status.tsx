import type { ReactNode } from "react";
import { userMessage } from "../../services/api/errors";

export function Spinner({ label = "Lädt …" }: { label?: string }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner__dot" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

export function LoadingBlock({ label = "Daten werden geladen …", height }: { label?: string; height?: number }) {
  return (
    <div className="status status--loading" style={height ? { minHeight: height } : undefined}>
      <Spinner label={label} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="status status--error" role="alert">
      <span>{userMessage(error)}</span>
      {onRetry && (
        <button type="button" className="btn btn--small" onClick={onRetry}>
          Erneut versuchen
        </button>
      )}
    </div>
  );
}

export function EmptyBlock({ children }: { children: ReactNode }) {
  return <div className="status status--empty">{children}</div>;
}
