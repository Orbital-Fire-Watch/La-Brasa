# La Brasa – Frontend

React + TypeScript + Vite, map with MapLibre GL, H3 cells with `h3-js`, charts with d3 (SVG).
Implements the Fire-API v3 specification (`/api/...`): page 1 "Auswahl" (`/`) and page 2 "Auswertung" (`/analysis`).

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # unit tests (lib/, mock API)
npm run build        # typecheck + production build into dist/
```

## Mock or real backend

The backend is not finished yet, so by default (`VITE_API_MODE=mock`) all requests go to a **mock API that
runs in a Web Worker** (`services/mock/`). It generates synthetic, deterministic fire data in exactly the
format of the specification, including error codes, so every view can be developed and tested.

| Variable | Meaning |
|---|---|
| `VITE_API_MODE` | `mock` (default) or `live` |
| `VITE_API_URL` | backend origin in `live` mode; empty = same origin (Vite proxy to `:8000` in dev, Caddy in Docker) |
| `VITE_MOCK_DISABLE` | mock only: switch off `features`, e.g. `events,areas`, to test the fallbacks (§7.6) |
| `VITE_BASEMAP_STYLE_URL` | other MapLibre style; default OpenFreeMap Positron (no API key) |
| `VITE_SATELLITE_TILES_URL`, `VITE_SATELLITE_ATTRIBUTION` | raster tiles (`{z}/{y}/{x}`) for the "Satellit" background; default Esri World Imagery (no API key) |

Copy `.env.example` to `.env.local` to set them.

When the backend changes its DTOs, regenerate the types: `npm run gen:types` (backend on `:8000`).

## Structure

| Folder | Content |
|---|---|
| `routes/` | the two pages: `SelectionPage`, `AnalysisPage` |
| `components/` | map (`map/FireMap`), charts (`charts/`), page building blocks (`selection/`, `analysis/`), `ui/` |
| `hooks/` | URL state (`useAppState`), requests with abort/debounce/cache (`useApiQuery`), map, drawing, area selection |
| `services/api/` | generated `schema.d.ts`, short type names, HTTP client, one function per endpoint |
| `services/mock/` | mock API (world generator, endpoint handlers, worker) |
| `lib/` | pure helpers: dates, geometry, §7 calculations (`analysis.ts`), colours, formatting |
| `public/mock/regions.json` | boundaries for the mock (`npm run build:mock-regions`, source: GISCO NUTS 2021) |

All view state lives in the URL (`?region=ES-OR&date=2025-08-14&lookback=7&metric=fires&conf=nominal`),
so reload, "Bearbeiten" and sharing work.
