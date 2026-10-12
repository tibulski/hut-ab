#!/usr/bin/env python3
"""Verbindet UFZ-Bodenfeuchte und Open-Meteo-Wetter zu einem Pilz-Score (0-100) je Rechteck.

Heuristik (siehe CLAUDE.md, Faustregel: ~50 l/m2 durchfeuchten den Waldboden,
Fruchtkoerper ca. 14 Tage spaeter; Nachttemperatur > ~5 Grad):
  Regen 30 Tage   40 Punkte  linear bis 50 l/m2
  Oberboden-nFK   30 Punkte  linear bis 60 %nFK (keine Daten -> 0)
  Duerreklasse    20 Punkte  keine Duerre 20, ungew. trocken 15, moderat 10, schwer 5, sonst 0
  Nachttemperatur 10 Punkte  Mittel Tmin 7 Tage: <= 2 Grad -> 0, >= 8 Grad -> 10
Waldtyp und Schutzgebiete sind noch nicht enthalten.

Aufruf: python scripts/score.py
"""
import json, os
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SM_POINTS = [20, 15, 10, 5, 0, 0]


def score(sm, nfk, w):
    rain = 40 * min(w['mm_30'] / 50, 1)
    water = 30 * min((nfk or 0) / 60, 1)
    temp = 10 * float(np.clip((w['tmin_7'] - 2) / 6, 0, 1))
    return round(rain + water + SM_POINTS[sm] + temp)


def main():
    geo = json.load(open(os.path.join(ROOT, 'data', 'ufz_BE-BB.geojson'), encoding='utf-8'))
    rain = json.load(open(os.path.join(ROOT, 'data', 'niederschlag_BE-BB.json'), encoding='utf-8'))
    pts = rain['points']
    dlon, dlat = rain['metadata']['dlon'], rain['metadata']['dlat']
    idx = {(int(np.floor(p['lon'] / dlon)), int(np.floor(p['lat'] / dlat))): p for p in pts}

    scores = []
    for f in geo['features']:
        r = f['geometry']['coordinates'][0]
        lon, lat = (r[0][0] + r[1][0]) / 2, (r[0][1] + r[2][1]) / 2
        w = idx[(int(np.floor(lon / dlon)), int(np.floor(lat / dlat)))]
        pr = f['properties']
        pr['score'] = score(pr['sm'], pr['nfk'], w)
        pr.update(mm_30=w['mm_30'], mm_14=w['mm_14'], mm_fc7=w['mm_fc7'], tmin_7=w['tmin_7'])
        scores.append(pr['score'])

    geo['metadata'].update(weather_date=rain['metadata']['date'],
                           score='0-100: Regen 30 T (40) + nFK (30) + Duerreklasse (20) + Nachttemp. (10)')
    out = os.path.join(ROOT, 'data', 'score_BE-BB.geojson')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(geo, f, separators=(',', ':'))
    s = np.array(scores)
    print(f'{len(s)} Rechtecke -> {out} ({os.path.getsize(out) / 1e6:.1f} MB)')
    print('Score: min', s.min(), 'Median', int(np.median(s)), 'max', s.max(),
          '| Verteilung:', np.histogram(s, bins=[0, 20, 40, 60, 80, 101])[0].tolist())
    top = sorted(geo['features'], key=lambda f: -f['properties']['score'])[:8]
    for f in top:
        r = f['geometry']['coordinates'][0]; p = f['properties']
        print(f"  {p['score']:3d}  {r[0][1]:.3f} N {r[0][0]:.3f} O  {p['cls']} nFK {p['nfk']} Regen30 {p['mm_30']}")


if __name__ == '__main__':
    main()
