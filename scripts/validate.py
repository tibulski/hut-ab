#!/usr/bin/env python3
"""Prueft die raeumliche Trefferguete der Prognose mit unabhaengigen aktuellen Fundmeldungen (iNaturalist).

AUC = Wahrscheinlichkeit, dass eine Rasterzelle mit aktueller Fundmeldung einen hoeheren Score hat als eine
zufaellige Waldzelle im Gebiet (0,5 = Zufall, 1 = perfekt). Fundmeldungen haeufen sich an Wegen und in
Stadtnaehe, deshalb ist die AUC eine grobe, eher pessimistische Kennzahl.

Aufruf: python scripts/validate.py [--ablation]   (--ablation: AUC ohne einzelne Faktorgruppen)
"""
import json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid


def auc(pos, neg):
    """Mann-Whitney-AUC mit Bindungen."""
    allv = np.concatenate([pos, neg])
    ranks = np.argsort(np.argsort(allv, kind='mergesort'), kind='mergesort').astype(float) + 1
    # mittlere Raenge fuer Bindungen
    order = np.argsort(allv, kind='mergesort')
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    rp = ranks[:len(pos)].sum()
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def evaluate(scores_by_species, recent, region, rng, bg_pts=None):
    res = {}
    if bg_pts is not None:
        bx, by = grid.merc_x(np.array([p[1] for p in bg_pts])), grid.merc_y(np.array([p[0] for p in bg_pts]))
        bj, bi = grid.to_index(bx, by)
        keep = bj >= 0
        bj, bi = bj[keep], bi[keep]
        keep = region[bj, bi]
        bj, bi = bj[keep], bi[keep]
    for sid, score in scores_by_species.items():
        funde = recent['arten'].get(sid, [])
        if len(funde) < 5:
            continue
        mx, my = grid.merc_x(np.array([f['lon'] for f in funde])), grid.merc_y(np.array([f['lat'] for f in funde]))
        j, i = grid.to_index(mx, my)
        ok = j >= 0
        pos = score[j[ok], i[ok]]
        inreg = region[j[ok], i[ok]]
        pos = pos[inreg]
        if bg_pts is not None:
            neg = score[bj, bi]
        else:
            cand = np.argwhere(region)
            pick = cand[rng.choice(len(cand), size=min(20000, len(cand)), replace=False)]
            neg = score[pick[:, 0], pick[:, 1]]
        if len(pos) >= 5:
            res[sid] = (round(float(auc(pos, neg)), 3), int(len(pos)))
    return res


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    recent = json.load(open(os.path.join(grid.WEB_DATA, 'recent.json'), encoding='utf-8'))
    meta = json.load(open(os.path.join(grid.WEB_DATA, 'meta.json'), encoding='utf-8'))
    forest = np.load(os.path.join(grid.STATIC, 'forest.npz'))['frac'][0]
    daily = np.array(Image.open(os.path.join(grid.WEB_DATA, 'daily.png')))
    region = (daily[..., 0] < 6) & (forest >= 20)
    rng = np.random.default_rng(1)
    scores = {}
    for a in meta['arten']:
        img = np.array(Image.open(os.path.join(grid.WEB_DATA, f"score_{a['id']}.png"))).astype(float)
        scores[a['id']] = np.where(img > 0, img - 1, -1)
    res = evaluate(scores, recent, region, rng)
    print('AUC je Art (Fundzellen vs. zufaellige Waldzellen):')
    for sid, (v, n) in res.items():
        print(f'  {sid:<14} AUC {v:.3f}  (n={n})')
    if res:
        print(f"  Mittel        AUC {np.mean([v for v, _ in res.values()]):.3f}")
    if '--ablation' in sys.argv:
        ablation(recent, region, rng)
    return res


def ablation(recent, region, rng):
    """AUC, wenn einzelne Datenebenen weggelassen werden (zeigt, welche Ebene die Trefferguete verbessert)."""
    import copy
    import build_daily as bd
    arten = json.load(open(os.path.join(grid.ROOT, 'data', 'arten.json'), encoding='utf-8'))['arten']
    C = bd.prepare()
    varianten = {
        'alle Ebenen': {},
        'ohne Standortskarte': {'nk': None, 'puffer': None, 'fdigit': None},
        'ohne Bestand (Hoehe/Deckung/Verlust)': {'hoehe': None, 'deckung': None, 'verlust': None},
        'ohne Stickstoff': {'stickstoff': None},
        'ohne DWD-Bodenfeuchte': {'dwd': None},
    }
    for name, aus in varianten.items():
        L = dict(C['L'], **aus)
        sc = {}
        for art in arten:
            a2 = copy.deepcopy(art)
            if name != 'alle Ebenen' and 'waldrand' in aus:
                a2['waldrand'] = 0
            s, hab, _ = bd.species_score(a2, *C['args'], C['M'], L)
            sc[art['id']] = np.where(hab & C['need'], s, -1)
        r = evaluate(sc, recent, region, rng)
        print(f"  {name:<38} mittlere AUC {np.mean([v for v, _ in r.values()]):.3f}  "
              + ' '.join(f"{k[:5]}={v:.2f}" for k, (v, _) in r.items()))


def fungi_background():
    """Orte aller Pilzmeldungen (GBIF, Reich Fungi) 2019-2025 im Gebiet als Ziel-Gruppen-Hintergrund:
    korrigiert die Beobachtungsverzerrung (Stadtnaehe, Wege), weil Pilzsammler dort generell melden."""
    import urllib.parse, urllib.request, time
    path = os.path.join(grid.ROOT, 'cache', 'kalibrierung', 'gbif_fungi_orte.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    q = {'taxonKey': 5, 'decimalLatitude': f'{grid.SOUTH},{grid.NORTH}', 'decimalLongitude': f'{grid.WEST},{grid.EAST}',
         'hasCoordinate': 'true', 'hasGeospatialIssue': 'false', 'basisOfRecord': 'HUMAN_OBSERVATION',
         'year': '2019,2025', 'limit': 300}
    pts, off = [], 0
    while off < 60000:
        d = json.load(urllib.request.urlopen('https://api.gbif.org/v1/occurrence/search?'
                                             + urllib.parse.urlencode(dict(q, offset=off)), timeout=120))
        pts += [[round(r['decimalLatitude'], 4), round(r['decimalLongitude'], 4)] for r in d['results']
                if (r.get('coordinateUncertaintyInMeters') or 0) <= 2000]
        off += 300
        if d['endOfRecords']:
            break
        time.sleep(0.3)
    json.dump(pts, open(path, 'w', encoding='utf-8'))
    return pts


def statisch(rng):
    """Raeumliche Pruefung der wetterunabhaengigen Ebenen (Lebensraum x Standort x Bestand) mit allen
    GBIF-Funden 2019-2025 (cache/kalibrierung/gbif_*.json) - deutlich mehr Funde als 14 Tage iNaturalist."""
    import build_daily as bd
    arten = json.load(open(os.path.join(grid.ROOT, 'data', 'arten.json'), encoding='utf-8'))['arten']
    C = bd.prepare()
    region = C['region'] & (C['forest'][0] >= 20)
    cache = os.path.join(grid.ROOT, 'cache', 'kalibrierung')
    funde = {a['id']: [{'lat': la, 'lon': lo} for la, lo, _ in
                       json.load(open(os.path.join(cache, f"gbif_{a['id']}.json"), encoding='utf-8'))] for a in arten}
    varianten = {
        'nur Baumarten (Lebensraum)': (('H',), {}),
        '+ Standort (Naehrkraft/pH)': (('H', 'P'), {}),
        '+ Bestand + Stickstoff (alles)': (('H', 'P', 'G'), {}),
        'alles ohne Stickstoff': (('H', 'P', 'G'), {'stickstoff': None}),
        'alles ohne Bestand': (('H', 'P', 'G'), {'hoehe': None, 'deckung': None, 'verlust': None}),
        'alles ohne Standortskarte': (('H', 'P', 'G'), {'nk': None, 'puffer': None, 'fdigit': None}),
    }
    bg = fungi_background()
    print(f'Raeumliche AUC der statischen Ebenen: Funde der Art vs. {len(bg)} Orte aller Pilzmeldungen (GBIF 2019-2025):')
    for name, (teile, aus) in varianten.items():
        L = dict(C['L'], **aus)
        sc = {}
        for art in arten:
            _, hab, parts = bd.species_score(art, *C['args'], C['M'], L)
            v = np.ones_like(parts['H'])
            for t in teile:
                v = v * parts[t]
            sc[art['id']] = np.where(hab & C['need'], v, -1)
        r = evaluate(sc, {'arten': funde}, region, rng, bg_pts=bg)
        print(f"  {name:<34} mittlere AUC {np.mean([v for v, _ in r.values()]):.3f}  "
              + ' '.join(f"{k[:5]}={v:.2f}" for k, (v, _) in r.items()))


if __name__ == '__main__':
    if '--statisch' in sys.argv:
        sys.stdout.reconfigure(encoding='utf-8')
        statisch(np.random.default_rng(1))
    else:
        main()
