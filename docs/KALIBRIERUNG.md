# Kalibrierung mit Fundmeldungen

Erstellt 2026-10-13 mit `scripts/calibrate_gbif.py`. Daten: GBIF-Beobachtungen 2019–2025 im Analysegebiet (iNaturalist, naturgucker, Observation.org u. a.), Wetter: ERA5 (Open-Meteo-Archiv), 0,5°-Zellen.

**Lesart:** Die Kurven sind Verhältnisse „Anteil der Funde / Anteil der Hintergrundtage“ (normiert auf 1). Sie zeigen, bei welchen Bedingungen Funde *überproportional* gemeldet werden. Es sind keine Ertragsdaten.

## Saison (Funde je Monat ÷ alle Pilzmeldungen je Monat, normiert)

| Art | n | Mai | Jun | Jul | Aug | Sep | Okt | Nov | Dez |
|---|---|---|---|---|---|---|---|---|---|
| Steinpilz | 370 | 0.00 | 0.05 | 0.19 | 0.56 | 1.00 | 0.78 | 0.26 | 0.03 |
| Maronenröhrling | 477 | 0.02 | 0.00 | 0.07 | 0.32 | 0.90 | 1.00 | 0.84 | 0.19 |
| Pfifferling | 149 | 0.00 | 0.56 | 0.95 | 1.00 | 0.73 | 0.41 | 0.17 | 0.27 |
| Birkenpilz | 108 | 0.06 | 0.00 | 0.30 | 0.43 | 1.00 | 0.63 | 0.39 | 0.00 |
| Rotkappe | 26 | 0.00 | 0.00 | 0.00 | 0.73 | 1.00 | 0.78 | 0.00 | 0.00 |
| Butterpilz | 287 | 0.00 | 0.02 | 0.07 | 0.25 | 0.82 | 1.00 | 0.75 | 0.07 |
| Krause Glucke | 249 | 0.00 | 0.00 | 0.02 | 0.23 | 1.00 | 0.64 | 0.21 | 0.21 |
| Parasol | 601 | 0.01 | 0.25 | 0.38 | 0.50 | 1.00 | 0.70 | 0.28 | 0.03 |
| Hallimasch | 172 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 1.00 | 0.96 | 0.17 |
| Edelreizker | 121 | 0.00 | 0.00 | 0.00 | 0.15 | 0.65 | 1.00 | 0.82 | 0.06 |

## Temperatur (20-Tage-Mittel vor dem Fund)

| Art | Funde mit Wetter | Median T20 der Funde | Optimum (Gauss-Fit) | Breite σ | bisher (Experte) |
|---|---|---|---|---|---|
| Steinpilz | 368 | 14.3 °C | 13.0 °C | 3.25 | 13 °C |
| Maronenröhrling | 463 | 11.9 °C | 11.25 °C | 2.5 | 12 °C |
| Pfifferling | 141 | 17.1 °C | 15.0 °C | 5.0 | 15 °C |
| Birkenpilz | 107 | 14.1 °C | 12.5 °C | 4.0 | 13 °C |
| Rotkappe | 26 | 16.7 °C |  |  | 13 °C |
| Butterpilz | 282 | 11.9 °C | 11.25 °C | 2.75 | 11 °C |
| Krause Glucke | 235 | 14.3 °C | 13.0 °C | 3.75 | 13 °C |
| Parasol | 597 | 14.7 °C | 12.75 °C | 4.25 | 15 °C |
| Hallimasch | 166 | 11.5 °C | 10.75 °C | 2.75 | 11 °C |
| Edelreizker | 119 | 11.6 °C | 10.75 °C | 2.25 | 11 °C |

## Wasserbilanz (Regen − ET0, 26 Tage vor dem Fund), alle Arten

| KWB-Klasse (mm) | relative Funddichte | Funde |
|---|---|---|
| -140 … -100 | 0.01 | 4 |
| -100 … -70 | 0.02 | 23 |
| -70 … -50 | 0.1 | 109 |
| -50 … -35 | 0.21 | 119 |
| -35 … -20 | 0.54 | 305 |
| -20 … -10 | 0.69 | 342 |
| -10 … 0 | 0.74 | 361 |
| 0 … 10 | 0.74 | 282 |
| 10 … 25 | 0.69 | 388 |
| 25 … 45 | 0.56 | 316 |
| 45 … 70 | 0.74 | 204 |
| 70 … 120 | 1.0 | 51 |
| 120 … 300 |  | 0 |

Grenzen: Presence-only-Daten mit Beobachtungsverzerrung (Wochenenden, Stadtnähe, Wege); Funddatum ≠ Erscheinungsdatum; Rotkappe hat nur wenige Funde.
