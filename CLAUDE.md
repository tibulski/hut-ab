# Hut ab! (Pilz-App Berlin/Brandenburg) – Projektkontext für Claude Code

## Ziel
Eine App, die anzeigt, wo rund um Berlin die Chancen auf Pilze am besten sind –
auf Basis von Bodenfeuchte (UFZ-Dürremonitor) und Niederschlag. Die Daten
sollen automatisch (z. B. täglich) aktualisiert werden.

## Was es schon gibt (Ergebnis einer Cowork-Sitzung vom 11./12.10.2026)
- `output/Pilzkarte_Schorfheide_Chorin.html` – Leaflet-Karte (OSM-Kacheln) mit Raster-Overlay
- `output/Pilzkarte_Schorfheide_Chorin.png` – statische Vorschau (matplotlib)
- `data/ufz_grid_2026-10-10_rle.txt` – ausgelesenes Raster (Ausschnitt Barnim/Uckermark), lauflängenkodiert
- `data/mapdata.json` – daraus erzeugte Rechtecke je Klasse + Orte + Spots
- `data/niederschlag_2026-10-11.csv` – Regensummen (Open-Meteo) für Waldgebiete
- `scripts/geo.py` – Dekodierung + Georeferenzierung, Cluster-Analyse (`python3 geo.py`)
- `scripts/build.py` – erzeugt `data/mapdata.json`
- `scripts/extract_in_browser.js` – so wurden die Pixel ausgelesen (lief im Browser, weil die Sandbox ufz.de nicht erreichte)

## Datenquellen
UFZ-Dürremonitor: https://www.ufz.de/index.php?de=37937
Bundeslandkarten Berlin/Brandenburg (PNG 1202×1025, täglich aktualisiert, Datum oben links im Bild):
- Oberboden-Dürre (0–25 cm, Perzentil-Klassen): https://files.ufz.de/~drought/SM_0_25cm_dry-wet_aktuell_BE-BB.png
- Pflanzenverfügbares Wasser Oberboden (%nFK): https://files.ufz.de/~drought/PAW_0_25cm_dry-wet_aktuell_BE-BB.png
- Gesamtboden (bis ~1,8 m): https://files.ufz.de/~drought/SM_Lall_dry-wet_aktuell_BE-BB.png
- Auch als PDF unter gleichem Namen mit `.pdf`. Andere Länder: Kürzel NRW, HE, BW, BY, MV, SN, ST, TH, SH-HH, NI-HB, RP-SL.
- Hinweis: Rohdaten (NetCDF/GeoTIFF) wären besser als Pixel-Auslesen – prüfen, ob UFZ diese anbietet (Kontakt laut Seite: Dr. Andreas Marx).

Niederschlag: Open-Meteo, z. B.
`https://api.open-meteo.com/v1/forecast?latitude=52.90&longitude=13.55&daily=precipitation_sum&past_days=31&forecast_days=7&timezone=Europe%2FBerlin`
(mehrere Punkte: Komma-getrennte latitude/longitude-Listen). Alternative: DWD Open Data (RADOLAN).

## Farbcodes (exakte RGB-Werte in den PNGs)
Oberboden-Dürre (SM_0_25cm):
| RGB | Klasse |
|---|---|
| 255,255,255 | keine Dürre (innerhalb der Landesgrenze; außerhalb = Hintergrund!) |
| 255,255,0 | ungewöhnlich trocken |
| 252,211,127 | moderate Dürre |
| 255,170,0 | schwere Dürre |
| 230,0,0 | extreme Dürre |
| 115,0,0 | außergewöhnliche Dürre |

Pflanzenverfügbares Wasser (PAW_0_25cm), Klassen à 10 %nFK:
| RGB | %nFK |
|---|---|
| 240,59,32 | 0–10 |
| 255,170,1 | 10–20 |
| 255,233,168 | 20–30 |
| 252,255,234 | 30–40 |
| 240,249,232 | 40–50 |
| 211,239,202 | 50–60 |
| 145,215,198 | 60–70 |
| 128,128,128 | keine Daten (Berlin/Siedlung) |
(<30 %nFK = Trockenstress, <50 % = beginnender Trockenstress. Höhere Klassen ggf. blau – Legende: https://www.ufz.de/export/data/2/237846_LegendeNFK.png)

Schwarz/Grau-Töne = Grenzlinien, Achsen, Beschriftung → ignorieren bzw. Nachbarpixel nehmen.

## Georeferenzierung (BE-BB-Bilder, 1202×1025 px)
- Kartenrahmen: x = 142.5 px (11° O) bis 1147.5 px (15° O) → 251,25 px/°, linear.
- y ist **Mercator**. Tick-Positionen: 53,5° N → 55,5 px; 53,0 → 264,5; 52,5 → 471,5; 52,0 → 676,5; 51,5 → 878,5.
  Fit: y = a + b·merc(lat), merc(φ) = deg(ln tan(π/4 + φ/2)) – siehe `scripts/geo.py`.
- Modellraster ≈ 4 px ≈ 1,1 km. Lagegenauigkeit der Auswertung ca. ±1 km.
- Plausibilitätscheck: Oder-Grenze bei 52,87° N lag bei ~14,16° O (passt).

## Bewertungslogik (bisher)
- Beste Flächen: Oberboden „keine Dürre“ UND ≥ 50 %nFK (Code `G` im Raster)
- Gut: „keine Dürre“ (`W`); „ungewöhnlich trocken“ aber ≥ 50 %nFK (`H`)
- Rest: Y/L/O/R/D wie Dürreklassen, `J` = Dürre aber ≥ 50 %nFK, `_` = außerhalb, `.` = Linie
- Faustregel Pilzwachstum: ~50 l/m² Regen durchfeuchten den Waldboden, Fruchtkörper ca. 14 Tage später.
  Ideen für einen Score: Niederschlag 14–30 Tage zurück, nFK Oberboden, Temperatur (nachts > ~5 °C), Waldtyp.

## Ergebnis 10.10.2026 (Ausschnitt Schorfheide/Chorin)
1. Westliche Schorfheide um Groß Schönebeck: ~140 km² ohne Dürre + ≥ 50 %nFK (52,86–52,98° N, 13,46–13,70° O)
2. Chorin – Parsteiner See – südl. Angermünde: ~90 km² ohne Dürre (40–50 %nFK); Grumsin = UNESCO-Kernzone (Betretungsverbot)
3. Kleine Insel südl. Joachimsthal; 4. nördl. Groß Schönebeck: ungewöhnlich trocken, aber ≥ 50 %nFK
Regen letzte 30 Tage in der Region nur ~19–31 l/m², Prognose bis ~26.10. überwiegend trocken.

## Wichtige Hinweise für die App
- Schutzgebiete berücksichtigen: Kernzonen/NSG (Sammel- bzw. Betretungsverbote). Geodaten z. B. vom LfU Brandenburg / BfN (WFS) einbinden.
- Disclaimer: keine Pilzbestimmung, Verweis auf Pilzsachverständige (DGfM).
- OSM-Kacheln: Nutzungsrichtlinien beachten (Attribution, kein Massenabruf).

## Vorschlag nächste Schritte
1. Skript, das die beiden PNGs herunterlädt, Datum prüft und das ganze Land (nicht nur den Ausschnitt) klassifiziert → GeoJSON.
2. Niederschlag per Open-Meteo für ein Punktraster dazu.
3. Web-App (z. B. Leaflet/MapLibre, statisch gehostet) mit täglichem Update (GitHub Action/Cron).
