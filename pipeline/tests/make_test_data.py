"""Create small fake test data: regions GeoJSON + tagged MODIS/VIIRS CSVs.
Geometries are rough boxes, NOT real borders. Only for testing the pipeline."""
import csv, json, random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
out = Path(__file__).resolve().parent / "testdata"; out.mkdir(exist_ok=True)  # git-ignored

# region_id: (name, country, west, south, east, north)
R = {
    "ES11": ("Galicia", "ES", -9.3, 41.8, -6.8, 43.8),
    "ES43": ("Extremadura", "ES", -7.5, 38.0, -4.7, 40.4),
    "ES51": ("Cataluna", "ES", 0.2, 40.6, 3.2, 42.8),
    "ES61": ("Andalucia", "ES", -7.5, 36.0, -1.6, 38.7),
    "PT11": ("Norte", "PT", -8.8, 41.0, -7.0, 42.1),
    "PT18": ("Alentejo", "PT", -8.9, 37.3, -6.9, 39.3),
}
feats = []
for rid, (name, cc, w, s, e, n) in R.items():
    feats.append({"type": "Feature",
        "properties": {"NUTS_ID": rid, "NUTS_NAME": name, "CNTR_CODE": cc, "LEVL_CODE": 2},
        "geometry": {"type": "Polygon", "coordinates": [[[w,s],[e,s],[e,n],[w,n],[w,s]]]}})
(out / "nuts2_test.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

def rand_date(a, b):
    return a + timedelta(days=random.randint(0, (b - a).days))

def point(rid):
    _, cc, w, s, e, n = R[rid]
    return round(random.uniform(s, n), 5), round(random.uniform(w, e), 5), cc

def write(name, header, rows):
    with open(out / name, "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(header); wr.writerows(rows)

# MODIS: only until 2012-01-31. acq_time WITHOUT leading zeros like the API.
mh = ["latitude","longitude","brightness","scan","track","acq_date","acq_time","satellite",
      "instrument","confidence","version","bright_t31","frp","daynight","country","region_id"]
mrows = []
for _ in range(300):
    rid = random.choice(list(R)); lat, lon, cc = point(rid)
    t = random.choice([0, 5, 134, 324, 917, 1030, 1345, 1802, 2250])
    mrows.append([lat, lon, round(random.uniform(300, 360), 1), 1.0, 1.0,
        rand_date(date(2005,6,1), date(2012,1,31)), t, random.choice(["Terra","Aqua"]),
        "MODIS", random.randint(20, 100), "6.1", round(random.uniform(280,300),1),
        round(random.uniform(1,80),1), "D" if t >= 600 and t < 1800 else "N", cc, rid])
mrows.append(mrows[0])                                   # exact duplicate
mrows.append([99.0, 0.0, 330, 1, 1, "2010-01-01", 1200, "Terra", "MODIS", 50, "6.1", 290, 5, "D", "ES", "ES51"])  # invalid lat
write("modis_test_tagged.csv", mh, mrows)

# VIIRS: from 2012-02-01. Includes NRT rows (provisional) and one invalid time.
vh = ["latitude","longitude","bright_ti4","scan","track","acq_date","acq_time","satellite",
      "instrument","confidence","version","bright_ti5","frp","daynight","country","region_id"]
vrows = []
for _ in range(400):
    rid = random.choice(list(R)); lat, lon, cc = point(rid)
    t = random.choice([12, 134, 245, 917, 1203, 1357, 1803, 2359])
    vrows.append([lat, lon, round(random.uniform(300, 367), 1), 0.4, 0.4,
        rand_date(date(2013,1,1), date(2026,10,31)), t, "N", "VIIRS",
        random.choice(["l","n","h"]), "2.0", round(random.uniform(280,300),1),
        round(random.uniform(0.5,60),1), "D" if 600 <= t < 1800 else "N", cc, rid])
for _ in range(40):                                       # recent NRT from NOAA-20/21
    rid = random.choice(list(R)); lat, lon, cc = point(rid)
    vrows.append([lat, lon, round(random.uniform(300, 367), 1), 0.4, 0.4,
        rand_date(date(2026,11,1), date(2026,11,12)), random.choice([134, 917, 1803]),
        random.choice(["N20","N21"]), "VIIRS", "n", "2.0NRT", 290.0,
        round(random.uniform(0.5,60),1), "D", cc, rid])
vrows.append([40, -4, 330, .4, .4, "2020-01-01", 2475, "N", "VIIRS", "n", "2.0", 290, 5, "D", "ES", "ES43"])  # invalid time
write("viirs_test_tagged.csv", vh, vrows)
print("written to", out.resolve())
