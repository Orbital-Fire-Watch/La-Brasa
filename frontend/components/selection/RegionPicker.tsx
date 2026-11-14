/** Left column of page 1: predefined areas – countries, regions and (once the API has them) provinces from /api/regions. */
import { useMemo, useState } from "react";
import type { RegionFeature, RegionsResponse } from "../../services/api/types";

interface RegionPickerProps {
  regions: RegionsResponse | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

interface Node {
  feature: RegionFeature;
  children: Node[];
}

const collator = new Intl.Collator("es");
const COUNTRY_ORDER = ["ES", "PT"];

function buildTree(regions: RegionsResponse): Node[] {
  const byParent = new Map<string | null, RegionFeature[]>();
  for (const f of regions.features) {
    const list = byParent.get(f.properties.parent) ?? [];
    list.push(f);
    byParent.set(f.properties.parent, list);
  }
  const build = (f: RegionFeature): Node => ({
    feature: f,
    children: (byParent.get(f.properties.id) ?? [])
      .sort((a, b) => collator.compare(a.properties.name, b.properties.name))
      .map(build),
  });
  return (byParent.get(null) ?? [])
    .filter((f) => f.properties.level === "country")
    .sort((a, b) => COUNTRY_ORDER.indexOf(a.properties.id) - COUNTRY_ORDER.indexOf(b.properties.id))
    .map(build);
}

function ancestors(regions: RegionsResponse, id: string | null): Set<string> {
  const byId = new Map(regions.features.map((f) => [f.properties.id, f]));
  const out = new Set<string>();
  let cur = id ? byId.get(id) : undefined;
  while (cur?.properties.parent) {
    out.add(cur.properties.parent);
    cur = byId.get(cur.properties.parent);
  }
  return out;
}

export function RegionPicker({ regions, selectedId, onSelect }: RegionPickerProps) {
  const [query, setQuery] = useState("");
  // Explicit user toggles; without one, the parents of the selected area are open.
  const [toggled, setToggled] = useState<Map<string, boolean>>(new Map());
  const forced = useMemo(() => (regions ? ancestors(regions, selectedId) : new Set<string>()), [regions, selectedId]);
  const isOpen = (id: string) => toggled.get(id) ?? forced.has(id);
  const tree = useMemo(() => (regions ? buildTree(regions) : []), [regions]);
  const matches = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("es");
    if (!regions || q.length < 2) return null;
    return regions.features
      .filter((f) => f.properties.name.toLocaleLowerCase("es").includes(q) || f.properties.id.toLowerCase().includes(q))
      .sort((a, b) => collator.compare(a.properties.name, b.properties.name))
      .slice(0, 30);
  }, [regions, query]);

  const toggle = (id: string) => setToggled((m) => new Map(m).set(id, !isOpen(id)));

  const item = (f: RegionFeature, depth: number, hasChildren: boolean) => (
    <div className="tree__row" style={{ paddingLeft: depth * 14 }}>
      {hasChildren ? (
        <button type="button" className="tree__toggle" aria-expanded={isOpen(f.properties.id)}
          aria-label={`${f.properties.name} ${isOpen(f.properties.id) ? "zuklappen" : "aufklappen"}`}
          onClick={() => toggle(f.properties.id)}>
          {isOpen(f.properties.id) ? "▾" : "▸"}
        </button>
      ) : (
        <span className="tree__toggle" aria-hidden="true" />
      )}
      <button type="button" className="tree__item" aria-pressed={selectedId === f.properties.id} onClick={() => onSelect(f.properties.id)}>
        {f.properties.name}
      </button>
    </div>
  );

  const renderNodes = (nodes: Node[], depth: number) => (
    <ul className="tree__list">
      {nodes.map((n) => (
        <li key={n.feature.properties.id}>
          {item(n.feature, depth, n.children.length > 0)}
          {n.children.length > 0 && isOpen(n.feature.properties.id) && renderNodes(n.children, depth + 1)}
        </li>
      ))}
    </ul>
  );

  return (
    <section className="panel" aria-labelledby="regions-title">
      <h2 id="regions-title" className="panel__title">Vordefinierte Gebiete</h2>
      <button type="button" className="tree__item tree__item--all" aria-pressed={selectedId === null} onClick={() => onSelect(null)}>
        Ganz Spanien + Portugal
      </button>
      <label className="field">
        <span className="visually-hidden">Gebiet suchen</span>
        <input type="search" className="input" placeholder="Gebiet suchen …" value={query}
          onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="tree">
        {!regions && <p className="muted">Grenzen werden geladen …</p>}
        {matches ? (
          matches.length ? (
            <ul className="tree__list">
              {matches.map((f) => (
                <li key={f.properties.id}>{item(f, 0, false)}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Kein Gebiet gefunden.</p>
          )
        ) : (
          renderNodes(tree, 0)
        )}
      </div>
    </section>
  );
}
