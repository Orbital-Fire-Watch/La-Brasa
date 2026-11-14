# Design-Mock „La Brasa“

Eigenständiger Design-Mock. Grundlage sind die Prompts [PROMPT.md](PROMPT.md) (Spezifikation 1) und
[PROMPT-2.md](PROMPT-2.md) (zurück zum ganzen Land, weniger KI-Look, Sprachen, Logo).
**Am bestehenden Frontend wurde nichts geändert**, alles liegt in diesem Ordner.

## Starten

```bash
cd frontend
npm install            # einmalig
npm run dev
# Startseite:  http://localhost:5173/design-mock/
# Auswertung:  http://localhost:5173/design-mock/?page=analysis
# Infoseite:   http://localhost:5173/design-mock/info.html
```

Daten: dieselbe Quelle wie die App (`services/api/fireApi.ts`). Standard ist die Mock-API im Browser,
mit `VITE_API_MODE=live` das echte Backend (siehe `frontend/README.md`).

## Logo

`assets/la-brasa-logo.svg`: Globus aus dem Spezifikations-Logo (KI-generiert), neuer Metallring mit „LA BRASA“
und unten klein „AI GENERATED“. Ein anderes Logo lässt sich mit `VITE_LOGO_URL=/pfad/zum/logo.svg` übergeben
(`src/config.ts`).

## Sprachen

English, Español, Português (Portugal); Auswahl oben rechts, gespeichert pro Browser, Startwert aus der
Browsersprache. Die Infoseite folgt derselben Einstellung.

**Weitere Sprache hinzufügen** (z. B. Französisch):
1. `src/i18n/messages/fr.ts` anlegen: `export const fr: Messages = { … }` mit allen Schlüsseln aus `en.ts`
   (fehlende Schlüssel meldet der Typecheck; für einen Entwurf `Partial<Messages>` verwenden, dann gilt Englisch).
2. In `src/i18n/locales.ts` eine Zeile ergänzen: `fr: { name: "Français", intl: "fr-FR", dir: "ltr", messages: fr }`.
3. Für die Infoseite einen `data-lang="fr"`-Block in `info.html` ergänzen.

Zahlen, Daten, Monatsnamen, Ländernamen, „gestern/vor 3 Tagen“ und Pluralformen kommen aus `Intl` und
brauchen keine eigene Übersetzung. Details und Grenzen bei 25+ Sprachen: [PROMPT-2.md](PROMPT-2.md), Abschnitt 3.

## Prüfen

```bash
npx tsc -p design-mock/tsconfig.json   # Typecheck nur des Mocks (inkl. Vollständigkeit der Übersetzungen)
npx eslint design-mock                  # Lint (läuft auch in `npm run lint` mit)
```

## Bekannte Grenzen

- **Diagramme auf der Auswertungsseite** (`SeasonChart`, `YearHeatmap`, `RingCalendar`) werden aus
  `components/charts/` wiederverwendet und zeigen intern weiter **deutsche Texte** (Monatsnamen, „Jahr vergleichen“,
  „Feld anklicken …“). Übersetzen geht nur über Änderungen an diesen Komponenten, die hier ausgeschlossen waren.
- Regionsnamen kommen aus der API (amtliche Namen, z. B. „Andalucía“) und werden nicht übersetzt;
  Ländernamen schon.
- Kartenbeschriftungen der Hintergrundkarte (OpenFreeMap) folgen nicht der gewählten Sprache.
- Das Datumsfeld zeigt das Format der Browser-Sprache (natives `<input type="date">`).
- Der Koordinaten-Dialog der App ist nicht enthalten. Der Mock wird von `npm run build` nicht mitgebaut.
