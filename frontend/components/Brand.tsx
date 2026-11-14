import { CONFIG } from "../lib/config";

export function Brand() {
  return (
    <div className="brand">
      <svg viewBox="0 0 32 32" className="brand__logo" aria-hidden="true">
        <path d="M16 3c2 6 9 9 9 17a9 9 0 0 1-18 0c0-5 3-7 4-11 1 3 2 4 3 4 0-4 1-7 2-10z" fill="#d9480f" />
        <path d="M16 17c1 3 4 4 4 7a4 4 0 0 1-8 0c0-2 2-3 2-5 1 1 1 1 2 1z" fill="#ffd8a8" />
      </svg>
      <div>
        <span className="brand__name">La Brasa</span>
        <span className="brand__sub">Feuer in Spanien & Portugal</span>
      </div>
      {CONFIG.apiMode === "mock" && (
        <span className="badge" title="Die Daten kommen aus der Mock-API im Browser, nicht vom Backend.">Mock-Daten</span>
      )}
    </div>
  );
}
