#!/usr/bin/env python3
"""Laedt die UFZ-Duerremonitor-PNGs (Oberboden-Duerre + pflanzenverfuegbares Wasser)
fuer ein Bundesland, klassifiziert das ganze Land und schreibt GeoJSON.

Aufruf:  python scripts/fetch_ufz.py [--region BE-BB] [--out data/ufz_BE-BB.geojson] [--max-age-days 3]

Das Datum der Karte steht nur als Text im Bild. Wir nehmen stattdessen das
Last-Modified-Datum der Datei minus 1 Tag (Karte vom Vortag, siehe CLAUDE.md /
Beobachtung 12.10.: Last-Modified 12.10., Bildtext 2026-10-11) und pruefen, dass
beide PNGs denselben Datumstext zeigen.
"""
import argparse, io, json, os, sys, urllib.request, email.utils, datetime as dt
from collections import Counter
import numpy as np
from PIL import Image
from scipy import ndimage

BASE = 'https://files.ufz.de/~drought/{name}_dry-wet_aktuell_{region}.png'
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

# --- Georeferenzierung (nur BE-BB kalibriert, siehe CLAUDE.md) ---
X0, X1 = 142.5, 1147.5           # 11 E .. 15 E
PX_PER_DEG = (X1 - X0) / 4.0
FRAME_Y = (14, 960)              # Kartenrahmen (grob)
CELL = 4                         # Modellraster ~4 px
PHASE_X, PHASE_Y = 693 % CELL, 150 % CELL   # Phase des bisherigen Rasters
merc = lambda la: np.degrees(np.log(np.tan(np.pi / 4 + np.radians(la) / 2)))
_ty = np.array([55.5, 264.5, 471.5, 676.5, 878.5]); _tl = np.array([53.5, 53, 52.5, 52, 51.5])
_b, _a = np.polyfit(merc(_tl), _ty, 1)
lat_of = lambda y: np.degrees(2 * np.arctan(np.exp(np.radians((y - _a) / _b))) - np.pi / 2)
lon_of = lambda x: 11 + (x - X0) / PX_PER_DEG

SM_PALETTE = {(255, 255, 255): 0, (255, 255, 0): 1, (252, 211, 127): 2,
              (255, 170, 0): 3, (230, 0, 0): 4, (115, 0, 0): 5}
PAW_PALETTE = {(240, 59, 32): 0, (255, 170, 1): 1, (255, 233, 168): 2, (252, 255, 234): 3,
               (240, 249, 232): 4, (211, 239, 202): 5, (145, 215, 198): 6, (128, 128, 128): 99}
SM_NAMES = ['keine Duerre', 'ungewoehnlich trocken', 'moderate Duerre', 'schwere Duerre',
            'extreme Duerre', 'ausserordentliche Duerre']


def download(name, region):
    url = BASE.format(name=name, region=region)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
        lm = email.utils.parsedate_to_datetime(r.headers['Last-Modified'])
    return Image.open(io.BytesIO(data)).convert('RGB'), lm


def land_mask(a):
    """Land = alles, was nicht von aussen (Ecke) ueber nicht-schwarze Pixel erreichbar ist.
    Die dicke schwarze Landesgrenze ist die Barriere."""
    barrier = a.max(axis=2) < 70
    barrier = ndimage.binary_dilation(barrier, iterations=1)
    lab, _ = ndimage.label(~barrier)           # 4er-Nachbarschaft
    outside = lab == lab[FRAME_Y[0] + 5, int(X0) + 6]
    land = ~ndimage.binary_dilation(outside, iterations=1)
    # Rahmen, Achsen und Datumstext sind kleine abgeschlossene Inseln -> nur groesste Flaeche behalten
    lab, n = ndimage.label(land)
    sizes = ndimage.sum(land, lab, range(1, n + 1))
    return lab == 1 + int(np.argmax(sizes))


def classify(a, palette):
    """Pro Zelle Modus der bekannten Palettenfarben im Block; -1 = unbekannt (Linie/Text)."""
    codes = np.full(a.shape[:2], -1, np.int16)
    for rgb, c in palette.items():
        codes[(a == np.array(rgb)).all(axis=2)] = c
    xs = np.arange(int(X0) + 1 + (PHASE_X - (int(X0) + 1)) % CELL, int(X1), CELL)
    ys = np.arange(FRAME_Y[0] + (PHASE_Y - FRAME_Y[0]) % CELL, FRAME_Y[1], CELL)
    out = np.full((len(ys), len(xs)), -1, np.int16)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            blk = codes[y - 2:y + 2, x - 2:x + 2].ravel()
            blk = blk[blk >= 0]
            if blk.size:
                out[j, i] = Counter(blk.tolist()).most_common(1)[0][0]
    return xs, ys, out


def fill_unknown(g, inside):
    """Unbekannte Zellen im Land (Grenzlinien) mit Modus der Nachbarn fuellen."""
    g = g.copy()
    for _ in range(3):
        todo = np.argwhere((g < 0) & inside)
        if not len(todo):
            break
        new = g.copy()
        for j, i in todo:
            nb = g[max(j - 1, 0):j + 2, max(i - 1, 0):i + 2].ravel()
            nb = nb[nb >= 0]
            if nb.size:
                new[j, i] = Counter(nb.tolist()).most_common(1)[0][0]
        g = new
    return g


def cell_class(sm, paw):
    """Code wie in CLAUDE.md: G/W/H/Y/L/O/R/D/J."""
    wet = 5 <= paw < 99          # >= 50 %nFK
    if sm == 0:
        return 'G' if wet else 'W'
    if sm == 1:
        return 'H' if wet else 'Y'
    if wet:
        return 'J'
    return {2: 'L', 3: 'O', 4: 'R', 5: 'D'}[sm]


def date_crop(a):
    return a[40:80, 165:365]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', default='BE-BB')
    ap.add_argument('--out')
    ap.add_argument('--max-age-days', type=float, default=3)
    ap.add_argument('--cache', default=os.path.join(ROOT, 'cache'))
    args = ap.parse_args()
    if args.region != 'BE-BB':
        sys.exit('Georeferenzierung ist nur fuer BE-BB kalibriert (siehe CLAUDE.md).')

    sm_img, sm_lm = download('SM_0_25cm', args.region)
    paw_img, paw_lm = download('PAW_0_25cm', args.region)
    if sm_img.size != (1202, 1025) or paw_img.size != (1202, 1025):
        sys.exit(f'Unerwartete Bildgroesse {sm_img.size}/{paw_img.size}')
    sm, paw = np.array(sm_img), np.array(paw_img)

    if not np.array_equal(date_crop(sm), date_crop(paw)):
        sys.exit('Datumstext in beiden PNGs unterschiedlich - Karten nicht vom selben Tag.')
    now = dt.datetime.now(dt.timezone.utc)
    age = (now - min(sm_lm, paw_lm)).total_seconds() / 86400
    if age > args.max_age_days:
        sys.exit(f'Daten veraltet: Last-Modified {sm_lm:%Y-%m-%d %H:%M} ({age:.1f} Tage alt).')
    date = (sm_lm.astimezone(dt.timezone(dt.timedelta(hours=2))) - dt.timedelta(days=1)).date().isoformat()

    os.makedirs(args.cache, exist_ok=True)
    sm_img.save(os.path.join(args.cache, f'SM_0_25cm_{args.region}.png'))
    paw_img.save(os.path.join(args.cache, f'PAW_0_25cm_{args.region}.png'))
    Image.fromarray(date_crop(sm)).save(os.path.join(args.cache, 'datum_crop.png'))

    xs, ys, gs = classify(sm, SM_PALETTE)
    _, _, gp = classify(paw, PAW_PALETTE)
    mask_px = land_mask(sm)
    frac = np.array([[mask_px[y - 2:y + 2, x - 2:x + 2].mean() for x in xs] for y in ys])
    # weisse Randzellen (Landesgrenze/Hintergrund) nur bei klar innenliegender Zelle als "keine Duerre" werten
    inside = (frac > 0.5) & ((gs != 0) | (frac > 0.95))
    gs, gp = fill_unknown(gs, inside), fill_unknown(gp, inside)

    # Zeilenweise Laufzeilen gleicher (sm, paw) -> ein Rechteck je Lauf
    feats, counts = [], Counter()
    for j, y in enumerate(ys):
        la_n, la_s = lat_of(y - 2), lat_of(y + 2)
        i = 0
        while i < len(xs):
            if not inside[j, i] or gs[j, i] < 0:
                i += 1; continue
            k = i
            while k + 1 < len(xs) and inside[j, k + 1] and gs[j, k + 1] == gs[j, i] and gp[j, k + 1] == gp[j, i]:
                k += 1
            s, p = int(gs[j, i]), int(gp[j, i])
            cls = cell_class(s, p)
            counts[cls] += k - i + 1
            w, e = lon_of(xs[i] - 2), lon_of(xs[k] + 2)
            ring = [[round(w, 4), round(la_n, 4)], [round(e, 4), round(la_n, 4)],
                    [round(e, 4), round(la_s, 4)], [round(w, 4), round(la_s, 4)], [round(w, 4), round(la_n, 4)]]
            feats.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]},
                          'properties': {'cls': cls, 'sm': s, 'nfk': None if p in (-1, 99) else p * 10}})
            i = k + 1

    out = args.out or os.path.join(ROOT, 'data', f'ufz_{args.region}.geojson')
    gj = {'type': 'FeatureCollection',
          'metadata': {'date': date, 'region': args.region, 'source': 'UFZ-Duerremonitor',
                       'sm_classes': SM_NAMES, 'nfk': 'Untergrenze der 10-%-Klasse, null = keine Daten',
                       'cell_counts': dict(counts)},
          'features': feats}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(gj, f, separators=(',', ':'))
    print(f'Datum {date}: {sum(counts.values())} Zellen, {len(feats)} Rechtecke -> {out} '
          f'({os.path.getsize(out) / 1e6:.1f} MB)')
    print('Klassen:', dict(counts))
    area = {k: round(v * 1.2) for k, v in counts.items()}  # grobe km2-Schaetzung
    print('~km2 (grob):', area)


if __name__ == '__main__':
    main()
