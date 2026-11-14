import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// MapLibre's styles first, then the base styles (the charts on the analysis page need them), then the design on top.
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/design.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing in index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
