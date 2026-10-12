# Hut ab! – Prognosemodell, Kalibrierung und Belege

Stand: 13.10.2026. Parameter: [`data/modell.json`](../data/modell.json), Artsteckbriefe: [`data/arten.json`](../data/arten.json),
Umsetzung: [`scripts/build_daily.py`](../scripts/build_daily.py) (identisch im Browser: [`web/app.js`](../web/app.js)).
Kalibrierung: [`docs/KALIBRIERUNG.md`](KALIBRIERUNG.md), `data/kalibrierung*.json`. Prüfung: [`scripts/validate.py`](../scripts/validate.py).

Die Chance (0–100) beschreibt, wie **günstig die Bedingungen morgen** für Fruchtkörper einer Art in einer
ca. 180 × 180 m großen Rasterzelle sind. Sie sagt nicht, dass dort Pilze stehen. Auch das operative
Vorbild, die tschechische Pilzprognose des ČHMÚ, liegt lokal oft daneben.

## Formel

```
Chance = 100 · Saison · Partnerbäume · Standort · Bestand · Wetter
Wetter = Regen^0,35 · Bodenwasser^0,25 · Temperatur^0,30 · Hitze^0,10 · Frost
```

Das Wetter ist ein **gewichtetes geometrisches Mittel**: Ein einzelner sehr ungünstiger Faktor (etwa Dürre)
drückt die Chance stark, wie bei einem Minimumfaktor. Jeder Wetterfaktor wird vorher auf mindestens 0,03 begrenzt.
In der App lässt sich jeder Faktor einzeln ansehen und abschalten; die Chance wird dann im Browser neu berechnet.

## Faktoren

| Faktor | Daten (offen abrufbar) | Form | Beleg / Kalibrierung |
|---|---|---|---|
| **Saison** | – | Monatsgewicht je Art | **kalibriert:** Funde je Monat ÷ alle Pilzmeldungen je Monat (GBIF 2019–2025), mit Pilzführer-Kurve geschrumpft (w = n/(n+150)) |
| **Partnerbäume** | Thünen-Baumartenkarte 2017/18 (10 m) | Σ Baumartenanteil × Wirtsgewicht, voll ab 50 % passenden Bäumen; Parasol: Waldrand (≈ 50 % Wald) | Mykorrhiza-/Wirtsbeziehungen (Pilzführer, Literatur). Trägt den größten Teil des räumlichen Signals (siehe Prüfung) |
| **Standort** | Forstliche Standortskarte Brandenburg (LFB): Nährkraft A–R; sonst SoilGrids-pH | Eignung je Nährkraftstufe | **kalibriert** an Funden vs. alle Pilzmeldungen. Bestätigt: Marone, Pfifferling, Butterpilz auf armen Standorten, Hallimasch auf reichen. **Widerlegt:** Kalkvorliebe des Edelreizkers (Funde v. a. auf armen Sanden; vgl. Taye et al. 2016) |
| **Bestand** | DLR: Kronenhöhe und -deckung 2023, Kronenverlust seit 2017; UBA: N-Deposition | Kulturen < 4 m ×0,5; Butterpilz 3–15 m, Krause Glucke ≥ 18 m; Deckung < 20 % ×0,6; frischer Kronenverlust bis −80 %; Waldrand-Bonus; N-Abschlag bis −50 % (Pfifferling) | Ortega-Martínez et al. 2011, Sánchez-González et al. 2019, van Strien et al. 2018, Arnolds 1991; Stärken = Expertenschätzung |
| **Regen & Wasserbilanz** | Open-Meteo (Regen, ET0) | Rampe auf Regen − Verdunstung der Tage t−26…t−1 (frischer Regen der letzten 4 Tage halb), mal Regentage-Faktor | Fenster: Brejon Lamartinière & Hoffman 2025, Karavani et al. 2018, Salerni et al. 2002, ČHMÚ. **Schwellen kalibriert:** relative Funddichte ≈ 0,2 bei −50 mm, ≈ 0,7 ab −20 mm → Rampe −55 … −15 mm. Wasserbilanz statt Regen: Ágreda et al. 2015 |
| **Bodenwasser** | DWD AMBAV (Kiefer, 0–30 cm, 1 km, täglich); UFZ-Dürremonitor als Rückfall; Open-Meteo-Bodenfeuchteprognose | Rampe auf % nFK, mit der modellierten Änderung bis morgen fortgeschrieben; grundwassernahe/nasse Standorte puffern | Karavani et al. 2018. **Schwellen kalibriert:** an Fundtagen Median ≈ 46 % nFK, Hintergrund 32 % → Rampe 12,5 … 57,5 % nFK (1.424 Funde) |
| **Temperatur** | Open-Meteo (20-Tage-Mittel inkl. Prognose) | Gauß-Kurve um das Art-Optimum | **kalibriert** mit ERA5 an den Fundtagen: Steinpilz 13,0 °C (σ 3,25) – identisch mit Brejon Lamartinière & Hoffman 2025; Marone/Butterpilz 11,25 °C, Edelreizker/Hallimasch 10,75 °C, Pfifferling 15 °C |
| **Hitze & Frost** | Open-Meteo (Tmax, Tmin, Bodentemperatur) | −15 % je Hitzetag ≥ 28 °C (7 T.); ×0,5 nach Frostnacht ≤ −2 °C, ×0,1 ab drei (10 T.); Boden < 2 °C ×0,5 | Karavani et al. 2018 (schwach); Schwellen = Expertenschätzung |
| **Schutz** | LfU Brandenburg (WFS) | Kernzonen = 0; NSG angezeigt, nicht als Stelle vorgeschlagen | rechtlich |

## Sammelstellen
Server (Startansicht): zusammenhängende Flächen mit Chance ≥ max(15; 97. Perzentil), außerhalb von Schutzgebieten.
App: Zellen im gewählten Umkreis, 3×3-geglättet, beste zuerst, mindestens 4 km Abstand. Ortsangabe: nächster GeoNames-Ort.

## Prüfung (Stand 13.10.2026)
AUC = Wahrscheinlichkeit, dass ein Fundort höher bewertet wird als ein Vergleichsort (0,5 = Zufall).
- **Räumlich, wetterunabhängig:** Funde der Art (GBIF 2019–2025) gegen 21.000 Orte *aller* Pilzmeldungen
  (korrigiert die Beobachtungsverzerrung zu Stadtnähe und Wegen): **AUC 0,62** im Mittel (Marone 0,66, Butterpilz 0,69,
  Krause Glucke 0,69, Edelreizker 0,70; Steinpilz 0,53, Parasol 0,52, Hallimasch 0,54).
  Fast das gesamte Signal kommt aus den Partnerbäumen; Standort, Bestand und Stickstoff ändern die AUC um weniger als ±0,01.
- **Aktuelle Funde (iNaturalist, 14 Tage, ≈ 200 Funde):** AUC 0,56–0,63 je nach Modellvariante – wegen der kleinen Zahl nur grob.
- Folgerung: Die **zeitliche** Vorhersage (wann) ist gut belegt; die **räumliche** Feinauswahl (wo genau) bleibt unsicher.
  Die App zeigt deshalb die Faktoren offen und lässt eigene Gewichtung zu.

## Wichtige Einschränkungen
1. Fundmeldungen sind keine Ertragsdaten (nur Vorkommen, mit Beobachtungsverzerrung); Funddatum ≠ Erscheinungsdatum.
2. Für Frost, Hitze und die Stärke der Bestandesfaktoren gibt es keine publizierten Zahlen (Expertenschätzung).
3. DWD-Bodenfeuchte nur für Kiefer gerechnet; Laubwald wird damit angenähert.
4. Rotkappe (26 Funde) und Birkenpilz (≈ 100) sind schwach belegt.
5. Berliner Schutzgebiete fehlen noch; die Forstliche Standortskarte deckt nur Brandenburg ab.

## Nächste Ausbaustufen
| Idee | Nutzen | Daten |
|---|---|---|
| Fundhistorie als Ebene | Krause Glucke und Steinpilz fruchten oft jahrelang an denselben Stellen | GBIF/iNaturalist |
| DWD-Bodenfeuchte auch für Buche/Eiche | genauer im Laubwald | DWD AMBAV `beech`/`oak` |
| Regen aus Radar statt Modell | trifft lokale Schauer | DWD RADOLAN |
| Simmel et al. 2017 Zeigerwerte | artspezifische N-/pH-Vorlieben | Paper-Tabelle |
| Rückmeldungen aus der App („gefunden/nichts gefunden“) | echte Ja/Nein-Daten zur Kalibrierung | eigene Datenbank |

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
