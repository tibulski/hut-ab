# Hut ab! – Prognosemodell und Belege

Stand: 12.10.2026. Parameter: [`data/modell.json`](../data/modell.json), Artsteckbriefe: [`data/arten.json`](../data/arten.json),
Umsetzung: [`scripts/build_daily.py`](../scripts/build_daily.py).

Der Score (0–100) beschreibt, wie **günstig die Bedingungen morgen** für Fruchtkörper einer Art in einer
ca. 180 × 180 m großen Rasterzelle sind. Er sagt nicht, dass dort Pilze stehen. Auch das operative
Vorbild, die tschechische Pilzprognose des ČHMÚ, liegt lokal oft daneben.

## Formel

```
Score = 100 · Saison · Wirt · pH · Wetter
Wetter = R^0,35 · B^0,25 · T^0,30 · X^0,10 · Frost
```

Das Wetter ist ein **gewichtetes geometrisches Mittel**. Ein einzelner limitierender Faktor, etwa Dürre
oder fehlender Regen, drückt den Score deshalb stark, wie bei einem Minimumfaktor. Jeder Faktor wird
vorher auf mindestens 0,03 begrenzt.

| Faktor | Form | Parameter | Beleg | Evidenz |
|---|---|---|---|---|
| **R Regen** | Rampe auf der Regensumme der Tage t−26 … t−1; Regen der letzten 4 Tage zählt halb. Dazu ein Regentage-Faktor min(1, n/8)^0,3 | 0 bei ≤ 25 l/m², 1 ab 80 l/m² (≈ 1–3 mm/Tag) | Brejon Lamartinière & Hoffman 2025: 26-Tage-Fenster, 2–4 mm/Tag, linear, Steinpilz bei Bielefeld. Karavani et al. 2018: 1 Monat Verzug, Zahl der Regentage besser als Summe. Salerni et al. 2002: 30 Tage. ČHMÚ: 30 Tage | mittel |
| **B Bodenwasser** | Rampe auf UFZ-%nFK 0–25 cm (Klassenmitte); ab „schwere Dürre“ ×0,5. Ohne nFK-Daten (Berlin): Wert je Dürreklasse | 0 bei ≤ 30 %nFK, 1 ab 60 %nFK | Karavani et al. 2018: Bodenfeuchte erklärt das Vorkommen (AUC 0,93 gegenüber 0,90). Ágreda et al. 2015: Wasserbilanz. Schwellen folgen den UFZ-Trockenstressklassen | mittel (Schwellen: Experte) |
| **T Temperatur** | Gauß-Kurve auf dem 20-Tage-Mittel (t−19 … t, inkl. Prognose) | σ = 3,5 °C; Optimum Steinpilz 13 °C, übrige Arten ±2 °C (siehe unten) | Brejon Lamartinière & Hoffman 2025: Optimum ≈ 13 °C, meiste Funde bei 10–15 °C. Karavani et al. 2018: Temperatur begrenzt die Saison an beiden Enden | Steinpilz mittel, übrige Arten Experte |
| **X Hitze** | 1 − 0,15 · Hitzetage (Tmax ≥ 28 °C in 7 Tagen), mindestens 0,3 | | Karavani et al. 2018: hohe Tmax im Sep/Okt wirken negativ | schwach |
| **Frost** | ×0,5 nach einer Nacht ≤ −2 °C in 10 Tagen, ×0,1 ab drei solchen Nächten | | Expertenwissen; Karavani et al. 2018: niedrige Tmin begrenzen die Spätsaison | schwach |
| **Saison** | Monatsgewicht 0–1 je Art | `arten.json` → `monate` | Pilzführer. Das ČHMÚ-Modell nutzt ebenfalls einen Saisonkoeffizienten | Experte → mit GBIF kalibrieren |
| **Wirt** | Σ Baumartenanteil × Wirtsgewicht; 50 % passende Bäume in der Zelle ergeben den vollen Wert. Parasol (Zersetzer): maximal bei ca. 50 % Wald (Waldrand/Lichtung) | Thünen-Baumartenkarte | Artsteckbriefe (Mykorrhizapartner). Obligate Partner: Birkenpilz → Birke, Butterpilz/Edelreizker → Kiefer | gut (Partnerbäume), Gewichte Experte |
| **pH** | Trapez um das pH-Optimum der Art, Untergrenze 0,2, mit Artgewicht abgeschwächt | SoilGrids pH(H₂O) 0–15 cm | Pilzführer. Taye et al. 2016: saurer Boden erhöht *Lactarius*-Erträge (Spanien) – deshalb Edelreizker-pH-Gewicht nur 0,5 | schwach |
| **Schutz** | Kernzonen = Score 0. NSG werden in der Karte angezeigt, aber nicht als Sammelstelle vorgeschlagen | LfU Brandenburg | rechtlich, nicht ökologisch | – |

### Temperatur-Optima (20-Tage-Mittel)
Steinpilz 13 °C (belegt) · Marone 12 · Pfifferling 15 · Birkenpilz 13 · Rotkappe 13 · Butterpilz 11 ·
Krause Glucke 13 · Parasol 15 · Hallimasch 11 · Edelreizker 11 (alle außer Steinpilz: Expertenschätzung,
Verschiebung um ±2 °C nach Hauptsaison).

## Sammelstellen („Top 10 für morgen“)
Zellen mit Score ≥ max(15; 97. Perzentil), mit Lebensraum und ohne Schutzgebiet, werden zu
zusammenhängenden Flächen gruppiert. Die Rangfolge ergibt sich aus mittlerem Score × (1 + log₁₀ Zellenzahl),
mindestens 3 Zellen (≈ 10 ha), mindestens 4 km Abstand zwischen zwei Sammelstellen. Die Ortsangabe nennt den
nächsten GeoNames-Ort.

## Wichtige Einschränkungen
1. Die einzige tagesgenau aufgelöste deutsche Studie (Bielefeld, Steinpilz unter Buche) ist ein **nicht
   begutachteter Preprint**. Die meisten quantitativen Ertragsmodelle stammen aus Spanien (Kiefer, Monatswerte).
   Dass sie auf Brandenburger Kiefernforste auf Sand übertragbar sind, ist plausibel, aber nicht geprüft.
2. Für Frost, einen Kälteauslöser und pilzspezifische nFK-Schwellen gibt es keine publizierten Zahlen.
3. Die Temperaturreaktionen der einzelnen Arten sind kaum untersucht und uneinheitlich (Andrew et al. 2018).
4. SoilGrids-pH ist modelliert (250 m) und überschätzt Waldoberböden auf Sand vermutlich.
5. UFZ-Werte stammen aus PNG-Pixeln (±1 km). Die Bodenfeuchte ist der Vortageswert, keine Prognose.
6. **Bestandesalter, Grundfläche/Kronenschluss und Stickstoffeintrag** sind noch nicht enthalten, obwohl sie belegt
   wirken (siehe unten).

## Nächste Ausbaustufen (belegt, mit offenen Datenquellen)
| Faktor | Beleg | mögliche Datenquelle |
|---|---|---|
| Kronenschluss/Grundfläche: Optimum 30–40 m²/ha | Sánchez-González et al. 2019 | Copernicus HRL Tree Cover Density (10 m); Kronenhöhe (ETH Global Canopy Height, Lang et al. 2023, noch nicht geprüft) als Ersatzgröße |
| Bestandesalter: Butterpilz in jungen Kiefern, Krause Glucke an alten | Ortega-Martínez et al. 2011; Tahvanainen et al. 2016; Taye et al. 2016 | Kronenhöhe als Altersersatz |
| Stickstoffeintrag schadet Mykorrhizapilzen, besonders Pfifferling | Arnolds 1991; van Strien et al. 2018; Lilleskov et al. 2002 | UBA-Depositionskarten (PINETI) |
| Artspezifische pH- und N-Zeigerwerte | Simmel, Bässler & Poschlod 2017 (≈ 650 Arten) | Tabelle aus dem Paper |
| Bodenfeuchte-Prognose statt Vortageswert | Karavani et al. 2018 | Open-Meteo `soil_moisture_3_to_9cm` (stündlich) |
| Kalibrierung Saison/Optima | – | GBIF-Funde (iNaturalist, naturgucker, Observation.org): Fundtage 2015–2025 gegen den Tages-Score |

## Quellen
Die Angaben wurden per Literaturrecherche geprüft (DOI bzw. Datenbankeintrag). Bei den mit * markierten Arbeiten
wurde nur das Abstract oder der Datenbankeintrag gelesen.

- Ágreda T et al. (2015) *Glob. Change Biol.* 21:3499–3510. doi:10.1111/gcb.12960 *
- Alday JG et al. (2017a) *Fungal Ecol.* 26:144–146. doi:10.1016/j.funeco.2017.01.004
- Alday JG et al. (2017b) *Sci. Rep.* 7:45824. doi:10.1038/srep45824
- Andrew C et al. (2018) *Ecology* 99:1306–1315. doi:10.1002/ecy.2237
- Arnolds E (1991) Decline of ectomycorrhizal fungi in Europe. *Agric. Ecosyst. Environ.* 35:209–244 *
- Blickensdörfer L, Oehmichen K, Pflugmacher D, Kleinschmit B, Hostert P (2022) Dominant Tree Species for Germany (2017/2018). Thünen-Atlas, https://atlas.thuenen.de/catalogue/uuid/3810c144-756b-11ed-a6bf-0242ac120008
- Boddy L et al. (2014) *Fungal Ecol.* 10:20–33. doi:10.1016/j.funeco.2013.10.006 *
- Bonet JA et al. (2012) *For. Ecol. Manage.* 265:211–217. doi:10.1016/j.foreco.2011.10.039 *
- Brejon Lamartinière E, Hoffman J (2025) *bioRxiv* (Preprint, **nicht begutachtet**), doi:10.64898/2025.12.12.693895
- Büntgen U et al. (2013) *Glob. Change Biol.* 19:2785–2794. doi:10.1111/gcb.12263
- Collado E et al. (2019) *Sci. Total Environ.* 689:602–615. doi:10.1016/j.scitotenv.2019.06.471
- Karavani A et al. (2018) *Agric. For. Meteorol.* 248:432–440. doi:10.1016/j.agrformet.2017.10.024
- Kauserud H et al. (2008) *PNAS* 105:3811. doi:10.1073/pnas.0709037105
- Kauserud H et al. (2012) *PNAS* 109:14488. doi:10.1073/pnas.1200789109
- Krebs CJ, Carrier P, Boutin S, Boonstra R, Hofer E (2008) Mushroom crops in relation to weather in the southwestern Yukon. *Botany* 86:1497–1502
- Lilleskov EA et al. (2002) *Ecology* 83:104–115 *
- Martínez de Aragón J et al. (2007) *For. Ecol. Manage.* 252:239–256. doi:10.1016/j.foreco.2007.06.040
- Ortega-Martínez P et al. (2011) *Mycorrhiza* 21:65–70. doi:10.1007/s00572-010-0320-8
- Salerni E et al. (2002) *Israel J. Plant Sci.* 50:189–198 *
- Sánchez-González M et al. (2019) *For. Ecosyst.* 6:52. doi:10.1186/s40663-019-0211-1
- Sato H, Morimoto S, Hattori T (2012) *PLoS ONE* 7:e49777. doi:10.1371/journal.pone.0049777
- Simmel J, Bässler C, Poschlod P (2017) *Fungal Ecol.* 27:202–212. doi:10.1016/j.funeco.2016.09.004 (Artentabelle noch nicht ausgewertet)
- Tahvanainen V et al. (2016) *For. Ecol. Manage.* 362:79–88. doi:10.1016/j.foreco.2015.11.040 *
- Taye ZM et al. (2016) *Fungal Ecol.* 23:30–41. doi:10.1016/j.funeco.2016.05.008 *
- van Strien AJ et al. (2018) *J. Appl. Ecol.* 55:290–298. doi:10.1111/1365-2664.12944
- ČHMÚ – Pilzprognose (Tschechien), https://info.chmi.cz/bio. Eingangsgrößen laut Presseberichten: Bodensättigung aus 30 Tagen Niederschlag, 7-Tage-Mitteltemperatur, Saisonkoeffizient. Die Methodikseite war nicht erreichbar.
