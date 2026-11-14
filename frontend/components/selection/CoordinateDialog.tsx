/** Enter an area by coordinates: corner points, centre + radius, or a city with radius (spec §6.3). */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { circlePolygon, closeRing, parseCoordinateList, type PolygonGeometry, type Position } from "../../lib/geo";
import { Segmented } from "../ui/Segmented";

const CITIES: { name: string; pos: Position }[] = [
  { name: "A Coruña", pos: [-8.4115, 43.3623] },
  { name: "Badajoz", pos: [-6.9707, 38.8794] },
  { name: "Barcelona", pos: [2.1734, 41.3851] },
  { name: "Bilbao", pos: [-2.935, 43.263] },
  { name: "Braga", pos: [-8.4265, 41.5454] },
  { name: "Coimbra", pos: [-8.4103, 40.2033] },
  { name: "Évora", pos: [-7.9135, 38.5714] },
  { name: "Faro", pos: [-7.9304, 37.0194] },
  { name: "Granada", pos: [-3.5986, 37.1773] },
  { name: "León", pos: [-5.5671, 42.5987] },
  { name: "Lisboa", pos: [-9.1393, 38.7223] },
  { name: "Lugo", pos: [-7.5559, 43.0097] },
  { name: "Madrid", pos: [-3.7038, 40.4168] },
  { name: "Málaga", pos: [-4.4214, 36.7213] },
  { name: "Murcia", pos: [-1.1307, 37.9922] },
  { name: "Ourense", pos: [-7.8641, 42.3358] },
  { name: "Oviedo", pos: [-5.8494, 43.3614] },
  { name: "Palma", pos: [2.6502, 39.5696] },
  { name: "Porto", pos: [-8.6291, 41.1579] },
  { name: "Salamanca", pos: [-5.6635, 40.9701] },
  { name: "Santiago de Compostela", pos: [-8.5448, 42.8782] },
  { name: "Sevilla", pos: [-5.9845, 37.3891] },
  { name: "Valencia", pos: [-0.3763, 39.4699] },
  { name: "Viseu", pos: [-7.9137, 40.661] },
  { name: "Zamora", pos: [-5.7445, 41.5034] },
  { name: "Zaragoza", pos: [-0.8891, 41.6488] },
];

type Tab = "polygon" | "circle" | "city";

interface CoordinateDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (g: PolygonGeometry) => void;
  maxVertices: number;
}

export function CoordinateDialog({ open, onClose, onSubmit, maxVertices }: CoordinateDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<Tab>("city");
  const [points, setPoints] = useState("-8.2, 42.0\n-6.8, 42.0\n-6.8, 42.6\n-8.2, 42.6");
  const [lon, setLon] = useState("-7.864");
  const [lat, setLat] = useState("42.336");
  const [radius, setRadius] = useState("20");
  const [city, setCity] = useState("Ourense");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const r = Number(radius.replace(",", "."));
    if (tab !== "polygon" && !(r > 0 && r <= 300)) return setError("Der Radius muss zwischen 0 und 300 km liegen.");
    if (tab === "polygon") {
      const pts = parseCoordinateList(points);
      if (!pts || pts.length < 3) return setError("Bitte mindestens drei Punkte im Format „Längengrad, Breitengrad“ eingeben.");
      if (pts.length > maxVertices) return setError(`Höchstens ${maxVertices} Punkte.`);
      return onSubmit({ type: "Polygon", coordinates: [closeRing(pts)] });
    }
    if (tab === "circle") {
      const x = Number(lon.replace(",", "."));
      const y = Number(lat.replace(",", "."));
      if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90) {
        return setError("Bitte gültige Koordinaten eingeben (Längengrad −180…180, Breitengrad −90…90).");
      }
      return onSubmit(circlePolygon([x, y], r));
    }
    const c = CITIES.find((x) => x.name === city);
    if (c) onSubmit(circlePolygon(c.pos, r));
  };

  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-labelledby="coord-title">
      <form onSubmit={submit} className="dialog__form">
        <h2 id="coord-title" className="dialog__title">Gebiet über Koordinaten festlegen</h2>
        <Segmented label="Art" hideLabel value={tab} onChange={setTab} options={[
          { value: "city", label: "Stadt + Radius" },
          { value: "circle", label: "Mittelpunkt + Radius" },
          { value: "polygon", label: "Eckpunkte" },
        ]} />
        {tab === "polygon" && (
          <label className="field">
            <span>Eckpunkte, ein Punkt pro Zeile: Längengrad, Breitengrad (WGS84)</span>
            <textarea className="input" rows={6} value={points} onChange={(e) => setPoints(e.target.value)} />
          </label>
        )}
        {tab === "circle" && (
          <div className="field-row">
            <label className="field">
              <span>Längengrad (lon)</span>
              <input className="input" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />
            </label>
            <label className="field">
              <span>Breitengrad (lat)</span>
              <input className="input" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />
            </label>
          </div>
        )}
        {tab === "city" && (
          <label className="field">
            <span>Stadt</span>
            <select className="input" value={city} onChange={(e) => setCity(e.target.value)}>
              {CITIES.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>
          </label>
        )}
        {tab !== "polygon" && (
          <label className="field">
            <span>Radius in km</span>
            <input className="input" type="number" min={1} max={300} step={1} value={radius} onChange={(e) => setRadius(e.target.value)} />
          </label>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog__actions">
          <button type="button" className="btn" onClick={onClose}>Abbrechen</button>
          <button type="submit" className="btn btn--primary">Gebiet übernehmen</button>
        </div>
      </form>
    </dialog>
  );
}
