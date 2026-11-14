"""Tagesraster: Tagessummen je Region, Betriebsfenster der Satelliten, Status je Tag, lueckenloses Raster."""
from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pandas as pd

from pipeline.config import satellite_key, viirs_keys
from pipeline.data_loading.ingest_csv_to_parquet import raw_parquet_path

BASIS_VIIRS, BASIS_PAIR, BASIS_AQUA, BASIS_TERRA, BASIS_NONE = (
    "viirs_measured", "modis_pair_scaled", "aqua_scaled", "terra_scaled", "none")


def satellites_of_basis(config: dict[str, Any]) -> dict[str, list[str]]:
    """Welche Satelliten liefern die Daten einer Basis (z. B. modis_pair_scaled -> Aqua und Terra, viirs_measured -> alle VIIRS)."""
    roles = config["satellites"]
    return {BASIS_VIIRS: list(roles["viirs"]), BASIS_PAIR: list(roles["modis_pair"]),
            BASIS_AQUA: [roles["modis_afternoon"]], BASIS_TERRA: [roles["modis_single"]], BASIS_NONE: []}


def sum_hotspots_by_day(hotspots: pd.DataFrame, config: dict[str, Any], keys: list[str] | None = None) -> pd.DataFrame:
    """Summiert die Hotspots je Schluessel (Standard: Region), Beobachtungstag und Satellit zu Anzahl und FRP.

    Die FRP-Summe eines Tages ist das Mass fuer die Staerke. `strength.frp_daynight` legt fest, ob
    Tag- und Nacht-Ueberfluege zusammenzaehlen (`all`) oder nur die Tag-Ueberfluege (`day`,
    Hypothese H5). Hintergrund: FRP ist eine Momentaufnahme der Leistung. Tag und Nacht zu addieren
    mischt zwei Zeitpunkte, ist aber das vollstaendigere Bild eines Tages.
    Die Tabelle ist duenn besetzt: nur Tage mit Erkennungen. Hotspots ohne Region zaehlen nicht mit.
    """
    keys = keys or ["region_id"]
    rows = hotspots.dropna(subset=["region_id"]) if "region_id" in keys and len(keys) == 1 else hotspots
    day_only = config["strength"]["frp_daynight"] == "day"
    rows = rows.assign(frp_counted=rows["frp"].where(rows["daynight"] == "D", 0.0) if day_only else rows["frp"])
    sums = rows.groupby(keys + ["obs_date", "satellite"], dropna=False).agg(n=("frp", "size"), frp=("frp_counted", "sum"))
    return sums.reset_index()


def find_satellite_coverage(config: dict[str, Any]) -> pd.DataFrame:
    """Bestimmt je Satellit die Zeitfenster, in denen das Produkt Daten liefert.

    Ein Fenster reicht vom ersten bis zum letzten Datum einer Quelldatei, beginnt aber fruehestens
    mit der ersten Erkennung des Satelliten (Aqua startet erst 07/2002). Gemessen wird am
    Produktfenster und nicht an den Erkennungen, weil Tage ohne Feuer legitim leer sind.
    Bei der Tageszuordnung `solar` fehlt dem letzten Tag einer Datei die zugehoerige Nacht (sie
    liegt im UTC-Datum des Folgetags). Das Fenster endet dann einen Tag frueher.
    """
    connection = duckdb.connect()
    files = ", ".join(f"'{raw_parquet_path(config, source)}'" for source in config["sources"])
    first_seen = dict(connection.execute(f"SELECT satellite, MIN(acq_date) FROM read_parquet([{files}]) GROUP BY ALL").fetchall())
    shorten = pd.Timedelta(days=1 if config["daily"]["date_assignment"] == "solar" else 0)
    windows = []
    for source in config["sources"]:
        raw = raw_parquet_path(config, source)
        start, end = connection.execute(f"SELECT MIN(acq_date), MAX(acq_date) FROM '{raw}'").fetchone()
        for (satellite,) in connection.execute(f"SELECT DISTINCT satellite FROM '{raw}'").fetchall():
            window_start = max(pd.Timestamp(start), pd.Timestamp(first_seen[satellite]))
            windows.append({"satellite": satellite, "source": source["source"], "window_start": window_start,
                            "window_end": pd.Timestamp(end) - shorten})
    coverage = pd.DataFrame(windows)
    coverage = coverage[coverage["window_start"] <= coverage["window_end"]]
    return coverage.sort_values(["satellite", "window_start"]).reset_index(drop=True)


def operating_days_of(coverage: pd.DataFrame, satellite: str, gap_tolerance_days: int, source: str | None = None) -> pd.DatetimeIndex:
    """Alle Tage, an denen ein Satellit Daten liefert. Kleine Luecken zwischen zwei Dateien zaehlen als abgedeckt."""
    windows = coverage[coverage["satellite"] == satellite].sort_values("window_start")
    days, previous_end = pd.DatetimeIndex([]), None
    for window in windows.itertuples():
        start = window.window_start
        if previous_end is not None and 0 < (start - previous_end).days <= gap_tolerance_days + 1:
            start = previous_end + pd.Timedelta(days=1)
        if source is None or window.source == source:
            days = days.union(pd.date_range(start, window.window_end, freq="D"))
        previous_end = window.window_end if previous_end is None else max(previous_end, window.window_end)
    return days


def choose_basis_per_day(status: pd.DataFrame, config: dict[str, Any], quantity: str) -> pd.Series:
    """Legt je Tag fest, aus welcher Quelle der harmonisierte Wert einer Groesse (count oder frp) kommt.

    Rangfolge:
    1. mindestens ein VIIRS-Satellit (SNPP, NOAA-20, NOAA-21) in Betrieb -> VIIRS gemessen. Eine
       Messung ist immer besser als eine Umrechnung.
    2. sonst MODIS umgerechnet, aber nur bis `modis_last_valid_date`. Danach driften Terra und Aqua
       von ihrer Ueberflugzeit weg, der Faktor gilt nicht mehr.
       - Anzahl: Aqua + Terra, wenn beide in Betrieb sind (im Test die beste Vorhersage der VIIRS-Zahl).
       - FRP: nach `strength.frp_modis_source` nur Aqua (fliegt wie SNPP am fruehen Nachmittag,
         Hypothese H1) oder ebenfalls das Paar.
       - Faellt der bevorzugte Satellit aus, gilt der jeweils verfuegbare (vor 07/2002 nur Terra).
    3. sonst kein Wert.
    Die Sensoren werden nie addiert: Dasselbe Feuer stuende sonst doppelt in der Reihe.
    """
    params, roles = config["daily"], config["satellites"]
    viirs = status["viirs_operating"]
    aqua, terra = (status[f"{satellite_key(config, roles[role])}_operating"] for role in ("modis_afternoon", "modis_single"))
    allowed = (status["date"] <= pd.Timestamp(params["modis_last_valid_date"])) | params["allow_drift_modis"]
    use_pair = quantity == "count" or config["strength"]["frp_modis_source"] == "pair"
    first, first_basis = (aqua & terra, BASIS_PAIR) if use_pair else (aqua, BASIS_AQUA)
    basis = np.select([viirs, allowed & first, allowed & terra, allowed & aqua],
                      [BASIS_VIIRS, first_basis, BASIS_TERRA, BASIS_AQUA], default=BASIS_NONE)
    return pd.Series(basis, index=status.index)


def flag_possible_gaps(daily_sums: pd.DataFrame, status: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Markiert je Satellit Tage, an denen er laut Produktfenster arbeitet, aber auffaellig nichts meldet.

    Auffaellig heisst: 0 Erkennungen im ganzen Gebiet, obwohl der Median der umliegenden Tage
    (Fenster von +-`gap_neighbour_days`) mindestens `gap_min_neighbour_median` betraegt. Das deutet
    auf einen Ausfall hin, den das Dateifenster nicht zeigt. Die Tage werden nur markiert und
    nicht entfernt, weil ein ruhiger Tag mitten in der Saison auch echt sein kann.
    """
    params = config["daily"]
    totals = daily_sums.groupby(["obs_date", "satellite"])["n"].sum().unstack("satellite")
    totals = totals.reindex(status["date"]).fillna(0.0)
    window = 2 * params["gap_neighbour_days"] + 1
    gaps = pd.DataFrame(index=status.index)
    for satellite in config["satellites"]["sensor_of"]:
        counts = totals[satellite].to_numpy() if satellite in totals else np.zeros(len(status))
        median = pd.Series(counts).rolling(window, center=True, min_periods=1).median().to_numpy()
        gaps[satellite] = status[f"{satellite_key(config, satellite)}_operating"].to_numpy() & (counts == 0) & (median >= params["gap_min_neighbour_median"])
    return gaps


def build_day_status(daily_sums: pd.DataFrame, coverage: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Baut die Statustabelle je Tag: Betrieb der Satelliten, Basis je Groesse, Vollstaendigkeit, Vorlaeufigkeit.

    Diese Tabelle ist der Schluessel, um einen Tag ohne Feuer (Satellit in Betrieb, 0 Erkennungen)
    von einem Tag ohne Daten (kein Satellit in Betrieb) zu unterscheiden. In den Punktdaten gibt
    es fuer beide Faelle schlicht keine Zeile.
    `is_provisional` ist wahr, wenn die Basis des Tages aus NRT-Daten stammt, die spaeter durch
    Archivdaten ersetzt werden und sich dabei leicht aendern koennen.
    """
    params, tolerance = config["daily"], config["daily"]["coverage_gap_tolerance_days"]
    status = pd.DataFrame({"date": pd.date_range(params["series_start"], coverage["window_end"].max(), freq="D")})
    nrt_days = {}
    for satellite in config["satellites"]["sensor_of"]:
        status[f"{satellite_key(config, satellite)}_operating"] = status["date"].isin(operating_days_of(coverage, satellite, tolerance))
        nrt_days[satellite] = status["date"].isin(operating_days_of(coverage, satellite, tolerance, source="nrt"))
    status["viirs_operating"] = status[[f"{key}_operating" for key in viirs_keys(config)]].any(axis=1)
    status["basis_count"] = choose_basis_per_day(status, config, "count")
    status["basis_frp"] = choose_basis_per_day(status, config, "frp")
    status["is_complete_day"] = (status["basis_count"] != BASIS_NONE) & (status["basis_frp"] != BASIS_NONE)
    gaps = flag_possible_gaps(daily_sums, status, config)
    provisional, possible_gap = np.zeros(len(status), bool), np.zeros(len(status), bool)
    for basis, satellites in satellites_of_basis(config).items():
        used = ((status["basis_count"] == basis) | (status["basis_frp"] == basis)).to_numpy()
        for satellite in satellites:
            provisional |= used & nrt_days[satellite].to_numpy()
            possible_gap |= used & gaps[satellite].to_numpy()
    return status.assign(is_provisional=provisional, possible_gap=possible_gap)


def build_daily_grid(daily_sums: pd.DataFrame, day_status: pd.DataFrame, config: dict[str, Any], key: str = "region_id") -> pd.DataFrame:
    """Baut das lueckenlose Raster Schluessel x Tag mit Anzahl und FRP je Satellit und der VIIRS-Referenz.

    Drei Faelle werden unterschieden, weil sie Verschiedenes bedeuten:
    - Zahl > 0: es gab Erkennungen.
    - 0: der Satellit lieferte Daten, aber es brannte nichts. Diese Nullen fehlen in den Rohdaten.
    - NA: der Satellit war an dem Tag nicht in Betrieb (z. B. VIIRS vor 2012). Eine 0 waere hier
      falsch und wuerde als feuerfreier Tag gelesen.
    Dazu kommen `n_viirs` und `frp_viirs`, das Mittel der aktiven VIIRS-Satelliten (siehe
    `add_viirs_reference`).
    """
    keys = sorted(daily_sums[key].dropna().unique())
    index = pd.MultiIndex.from_product([keys, day_status["date"]], names=[key, "date"])
    wide = daily_sums.rename(columns={"obs_date": "date"}).pivot_table(index=[key, "date"], columns="satellite",
                                                                     values=["n", "frp"], aggfunc="sum")
    wide.columns = [f"{measure}_{satellite_key(config, satellite)}" for measure, satellite in wide.columns]
    operating = [column for column in day_status.columns if column.endswith("_operating") and column != "viirs_operating"]
    grid = wide.reindex(index).reset_index().merge(day_status[["date", "viirs_operating"] + operating], on="date")
    for column in operating:
        satellite = column.removesuffix("_operating")
        for measure in ("n", "frp"):
            name = f"{measure}_{satellite}"
            values = grid[name] if name in grid else pd.Series(np.nan, index=grid.index)
            grid[name] = values.fillna(0.0).where(grid[column])
    grid = add_viirs_reference(grid, config)
    return grid.sort_values([key, "date"]).reset_index(drop=True)


def add_viirs_reference(table: pd.DataFrame, config: dict[str, Any], keys: list[str] | None = None) -> pd.DataFrame:
    """Ergaenzt `n_viirs` und `frp_viirs`: das Mittel ueber die an diesem Tag aktiven VIIRS-Satelliten.

    Warum das Mittel und nicht die Summe: SNPP, NOAA-20 und NOAA-21 tragen baugleiche Instrumente
    und ueberfliegen Iberien mit etwa 50 Minuten Abstand. Sie sehen dieselben Feuer zu einer
    anderen Uhrzeit, ihre Erkennungen sind keine Doppelte desselben Pixels und lassen sich nicht
    entdoppeln. Eine Summe wuerde die Reihe ab 2018 etwa verdoppeln. Das Mittel bleibt auf dem
    Niveau eines Satelliten (Voranalyse 09: NOAA-20 / SNPP 0,98, NOAA-21 / SNPP 0,94) und damit
    auf dem Niveau der Kalibrierung, und es daempft den Zufall, ob ein einzelner Ueberflug ein
    kleines Feuer gerade trifft (typischer Fehler gegen einen zurueckgehaltenen Satelliten x 2,0
    einzeln, x 1,5 gemittelt).
    Regeln: Ein aktiver Satellit ohne Erkennung zaehlt als 0. Ein nicht aktiver Satellit
    (`<key>_operating` falsch oder Wert leer) zaehlt nicht mit. Ist keiner aktiv, bleibt der Wert leer.
    `keys` waehlt andere Satelliten als alle VIIRS-Satelliten (die Kalibrierung nutzt nur SNPP).
    """
    result = table.copy()
    for measure in ("n", "frp"):
        parts = [result[f"{measure}_{key}"].where(result[f"{key}_operating"]) if f"{key}_operating" in result else result[f"{measure}_{key}"]
                 for key in (keys or viirs_keys(config))]
        result[f"{measure}_viirs"] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    return result
