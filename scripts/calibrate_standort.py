#!/usr/bin/env python3
"""Kalibriert die Naehrkraft-Vorlieben (A/Z/M/K/R der Forstlichen Standortskarte) je Art an GBIF-Funden.

Verhaeltnis "Anteil der Funde der Art auf Stufe X" / "Anteil aller Pilzmeldungen auf Stufe X" (Ziel-Gruppen-
Hintergrund, korrigiert, wo Sammler ueberhaupt unterwegs sind), auf das Maximum normiert, mit der
Pilzfuehrer-Einschaetzung geschrumpft: w = n / (n + 150), Untergrenze 0,15.

Voraussetzung: cache/kalibrierung/gbif_<art>.json (calibrate_gbif.py), gbif_fungi_orte.json (validate.py).
Aufruf: python scripts/calibrate_standort.py [--apply]   Ausgabe: data/kalibrierung_standort.json
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

NK = 'AZMKR'


def nk_of_points(pts, nk_grid):
    mx, my = grid.merc_x(np.array([p[1] for p in pts])), grid.merc_y(np.array([p[0] for p in pts]))
    j, i = grid.to_index(mx, my)
    ok = j >= 0
    v = nk_grid[j[ok], i[ok]]
    return v[v > 0]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    st = np.load(os.path.join(grid.STATIC, 'struktur.npz'))
    codes = [str(c) for c in st['stok_codes']]
    lut = np.zeros(len(codes), np.int8)
    for k, c in enumerate(codes):
        pre = c[0] if c and c[0] in 'NO+' else ''
        letter = next((ch for ch in c[len(pre):] if ch in NK), '') if c else ''
        lut[k] = NK.index(letter) + 1 if letter else 0
    nk_grid = lut[st['stok']]
    cache = os.path.join(grid.ROOT, 'cache', 'kalibrierung')
    bg = nk_of_points(json.load(open(os.path.join(cache, 'gbif_fungi_orte.json'), encoding='utf-8')), nk_grid)
    hb = np.bincount(bg, minlength=6)[1:].astype(float)
    print('Hintergrund (alle Pilzmeldungen) je Stufe A Z M K R:', hb.astype(int).tolist())
    arten_path = os.path.join(grid.ROOT, 'data', 'arten.json')
    arten = json.load(open(arten_path, encoding='utf-8'))
    out = {}
    for art in arten['arten']:
        pts = [[la, lo] for la, lo, _ in json.load(open(os.path.join(cache, f"gbif_{art['id']}.json"), encoding='utf-8'))]
        v = nk_of_points(pts, nk_grid)
        hf = np.bincount(v, minlength=6)[1:].astype(float)
        n = int(hf.sum())
        with np.errstate(invalid='ignore', divide='ignore'):
            r = (hf / max(n, 1)) / (hb / hb.sum())
        r = np.where(hb >= 30, r, np.nan)
        emp = r / np.nanmax(r) if n and np.nanmax(r) > 0 else np.full(5, np.nan)
        w = n / (n + 150)
        expert = np.array([art['naehrkraft'][c] for c in NK])
        cal = np.where(np.isnan(emp), expert, w * emp + (1 - w) * expert)
        cal = np.clip(cal / cal.max(), 0.15, 1)
        out[art['id']] = {'n': n, 'funde_je_stufe': hf.astype(int).tolist(),
                          'verhaeltnis': [None if np.isnan(x) else round(float(x), 2) for x in emp],
                          'experte': expert.tolist(), 'kalibriert': [round(float(x), 2) for x in cal]}
        print(f"{art['name']:<16} n={n:4d}  Verhaeltnis A..R {out[art['id']]['verhaeltnis']}  -> {out[art['id']]['kalibriert']}")
        if '--apply' in sys.argv:
            art['naehrkraft'] = {c: out[art['id']]['kalibriert'][k] for k, c in enumerate(NK)}
    json.dump({'hintergrund_je_stufe': hb.astype(int).tolist(), 'arten': out},
              open(os.path.join(grid.ROOT, 'data', 'kalibrierung_standort.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if '--apply' in sys.argv:
        json.dump(arten, open(arten_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('-> data/arten.json aktualisiert')


if __name__ == '__main__':
    main()
