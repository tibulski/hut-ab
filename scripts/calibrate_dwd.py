#!/usr/bin/env python3
"""Kalibriert die Bodenwasser-Rampe fuer die DWD-Bodenfeuchte (Kiefer, 0-30 cm, % nFK) an GBIF-Funden.

Die UFZ-Schwellen (30-60 % nFK) lassen sich nicht uebertragen: das DWD-Modell AMBAV liefert unter Kiefer
im Herbst typischerweise 5-25 % nFK. Deshalb: Bodenfeuchte am Fundort (1-km-Zelle) am Fundtag gegen alle
Tage Jun-Nov derselben Orte (Hintergrund) -> Antwortkurve -> Rampe [unten, oben] = Werte, bei denen die
relative Funddichte 20 % bzw. 80 % ihres Maximums erreicht (gepoolt ueber alle Mykorrhiza-Arten).

Voraussetzung: calibrate_gbif.py hat cache/kalibrierung/gbif_*.json angelegt.
Aufruf: python scripts/calibrate_dwd.py   Ausgabe: data/kalibrierung_dwd.json
"""
import datetime as dt, glob, json, os, sys, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid
import fetch_dwd

JAHRE = range(2019, 2026)
MYKORRHIZA = ['steinpilz', 'marone', 'pfifferling', 'birkenpilz', 'rotkappe', 'butterpilz', 'edelreizker']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    import h5py
    from pyproj import Transformer
    cache = os.path.join(grid.ROOT, 'cache', 'kalibrierung')
    finds = []
    for sid in MYKORRHIZA + ['krause_glucke', 'parasol', 'hallimasch']:
        for la, lo, d in json.load(open(os.path.join(cache, f'gbif_{sid}.json'), encoding='utf-8')):
            finds.append((sid, la, lo, d))
    to_gk = Transformer.from_crs(4326, 31467, always_xy=True)
    res = {'fund': {}, 'hg': []}
    for y in JAHRE:
        path = os.path.join(tempfile.gettempdir(), f'dwd_pine_{y}_0-30.nc')
        if not os.path.exists(path):
            print('lade', y); fetch_dwd.download(y, path)
        with h5py.File(path, 'r') as f:
            x, yy = f['x'][:], f['y'][:]
            t = f['time']
            units = t.attrs['units'].decode() if isinstance(t.attrs['units'], bytes) else t.attrs['units']
            base = dt.date.fromisoformat(units.split('since')[1].strip()[:10])
            dates = [(base + dt.timedelta(days=int(v))).isoformat() for v in t[:]]
            var = f['paws']
            scale = float(np.ravel(var.attrs.get('scale_factor', 0.1))[0])
            fy = [fd for fd in finds if fd[3][:4] == str(y)]
            if not fy:
                continue
            gx, gy = to_gk.transform([fd[2] for fd in fy], [fd[1] for fd in fy])
            ii = np.round((np.asarray(gx) - x[0]) / (x[1] - x[0])).astype(int)
            jj = np.round((np.asarray(gy) - yy[0]) / (yy[1] - yy[0])).astype(int)
            idx = {d: k for k, d in enumerate(dates)}
            season = [k for k, d in enumerate(dates) if d[5:7] in ('06', '07', '08', '09', '10', '11')]
            # alle Saisontage an den Fundzellen dieses Jahres lesen (Tag fuer Tag, nur benoetigte Pixel)
            vals = np.full((len(dates), len(fy)), np.nan, np.float32)
            for k in season:
                a = var[k]
                v = a[jj, ii].astype(np.float32)
                vals[k] = np.where(v < 0, np.nan, v * scale)
            for n, fd in enumerate(fy):
                k = idx.get(fd[3])
                if k is not None and np.isfinite(vals[k, n]):
                    res['fund'].setdefault(fd[0], []).append(float(vals[k, n]))
            res['hg'] += [float(v) for v in vals[season].ravel() if np.isfinite(v)]
        print(y, len(fy), 'Funde')
    bins = np.arange(0, 102, 5.0)
    hb, _ = np.histogram(res['hg'], bins=bins)
    pooled = sum((res['fund'].get(s, []) for s in MYKORRHIZA), [])
    hf, _ = np.histogram(pooled, bins=bins)
    with np.errstate(invalid='ignore', divide='ignore'):
        r = (hf / hf.sum()) / (hb / hb.sum())
    r[hb < 200] = np.nan
    r = r / np.nanmax(r)
    # geglaettete, monotone Huelle -> Rampengrenzen
    centers = (bins[:-1] + bins[1:]) / 2
    rs = np.fmax.accumulate(np.nan_to_num(r))
    lo = float(centers[np.argmax(rs >= 0.2)])
    hi = float(centers[np.argmax(rs >= 0.8)])
    out = {'erstellt': dt.date.today().isoformat(), 'quelle': 'DWD AMBAV pine 0-30 cm, GBIF-Funde 2019-2025',
           'klassen': bins.tolist(), 'kurve_mykorrhiza': [None if np.isnan(v) else round(float(v), 2) for v in r],
           'funde_je_klasse': hf.tolist(), 'hintergrund_je_klasse': hb.tolist(),
           'median_funde': {s: round(float(np.median(v)), 1) for s, v in res['fund'].items()},
           'median_hintergrund': round(float(np.median(res['hg'])), 1),
           'rampe': [lo, hi], 'n_mykorrhiza': len(pooled)}
    json.dump(out, open(os.path.join(grid.ROOT, 'data', 'kalibrierung_dwd.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ('rampe', 'n_mykorrhiza', 'median_hintergrund', 'median_funde', 'kurve_mykorrhiza')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
