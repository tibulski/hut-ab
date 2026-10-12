#!/usr/bin/env python3
"""Holt Niederschlag und Nachttemperatur (Open-Meteo) fuer ein Punktraster ueber Berlin/Brandenburg.

Das Raster wird aus dem UFZ-GeoJSON abgeleitet (nur Punkte mit Land), damit keine
Anfragen fuer Polen/Sachsen-Anhalt anfallen.

Aufruf: python scripts/fetch_rain.py [--geo data/ufz_BE-BB.geojson] [--out data/niederschlag_BE-BB.json]
"""
import argparse, datetime as dt, json, os, time, urllib.parse, urllib.request, urllib.error
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DLON, DLAT = 0.10, 0.06          # ~7 km Punktabstand (Open-Meteo-Modelle sind ohnehin 2-11 km)
BATCH = 50
API = 'https://api.open-meteo.com/v1/forecast'


def grid_points(geo):
    """Mittelpunkte der Rasterzellen (DLON x DLAT), die mindestens ein UFZ-Rechteck enthalten."""
    cells = set()
    for f in geo['features']:
        r = f['geometry']['coordinates'][0]
        lon, lat = (r[0][0] + r[1][0]) / 2, (r[0][1] + r[2][1]) / 2
        cells.add((int(np.floor(lon / DLON)), int(np.floor(lat / DLAT))))
    return sorted(((i + .5) * DLON, (j + .5) * DLAT) for i, j in cells)


def fetch(points):
    q = {'latitude': ','.join(f'{la:.3f}' for _, la in points),
         'longitude': ','.join(f'{lo:.3f}' for lo, _ in points),
         'daily': 'precipitation_sum,temperature_2m_min', 'past_days': 31, 'forecast_days': 7,
         'timezone': 'Europe/Berlin'}
    url = API + '?' + urllib.parse.urlencode(q, safe=',')
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.load(r)
            return d if isinstance(d, list) else [d]
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(20 * (attempt + 1))
    raise RuntimeError('Open-Meteo: zu viele Anfragen (429)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--geo', default=os.path.join(ROOT, 'data', 'ufz_BE-BB.geojson'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'niederschlag_BE-BB.json'))
    args = ap.parse_args()
    geo = json.load(open(args.geo, encoding='utf-8'))
    pts = grid_points(geo)
    print(len(pts), 'Punkte ->', -(-len(pts) // BATCH), 'Anfragen')

    today = dt.date.today().isoformat()
    out = []
    for k in range(0, len(pts), BATCH):
        res = fetch(pts[k:k + BATCH])
        for (lo, la), d in zip(pts[k:k + BATCH], res):
            days = d['daily']['time']
            p = np.array([np.nan if v is None else v for v in d['daily']['precipitation_sum']])
            t = np.array([np.nan if v is None else v for v in d['daily']['temperature_2m_min']])
            n = days.index(today)                      # heute zaehlt schon zur Prognose
            s = lambda a: round(float(np.nansum(a)), 1)
            out.append({'lat': round(la, 3), 'lon': round(lo, 3),
                        'mm_30': s(p[n - 30:n]), 'mm_14': s(p[n - 14:n]), 'mm_7': s(p[n - 7:n]),
                        'mm_fc7': s(p[n:n + 7]),
                        'tmin_7': round(float(np.nanmean(t[n - 7:n])), 1),
                        'tmin_fc7': round(float(np.nanmean(t[n:n + 7])), 1),
                        'frost_fc7': bool(np.nanmin(t[n:n + 7]) < 0)})
        time.sleep(2)
    meta = {'date': today, 'source': 'Open-Meteo', 'dlon': DLON, 'dlat': DLAT,
            'fields': 'mm_N = Summe der letzten N Tage bis gestern; mm_fc7 = heute+6 Tage Prognose; tmin = Mittel der Tagesminima'}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump({'metadata': meta, 'points': out}, f, separators=(',', ':'))
    mm = np.array([p['mm_30'] for p in out])
    print(f'{len(out)} Punkte -> {args.out}; mm_30: min {mm.min()}, Median {np.median(mm)}, max {mm.max()}')


if __name__ == '__main__':
    main()
