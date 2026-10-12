#!/usr/bin/env python3
"""Holt Niederschlag und Temperatur (Open-Meteo, CC BY 4.0) fuer ein Punktraster ueber den Waeldern.

Je Punkt werden die Tageswerte der letzten 31 Tage und die Prognose fuer 3 Tage
gespeichert; die Auswertung (Fenster, Zieltag) macht build_daily.py.
Punktabstand ~7 km (Open-Meteo-Modelle haben ohnehin 2-11 km Aufloesung).

Aufruf: python scripts/fetch_weather.py
Ausgabe: data/daily/weather.json
"""
import datetime as dt, json, os, sys, time, urllib.error, urllib.parse, urllib.request
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

DLON, DLAT = 0.10, 0.06
BATCH = 50
API = 'https://api.open-meteo.com/v1/forecast'
DAILY = 'precipitation_sum,temperature_2m_min,temperature_2m_max,temperature_2m_mean'


def grid_points():
    """Punktraster-Mittelpunkte, in deren Masche mindestens etwas Wald liegt."""
    frac = np.load(os.path.join(grid.STATIC, 'forest.npz'))['frac'][0]
    lon, lat = grid.cell_lonlat()
    m = frac >= 10
    cells = set(zip(np.floor(lon[m] / DLON).astype(int).tolist(), np.floor(lat[m] / DLAT).astype(int).tolist()))
    return sorted(((i + .5) * DLON, (j + .5) * DLAT) for i, j in cells)


def fetch(points):
    q = {'latitude': ','.join(f'{la:.3f}' for _, la in points),
         'longitude': ','.join(f'{lo:.3f}' for lo, _ in points),
         'daily': DAILY, 'past_days': 31, 'forecast_days': 3, 'timezone': 'Europe/Berlin'}
    url = API + '?' + urllib.parse.urlencode(q, safe=',')
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                d = json.load(r)
            return d if isinstance(d, list) else [d]
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:   # z. B. TLS-Handshake-Timeout
            err = e
        print(f'  Open-Meteo: {err} - neuer Versuch {attempt + 1}/4')
        time.sleep(30 * (attempt + 1))
    raise RuntimeError(f'Open-Meteo nicht erreichbar: {err}')


def main():
    pts = grid_points()
    print(len(pts), 'Punkte ->', -(-len(pts) // BATCH), 'Anfragen')
    out, dates = [], None
    for k in range(0, len(pts), BATCH):
        for (lo, la), d in zip(pts[k:k + BATCH], fetch(pts[k:k + BATCH])):
            dd = d['daily']
            dates = dates or dd['time']
            out.append({'lon': round(lo, 3), 'lat': round(la, 3),
                        **{v: dd[v] for v in DAILY.split(',')}})
        time.sleep(2)
    path = os.path.join(grid.ROOT, 'data', 'daily', 'weather.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'metadata': {'abgerufen': dt.datetime.now().isoformat(timespec='minutes'),
                                'quelle': 'Open-Meteo (CC BY 4.0)', 'dlon': DLON, 'dlat': DLAT,
                                'dates': dates},
                   'points': out}, f, separators=(',', ':'))
    print(f'{len(out)} Punkte, {dates[0]} .. {dates[-1]} -> {path}')


if __name__ == '__main__':
    main()
