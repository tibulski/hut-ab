#!/usr/bin/env python3
"""Bodenfeuchte unter Kiefer, 0-30 cm, in % nFK vom Deutschen Wetterdienst (AMBAV 2.0, 1 km, CC BY 4.0).

Der DWD schreibt taeglich (~12:40 UTC) eine Jahresdatei mit allen Tagen bis gestern. Wir laden sie,
nehmen den letzten Tag und uebertragen ihn (naechster Nachbar) auf das Analyse-Raster.
Kiefer, weil ~2/3 der Brandenburger Waldflaeche Kiefer sind; fuer Laubwald waere 'beech'/'oak' passender.

Die Jahresdateien dienen auch der Kalibrierung (calibrate_gbif.py --dwd): read_year() liefert alle Tage.

Aufruf: python scripts/fetch_dwd.py   Ausgabe: data/daily/dwd_nfk.npz (nfk: float32 % nFK, datum)
"""
import datetime as dt, os, sys, tempfile, time, urllib.request
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

URL = ('https://opendata.dwd.de/climate_environment/CDC/grids_germany/daily/soil_moisture/{crop}/{y}/'
       'grids_germany_daily_soil_moisture_{crop}_{y}_{layer}_v1.nc')
CROP, LAYER = 'pine', '0-30'


def download(year, path):
    url = URL.format(crop=CROP, y=year, layer=LAYER)
    for k in range(4):
        try:
            urllib.request.urlretrieve(url, path)
            return path
        except Exception as e:
            print('  DWD:', e); time.sleep(30 * (k + 1))
    raise RuntimeError(url)


def grid_index(x, y):
    """Index (zeile, spalte) im DWD-Gitter (EPSG:31467) fuer jede Zelle des Analyse-Rasters."""
    from pyproj import Transformer
    lon, lat = grid.cell_lonlat()
    gx, gy = Transformer.from_crs(4326, 31467, always_xy=True).transform(lon, lat)
    dx, dy = x[1] - x[0], y[1] - y[0]
    i = np.round((np.asarray(gx) - x[0]) / dx).astype(int)
    j = np.round((np.asarray(gy) - y[0]) / dy).astype(int)
    ok = (i >= 0) & (i < len(x)) & (j >= 0) & (j < len(y))
    return np.where(ok, j, 0), np.where(ok, i, 0), ok


def read_year(path, days=None):
    """-> (datumsliste, Werte[t, NY, NX] in % nFK, NaN = keine Daten) fuer die gewuenschten Tagesindizes."""
    import h5py
    with h5py.File(path, 'r') as f:
        x, y = f['x'][:], f['y'][:]
        t = f['time']
        units = t.attrs['units'].decode() if isinstance(t.attrs['units'], bytes) else t.attrs['units']
        base = dt.date.fromisoformat(units.split('since')[1].strip()[:10])
        tv = t[:]
        days = range(len(tv)) if days is None else days
        jj, ii, ok = grid_index(x, y)
        var = f['paws']
        fill = float(np.ravel(var.attrs.get('_FillValue', -9999))[0])
        scale = float(np.ravel(var.attrs.get('scale_factor', 0.1))[0])
        out, dates = [], []
        for d in days:
            a = var[d].astype(np.float32)
            v = np.where(a[jj, ii] == fill, np.nan, a[jj, ii] * scale)
            out.append(np.where(ok, v, np.nan))
            dates.append((base + dt.timedelta(days=int(tv[d]))).isoformat())
    return dates, np.array(out, np.float32)


def main():
    year = dt.date.today().year
    tmp = os.path.join(tempfile.gettempdir(), f'dwd_{CROP}_{year}_{LAYER}.nc')
    if not (os.path.exists(tmp) and time.time() - os.path.getmtime(tmp) < 6 * 3600):
        download(year, tmp)
    import h5py
    with h5py.File(tmp, 'r') as f:
        n = f['time'].shape[0]
    dates, vals = read_year(tmp, [n - 1])
    out = os.path.join(grid.ROOT, 'data', 'daily', 'dwd_nfk.npz')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    np.savez_compressed(out, nfk=vals[0], datum=dates[0])
    v = vals[0][np.isfinite(vals[0])]
    print(f'DWD-Bodenfeuchte {dates[0]} ({CROP}, {LAYER} cm): Median {np.median(v):.1f} % nFK -> {out}')


if __name__ == '__main__':
    main()
