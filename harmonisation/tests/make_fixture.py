"""Erzeugt den kleinen Test-Ausschnitt aus den echten CSVs (jede n-te Zeile, fest und wiederholbar).

Aufruf: .venv/bin/python tests/make_fixture.py
Die Ausschnitte liegen in tests/fixtures/ und machen die Tests unabhaengig von den grossen Dateien.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import load_config  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
EVERY_NTH_ROW = {"archive": 150, "nrt": 5}


def write_sampled_csv(source_csv: Path, target_csv: Path, every_nth: int) -> int:
    """Schreibt die Kopfzeile und jede n-te Datenzeile. Gibt die Zahl der Datenzeilen zurueck."""
    lines = source_csv.read_text(encoding="utf-8").splitlines()
    sampled = lines[1::every_nth]
    target_csv.write_text("\n".join([lines[0]] + sampled) + "\n", encoding="utf-8")
    return len(sampled)


def main() -> None:
    """Erzeugt je Quelle der Konfiguration einen Ausschnitt."""
    FIXTURE_DIR.mkdir(exist_ok=True)
    for source in load_config()["sources"]:
        rows = write_sampled_csv(Path(source["csv"]), FIXTURE_DIR / f"{source['name']}.csv", EVERY_NTH_ROW[source["source"]])
        print(source["name"], rows, "Zeilen")


if __name__ == "__main__":
    main()
