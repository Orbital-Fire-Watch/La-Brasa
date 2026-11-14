import type { ErrorCode } from "./types";

/** API error with a code from spec §8 – the UI reacts based on `code`. */
export class ApiError extends Error {
  constructor(public status: number, public code: ErrorCode, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export const isAbortError = (e: unknown): boolean => e instanceof DOMException && e.name === "AbortError";

/** German text for the user, based on the reaction table in spec §8. */
export function userMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Keine Verbindung zum Server. Bitte später erneut versuchen.";
  switch (e.code) {
    case "INVALID_DATE_RANGE":
      return "Der Zeitraum liegt außerhalb der verfügbaren Daten.";
    case "GEOMETRY_INVALID":
      return "Das Gebiet ist ungültig. Bitte neu zeichnen.";
    case "AREA_OUTSIDE_REGION":
      return "Das Gebiet liegt außerhalb von Spanien und Portugal.";
    case "GEOMETRY_TOO_COMPLEX":
      return "Das Gebiet hat zu viele Eckpunkte. Bitte einfacher zeichnen.";
    case "AREA_NOT_FOUND":
      return "Das gezeichnete Gebiet ist dem Server nicht mehr bekannt. Bitte neu zeichnen.";
    case "EVENT_NOT_FOUND":
      return "Dieses Ereignis gibt es nicht mehr (z. B. nach einem Datenimport).";
    case "NOT_IMPLEMENTED":
      return "Diese Funktion ist im Backend noch nicht verfügbar.";
    case "QUERY_TIMEOUT":
      return "Die Abfrage hat zu lange gedauert. Bitte ein kleineres Gebiet oder einen kürzeren Zeitraum wählen.";
    case "INTERNAL_ERROR":
      return "Interner Fehler. Bitte später erneut versuchen.";
    default:
      return `Ungültige Anfrage (${e.code}): ${e.message}`;
  }
}
