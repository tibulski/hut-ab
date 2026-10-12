#!/usr/bin/env python3
"""Artbilder fuer die Auswahlliste von Wikimedia Commons (Hauptbild des de.wikipedia-Artikels).

Speichert 480-px-Vorschaubilder nach web/img/arten/<id>.jpg und Urheber/Lizenz nach
web/img/arten/credits.json. Nur freie Lizenzen (CC0, CC BY, CC BY-SA, Public Domain).
Einmalig bzw. bei Aenderung der Artenliste ausfuehren.
"""
import json, os, re, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid

UA = {'User-Agent': 'hut-ab/0.1 (Pilzkarte Berlin-Brandenburg; https://github.com/tibulski/hut-ab)'}
# de.wikipedia-Artikel je Art (Weiterleitungen werden aufgeloest)
ARTIKEL = {'steinpilz': 'Gemeiner Steinpilz', 'marone': 'Maronen-Röhrling', 'pfifferling': 'Echter Pfifferling',
           'birkenpilz': 'Gemeiner Birkenpilz', 'rotkappe': ['Heide-Rotkappe', 'Espen-Rotkappe', 'Rotkappen'], 'butterpilz': 'Butter-Röhrling',
           'krause_glucke': 'Krause Glucke', 'parasol': 'Parasol (Pilz)', 'hallimasch': 'Hallimasche',
           'edelreizker': 'Echter Reizker'}
# Fallback: Commons-Suche nach lateinischem Namen, wenn Artikelbild fehlt oder nicht frei lizenziert ist
LATEIN = {'krause_glucke': 'Sparassis crispa', 'parasol': 'Macrolepiota procera'}
FREE = re.compile(r'^(CC0|CC BY(-SA)? [\d.]+( \w+)?|Public domain|PD.*)$', re.I)


def api(base, **q):
    q.update(format='json', formatversion=2)
    req = urllib.request.Request(base + '?' + urllib.parse.urlencode(q), headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=60))


def strip_html(s):
    return re.sub(r'<[^>]+>', '', s or '').strip()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    out_dir = os.path.join(grid.ROOT, 'web', 'img', 'arten')
    os.makedirs(out_dir, exist_ok=True)
    credits = {}
    for sid, title in ARTIKEL.items():
        for t in ([title] if isinstance(title, str) else title):
            p = api('https://de.wikipedia.org/w/api.php', action='query', titles=t, redirects=1,
                    prop='pageimages', piprop='name')['query']['pages'][0]
            name = p.get('pageimage')
            if name:
                break
        cands = ['File:' + name] if name else []
        if sid in LATEIN:
            hits = api('https://commons.wikimedia.org/w/api.php', action='query', list='search', srnamespace=6,
                       srsearch=LATEIN[sid] + ' filetype:bitmap', srlimit=15)['query']['search']
            cands += [h['title'] for h in hits if h['title'].lower().endswith(('.jpg', '.jpeg'))]
        for cand in cands:
            ii = api('https://commons.wikimedia.org/w/api.php', action='query', titles=cand,
                     prop='imageinfo', iiprop='url|extmetadata', iiurlwidth=480)['query']['pages'][0]['imageinfo'][0]
            meta = ii['extmetadata']
            lic = meta.get('LicenseShortName', {}).get('value', '')
            if FREE.match(lic):
                name = cand.removeprefix('File:')
                break
        else:
            print(sid, 'kein frei lizenziertes Bild gefunden'); continue
        req = urllib.request.Request(ii['thumburl'], headers=UA)
        with open(os.path.join(out_dir, sid + '.jpg'), 'wb') as f:
            f.write(urllib.request.urlopen(req, timeout=60).read())
        credits[sid] = {'datei': name, 'urheber': strip_html(meta.get('Artist', {}).get('value')),
                        'lizenz': lic, 'lizenz_url': meta.get('LicenseUrl', {}).get('value', ''),
                        'quelle': ii['descriptionurl']}
        print(sid, name, '|', lic, '|', credits[sid]['urheber'][:60])
    with open(os.path.join(out_dir, 'credits.json'), 'w', encoding='utf-8') as f:
        json.dump(credits, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
