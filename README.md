# Hut ab! – Pilzprognose Berlin/Brandenburg

Web-App, die für **morgen** zeigt, wo rund um Berlin die Bedingungen für die 10 beliebtesten Speisepilze
am günstigsten sind – aus Bodenfeuchte (UFZ-Dürremonitor), Regen und Temperatur (Open-Meteo),
Baumarten (Thünen-Institut), Boden-pH (SoilGrids) und Schutzgebieten (LfU Brandenburg).
Methode und Quellen: [docs/MODELL.md](docs/MODELL.md).

## Aufbau
```
web/                  statische App (Leaflet), wird auf GitHub Pages veröffentlicht
  index.html, app.js, style.css
  img/arten/          Artbilder (Wikimedia Commons, Lizenzen in credits.json)
  data/               täglich erzeugt (nicht im Git)
data/
  arten.json          Steckbriefe der 10 Arten (Partnerbäume, pH, Saison, Temperatur)
  modell.json         Modellparameter mit Belegen
  static/             statische Rasterebenen (im Git, selten neu erzeugen)
  daily/              tägliche Rohdaten (nicht im Git)
scripts/
  grid.py             gemeinsames Analyse-Raster (Web-Mercator, 300 m ≈ 180 m am Boden)
  fetch_forest.py     Waldmaske + Baumartenanteile (Thünen-WCS)          ┐ statisch
  fetch_static.py     Boden-pH (SoilGrids), Schutzgebiete (LfU-WFS), Orte ┘ (requirements-static.txt)
  fetch_images.py     Artbilder von Wikimedia Commons
  fetch_ufz.py        UFZ-Dürremonitor-PNGs → GeoJSON                    ┐
  fetch_weather.py    Open-Meteo: 31 Tage Rückblick + 3 Tage Prognose    │ täglich
  build_daily.py      Score je Art + Top-10-Sammelstellen → web/data/    ┘
```

## Lokal ausführen
```bash
python -m pip install -r requirements.txt
python scripts/fetch_ufz.py && python scripts/fetch_weather.py && python scripts/build_daily.py
python -m http.server 8765 --directory web
```
Dann http://localhost:8765 öffnen.

## Tägliches Update
`.github/workflows/daily.yml` läuft täglich um 11:40 UTC (nach dem UFZ-Update), rechnet die Prognose
für den Folgetag und veröffentlicht `web/` auf GitHub Pages. Einmalig nötig: im Repository unter
*Settings → Pages → Build and deployment* als Quelle **GitHub Actions** wählen.

## Hinweise
- Keine Pilzbestimmung! Funde im Zweifel von DGfM-Pilzsachverständigen prüfen lassen.
- Schutzgebiete beachten. Berliner Schutzgebiete sind noch nicht eingebunden.
- Der Ordner `output/` und `scripts/geo.py`, `build.py` stammen aus der ersten Auswertung (Schorfheide, 10.10.2026).

Daten: UFZ-Dürremonitor · Thünen-Institut · ISRIC SoilGrids (CC BY 4.0) · LfU Brandenburg (dl-de/by-2-0) ·
Open-Meteo (CC BY 4.0) · GeoNames (CC BY 4.0) · © OpenStreetMap-Mitwirkende · Wikimedia Commons.
