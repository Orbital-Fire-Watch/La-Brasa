"""Schritt 0: Roh-CSVs einmal einlesen und als Parquet cachen.

Erzeugt
  cache/iberia.parquet  MODIS (Terra/Aqua) 2000-2026 + VIIRS SNPP 2012-2026, Iberien
  cache/global.parquet  MODIS, SNPP, NOAA-20, NOAA-21 weltweit, 2025-10-17 bis 2026-10-17

Zusaetzliche Spalten:
  sensor   MODIS / VIIRS
  sat      Terra / Aqua / SNPP / N20 / N21
  source   archive / nrt
  utc_h    Ueberflugzeit in Dezimalstunden UTC
  lst      lokale Sonnenzeit = utc_h + longitude/15  (0-24 h)
  type     im NRT nicht vorhanden -> NULL
"""
from common import DATA, GLOBAL, IBERIA, con

SELECT = """
SELECT
    CASE WHEN satellite IN ('Terra','Aqua') THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
    satellite AS sat,
    CASE WHEN filename LIKE '%fire_nrt%' THEN 'nrt' ELSE 'archive' END AS source,
    latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude,
    acq_date::DATE AS acq_date,
    lpad(acq_time, 4, '0') AS acq_time,
    brightness::DOUBLE AS brightness, bright_t31::DOUBLE AS bright_t31,
    frp::DOUBLE AS frp, scan::DOUBLE AS scan, track::DOUBLE AS track,
    daynight, confidence, version,
    TRY_CAST(type AS INTEGER) AS type,
    (lpad(acq_time,4,'0')[1:2]::INT + lpad(acq_time,4,'0')[3:4]::INT / 60.0) AS utc_h,
    fmod((lpad(acq_time,4,'0')[1:2]::INT + lpad(acq_time,4,'0')[3:4]::INT / 60.0)
         + longitude::DOUBLE / 15.0 + 24.0, 24.0) AS lst
FROM read_csv({files}, union_by_name=true, filename=true, all_varchar=true)
"""


def build(files, out):
    c = con()
    lst = "[" + ",".join(f"'{f}'" for f in files) + "]"
    c.execute(f"COPY ({SELECT.format(files=lst)}) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    print(out.name)
    print(c.execute(f"""SELECT sensor, sat, source, COUNT(*) n, MIN(acq_date), MAX(acq_date)
                        FROM '{out}' GROUP BY ALL ORDER BY ALL""").df().to_string(index=False))


if __name__ == "__main__":
    ib = DATA / "NASA_SPACEAPP"
    build([ib / "DL_FIRE_M-C61_845369" / "fire_archive_M-C61_845369.csv",
           ib / "DL_FIRE_M-C61_845369" / "fire_nrt_M-C61_845369.csv",
           ib / "DL_FIRE_SV-C2_845370" / "fire_archive_SV-C2_845370.csv",
           ib / "DL_FIRE_SV-C2_845370" / "fire_nrt_SV-C2_845370.csv"], IBERIA)
    gl = []
    for d in ["DL_FIRE_M-C61_835029", "DL_FIRE_SV-C2_835019",
              "DL_FIRE_J1V-C2_835017", "DL_FIRE_J2V-C2_835018"]:
        gl += sorted((DATA / d).glob("fire_*.csv"))
    build(gl, GLOBAL)
