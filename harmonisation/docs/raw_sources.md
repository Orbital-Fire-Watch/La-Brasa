# Rohdaten (FIRMS-Downloads)

Die CSVs liegen in `La-Brasa/data/raw/` (nicht in Git), ein Unterordner je FIRMS-Produkt, Original-Dateinamen.
Die Pipeline liest sie über `sources` in `pipeline_config.yaml`. Die SHA-256-Werte jedes Laufs stehen zusätzlich in
`data/harmonised/manifest.json` (`input_files`). Stand: 14.11.2026.

| Ordner | FIRMS-Produkt | Satellit (`satellite`) | Datei | Zeitraum | Zeilen | SHA-256 |
|---|---|---|---|---|---|---|
| `modis/` | `DL_FIRE_M-C61_845369` (MODIS C6.1) | Terra, Aqua | `fire_archive_M-C61_845369.csv` | 2000-11-01 bis 2026-08-31 | 200.966 | `9389fbdafb8364a0d69f16910cff354d9fb51998b39583474b572e5e69ac802a` |
| `modis/` | | | `fire_nrt_M-C61_845369.csv` | 2026-09-01 bis 2026-11-12 | 1.201 | `3952543f700eb4dbeac612bec6bddded50f1ae3c22b99091fb71d22442afa619` |
| `viirs_snpp/` | `DL_FIRE_SV-C2_845370` (VIIRS C2) | SNPP | `fire_archive_SV-C2_845370.csv` | 2012-01-20 bis 2026-07-31 | 362.619 | `fcf96294e8c3aaa8c64e58b0351fae37bde0a12db3946a41e7ba830f5c14c4c0` |
| `viirs_snpp/` | | | `fire_nrt_SV-C2_845370.csv` | 2026-08-01 bis 2026-11-02 | 8.676 | `50114a0ac2832c3e5b9ca7eeb5635ab5fe19356c0efce555f407e3abf9e4f77e` |
| `viirs_noaa20/` | `DL_FIRE_J1V-C2_848091` (VIIRS C2) | N20 (NOAA-20) | `fire_archive_J1V-C2_848091.csv` | 2018-04-01 bis 2026-07-31 | 238.511 | `43e5b41cad9d4b0dc86f293d9d9aef4611eb4a7a232faa40b7d9d3f08c7f82b7` |
| `viirs_noaa20/` | | | `fire_nrt_J1V-C2_848091.csv` | 2026-08-01 bis 2026-11-13 | 10.938 | `500a69c2a8ef12498b1cabbcefce6af5fd20f677bea508ff42b27de23be81772` |
| `viirs_noaa21/` | `DL_FIRE_J2V-C2_848092` (VIIRS C2) | N21 (NOAA-21) | `fire_archive_J2V-C2_848092.csv` | 2023-03-01 bis 2026-07-31 | 107.197 | `21b51bfdfd9b730e6b7d69912b657c067ac9ccef4e067dd08501515557722d74` |
| `viirs_noaa21/` | | | `fire_nrt_J2V-C2_848092.csv` | 2026-08-01 bis 2026-11-13 | 10.185 | `617c63cb3717893a25eb52344f417191649fd9a9bd98557c43229929e211951a` |

## Herkunft und Download

- Quelle: NASA FIRMS, Archiv-Download (https://firms.modaps.eosdis.nasa.gov/download/), Format CSV.
  Erklärung der Spalten: https://firms.modaps.eosdis.nasa.gov/download/Readme.txt
- MODIS und SNPP: Download vom 13.11.2026 (Zeitstempel in den ZIPs 18:21 bzw. 18:24). Gebiet: Iberien mit einem Rand
  in Südwestfrankreich, **kein Rechteck** (in Frankreich nördlich von etwa 43,5° keine Daten).
- NOAA-20 und NOAA-21: Download vom 14.11.2026 (Zeitstempel 13:34). Gebiet: Rechteck bis 44,8° N und 4,9° O, also
  größer als MODIS/SNPP. Die Pipeline beschränkt alle Satelliten auf das gemeinsame Gebiet (`common_area` in der Config,
  `pipeline/data_loading/common_area.py`). Dabei fallen 52.941 NOAA-Zeilen mit Grund `outside_common_area` heraus.
- Originale und ZIPs: `Daten_Satellit/NASA_SPACEAPP/Data_implemented/` (MODIS, SNPP) und `Data_new/` (NOAA-20/21).
  Die CSVs in `data/raw/` sind Kopien. Sie stimmen Byte für Byte mit den ZIPs überein (SHA-256 geprüft).

## Bekannte Abweichungen

- **SNPP-Archiv:** Die entpackte CSV in `Data_implemented/DL_FIRE_SV-C2_845370/` enthält in Zeile 362617 eingefügten Text
  in `track` (`0.https://firms…zip77` statt `0.77`). In `data/raw/viirs_snpp/` liegt deshalb die Fassung aus dem ZIP
  (`DL_FIRE_SV-C2_845370.zip`), die korrekt ist. Die Pipeline würde eine solche Zeile sonst als `invalid_value` verwerfen.
- **Erster NOAA-Download** (`DL_FIRE_J1V-C2_847834`, `DL_FIRE_J2V-C2_847835`, jetzt in `Data_new_false/`): Er deckte den
  Nordosten nicht ab (Katalonien nur 44 % der SNPP-Erkennungen, Midi-Pyrénées und Aquitaine fast keine). Er wird nicht verwendet.
- **NRT-Ende:** SNPP-NRT endet am 02.11.2026, NOAA-20/21-NRT am 13.11.2026, MODIS-NRT am 12.11.2026. Die Tage 03. bis 13.11.
  sind damit nur von NOAA-20/21 gemessen.

## Neue Daten einspielen

1. Neues FIRMS-Produkt in einen eigenen Unterordner von `data/raw/` legen, Dateinamen nicht ändern.
2. `sources` in `pipeline_config.yaml` anpassen. Für einen weiteren VIIRS-Satelliten zusätzlich `satellites.sensor_of`,
   `satellites.column_key` und `satellites.viirs` ergänzen und den Spaltenkatalog um seine Rohspalten erweitern.
3. Download-Gebiet prüfen: Es muss das gemeinsame Gebiet mindestens abdecken (KPI N1c zeigt fehlende Abdeckung je Region).
4. `run_pipeline.py --force`, danach diese Tabelle aktualisieren.
