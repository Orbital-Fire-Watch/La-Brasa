import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MockApp } from "./MockApp";
// MapLibre first, then the app styles (the reused charts on the analysis page need them), then the mock design on top.
import "maplibre-gl/dist/maplibre-gl.css";
import "../../styles/tokens.css";
import "../../styles/app.css";
import "./mock.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing in design-mock/index.html");

createRoot(root).render(
  <StrictMode>
    <MockApp />
  </StrictMode>,
);
