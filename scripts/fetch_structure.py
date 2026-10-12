#!/usr/bin/env python3
"""Statische Ebenen zu Standort und Bestandesstruktur, je Rasterzelle aggregiert.

  stok      Forstliche Standortskarte Brandenburg (Landesbetrieb Forst, WMS, dl-de/by-2.0):
            haeufigste Stamm-Standortsgruppe (nfgr1) je Zelle -> Naehrkraft A/Z/M/K/R, Feuchte, Nass-/Moorstandort.
            Der Dienst liefert nur Bilder: Klassen werden ueber die exakten Legendenfarben zurueckgelesen.
  hoehe     Kronenhoehe RH95 2023 (DLR EOC, Forest Structure Germany, WCS, 10 m -> 40-m-Stichprobe): Median je Zelle
  deckung   Kronendeckungsgrad 2023 (DLR EOC, WCS): Mittel je Zelle
  verlust   Kronenverlust seit 09/2017 (DLR EOC FCCL, monatlich, WCS): Anteil verlorener Waldflaeche je Zelle,
            getrennt nach "seit 2021" (frisch) und gesamt
  stickstoff  Stickstoff-Gesamtdeposition 2017-2019 (UBA PINETI, 1 km): kg N/ha/a
  ph_thuenen  Oberboden-pH 0-30 cm (Thuenen-Atlas, 1 km, aus der Bodenzustandserhebung Wald abgeleitet)

Ausgabe: data/static/struktur.npz
Aufruf:  python scripts/fetch_structure.py [stok hoehe deckung verlust stickstoff ph]
"""
import io, json, os, sys, time, urllib.parse, urllib.request
import numpy as np
import tifffile
from PIL import Image
from pyproj import Transformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

UA = {'User-Agent': 'hut-ab (Pilzprognose Berlin-Brandenburg)'}
OUT = os.path.join(grid.STATIC, 'struktur.npz')
DLR = 'https://geoservice.dlr.de/eoc/land/wcs?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&FORMAT=image/tiff'
STOK = ('https://www.brandenburg-forst.de/ogc/stok?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=stok_fskf'
        '&STYLES=kolorit&CRS=EPSG:3857&FORMAT=image/png&TRANSPARENT=true')
# Legendenfarben der Stamm-Standortsgruppen (GetLegendGraphic, kolorit)
STOK_FARBEN = {
    'A3': (255, 255, 187), 'Z3': (255, 238, 251), 'M3': (244, 254, 206), 'K3': (196, 198, 172), 'R3': (220, 220, 220),
    'A2': (255, 255, 0), 'Z2': (255, 210, 231), 'M2': (232, 255, 164), 'K2': (214, 230, 192), 'R2': (240, 240, 240),
    'A1': (255, 218, 0), 'Z1': (236, 180, 194), 'M1': (212, 230, 154), 'K1': (180, 194, 134), 'R1': (190, 190, 190),
    'NA2': (230, 230, 255), 'NZ2': (119, 232, 242), 'NM2': (242, 255, 255), 'NK2': (190, 226, 230), 'NR2': (176, 242, 255),
    'NA1': (218, 215, 255), 'NZ1': (191, 218, 242), 'NM1': (210, 255, 255), 'NK1': (174, 211, 200), 'NR1': (0, 230, 230),
    'NM0': (128, 227, 247), 'NK0': (146, 196, 200), 'NR0': (151, 206, 206), '+K0': (125, 172, 162), '+R0': (0, 175, 174),
    'OMZA4': (203, 198, 178), 'ORK4': (200, 255, 83), 'OA3': (182, 176, 132), 'OMZ3': (184, 188, 125), 'OK3': (170, 222, 75),
    'OR3': (72, 222, 171), 'OA2': (182, 172, 101), 'OMZ2': (142, 164, 73), 'ORK2': (65, 199, 73), 'OA1': (182, 158, 0),
    'OMZ1': (123, 164, 0), 'ORK1': (0, 178, 37)}
STOK_CODES = list(STOK_FARBEN)          # Index + 1 = gespeicherter Wert, 0 = keine Angabe


def get(url, timeout=600):
    for k in range(5):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            code = getattr(e, 'code', None)
            if code and code != 429 and code < 500:
                raise                                    # Anfragefehler: Wiederholen hilft nicht
            print('   Fehler:', e, '- neuer Versuch'); time.sleep(15 * (k + 1))
    raise RuntimeError(url)


def region_mask():
    """Zellen in Berlin/Brandenburg (aus der letzten UFZ-Klassifikation) bzw. mit Wald."""
    frac = np.load(os.path.join(grid.STATIC, 'forest.npz'))['frac'][0]
    return frac > 0


def accumulate(mx, my, values, valid):
    """Summe und Anzahl je Rasterzelle."""
    j, i = grid.to_index(np.asarray(mx), np.asarray(my))
    ok = (j >= 0) & valid
    flat = j[ok] * grid.NX + i[ok]
    n = grid.NX * grid.NY
    return (np.bincount(flat, weights=values[ok], minlength=n).reshape(grid.SHAPE),
            np.bincount(flat, minlength=n).reshape(grid.SHAPE))


# ------------------------------------------------------------------ Standortskarte
def stok():
    res, px = 12.0, 2500                   # <= 14 m/px, sonst zeichnet der Dienst keine Klassen
    tile = res * px
    mask = region_mask()
    pal = np.zeros(1 << 24, np.int16)
    for k, rgb in enumerate(STOK_FARBEN.values(), 1):
        pal[(rgb[0] << 16) | (rgb[1] << 8) | rgb[2]] = k
    counts = np.zeros((len(STOK_CODES) + 1, grid.NY * grid.NX), np.uint32)
    xs = np.arange(grid.X0, grid.X1, tile)
    ys = np.arange(grid.Y0, grid.Y1, tile)
    todo = []
    for x in xs:
        for y in ys:
            i0, i1 = int((x - grid.X0) // grid.RES), int((x + tile - grid.X0) // grid.RES)
            j0, j1 = int((grid.Y1 - y - tile) // grid.RES), int((grid.Y1 - y) // grid.RES)
            if mask[max(j0, 0):j1, max(i0, 0):i1].any():
                todo.append((x, y))
    for t, (x, y) in enumerate(todo, 1):
        a = np.asarray(Image.open(io.BytesIO(get(f'{STOK}&BBOX={x},{y},{x + tile},{y + tile}&WIDTH={px}&HEIGHT={px}'))).convert('RGBA'))
        rgb = a[..., :3].astype(np.int32)
        k = pal[(rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]]
        k[a[..., 3] == 0] = 0
        cx = x + (np.arange(px) + 0.5) * res
        cy = y + tile - (np.arange(px) + 0.5) * res
        i = ((cx - grid.X0) // grid.RES).astype(int)
        j = ((grid.Y1 - cy) // grid.RES).astype(int)
        J, I = np.meshgrid(j, i, indexing='ij')
        ok = (k > 0) & (J >= 0) & (J < grid.NY) & (I >= 0) & (I < grid.NX)
        flat = J[ok] * grid.NX + I[ok]
        counts += np.bincount(k[ok].astype(np.int64) * (grid.NY * grid.NX) + flat,
                              minlength=(len(STOK_CODES) + 1) * grid.NY * grid.NX).reshape(counts.shape).astype(np.uint32)
        if t % 10 == 0 or t == len(todo):
            print(f'  Standortskarte {t}/{len(todo)}')
    best = counts[1:].argmax(0) + 1
    covered = counts[1:].sum(0)
    return {'stok': np.where(covered >= 30, best, 0).reshape(grid.SHAPE).astype(np.uint8),
            'stok_codes': np.array([''] + STOK_CODES)}


# ------------------------------------------------------------------ DLR-Bestandesstruktur
def dlr_tiles(coverage, time_subset=None, scale=0.25):
    to_merc = Transformer.from_crs(4326, 3857, always_xy=True)
    for lo in np.arange(grid.WEST, grid.EAST, 1.0):
        for la in np.arange(grid.SOUTH, grid.NORTH, 1.0):
            url = (f'{DLR}&COVERAGEID={coverage}&SUBSET=Lat({la},{min(la + 1, grid.NORTH)})'
                   f'&SUBSET=Long({lo},{min(lo + 1, grid.EAST)})&SCALEFACTOR={scale}')
            if time_subset:
                url += f'&SUBSET=time(%22{time_subset}%22)'
            a = tifffile.imread(io.BytesIO(get(url))).astype(np.float32)
            h, w = a.shape
            lons = lo + (np.arange(w) + 0.5) * (min(lo + 1, grid.EAST) - lo) / w
            lats = min(la + 1, grid.NORTH) - (np.arange(h) + 0.5) * (min(la + 1, grid.NORTH) - la) / h
            LON, LAT = np.meshgrid(lons, lats)
            mx, my = to_merc.transform(LON.ravel(), LAT.ravel())
            yield np.asarray(mx), np.asarray(my), a.ravel()


def hoehe_deckung():
    out = {}
    for key, cov in (('hoehe', 'land__FOREST_STRUCTURE_DE_RH95_P1Y'), ('deckung', 'land__FOREST_STRUCTURE_DE_COVER_P1Y')):
        s = np.zeros(grid.SHAPE); n = np.zeros(grid.SHAPE)
        for mx, my, v in dlr_tiles(cov, '2023-01-01T00:00:00.000Z'):
            ds, dn = accumulate(mx, my, v, v >= 0)
            s += ds; n += dn
        out[key] = np.where(n >= 10, s / np.maximum(n, 1), np.nan).astype(np.float32)
        print(f'  {key}: Median {np.nanmedian(out[key]):.1f}')
    return out


def verlust():
    """FCCL: 0 = intakter Wald, 1..98 = Verlustmonat ab 09/2017, 255 = kein Wald."""
    to_3035 = Transformer.from_crs(4326, 3035, always_xy=True)
    to_merc = Transformer.from_crs(3035, 3857, always_xy=True)
    lost = np.zeros(grid.SHAPE); lost_new = np.zeros(grid.SHAPE); forest = np.zeros(grid.SHAPE)
    neu_ab = (2021 - 2017) * 12 + (1 - 9) + 1        # Monatsindex Jan 2021
    for lo in np.arange(grid.WEST, grid.EAST, 1.0):
        for la in np.arange(grid.SOUTH, grid.NORTH, 1.0):
            xs, ys = to_3035.transform([lo, lo + 1, lo, lo + 1], [la, la, la + 1, la + 1])
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            a = tifffile.imread(io.BytesIO(get(f'{DLR}&COVERAGEID=land__FCCL_DE_P1M&SUBSET=X({x0:.0f},{x1:.0f})'
                                               f'&SUBSET=Y({y0:.0f},{y1:.0f})&SCALEFACTOR=0.25')))
            h, w = a.shape
            X, Y = np.meshgrid(x0 + (np.arange(w) + 0.5) * (x1 - x0) / w, y1 - (np.arange(h) + 0.5) * (y1 - y0) / h)
            mx, my = to_merc.transform(X.ravel(), Y.ravel())
            v = a.ravel().astype(np.int32)
            wald = v < 255
            for target, sel in ((forest, wald), (lost, wald & (v > 0)), (lost_new, wald & (v >= neu_ab))):
                ds, _ = accumulate(mx, my, np.ones(v.size), sel)
                target += ds
    with np.errstate(invalid='ignore', divide='ignore'):
        return {'verlust': np.where(forest >= 10, lost / forest, np.nan).astype(np.float32),
                'verlust_neu': np.where(forest >= 10, lost_new / forest, np.nan).astype(np.float32)}


# ------------------------------------------------------------------ Stickstoff und Thuenen-pH
def stickstoff():
    S = 'https://datahub.uba.de/server/rest/services/Lu/Hintergrundbelastungsdaten_Stickstoff/MapServer/1/query'
    pts, vals, off = [], [], 0
    while True:
        q = {'geometry': f'{grid.WEST},{grid.SOUTH},{grid.EAST},{grid.NORTH}', 'geometryType': 'esriGeometryEnvelope',
             'inSR': 4326, 'outFields': 'f2017_2019_fluxall_n', 'returnGeometry': 'true', 'geometryPrecision': 0,
             'outSR': 3857, 'f': 'json', 'resultOffset': off, 'resultRecordCount': 2000}
        d = json.loads(get(S + '?' + urllib.parse.urlencode(q)))
        feats = d.get('features', [])
        for f in feats:
            ring = (f.get('geometry') or {}).get('rings', [[]])[0]
            if ring and f['attributes']['f2017_2019_fluxall_n'] is not None:
                r = np.asarray(ring, float)
                pts.append((r[:, 0].mean(), r[:, 1].mean()))              # Quadrat -> Mittelpunkt
                vals.append(f['attributes']['f2017_2019_fluxall_n'] * 0.014)   # eq N/ha/a -> kg N/ha/a
        off += len(feats)
        if not feats or not d.get('exceededTransferLimit'):
            break
    from scipy.spatial import cKDTree
    x, y = grid.cell_centers()
    dist, idx = cKDTree(np.array(pts)).query(np.c_[x.ravel(), y.ravel()])
    n = np.array(vals, np.float32)[idx]
    n[dist > 1500] = np.nan                         # ausserhalb Deutschlands keine Daten
    print(f'  Stickstoff: {len(vals)} km-Zellen, Median {np.nanmedian(n):.1f} kg N/ha/a')
    return {'stickstoff': n.reshape(grid.SHAPE)}


def ph_thuenen():
    """Thuenen pH 0-30 cm, 1 km, GK4 (EPSG:31468)."""
    to_gk = Transformer.from_crs(4326, 31468, always_xy=True)
    xs, ys = to_gk.transform([grid.WEST, grid.EAST, grid.WEST, grid.EAST], [grid.SOUTH, grid.SOUTH, grid.NORTH, grid.NORTH])
    x0, x1, y0, y1 = min(xs) - 2000, max(xs) + 2000, min(ys) - 2000, max(ys) + 2000
    # Achtung: Der Dienst benennt die Achsen vertauscht - "X" ist hier der Hochwert, "Y" der Rechtswert.
    # Geprueft am 12.10.2026: Zeile 0 = Norden (Ostseekueste bei 54,4 Grad N leer), Spalten = Rechtswert.
    url = ('https://atlas.thuenen.de/geoserver/ows?service=WCS&version=2.0.1&request=GetCoverage'
           f'&coverageId=geonode__pH_map_0_30&format=image/tiff&subset=X({y0:.0f},{y1:.0f})&subset=Y({x0:.0f},{x1:.0f})')
    a = tifffile.imread(io.BytesIO(get(url))).astype(np.float32)
    h, w = a.shape
    gx = x0 + (np.arange(w) + 0.5) * (x1 - x0) / w
    gy = y1 - (np.arange(h) + 0.5) * (y1 - y0) / h
    to_merc = Transformer.from_crs(31468, 3857, always_xy=True)
    X, Y = np.meshgrid(gx, gy)
    mx, my = to_merc.transform(X.ravel(), Y.ravel())
    v = a.ravel()
    ok = np.isfinite(v) & (v > 2) & (v < 10)
    from scipy.spatial import cKDTree
    cx, cy = grid.cell_centers()
    dist, idx = cKDTree(np.c_[np.asarray(mx)[ok], np.asarray(my)[ok]]).query(np.c_[cx.ravel(), cy.ravel()])
    ph = v[ok][idx]
    ph[dist > 1200] = np.nan
    print(f'  Thünen-pH: {w}x{h} px, Median {np.nanmedian(ph):.2f}')
    return {'ph_thuenen': ph.reshape(grid.SHAPE).astype(np.float32)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    what = sys.argv[1:] or ['ph', 'stickstoff', 'hoehe', 'verlust', 'stok']
    data = dict(np.load(OUT, allow_pickle=False)) if os.path.exists(OUT) else {}
    steps = {'ph': ph_thuenen, 'stickstoff': stickstoff, 'hoehe': hoehe_deckung, 'verlust': verlust, 'stok': stok}
    for w in what:
        print(w, '...')
        data.update(steps[w]())
        np.savez_compressed(OUT, **data)          # nach jedem Schritt sichern
    print('->', OUT, f'({os.path.getsize(OUT) / 1e6:.1f} MB)', sorted(data))


if __name__ == '__main__':
    main()
