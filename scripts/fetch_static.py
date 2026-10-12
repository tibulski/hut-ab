#!/usr/bin/env python3
"""Statische Ebenen ausser Wald: Boden-pH (SoilGrids) und Schutzgebiete (LfU Brandenburg).

Boden-pH: ISRIC SoilGrids 2.0, phh2o 0-5 cm und 5-15 cm (Mittelwert), 250 m, CC BY 4.0
  https://maps.isric.org/mapserv?map=/map/phh2o.map (WCS)
  pH ist auch der beste frei verfuegbare Anzeiger fuer Kalk: pH >= ~6,5 = kalkbeeinflusst.
Schutzgebiete: LfU Brandenburg, INSPIRE-WFS https://inspire.brandenburg.de/services/schutzg_wfs,
  Datenlizenz Deutschland Namensnennung 2.0
  Code 2 = Betretungsverbot (Kernzone BR Zone I, Nationalpark Zone 1 / Totalreservat)
  Code 1 = Naturschutzgebiet bzw. NSG-Zone (Sammeln meist verboten, Verordnung pruefen)
  Berlin ist in diesem Dienst NICHT enthalten (TODO: FIS-Broker Berlin).

Ausgabe: data/static/soil.npz (ph10: uint8 pH*10, 0 = keine Daten),
         data/static/protected.npz (code: uint8)
"""
import io, json, os, sys, urllib.request
import numpy as np
import tifffile
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

SOIL = ('https://maps.isric.org/mapserv?map=/map/phh2o.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage'
        '&COVERAGEID=phh2o_{depth}_mean&FORMAT=GEOTIFF_INT16'
        '&SUBSET=X({w},{e})&SUBSET=Y({s},{n})'
        '&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326'
        '&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326')
WFS = ('https://inspire.brandenburg.de/services/schutzg_wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature'
       '&TYPENAMES=app:{t}&OUTPUTFORMAT=application/geo%2Bjson&NAMESPACES=xmlns(app,http://www.deegree.org/app)')


def get(url, timeout=600):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def soil():
    lon, lat = grid.cell_lonlat()
    acc = []
    for depth in ('0-5cm', '5-15cm'):
        a = tifffile.imread(io.BytesIO(get(SOIL.format(depth=depth, w=grid.WEST, e=grid.EAST,
                                                       s=grid.SOUTH, n=grid.NORTH))))
        h, w = a.shape
        # Pixelmitten liegen gleichmaessig zwischen den angefragten Grenzen
        ii = np.clip(((lon - grid.WEST) / (grid.EAST - grid.WEST) * w).astype(int), 0, w - 1)
        jj = np.clip(((grid.NORTH - lat) / (grid.NORTH - grid.SOUTH) * h).astype(int), 0, h - 1)
        acc.append(a[jj, ii].astype(float))
        print(f'pH {depth}: {w}x{h} px')
    a, b = acc
    ph = np.where((a > 0) & (b > 0), (a + b) / 2, np.maximum(a, b))   # Werte sind pH*10
    out = os.path.join(grid.STATIC, 'soil.npz')
    np.savez_compressed(out, ph10=np.clip(ph, 0, 255).round().astype(np.uint8))
    v = ph[ph > 0] / 10
    print(f'-> {out}; pH Median {np.median(v):.1f}, 5-95 %: {np.percentile(v, 5):.1f}-{np.percentile(v, 95):.1f}')


def load_geojson(raw):
    try:
        return json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(raw.decode('latin-1'))


def rasterize(features, value, img):
    draw = ImageDraw.Draw(img)
    for f in features:
        g = f['geometry']
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        for poly in polys:
            for k, ring in enumerate(poly):
                r = np.asarray(ring)[:, :2]
                px, py = grid.lonlat_to_pixel(r[:, 0], r[:, 1])
                pts = list(zip(px.tolist(), py.tolist()))
                if len(pts) >= 3:
                    draw.polygon(pts, fill=value if k == 0 else 0)


def protected():
    layers = {t: load_geojson(get(WFS.format(t=t))) for t in ('nsg_mz', 'natp_mz', 'br_mz')}
    nsg = [f for f in layers['nsg_mz']['features']]
    core = [f for f in layers['natp_mz']['features'] if 'Zone 1' in f['properties'].get('Flaechentyp', '')]
    core += [f for f in layers['br_mz']['features'] if 'Kernzone' in f['properties'].get('Flaechentyp', '')]
    nsg += [f for f in layers['natp_mz']['features'] if 'Zone 2' in f['properties'].get('Flaechentyp', '')]
    nsg += [f for f in layers['br_mz']['features'] if 'Pflegezone' in f['properties'].get('Flaechentyp', '')]
    # Getrennt rastern und per Maximum vereinen (Loecher eines Layers ueberschreiben sonst andere)
    code = np.zeros(grid.SHAPE, np.uint8)
    for feats, val in ((nsg, 1), (core, 2)):
        img = Image.new('L', (grid.NX, grid.NY), 0)
        rasterize(feats, val, img)
        code = np.maximum(code, np.array(img))
    out = os.path.join(grid.STATIC, 'protected.npz')
    np.savez_compressed(out, code=code)
    km2 = (grid.RES * np.cos(np.radians(52.5))) ** 2 / 1e6
    print(f'-> {out}; NSG {int((code == 1).sum() * km2)} km2, Kernzonen {int((code == 2).sum() * km2)} km2 '
          f'({len(nsg)} NSG-Flaechen, {len(core)} Kernzonen-Flaechen)')


def places():
    """Orte fuer Lagebeschreibungen der Spots aus GeoNames (CC BY 4.0), Laender DE + PL.
    Rang: 3 = Stadt > 20.000 Einw., 2 = > 2.000, 1 = Dorf/Ortsteil."""
    import zipfile
    out = []
    for cc in ('DE', 'PL'):
        z = zipfile.ZipFile(io.BytesIO(get(f'https://download.geonames.org/export/dump/{cc}.zip')))
        for line in z.read(f'{cc}.txt').decode('utf-8').splitlines():
            c = line.split('\t')
            if c[6] != 'P' or c[7] in ('PPLX', 'PPLH', 'PPLQ', 'PPLW'):
                continue
            la, lo, pop = float(c[4]), float(c[5]), int(c[14] or 0)
            if grid.SOUTH <= la <= grid.NORTH and grid.WEST <= lo <= grid.EAST:
                out.append([c[1], round(la, 4), round(lo, 4), 3 if pop > 20000 else 2 if pop > 2000 else 1])
    path = os.path.join(grid.STATIC, 'places.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'-> {path}; {len(out)} Orte')


if __name__ == '__main__':
    import urllib.parse
    os.makedirs(grid.STATIC, exist_ok=True)
    what = sys.argv[1:] or ['soil', 'protected', 'places']
    if 'soil' in what:
        soil()
    if 'protected' in what:
        protected()
    if 'places' in what:
        places()
