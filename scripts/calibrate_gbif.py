#!/usr/bin/env python3
"""Kalibrierung der Artparameter mit Fundmeldungen (GBIF) und historischem Wetter (ERA5 via Open-Meteo).

Vorgehen (Presence-only mit Ziel-Gruppen-Hintergrund):
- Saison: Funde je Monat / alle Pilzmeldungen (Fungi) je Monat in derselben Region -> korrigiert den
  Beobachtungsaufwand (im Herbst wird generell mehr gemeldet). Normiert auf das Maximum, mit der
  Expertenkurve geschrumpft: w = n / (n + 150).
- Temperatur und Wasserbilanz: fuer jeden Fund das 20-Tage-Temperaturmittel und die 26-Tage-Wasserbilanz
  (Regen - ET0) vor dem Fundtag; verglichen mit allen Tagen Jun-Nov derselben Orte (Hintergrund).
  Antwortkurve = Dichte(Funde) / Dichte(Hintergrund); daraus Optimum und Breite (Gauss-Fit).
Grenzen: Funde sind keine Ertragsdaten, Meldungen haeufen sich an Wochenenden, in Stadtnaehe und an Wegen.
Die raeumliche Verzerrung kuerzt sich beim Wetter weitgehend heraus, weil der Hintergrund dieselben Orte nutzt.

Aufruf: python scripts/calibrate_gbif.py [--apply]   (--apply schreibt Saison/Temperatur nach data/arten.json)
Ausgabe: data/kalibrierung.json, docs/KALIBRIERUNG.md
"""
import argparse, datetime as dt, json, math, os, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

GBIF = 'https://api.gbif.org/v1/'
ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
JAHRE = (2019, 2025)            # 2019+ enthaelt ~90 % der Funde; schont das Open-Meteo-Kontingent
ZELLE = 0.5                      # Grad; ERA5 hat 0,25 Grad, fuer Temperatur/Wasserbilanz reicht 0,5
TAXA = {'steinpilz': ['Boletus edulis'], 'marone': ['Imleria badia'], 'pfifferling': ['Cantharellus cibarius'],
        'birkenpilz': ['Leccinum scabrum'], 'rotkappe': ['Leccinum versipelle', 'Leccinum aurantiacum', 'Leccinum albostipitatum'],
        'butterpilz': ['Suillus luteus'], 'krause_glucke': ['Sparassis crispa'], 'parasol': ['Macrolepiota procera'],
        'hallimasch': ['Armillaria'], 'edelreizker': ['Lactarius deliciosus']}
CACHE = os.path.join(grid.ROOT, 'cache', 'kalibrierung')
REGION = {'decimalLatitude': f'{grid.SOUTH},{grid.NORTH}', 'decimalLongitude': f'{grid.WEST},{grid.EAST}',
          'hasCoordinate': 'true', 'hasGeospatialIssue': 'false', 'basisOfRecord': 'HUMAN_OBSERVATION',
          'year': f'{JAHRE[0]},{JAHRE[1]}'}


def get_json(url, tries=5):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'hut-ab (Pilzprognose Berlin-Brandenburg)'})
            return json.load(urllib.request.urlopen(req, timeout=120))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            code = getattr(e, 'code', None)
            if code and code not in (429,) and code < 500:
                raise
            print('  warte ...', e, flush=True); time.sleep(60 * (k + 1))   # Kontingent/Stoerung: laenger warten
    raise RuntimeError(url)


def cached(name, fn):
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    data = fn()
    json.dump(data, open(path, 'w', encoding='utf-8'))
    return data


def taxon_key(name):
    return get_json(GBIF + 'species/match?' + urllib.parse.urlencode({'name': name, 'kingdom': 'Fungi'}))['usageKey']


def occurrences(keys):
    out, off = [], 0
    while True:
        q = dict(REGION, limit=300, offset=off)
        url = GBIF + 'occurrence/search?' + urllib.parse.urlencode(q) + ''.join(f'&taxonKey={k}' for k in keys)
        d = get_json(url)
        for r in d['results']:
            unc = r.get('coordinateUncertaintyInMeters')
            if r.get('eventDate') and r.get('month') and (unc is None or unc <= 2000):
                out.append([round(r['decimalLatitude'], 4), round(r['decimalLongitude'], 4), r['eventDate'][:10]])
        off += 300
        if d['endOfRecords'] or off >= d['count']:
            return out


def month_effort():
    """Alle Pilzmeldungen je Monat (Ziel-Gruppen-Hintergrund)."""
    q = dict(REGION, limit=0, facet='month', **{'facetLimit': 12})
    d = get_json(GBIF + 'occurrence/search?' + urllib.parse.urlencode(q) + '&taxonKey=5')
    return {int(c['name']): c['count'] for c in d['facets'][0]['counts']}


def cell_of(lat, lon):
    return (round(math.floor(lat / ZELLE) * ZELLE + ZELLE / 2, 3), round(math.floor(lon / ZELLE) * ZELLE + ZELLE / 2, 3))


def weather_history(cells):
    """ERA5-Tageswerte (Tmittel, Regen, ET0) Jun-Nov je Jahr und Zelle. ~70 Abrufgewichte je Zelle."""
    hist = {}
    for c in cells:
        key = f'{c[0]}_{c[1]}'
        def fetch():
            days, tm, pr, et = [], [], [], []
            for y in range(JAHRE[0], JAHRE[1] + 1):
                q = {'latitude': c[0], 'longitude': c[1], 'start_date': f'{y}-05-01', 'end_date': f'{y}-11-30',
                     'daily': 'temperature_2m_mean,precipitation_sum,et0_fao_evapotranspiration', 'timezone': 'Europe/Berlin'}
                d = get_json(ARCHIVE + '?' + urllib.parse.urlencode(q))['daily']
                days += d['time']; tm += d['temperature_2m_mean']; pr += d['precipitation_sum']; et += d['et0_fao_evapotranspiration']
                time.sleep(6)          # Archiv-Kontingent: ~15 Gewichtseinheiten je Abruf
            return {'days': days, 't': tm, 'p': pr, 'e': et}
        hist[key] = cached(f'era5_{key}.json', fetch)
        print('  Wetter', key)
    return hist


def indicators(h):
    """T20 und KWB26 fuer jeden Tag ab Juni (Mai dient als Vorlauf)."""
    days = h['days']
    t = np.array([np.nan if v is None else v for v in h['t']], float)
    p = np.array([np.nan if v is None else v for v in h['p']], float)
    e = np.array([np.nan if v is None else v for v in h['e']], float)
    res = {}
    for i, d in enumerate(days):
        if d[5:7] in ('05',) or i < 30 or days[i - 30][:4] != d[:4]:
            continue
        res[d] = (float(np.nanmean(t[i - 19:i + 1])), float(np.nansum(p[i - 26:i] - e[i - 26:i])),
                  float(np.nansum(p[i - 26:i])))
    return res


def response(x_find, x_bg, bins):
    """Dichteverhaeltnis Funde/Hintergrund je Klasse, auf Maximum 1 normiert."""
    hf, _ = np.histogram(x_find, bins=bins)
    hb, _ = np.histogram(x_bg, bins=bins)
    with np.errstate(invalid='ignore', divide='ignore'):
        r = (hf / max(hf.sum(), 1)) / (hb / max(hb.sum(), 1))
    r[hb < 20] = np.nan
    return r / np.nanmax(r), hf


def gauss_fit(centers, r, n):
    """Gewichteter Gauss-Fit auf das Dichteverhaeltnis (Gewichte = Fundzahl je Klasse)."""
    ok = ~np.isnan(r) & (n > 0)
    best = None
    for mu in np.arange(5, 22.01, 0.25):
        for sg in np.arange(2, 8.01, 0.25):
            g = np.exp(-(centers[ok] - mu) ** 2 / (2 * sg ** 2))
            err = np.sum(n[ok] * (r[ok] - g) ** 2)
            if best is None or err < best[0]:
                best = (err, mu, sg)
    return best[1], best[2]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    arten = json.load(open(os.path.join(grid.ROOT, 'data', 'arten.json'), encoding='utf-8'))

    effort = cached('effort_month.json', month_effort)
    effort = {int(k): v for k, v in effort.items()}
    finds = {}
    for sid, names in TAXA.items():
        keys = [taxon_key(n) for n in names]
        finds[sid] = cached(f'gbif_{sid}.json', lambda: occurrences(keys))
        print(f'{sid:<14} {len(finds[sid])} Funde')

    cells = sorted({cell_of(la, lo) for f in finds.values() for la, lo, _ in f})
    print(len(cells), 'Wetterzellen')
    hist = weather_history(cells)
    ind = {k: indicators(h) for k, h in hist.items()}

    T_BINS = np.arange(0, 26.01, 2.0)
    K_BINS = np.array([-140, -100, -70, -50, -35, -20, -10, 0, 10, 25, 45, 70, 120, 300], float)
    result, pooled_k, pooled_kbg = {}, [], []
    for art in arten['arten']:
        sid = art['id']
        f = finds[sid]
        n = len(f)
        # Saison
        cnt = Counter(int(d[5:7]) for _, _, d in f)
        rate = np.array([cnt.get(m, 0) / effort.get(m, 1) for m in range(1, 13)])
        emp = rate / rate.max() if rate.max() > 0 else rate
        w = n / (n + 150)
        monate = [round(float(w * e + (1 - w) * x), 2) for e, x in zip(emp, art['monate'])]
        # Wetter bei Fund vs. Hintergrund
        tf, kf, tb, kb = [], [], [], []
        per_cell = Counter()
        for la, lo, d in f:
            c = cell_of(la, lo)
            v = ind[f'{c[0]}_{c[1]}'].get(d)
            if v:
                tf.append(v[0]); kf.append(v[1]); per_cell[c] += 1
        for c, k in per_cell.items():           # Hintergrund mit Fundzahl je Zelle gewichtet
            vals = list(ind[f'{c[0]}_{c[1]}'].values())
            tb += [v[0] for v in vals] * k; kb += [v[1] for v in vals] * k
        rt, nt = response(np.array(tf), np.array(tb), T_BINS)
        rk, nk = response(np.array(kf), np.array(kb), K_BINS)
        tc = (T_BINS[:-1] + T_BINS[1:]) / 2
        mu, sg = gauss_fit(tc, rt, nt) if len(tf) >= 40 else (None, None)
        pooled_k += kf; pooled_kbg += kb
        result[sid] = {'n': n, 'n_wetter': len(tf), 'monate_empirisch': [round(float(x), 2) for x in emp],
                       'monate_kalibriert': monate, 'gewicht_empirie': round(w, 2),
                       't20_median_funde': round(float(np.median(tf)), 1) if tf else None,
                       't_opt': mu, 't_sigma': sg, 't_kurve': [None if np.isnan(x) else round(float(x), 2) for x in rt],
                       'kwb_median_funde': round(float(np.median(kf)), 1) if kf else None,
                       'kwb_kurve': [None if np.isnan(x) else round(float(x), 2) for x in rk]}
        print(f"{sid:<14} n={n:4d}  T20 Funde Median {result[sid]['t20_median_funde']}  T_opt {mu} sigma {sg}  "
              f"KWB Median {result[sid]['kwb_median_funde']}")
    rk_all, nk_all = response(np.array(pooled_k), np.array(pooled_kbg), K_BINS)
    out = {'erstellt': dt.date.today().isoformat(), 'jahre': JAHRE, 'quelle': 'GBIF (HUMAN_OBSERVATION), ERA5 via Open-Meteo',
           'aufwand_monat': effort, 't_klassen': T_BINS.tolist(), 'kwb_klassen': K_BINS.tolist(),
           'kwb_kurve_alle': [None if np.isnan(x) else round(float(x), 2) for x in rk_all],
           'kwb_funde_je_klasse_alle': nk_all.tolist(), 'arten': result}
    json.dump(out, open(os.path.join(grid.ROOT, 'data', 'kalibrierung.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    write_report(out, arten)
    if args.apply:
        for art in arten['arten']:
            r = result[art['id']]
            art['monate'] = r['monate_kalibriert']
            if r['t_opt'] is not None and r['n_wetter'] >= 100:
                art['temp']['opt'] = round(r['t_opt'], 2)
                art['temp']['sigma'] = round(r['t_sigma'], 2)
                art['temp']['quelle'] = f"GBIF-Kalibrierung {out['erstellt']} (n={r['n_wetter']})"
        with open(os.path.join(grid.ROOT, 'data', 'arten.json'), 'w', encoding='utf-8') as fh:
            json.dump(arten, fh, ensure_ascii=False, indent=2)
        print('-> data/arten.json aktualisiert')


def write_report(out, arten):
    M = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
    L = ['# Kalibrierung mit Fundmeldungen', '',
         f"Erstellt {out['erstellt']} mit `scripts/calibrate_gbif.py`. Daten: GBIF-Beobachtungen {out['jahre'][0]}–{out['jahre'][1]} "
         'im Analysegebiet (iNaturalist, naturgucker, Observation.org u. a.), Wetter: ERA5 (Open-Meteo-Archiv), 0,5°-Zellen.', '',
         '**Lesart:** Die Kurven sind Verhältnisse „Anteil der Funde / Anteil der Hintergrundtage“ (normiert auf 1). '
         'Sie zeigen, bei welchen Bedingungen Funde *überproportional* gemeldet werden. Es sind keine Ertragsdaten.', '',
         '## Saison (Funde je Monat ÷ alle Pilzmeldungen je Monat, normiert)', '',
         '| Art | n | ' + ' | '.join(M[4:12]) + ' |', '|---|---|' + '---|' * 8]
    for art in arten['arten']:
        r = out['arten'][art['id']]
        L.append(f"| {art['name']} | {r['n']} | " + ' | '.join(f"{x:.2f}" for x in r['monate_empirisch'][4:12]) + ' |')
    L += ['', '## Temperatur (20-Tage-Mittel vor dem Fund)', '',
          '| Art | Funde mit Wetter | Median T20 der Funde | Optimum (Gauss-Fit) | Breite σ | bisher (Experte) |', '|---|---|---|---|---|---|']
    for art in arten['arten']:
        r = out['arten'][art['id']]
        L.append(f"| {art['name']} | {r['n_wetter']} | {r['t20_median_funde']} °C | "
                 f"{'' if r['t_opt'] is None else str(r['t_opt']) + ' °C'} | {'' if r['t_sigma'] is None else r['t_sigma']} | {art['temp']['opt']} °C |")
    kb = out['kwb_klassen']
    L += ['', '## Wasserbilanz (Regen − ET0, 26 Tage vor dem Fund), alle Arten', '',
          '| KWB-Klasse (mm) | relative Funddichte | Funde |', '|---|---|---|']
    for i, (v, nn) in enumerate(zip(out['kwb_kurve_alle'], out['kwb_funde_je_klasse_alle'])):
        L.append(f"| {kb[i]:.0f} … {kb[i + 1]:.0f} | {'' if v is None else v} | {int(nn)} |")
    L += ['', 'Grenzen: Presence-only-Daten mit Beobachtungsverzerrung (Wochenenden, Stadtnähe, Wege); '
          'Funddatum ≠ Erscheinungsdatum; Rotkappe hat nur wenige Funde.']
    open(os.path.join(grid.ROOT, 'docs', 'KALIBRIERUNG.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
