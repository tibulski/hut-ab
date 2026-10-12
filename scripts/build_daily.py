#!/usr/bin/env python3
"""Pilzprognose fuer morgen: Score je Art und Rasterzelle + beste Sammelstellen.

Eingaben (vorher erzeugen):
  statisch:  data/static/forest.npz, soil.npz, protected.npz, places.json (fetch_forest.py, fetch_static.py)
  taeglich:  data/daily/ufz_BE-BB.geojson (fetch_ufz.py), data/daily/weather.json (fetch_weather.py)
  Arten:     data/arten.json, Modellparameter: data/modell.json
Ausgabe nach web/data/:
  meta.json            Datum, Arten, Sammelstellen, Quellen
  score_<art>.png      Graustufen: 0 = kein Lebensraum, 1..101 = Score 0..100
  daily.png            R = Oberboden-Duerreklasse (0-5, 255 = keine Daten), G = nFK-Klasse*10 (255 = keine)
  info.png             R = dominante Baumart-Index + 16 * Schutzstatus, G = pH*10, B = Waldanteil %
  weather.json         Wetterkennzahlen je Punkt (fuer Klick-Infos)
"""
import datetime as dt, json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid


def load_json(*p):
    with open(os.path.join(grid.ROOT, *p), encoding='utf-8') as f:
        return json.load(f)


def trapezoid(x, lo, hi, tol):
    """1 im Bereich [lo, hi], linear auf 0 im Abstand tol ausserhalb."""
    d = np.maximum(lo - x, 0) + np.maximum(x - hi, 0)
    return np.clip(1 - d / tol, 0, 1)


# ---------------------------------------------------------------- Eingaben auf das Raster bringen
def rasterize_ufz(geo):
    sm = Image.new('L', (grid.NX, grid.NY), 255)
    nfk = Image.new('L', (grid.NX, grid.NY), 255)
    ds, dn = ImageDraw.Draw(sm), ImageDraw.Draw(nfk)
    for f in geo['features']:
        r = np.asarray(f['geometry']['coordinates'][0])
        px, py = grid.lonlat_to_pixel(r[:, 0], r[:, 1])
        box = [px.min(), py.min(), px.max(), py.max()]
        ds.rectangle(box, fill=f['properties']['sm'])
        v = f['properties']['nfk']
        dn.rectangle(box, fill=255 if v is None else v)
    return np.array(sm), np.array(nfk)


WETTER_FELDER = ['regen_26', 'regentage', 'tmittel_20', 'tmittel_ziel', 'tmin_ziel', 'hitzetage', 'frostnaechte',
                 'kwb_26', 'tboden_ziel', 'dtheta']


def weather_fields(w, target, need, W, ufz_date):
    """Wetterkennzahlen fuer den Zieltag t (morgen) am naechstgelegenen Wetterpunkt, nur fuer Zellen in `need`.
    Tageswerte bis t-1 sind Beobachtung/Analyse, t ist Prognose."""
    dates = w['metadata']['dates']
    t = dates.index(target)
    p = w['points']
    arr = lambda k: np.array([[np.nan if v is None else v for v in q[k]] for q in p], float)
    rain, tmin = arr('precipitation_sum'), arr('temperature_2m_min')
    tmax, tmean = arr('temperature_2m_max'), arr('temperature_2m_mean')
    et0, theta = arr('et0_fao_evapotranspiration'), arr('soil_moisture_0_to_10cm_mean')
    tsoil = arr('soil_temperature_0_to_7cm_mean')
    u = dates.index(ufz_date) if ufz_date in dates else t - 2
    r, tc, h, fr = W['regen'], W['temperatur'], W['hitze'], W['frost']
    win = rain[:, t - r['fenster_tage']:t]                       # Tag t-26 .. t-1
    weights = np.ones(win.shape[1])
    weights[-r['frisch_tage']:] = r['frisch_gewicht']             # frischer Regen wirkt erst spaeter
    evap = et0[:, t - r['fenster_tage']:t]
    wb = r['wasserbilanz']
    pts = {
        'regen_26': np.nansum(win, axis=1),
        # Klimatische Wasserbilanz, auf die Regen-Rampe bezogen: Regen - (ET0 - Referenz-ET0)
        'regen_eff': np.nansum(win * weights, axis=1) - (
            np.nansum(evap, axis=1) - wb['et0_referenz_mm_tag'] * r['fenster_tage'] if wb['aktiv'] else 0),
        'kwb_26': np.nansum(win - evap, axis=1),
        'tboden_ziel': tsoil[:, t],
        # modellierte Aenderung der Bodenfeuchte 0-10 cm vom UFZ-Datum bis zum Zieltag
        'dtheta': theta[:, t] - theta[:, u],
        'regentage': (win >= r['regentag_mm']).sum(axis=1).astype(float),
        'tmittel_20': np.nanmean(tmean[:, t - tc['mittel_tage'] + 1:t + 1], axis=1),
        'tmittel_ziel': tmean[:, t],
        'tmin_ziel': tmin[:, t],
        'hitzetage': (tmax[:, t - h['tage'] + 1:t + 1] >= h['tmax_grad']).sum(axis=1).astype(float),
        'frostnaechte': (tmin[:, t - fr['tage'] + 1:t + 1] <= fr['tmin_grad']).sum(axis=1).astype(float),
    }
    lon, lat = grid.cell_lonlat()
    k = math.cos(math.radians(52.5))
    tree = cKDTree(np.c_[[q['lon'] for q in p], [q['lat'] for q in p]] * [k, 1])
    _, idx = tree.query(np.c_[lon[need], lat[need]] * [k, 1])
    fields = {}
    for key, v in pts.items():
        a = np.full(grid.SHAPE, np.nan, np.float32)
        a[need] = v[idx]
        fields[key] = a
    return fields, pts, p


def ramp(x, lo, hi):
    return np.clip((x - lo) / (hi - lo), 0, 1)


# ---------------------------------------------------------------- statische Standort-/Bestandesebenen
NK = 'AZMKR'


def load_layers(M):
    """Statische Zusatzebenen; fehlende Dateien/Schluessel -> None (Modell faellt auf Basisdaten zurueck)."""
    L = {}
    path = os.path.join(grid.STATIC, 'struktur.npz')
    st = dict(np.load(path)) if os.path.exists(path) else {}
    for k in ('hoehe', 'deckung', 'verlust', 'verlust_neu', 'stickstoff'):
        L[k] = st.get(k)
    L['nk'] = L['puffer'] = L['fdigit'] = None
    if 'stok' in st:
        codes = [str(c) for c in st['stok_codes']]
        nk_of = np.zeros(len(codes), np.int8)
        puf_of = np.zeros(len(codes), np.float32)
        dig_of = np.zeros(len(codes), np.int8)
        for k, c in enumerate(codes):
            if not c:
                continue
            pre = c[0] if c[0] in 'NO+' else ''
            letter = next((ch for ch in c[len(pre):] if ch in NK), '')
            nk_of[k] = NK.index(letter) + 1 if letter else 0
            puf_of[k] = M['standort']['feuchte_puffer'].get(pre, 0.0)
            dig_of[k] = int(c[-1]) if c[-1].isdigit() and not pre else 0
        L['nk'], L['puffer'], L['fdigit'] = nk_of[st['stok']], puf_of[st['stok']], dig_of[st['stok']]
    dwd = os.path.join(grid.ROOT, 'data', 'daily', 'dwd_nfk.npz')
    if os.path.exists(dwd):
        z = np.load(dwd)
        L['dwd'], L['dwd_datum'] = z['nfk'], str(z['datum'])
    else:
        L['dwd'], L['dwd_datum'] = None, None
    return L


# ---------------------------------------------------------------- Modell (Belege: docs/MODELL.md)
def species_score(art, forest, names, ph, sm, nfk, wf, month, M, L):
    """Score = 100 * Saison * Lebensraum * Standort * Bestand * Wetter.
    Wetter = gewichtetes geometrisches Mittel aus Regen/Wasserbilanz, Bodenwasser, Temperatur, Hitze,
    mal Frost-/Bodenkaelte-Abschlag. Das geometrische Mittel laesst einen limitierenden Faktor durchschlagen."""
    frac = {n: forest[k].astype(np.float32) / 100 for k, n in enumerate(names)}
    wald = frac['wald']
    host = sum(frac[n] * w for n, w in art['baeume'].items())
    edge = np.clip(4 * wald * (1 - wald), 0, 1)            # Mischzelle Wald/Offenland = Rand
    if art['habitat'] == 'waldrand':
        # Zersetzer an Waldraendern/Lichtungen: maximal bei ~50 % Waldanteil in der Zelle (Pilzfuehrer, experte)
        H = edge * host / np.maximum(wald, 1e-3)
    else:
        H = np.clip(host / M['wirt_saettigung'], 0, 1)

    # Standort: Naehrkraft der Forstlichen Standortskarte, sonst modellierter pH (SoilGrids)
    p = art['ph']
    P_raw = np.where(ph > 0, trapezoid(ph.astype(np.float32) / 10, p['opt'][0], p['opt'][1], p['toleranz']), 0.7)
    P = 1 - p['gewicht'] * (1 - np.maximum(P_raw, M['ph_boden']))
    if L['nk'] is not None:
        nkw = np.array([np.nan] + [art['naehrkraft'][c] for c in NK], np.float32)[L['nk']]
        P = np.where(np.isnan(nkw), P, nkw)

    # Bestand: Kronenhoehe, Deckungsgrad, Kronenverlust, Waldrand, Stickstoff
    BM = M['bestand']
    G = np.ones_like(wald)
    if L['hoehe'] is not None:
        hh = L['hoehe']
        if 'bestand' in art:
            lo, hi = art['bestand']['hoehe_opt']
            G = G * np.where(np.isnan(hh), 1, np.maximum(trapezoid(hh, lo, hi, art['bestand']['toleranz']), 0.3))
        elif art['habitat'] == 'mykorrhiza':
            G = G * np.where(hh < BM['hoehe_min_m'], BM['hoehe_min_faktor'], 1.0)
    if L['deckung'] is not None and art['habitat'] != 'waldrand':
        c = L['deckung']
        G = G * np.where(np.isnan(c), 1, np.where(c < BM['deckung_gering'], BM['deckung_gering_faktor'],
                                                np.where(c > BM['deckung_opt'][1] + 10, BM['deckung_dicht_faktor'], 1.0)))
    if L['verlust'] is not None:
        vn, va = np.nan_to_num(L['verlust_neu']), np.nan_to_num(L['verlust'])
        if art['id'] == 'hallimasch':
            G = G * np.minimum(1, 1 - BM['hallimasch_verlust_bonus'] / 2 + BM['hallimasch_verlust_bonus'] * va)
        elif art['habitat'] == 'mykorrhiza':
            G = G * np.clip(1 - BM['verlust_neu_abzug'] * vn - BM['verlust_alt_abzug'] * (va - vn), 0.1, 1)
    if art.get('waldrand'):
        g = BM['rand_gewicht'] * art['waldrand']
        G = G * ((1 - g) + g * edge)
    if L['stickstoff'] is not None and art.get('stickstoff_empfindlich'):
        NM = M['stickstoff']
        n_kg = np.nan_to_num(L['stickstoff'], nan=NM['rampe_kg'][0])
        G = G * (1 - art['stickstoff_empfindlich'] * NM['max_abzug'] * ramp(n_kg, *NM['rampe_kg']))

    S = art['monate'][month - 1]

    W = M['wetter']
    r, bw, tc, h, fr = W['regen'], W['bodenwasser'], W['temperatur'], W['hitze'], W['frost']
    # Regen: Rampe auf der (frisch abgewichteten, um Verdunstung korrigierten) 26-Tage-Summe, mal Regentage-Faktor
    R = ramp(wf['regen_eff'], *r['rampe_mm']) \
        * np.minimum(1, wf['regentage'] / r['regentage_voll']) ** r['regentage_exponent']
    # Bodenwasser: DWD (Kiefer 0-30 cm, kalibrierte Rampe) bzw. UFZ-nFK; jeweils bis morgen fortgeschrieben
    dtheta = 100 * np.nan_to_num(wf['dtheta']) / bw['prognose']['nfk_spanne_m3m3'] if bw['prognose']['aktiv'] else 0
    klasse = np.take(np.array(bw['ohne_nfk_nach_klasse'] + [0.5] * 250, np.float32), sm)
    B_ufz = np.where(nfk < 100, ramp(np.clip(nfk + 5.0 + dtheta, 0, 100), *bw['nfk_rampe']), klasse)
    B_ufz = np.where((sm >= bw['duerre_ab_klasse']) & (sm < 6), B_ufz * bw['duerre_faktor'], B_ufz)
    if L['dwd'] is not None and bw['dwd']['aktiv'] and bw['dwd']['rampe_nfk']:
        B = np.where(np.isfinite(L['dwd']), ramp(np.clip(L['dwd'] + dtheta, 0, 100), *bw['dwd']['rampe_nfk']), B_ufz)
    else:
        B = B_ufz
    if L['puffer'] is not None:                    # grundwassernahe/nasse Standorte puffern Trockenheit
        SO = M['standort']
        B = np.maximum(B, L['puffer'])
        B = np.where(L['fdigit'] == 1, np.minimum(1, B + SO['frisch_bonus']),
                     np.where(L['fdigit'] == 3, B * SO['trocken_faktor'], B))
    # Temperatur: Gauss-Kurve um das Art-Optimum des 20-Tage-Mittels
    T = np.exp(-((wf['tmittel_20'] - art['temp']['opt']) ** 2) / (2 * art['temp'].get('sigma', tc['sigma']) ** 2))
    X = np.maximum(1 - h['abzug_je_tag'] * wf['hitzetage'], h['minimum'])
    F = np.where(wf['frostnaechte'] >= 3, fr['faktor_drei_naechte'],
                 np.where(wf['frostnaechte'] >= 1, fr['faktor_eine_nacht'], 1.0))
    bt = W['bodentemperatur']
    F = F * np.where(wf['tboden_ziel'] < bt['grad'], bt['faktor'], 1.0)
    f, e = W['boden_min'], W['exponenten']
    Wx = (np.maximum(R, f) ** e['regen'] * np.maximum(B, f) ** e['bodenwasser']
          * np.maximum(T, f) ** e['temperatur'] * X ** e['hitze']) * F
    score = np.nan_to_num(100 * S * H * P * G * Wx, nan=0.0)
    return np.clip(score, 0, 100), H >= M['wirt_min'], {'H': H, 'P': P, 'G': G, 'R': R, 'B': B, 'T': T, 'X': X, 'F': F}


def enc01(v, mask):
    """Faktor 0..1 -> PNG-Wert 1..251 (0 = keine Daten), fuer die Neuberechnung im Browser."""
    return np.where(mask & np.isfinite(v), 1 + np.round(np.clip(np.nan_to_num(v), 0, 1) * 250), 0).astype(np.uint8)


# ---------------------------------------------------------------- Sammelstellen
DIRS = ['N', 'NO', 'O', 'SO', 'S', 'SW', 'W', 'NW']


def describe(lon, lat, places, ptree):
    """'3 km NO von Groß Schönebeck' - naechster Ort, bei Staedten bevorzugt groessere."""
    k = math.cos(math.radians(lat))
    d, i = ptree.query([lon * k, lat], k=8)
    best = min(zip(d, i), key=lambda t: t[0] / (1 + 0.3 * places[t[1]][3]))
    name, pla, plo, _ = places[best[1]]
    dx, dy = (lon - plo) * k * 111.32, (lat - pla) * 111.32
    km = math.hypot(dx, dy)
    if km < 0.7:
        return f'bei {name}'
    deg = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return f'{km:.0f} km {DIRS[int((deg + 22.5) // 45) % 8]} von {name}'


def find_spots(score, eligible, forest, names, M, places, ptree, lon, lat):
    S = M['spots']
    vals = score[eligible & (score > 0)]
    if vals.size == 0 or vals.max() < S['min_score']:
        return []
    thr = max(S['min_score'], float(np.percentile(vals, S['perzentil'])))
    lab, n = ndimage.label(eligible & (score >= thr), structure=np.ones((3, 3)))
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    cnt = ndimage.sum(np.ones_like(score), lab, idx)
    mean = ndimage.mean(score, lab, idx)
    mx = ndimage.maximum(score, lab, idx)
    cand = [(m * (1 + math.log10(c)), i, c, m, x) for i, c, m, x in zip(idx, cnt, mean, mx) if c >= S['min_zellen']]
    cand.sort(reverse=True)
    cell_ha = (grid.RES * math.cos(math.radians(52.5))) ** 2 / 1e4
    spots = []
    for rank_val, i, c, m, x in cand:
        sel = lab == i
        wgt = score[sel]
        clon, clat = float((lon[sel] * wgt).sum() / wgt.sum()), float((lat[sel] * wgt).sum() / wgt.sum())
        if any(math.hypot((clon - s['lon']) * 0.61, clat - s['lat']) * 111.32 < S['min_abstand_km'] for s in spots):
            continue
        tree_share = {n_: float(forest[k][sel].mean()) for k, n_ in enumerate(names) if k > 0}
        top = [t for t in sorted(tree_share, key=tree_share.get, reverse=True)[:2] if tree_share[t] >= 10]
        spots.append({'lon': round(clon, 4), 'lat': round(clat, 4), 'score': round(float(m)),
                      'max': round(float(x)), 'flaeche_ha': round(float(c) * cell_ha),
                      'baeume': top, 'lage': describe(clon, clat, places, ptree)})
        if len(spots) >= S['anzahl']:
            break
    return spots


# ---------------------------------------------------------------- Hauptprogramm
def prepare():
    """Laedt alle Eingaben fuer den Zieltag (morgen); auch von validate.py genutzt."""
    M = load_json('data', 'modell.json')
    fz = np.load(os.path.join(grid.STATIC, 'forest.npz'))
    forest, names = fz['frac'], [str(n) for n in fz['names']]
    ph = np.load(os.path.join(grid.STATIC, 'soil.npz'))['ph10']
    ufz = load_json('data', 'daily', 'ufz_BE-BB.geojson')
    w = load_json('data', 'daily', 'weather.json')
    target = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    if target not in w['metadata']['dates']:
        sys.exit(f'Wetterdaten enthalten den Zieltag {target} nicht - fetch_weather.py ausfuehren.')
    sm, nfk = rasterize_ufz(ufz)
    region = sm < 6                                   # nur wo der UFZ-Duerremonitor Daten hat (BE-BB)
    need = (forest[0] > 0) & region
    wf, wpts, wraw = weather_fields(w, target, need, M['wetter'], ufz['metadata']['date'])
    month = int(target[5:7])
    return {'M': M, 'forest': forest, 'names': names, 'ph': ph, 'ufz': ufz, 'w': w, 'target': target,
            'sm': sm, 'nfk': nfk, 'region': region, 'need': need, 'wf': wf, 'wpts': wpts, 'wraw': wraw,
            'month': month, 'L': load_layers(M), 'args': (forest, names, ph, sm, nfk, wf, month)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    arten = load_json('data', 'arten.json')['arten']
    prot = np.load(os.path.join(grid.STATIC, 'protected.npz'))['code']
    places = load_json('data', 'static', 'places.json')
    ptree = cKDTree(np.c_[[p[2] * math.cos(math.radians(p[1])) for p in places], [p[1] for p in places]])
    C = prepare()
    M, forest, names, ph, ufz, w, target = C['M'], C['forest'], C['names'], C['ph'], C['ufz'], C['w'], C['target']
    sm, nfk, region, need, wf, wpts, wraw = C['sm'], C['nfk'], C['region'], C['need'], C['wf'], C['wpts'], C['wraw']
    month, L = C['month'], C['L']
    lon, lat = grid.cell_lonlat()

    out = grid.WEB_DATA
    os.makedirs(out, exist_ok=True)
    credits = load_json('web', 'img', 'arten', 'credits.json')
    result = []
    parts = None
    for art in arten:
        score, habitat, parts = species_score(art, forest, names, ph, sm, nfk, wf, month, M, L)
        score[prot == 2] = 0                                    # Betretungsverbot
        img = np.where(habitat & need, 1 + np.round(score), 0).astype(np.uint8)
        Image.fromarray(img).save(os.path.join(out, f"score_{art['id']}.png"), optimize=True)
        # artspezifische Faktoren fuer die Filter im Browser: R = Partnerbaeume, G = Standort, B = Bestand
        m = habitat & need
        Image.fromarray(np.dstack([enc01(parts['H'], m), enc01(parts['P'], m), enc01(parts['G'], m)]), 'RGB') \
            .save(os.path.join(out, f"faktoren_{art['id']}.png"), optimize=True)
        eligible = habitat & need & (prot == 0)
        spots = find_spots(score, eligible, forest, names, M, places, ptree, lon, lat)
        result.append({**{k: art[k] for k in ('id', 'name', 'latein', 'info', 'vorsicht', 'monate', 'baeume')},
                       'bild': credits.get(art['id']), 'saison': art['monate'][month - 1],
                       'max': round(float(score[eligible].max())) if eligible.any() else 0, 'spots': spots})
        print(f"{art['name']:<16} Saison {art['monate'][month - 1]:.1f}  max {result[-1]['max']:3d}  "
              f"Spots {len(spots)}  {spots[0]['lage'] if spots else ''}")

    # gemeinsame Wetterfaktoren (fuer alle Arten gleich): R = Regen/Wasserbilanz, G = Bodenwasser,
    # B = 20-Tage-Temperaturmittel (Wert = 1 + (T + 10) * 5); die Temperaturkurve rechnet der Browser je Art
    t20 = np.where(need, 1 + np.clip(np.round((np.nan_to_num(wf['tmittel_20']) + 10) * 5), 0, 254), 0).astype(np.uint8)
    Image.fromarray(np.dstack([enc01(parts['R'], need), enc01(parts['B'], need), t20]), 'RGB') \
        .save(os.path.join(out, 'wetter.png'), optimize=True)
    # R = Hitze-Abschlag, G = Frost-/Bodenkaelte-Abschlag
    xf = lambda v: v if np.ndim(v) else np.full(grid.SHAPE, v, np.float32)
    Image.fromarray(np.dstack([enc01(xf(parts['X']), need), enc01(xf(parts['F']), need), np.zeros(grid.SHAPE, np.uint8)]), 'RGB') \
        .save(os.path.join(out, 'wetter2.png'), optimize=True)
    # Orte fuer Lagebeschreibungen der im Browser berechneten Stellen (nur im Gebiet)
    with open(os.path.join(out, 'orte.json'), 'w', encoding='utf-8') as f:
        json.dump([p for p in places if grid.SOUTH <= p[1] <= grid.NORTH and grid.WEST <= p[2] <= grid.EAST],
                  f, ensure_ascii=False, separators=(',', ':'))

    # Klick-Infos: statisch (Baumart, pH, Wald, Schutz) und taeglich (Duerre, nFK)
    dom = np.where(forest[0] >= 10, forest[1:].argmax(0) + 1, 0)
    info = np.dstack([dom + 16 * prot, ph, forest[0]]).astype(np.uint8) * region[..., None]
    Image.fromarray(info, 'RGB').save(os.path.join(out, 'info.png'), optimize=True)
    dwd = np.where(np.isfinite(L['dwd']), np.clip(np.round(L['dwd']), 0, 100), 255).astype(np.uint8)         if L['dwd'] is not None else np.full_like(sm, 255)
    Image.fromarray(np.dstack([sm, nfk, dwd * region]), 'RGB').save(os.path.join(out, 'daily.png'), optimize=True)
    # Standort/Bestand fuer Klick-Infos: R = Standortsgruppe (Index), G = Kronenhoehe m, B = Kronendeckung %
    st_path = os.path.join(grid.STATIC, 'struktur.npz')
    if os.path.exists(st_path):
        st = np.load(st_path)
        enc = lambda a: np.where(np.isfinite(a), np.clip(np.round(a), 0, 254), 255).astype(np.uint8)
        std = np.dstack([st['stok'] if 'stok' in st else np.zeros(grid.SHAPE, np.uint8), enc(st['hoehe']), enc(st['deckung'])])
        Image.fromarray((std * region[..., None]).astype(np.uint8), 'RGB').save(os.path.join(out, 'standort.png'), optimize=True)
    with open(os.path.join(out, 'weather.json'), 'w', encoding='utf-8') as f:
        json.dump([[q['lon'], q['lat']] + [round(float(wpts[k][i]), 1) for k in WETTER_FELDER]
                   for i, q in enumerate(wraw)], f, separators=(',', ':'))

    meta = {'zieltag': target, 'erstellt': dt.datetime.now().isoformat(timespec='minutes'),
            'ufz_datum': ufz['metadata']['date'], 'wetter_abruf': w['metadata']['abgerufen'],
            'bounds': grid.leaflet_bounds(), 'groesse': [grid.NX, grid.NY],
            'raster': {'x0': grid.X0, 'y1': grid.Y1, 'res': grid.RES},
            'standort_codes': [str(c) for c in np.load(os.path.join(grid.STATIC, 'struktur.npz'))['stok_codes']]
            if os.path.exists(os.path.join(grid.STATIC, 'struktur.npz')) else [],
            'dwd_datum': L['dwd_datum'],
            'baumarten': names[1:], 'wetter_felder': WETTER_FELDER,
            # Formel fuer die Neuberechnung im Browser (identisch zu species_score)
            'modell': {'exponenten': M['wetter']['exponenten'], 'boden_min': M['wetter']['boden_min'],
                       'sigma': M['wetter']['temperatur']['sigma'],
                       'temp': {a['id']: a['temp'] for a in arten}},
            'arten': result}
    with open(os.path.join(out, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    print('->', out)


if __name__ == '__main__':
    main()
