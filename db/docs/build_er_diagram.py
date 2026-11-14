#!/usr/bin/env python3
"""Draw er_diagram.svg from the Mermaid erDiagram block in data_model.md (standard library only, no network).

    python db/docs/build_er_diagram.py

The Mermaid block stays the single source: entities, attributes, keys and relationships are read from it.
The layout (which entity sits where) is fixed below because the model is small and should read the same way
every time: regions in the middle, the two big fact tables around it, the lookup tables on the right.
mermaid-cli (see data_model.md) draws the same diagram if Node and a headless browser are available.
"""
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE, TARGET = HERE / "data_model.md", HERE / "er_diagram.svg"

# Grid position (column, row) of every entity
LAYOUT = {"activity_daily_harmonised": (0, 0), "regions": (1, 0), "calib_factors": (2, 0), "quality_by_scale": (3, 0),
          "day_status": (0, 1), "hotspots_harmonised": (1, 1), "strength_confusion": (2, 1), "big_fire_day_quality": (3, 1)}
CHAR_W, LINE_H, PAD, HEAD_H, COL_GAP, ROW_GAP, MARGIN = 6.6, 20, 10, 30, 70, 80, 24
COLORS = {"line": "#4a4f57", "head": "#1f3b57", "head_text": "#ffffff", "box": "#ffffff", "border": "#8b97a6",
          "key": "#9a3412", "type": "#5b6573", "text": "#1d2127", "note": "#6b7280", "zebra": "#f3f5f8"}


def parse_mermaid(text: str) -> tuple[dict[str, list[tuple[str, str, str, str]]], list[tuple[str, str, str, str]]]:
    """Entities with (type, name, keys, comment) and relationships (left, marker, right, label) of the erDiagram block."""
    block = text.split("```mermaid")[1].split("```")[0]
    entities, relations, current = {}, [], None
    for raw in block.splitlines():
        line = raw.strip()
        if match := re.match(r'(\w+)\s+([|}o][|o])(--|\.\.)([o|][|{])\s+(\w+)\s*:\s*"(.*)"', line):
            left, end_left, style, end_right, right, label = match.groups()
            relations.append((left, end_left + style + end_right, right, label))
        elif match := re.match(r"(\w+)\s*\{$", line):
            current = match.group(1)
            entities[current] = []
        elif line == "}":
            current = None
        elif current and line:
            parts = re.match(r'(\w+)\s+(\w+)\s*([A-Z, ]*?)\s*(?:"(.*)")?$', line)
            entities[current].append((parts.group(1), parts.group(2), parts.group(3).strip(), parts.group(4) or ""))
    return entities, relations


def box_width(attributes: list[tuple[str, str, str, str]], name: str) -> float:
    """Width of an entity box: the longest of title and attribute rows."""
    rows = [len(f"{kind}  {attr}  {keys}  {note}") for kind, attr, keys, note in attributes]
    return max([len(name) + 4] + rows) * CHAR_W + 2 * PAD


def place_boxes(entities: dict) -> dict[str, tuple[float, float, float, float]]:
    """x, y, width, height of every box on the fixed grid (columns as wide as their widest box)."""
    widths = {name: box_width(attrs, name) for name, attrs in entities.items()}
    heights = {name: HEAD_H + len(attrs) * LINE_H + PAD for name, attrs in entities.items()}
    columns = max(c for c, _ in LAYOUT.values()) + 1
    col_w = [max(widths[n] for n, (c, _) in LAYOUT.items() if c == col) for col in range(columns)]
    row_h = [max(heights[n] for n, (_, r) in LAYOUT.items() if r == row) for row in range(2)]
    boxes = {}
    for name, (col, row) in LAYOUT.items():
        x = MARGIN + sum(col_w[:col]) + col * COL_GAP + (col_w[col] - widths[name]) / 2
        y = MARGIN + sum(row_h[:row]) + row * ROW_GAP
        boxes[name] = (x, y, widths[name], heights[name])
    return boxes


def draw_box(name: str, attributes: list, box: tuple[float, float, float, float]) -> str:
    """One entity: dark title bar, then one row per attribute (type, name, key flags, comment)."""
    x, y, w, h = box
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="{COLORS["box"]}" stroke="{COLORS["border"]}"/>',
             f'<path d="M{x:.1f},{y + HEAD_H:.1f} V{y + 4:.1f} Q{x:.1f},{y:.1f} {x + 4:.1f},{y:.1f} H{x + w - 4:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + 4:.1f} V{y + HEAD_H:.1f} Z" fill="{COLORS["head"]}"/>',
             f'<text x="{x + w / 2:.1f}" y="{y + 20:.1f}" text-anchor="middle" font-weight="700" fill="{COLORS["head_text"]}">{name}</text>']
    for index, (kind, attr, keys, note) in enumerate(attributes):
        top = y + HEAD_H + index * LINE_H
        if index % 2:
            parts.append(f'<rect x="{x + 1:.1f}" y="{top:.1f}" width="{w - 2:.1f}" height="{LINE_H}" fill="{COLORS["zebra"]}"/>')
        base = top + 14
        parts.append(f'<text x="{x + PAD:.1f}" y="{base:.1f}" fill="{COLORS["type"]}">{kind}</text>')
        label = f'<tspan font-weight="700" fill="{COLORS["key"]}"> {keys}</tspan>' if keys else ""
        comment = f'<tspan fill="{COLORS["note"]}" font-style="italic">  {html.escape(note)}</tspan>' if note else ""
        type_width = max(len(row[0]) for row in attributes) * CHAR_W + 14
        parts.append(f'<text x="{x + PAD + type_width:.1f}" y="{base:.1f}" fill="{COLORS["text"]}">{attr}{label}{comment}</text>')
    return "\n".join(parts)


def end_marker(px: float, py: float, dx: float, dy: float, code: str) -> str:
    """Crow's-foot end at (px, py), pointing into the box along (dx, dy): | = one, o = zero, { or } = many."""
    nx, ny = -dy, dx
    out, at = [], lambda d: (px - dx * d, py - dy * d)
    many, outer = code in ("o{", "}o", "|{", "}|"), code.replace("{", "").replace("}", "")
    if many:
        a, b, c = at(14), (px + nx * 8, py + ny * 8), (px - nx * 8, py - ny * 8)
        out.append(f'<path d="M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f} M{a[0]:.1f},{a[1]:.1f} L{px:.1f},{py:.1f} M{a[0]:.1f},{a[1]:.1f} L{c[0]:.1f},{c[1]:.1f}" fill="none"/>')
    if "|" in code:
        bar = at(6 if not many else 18)
        out.append(f'<path d="M{bar[0] + nx * 7:.1f},{bar[1] + ny * 7:.1f} L{bar[0] - nx * 7:.1f},{bar[1] - ny * 7:.1f}" fill="none"/>')
        if code == "||":
            second = at(11)
            out.append(f'<path d="M{second[0] + nx * 7:.1f},{second[1] + ny * 7:.1f} L{second[0] - nx * 7:.1f},{second[1] - ny * 7:.1f}" fill="none"/>')
    if "o" in outer:
        circle = at(24 if many else 18)
        out.append(f'<circle cx="{circle[0]:.1f}" cy="{circle[1]:.1f}" r="5" fill="{COLORS["box"]}"/>')
    return "\n".join(out)


def anchor(box: tuple[float, float, float, float], other: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Point on the side of `box` facing `other`, with the unit direction pointing out of the box."""
    x, y, w, h = box
    ox, oy = other[0] + other[2] / 2, other[1] + other[3] / 2
    cx, cy = x + w / 2, y + h / 2
    if abs(ox - cx) * h > abs(oy - cy) * w:
        side = 1 if ox > cx else -1
        return cx + side * w / 2, min(max(oy, y + HEAD_H + 10), y + h - 10) if abs(oy - cy) < h / 2 else cy, side, 0
    side = 1 if oy > cy else -1
    return cx, cy + side * h / 2, 0, side


def draw_relation(left: str, marker: str, right: str, label: str, boxes: dict) -> str:
    """Line between two boxes with crow's-foot ends; dashed for logical (not enforced) relationships."""
    x1, y1, dx1, dy1 = anchor(boxes[left], boxes[right])
    x2, y2, dx2, dy2 = anchor(boxes[right], boxes[left])
    if dx1 == 0:
        x1 = x2 = (max(boxes[left][0], boxes[right][0]) + min(boxes[left][0] + boxes[left][2], boxes[right][0] + boxes[right][2])) / 2
    else:
        y1 = y2 = (max(boxes[left][1], boxes[right][1]) + HEAD_H + min(boxes[left][1] + boxes[left][3], boxes[right][1] + boxes[right][3])) / 2
    dash = ' stroke-dasharray="6 4"' if ".." in marker else ""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return "\n".join([f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"{dash}/>',
                      end_marker(x1, y1, -dx1, -dy1, marker[:2]), end_marker(x2, y2, -dx2, -dy2, marker[-2:]),
                      f'<text x="{mx + (6 if dx1 == 0 else 0):.1f}" y="{my - (6 if dx1 != 0 else 0):.1f}" text-anchor="{"start" if dx1 == 0 else "middle"}" '
                      f'fill="{COLORS["note"]}" font-style="italic" stroke="none">{html.escape(label)}</text>'])


def build_svg(text: str) -> str:
    """The whole diagram as a standalone SVG with a white background (readable in dark mode too)."""
    entities, relations = parse_mermaid(text)
    boxes = place_boxes(entities)
    width = max(x + w for x, _, w, _ in boxes.values()) + MARGIN
    height = max(y + h for _, y, _, h in boxes.values()) + MARGIN
    lines = "\n".join(draw_relation(*relation, boxes) for relation in relations)
    body = "\n".join(draw_box(name, entities[name], boxes[name]) for name in LAYOUT)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {width:.0f} {height:.0f}" style="max-width:{width:.0f}px;background:#ffffff" '
            f'font-family="Arial, Helvetica, sans-serif" font-size="12" role="img" aria-label="ER diagram of the La-Brasa database">\n'
            f'<rect width="100%" height="100%" fill="#ffffff"/>\n{body}\n'
            f'<g stroke="{COLORS["line"]}" stroke-width="1.5" font-size="11">\n{lines}\n</g>\n</svg>\n')


if __name__ == "__main__":
    TARGET.write_text(build_svg(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print("->", TARGET)
