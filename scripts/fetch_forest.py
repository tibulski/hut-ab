#!/usr/bin/env python3
"""Waldmaske + Baumartenanteile je Rasterzelle aus der Thuenen-Baumartenkarte.

Quelle: Blickensdoerfer L, Oehmichen K, Pflugmacher D, Kleinschmit B, Hostert P (2022)
Dominant Tree Species for Germany (2017/2018). Thuenen-Atlas, WCS
https://atlas.thuenen.de/geoserver/ows (geonode__Dominant_Species_Class), 10 m, UTM 32N.

Wir laden mit scaleFactor 0.2 (= 50-m-Stichprobe, ca. 36 Stichproben je Zelle) in
50-km-Kacheln und zaehlen je Rasterzelle die Anteile der Baumartengruppen.
Statische Ebene: nur bei Bedarf neu erzeugen.

Ausgabe: data/static/forest.npz  (frac: uint8[12, NY, NX] in Prozent, Index siehe CLASSES)
"""
import io, os, sys, time, urllib.request
import numpy as np
import tifffile
from pyproj import Transformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

WCS = ('https://atlas.thuenen.de/geoserver/ows?service=WCS&version=2.0.1&request=GetCoverage'
       '&coverageId=geonode__Dominant_Species_Class&format=image/tiff'
       '&subset=E({e0},{e1})&subset=N({n0},{n1})&scaleFactor={sf}')
SRC_RES = 10.0
SCALE = 0.2
TILE = 50000.0
# Thuenen-Code -> Index in frac; Index 0 = Wald gesamt
CLASSES = {2: ('birke', 'Birke'), 3: ('buche', 'Buche'), 4: ('douglasie', 'Douglasie'),
           5: ('eiche', 'Eiche'), 6: ('erle', 'Erle'), 8: ('fichte', 'Fichte'), 9: ('kiefer', 'Kiefer'),
           10: ('laerche', 'Laerche'), 14: ('tanne', 'Tanne'),
           16: ('laub_lang', 'sonst. Laubholz (langlebig, z. B. Ahorn, Esche, Linde)'),
           17: ('laub_kurz', 'sonst. Laubholz (kurzlebig, z. B. Pappel, Weide, Aspe)')}
CODES = list(CLASSES)


def fetch_tile(e0, n0):
    url = WCS.format(e0=int(e0), e1=int(e0 + TILE), n0=int(n0), n1=int(n0 + TILE), sf=SCALE)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return tifffile.imread(io.BytesIO(r.read()))
        except Exception as e:  # Netzfehler: kurz warten, erneut versuchen
            print('  Fehler', e, '- neuer Versuch'); time.sleep(10 * (attempt + 1))
    raise RuntimeError('Kachel nicht ladbar: ' + url)


def main():
    to_utm = Transformer.from_crs(4326, 32632, always_xy=True)
    to_merc = Transformer.from_crs(32632, 3857, always_xy=True)
    # UTM-Huelle des Rasters (Ecken + Kantenmitten reichen, Gebiet ist klein)
    lons = [grid.WEST, grid.EAST, (grid.WEST + grid.EAST) / 2]
    lats = [grid.SOUTH, grid.NORTH, (grid.SOUTH + grid.NORTH) / 2]
    ex, ny_ = zip(*[to_utm.transform(lo, la) for lo in lons for la in lats])
    e_min, e_max = np.floor(min(ex) / TILE) * TILE, np.ceil(max(ex) / TILE) * TILE
    n_min, n_max = np.floor(min(ny_) / TILE) * TILE, np.ceil(max(ny_) / TILE) * TILE

    counts = np.zeros((len(CODES) + 1,) + grid.SHAPE, np.uint32)   # letzte Ebene: alle Stichproben
    code_idx = np.full(256, -1, np.int64)
    for k, c in enumerate(CODES):
        code_idx[c] = k
    tiles = [(e, n) for e in np.arange(e_min, e_max, TILE) for n in np.arange(n_min, n_max, TILE)]
    for t, (e0, n0) in enumerate(tiles, 1):
        a = fetch_tile(e0, n0)
        h, w = a.shape
        px = TILE / w
        ee = e0 + (np.arange(w) + 0.5) * px
        nn = n0 + TILE - (np.arange(h) + 0.5) * px
        E, N = np.meshgrid(ee, nn)
        mx, my = to_merc.transform(E.ravel(), N.ravel())
        j, i = grid.to_index(np.asarray(mx), np.asarray(my))
        ok = j >= 0
        flat = j[ok] * grid.NX + i[ok]
        counts[-1].ravel()[:] += np.bincount(flat, minlength=grid.NX * grid.NY).astype(np.uint32)
        v = code_idx[a.ravel()[ok]]
        sel = v >= 0
        nn_ = grid.NX * grid.NY
        counts[:-1] += np.bincount(v[sel] * nn_ + flat[sel], minlength=len(CODES) * nn_) \
            .reshape((len(CODES),) + grid.SHAPE).astype(np.uint32)
        print(f'Kachel {t}/{len(tiles)}: {w}x{h} px, Wald {sel.mean():.0%}')

    total = np.maximum(counts[-1], 1)
    species = counts[:-1] / total * 100
    frac = np.concatenate([species.sum(0, keepdims=True), species]).round().astype(np.uint8)
    os.makedirs(grid.STATIC, exist_ok=True)
    out = os.path.join(grid.STATIC, 'forest.npz')
    np.savez_compressed(out, frac=frac, codes=np.array([0] + CODES),
                        names=np.array(['wald'] + [CLASSES[c][0] for c in CODES]))
    print(f'-> {out} ({os.path.getsize(out) / 1e6:.1f} MB); Waldanteil im Raster {frac[0].mean():.1f} %')


if __name__ == '__main__':
    main()
