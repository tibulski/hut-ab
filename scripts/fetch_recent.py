#!/usr/bin/env python3
"""Aktuelle Fundmeldungen (letzte 14 Tage) je Art von iNaturalist als Signal "die Art fruchtet gerade".

Vorbild: Die tschechische Pilzprognose (CHMU) wird erst freigeschaltet, wenn Mykologen das Erscheinen
der Fruchtkoerper bestaetigen. Hier werden die Meldungen nur angezeigt und fliessen nicht in den Score ein.
Datenschutz: keine Nutzernamen, nur Datum, Ort (iNaturalist verschleiert geschuetzte Orte selbst) und Link.

Aufruf: python scripts/fetch_recent.py   Ausgabe: web/data/recent.json
"""
import datetime as dt, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid
from calibrate_gbif import TAXA

API = 'https://api.inaturalist.org/v1/'
TAGE = 14
UA = {'User-Agent': 'hut-ab (Pilzprognose Berlin-Brandenburg; https://github.com/tibulski/hut-ab)'}


def get(path, **q):
    req = urllib.request.Request(API + path + '?' + urllib.parse.urlencode(q), headers=UA)
    for k in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:
            print('  iNaturalist:', e); time.sleep(10 * (k + 1))
    raise RuntimeError(path)


def taxon_id(name):
    for t in get('taxa', q=name, is_active='true', per_page=10)['results']:
        if t['name'] == name and t.get('iconic_taxon_name') == 'Fungi':
            return t['id']
    return None


def main():
    seit = (dt.date.today() - dt.timedelta(days=TAGE)).isoformat()
    out = {'seit': seit, 'tage': TAGE, 'quelle': 'iNaturalist', 'arten': {}}
    for sid, names in TAXA.items():
        ids = [i for i in (taxon_id(n) for n in names) if i]
        time.sleep(1)
        obs = get('observations', taxon_id=','.join(map(str, ids)), swlat=grid.SOUTH, swlng=grid.WEST,
                  nelat=grid.NORTH, nelng=grid.EAST, d1=seit, per_page=200, order_by='observed_on',
                  quality_grade='research,needs_id')['results'] if ids else []
        funde = []
        for o in obs:
            g = o.get('geojson')
            if not g or (o.get('positional_accuracy') or 0) > 5000:
                continue
            funde.append({'lat': round(g['coordinates'][1], 3), 'lon': round(g['coordinates'][0], 3),
                          'datum': o.get('observed_on'), 'url': o.get('uri'),
                          'bestaetigt': o.get('quality_grade') == 'research'})
        out['arten'][sid] = funde
        print(f'{sid:<14} {len(funde)} Meldungen seit {seit}')
        time.sleep(1)
    os.makedirs(grid.WEB_DATA, exist_ok=True)
    with open(os.path.join(grid.WEB_DATA, 'recent.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
