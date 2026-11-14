"""Make backend/assets/nuts2_iberia.geojson from the Eurostat GISCO NUTS-2 GeoJSON.

    python backend/tools/make_regions_asset.py --input data/raw/NUTS_RG_01M_2021_4326_LEVL_2.geojson

Keeps NUTS-2 regions of ES and PT (without Canary Islands, Azores, Madeira, Ceuta, Melilla),
simplifies them (about 0.005 degrees) and rounds the coordinates, so the file stays small.
The asset is committed to Git (unlike data/), because the API serves it at /api/regions.
Boundaries: (C) EuroGeographics, Eurostat GISCO. Keep the attribution (see core/config.py).
"""
import argparse
import json
from pathlib import Path

from shapely.geometry import mapping, shape

EXCLUDE = {"ES70", "ES63", "ES64", "PT20", "PT30"}
COUNTRIES = {"ES", "PT"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "assets" / "nuts2_iberia.geojson")
    parser.add_argument("--tolerance", type=float, default=0.005)
    args = parser.parse_args()

    features = []
    for f in json.loads(args.input.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        if p.get("LEVL_CODE") != 2 or p.get("CNTR_CODE") not in COUNTRIES or p["NUTS_ID"] in EXCLUDE:
            continue
        geom = shape(f["geometry"]).simplify(args.tolerance, preserve_topology=True)
        features.append({"type": "Feature", "properties": {"NUTS_ID": p["NUTS_ID"], "NUTS_NAME": p.get("NUTS_NAME")},
                         "geometry": mapping(geom)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    # round to 4 decimals (about 11 m)
    import re
    text = re.sub(r"(\d+\.\d{4})\d+", r"\1", text)
    args.output.write_text(text, encoding="utf-8")
    print(f"{len(features)} regions, {args.output.stat().st_size / 1024:.0f} KB -> {args.output}")


if __name__ == "__main__":
    main()
