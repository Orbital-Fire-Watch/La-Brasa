import type { DrawMode } from "../../hooks/useDrawTool";

interface DrawToolbarProps {
  mode: DrawMode;
  onMode: (mode: DrawMode) => void;
  onCoordinates: () => void;
  onClear: (() => void) | null;
  hint: string;
  busy: boolean;
}

const TOOLS: { mode: Exclude<DrawMode, "none">; label: string; icon: string }[] = [
  { mode: "rectangle", label: "Rechteck", icon: "M3 5h14v10H3z" },
  { mode: "circle", label: "Kreis", icon: "M10 3a7 7 0 1 0 0.01 0z" },
  { mode: "polygon", label: "Vieleck", icon: "M4 15 3 7l7-4 7 5-3 8z" },
  { mode: "freehand", label: "Freihand", icon: "M3 13c2-6 5 3 7-3s4 4 7-2" },
];

/** Tools to draw an area on the map (spec §6.3). */
export function DrawToolbar({ mode, onMode, onCoordinates, onClear, hint, busy }: DrawToolbarProps) {
  return (
    <div className="map-toolbar" role="toolbar" aria-label="Gebiet zeichnen">
      {TOOLS.map((t) => (
        <button key={t.mode} type="button" className="map-toolbar__btn" aria-pressed={mode === t.mode} disabled={busy}
          onClick={() => onMode(mode === t.mode ? "none" : t.mode)} title={`${t.label} zeichnen`}>
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d={t.icon} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
          <span>{t.label}</span>
        </button>
      ))}
      <button type="button" className="map-toolbar__btn" onClick={onCoordinates} disabled={busy} title="Koordinaten oder Stadt eingeben">
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M10 18s6-5.5 6-10a6 6 0 0 0-12 0c0 4.5 6 10 6 10zm0-8a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        <span>Koordinaten</span>
      </button>
      {onClear && (
        <button type="button" className="map-toolbar__btn map-toolbar__btn--danger" onClick={onClear} disabled={busy}>
          <span>Gebiet entfernen</span>
        </button>
      )}
      {(hint || busy) && <p className="map-toolbar__hint" aria-live="polite">{busy ? "Gebiet wird registriert …" : hint}</p>}
    </div>
  );
}
