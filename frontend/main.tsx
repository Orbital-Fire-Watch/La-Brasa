import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// MapLibre's styles first, so ours (e.g. the absolute map canvas) win. Loaded here and not with the map,
// because the pages are loaded later and their CSS would otherwise come after app.css.
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/tokens.css";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing in index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
