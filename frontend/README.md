# La Brasa – Frontend

React + TypeScript + Vite, map with MapLibre GL, H3 cells with `h3-js`, charts with d3 (SVG).
Implements the Fire-API v3 specification (`/api/...`): start page (`/`), analysis page (`/?page=analysis`) and a
plain info page (`/info.html`). Languages EN/ES/PT (`i18n/`). Design history and decisions: [DESIGN.md](DESIGN.md).

Node 22 (`.nvmrc`; at least 20.19 for the dev tools vitest and ESLint).

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # unit tests (lib/)
npm run lint         # ESLint: TypeScript + rules of hooks
npm run build        # typecheck + production build into dist/
```

## Backend

The app always talks to the backend (see `startup.md` in the repository root).

| Variable | Meaning |
|---|---|
| `VITE_API_URL` | backend origin; empty = same origin (Vite proxy to `:8000` in dev, Caddy in Docker) |
| `VITE_BASEMAP_STYLE_URL` | other MapLibre style; default OpenFreeMap Positron (no API key) |
| `VITE_SATELLITE_TILES_URL`, `VITE_SATELLITE_ATTRIBUTION` | raster tiles (`{z}/{y}/{x}`) for the "Satellit" background; default Esri World Imagery (no API key) |

Copy `.env.example` to `.env.local` to set them.

When the backend changes its DTOs, regenerate the types: `npm run gen:types` (backend on `:8000`).

## Structure

| Folder | Content |
|---|---|
| `routes/` | the two pages: `StartPage`, `AnalysisPage` |
| `components/` | map (`map/OrbitalMap`, `map/MapTools`), charts (`charts/`), page building blocks (`start/`, `analysis/`), `Header`, `SensorCompare`, `ui/` |
| `i18n/` | translations (`messages/en.ts` is the reference) and `Intl` formatters |
| `hooks/` | URL state (`useAppState`), requests with abort/debounce/cache (`useApiQuery`), map, drawing, area selection |
| `services/api/` | generated `schema.d.ts`, short type names, HTTP client, one function per endpoint |
| `lib/` | pure helpers: dates, geometry, §7 calculations (`analysis.ts`), colours, formatting |

Build notes: the pages are loaded on demand and MapLibre, h3, d3 and React get their own chunks.
MapLibre 6 starts its web worker from a URL that Vite builds (`hooks/useMapLibre.ts`), and its CSS is
imported in `main.tsx` before `styles/app.css`, so the app styles win.

All view state lives in the URL (`?region=ES-OR&date=2025-08-14&lookback=7&metric=fires&conf=nominal`),
so reload, "Bearbeiten" and sharing work.
