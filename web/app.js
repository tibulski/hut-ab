/* Hut ab! – Pilzprognose Berlin/Brandenburg
 *
 * Startansicht: Artauswahl ("Was suchst du?").
 * Kartenansicht: Chance fuer morgen, einzeln zu- und abschaltbare Faktoren, Top-Stellen im gewaehlten Umkreis,
 * "Warum hier?"-Aufschluesselung per Klick.
 *
 * Die Chance wird im Browser aus den Faktor-Rastern neu berechnet (gleiche Formel wie scripts/build_daily.py):
 *   Chance = 100 * Saison * Baeume * Standort * Bestand
 *            * Regen^eR * Bodenwasser^eB * Temperatur^eT * Hitze^eX * Frost
 */
(() => {
  'use strict';

  // ------------------------------------------------------------ Konstanten
  const TREE_NAMES = {
    birke: 'Birke', buche: 'Buche', douglasie: 'Douglasie', eiche: 'Eiche', erle: 'Erle', fichte: 'Fichte',
    kiefer: 'Kiefer', laerche: 'Lärche', tanne: 'Tanne', laub_lang: 'sonst. Laubholz', laub_kurz: 'Pappel/Weide u. a.',
  };
  const SM_NAMES = ['keine Dürre', 'ungewöhnlich trocken', 'moderate Dürre', 'schwere Dürre', 'extreme Dürre', 'außergewöhnliche Dürre'];
  const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
  const MONTHS_LONG = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  const FACTORS = [
    { id: 'H', icon: '🌲', name: 'Partnerbäume', desc: 'Anteil passender Mykorrhiza- bzw. Wirtsbäume' },
    { id: 'P', icon: '🪨', name: 'Boden & Standort', desc: 'Nährkraft der Forstlichen Standortskarte (sonst Boden-pH)' },
    { id: 'G', icon: '📏', name: 'Bestand', desc: 'Baumhöhe, Kronendichte, Kahlflächen, Waldrand, Stickstoff' },
    { id: 'B', icon: '💧', name: 'Bodenfeuchte', desc: 'Bodenwasser (DWD/UFZ), bis morgen fortgeschrieben' },
    { id: 'R', icon: '🌧️', name: 'Regen & Wasserbilanz', desc: 'Regen minus Verdunstung der letzten 26 Tage' },
    { id: 'T', icon: '🌡️', name: 'Temperatur', desc: '20-Tage-Mittel im Vergleich zum Optimum der Art' },
    { id: 'XF', icon: '❄️', name: 'Hitze & Frost', desc: 'Abschläge für Hitzetage, Frostnächte, kalten Boden' },
  ];
  // warme Farbskala, hebt sich vom Gruen der Karte ab
  const STOPS = [[0, [255, 237, 160]], [15, [254, 196, 79]], [30, [245, 128, 37]], [45, [214, 60, 35]], [60, [150, 20, 60]], [80, [84, 10, 72]]];
  const STOPS_FACTOR = [[0, [215, 48, 39]], [25, [252, 141, 89]], [50, [254, 224, 139]], [75, [145, 207, 96]], [100, [26, 152, 80]]];
  const BERLIN = { lat: 52.5219, lon: 13.4132, label: 'Berlin' };
  const R_EARTH = 6378137;

  const $ = (id) => document.getElementById(id);
  const state = {
    meta: null, species: null, grids: {}, weather: [], recent: null, orte: [],
    on: Object.fromEntries(FACTORS.map((f) => [f.id, true])), view: 'score',
    start: { ...BERLIN }, radius: 80, score: null, g: null, spots: [], lonOfCol: null, latOfRow: null,
    layers: {}, mapReady: false,
  };

  // ------------------------------------------------------------ Hilfsfunktionen
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function colorFor(v, stops) {
    for (let i = 1; i < stops.length; i++) {
      if (v <= stops[i][0]) {
        const [a, ca] = stops[i - 1], [b, cb] = stops[i];
        const t = (v - a) / (b - a);
        return ca.map((c, k) => Math.round(c + t * (cb[k] - c)));
      }
    }
    return stops[stops.length - 1][1];
  }
  const gradientCss = (stops, max) => `linear-gradient(90deg, ${stops.map(([v, c]) => `rgb(${c}) ${(v / max) * 100}%`).join(',')})`;
  const escapeHtml = (s) => String(s || '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const fmtDate = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
  function km(lat1, lon1, lat2, lon2) {
    const k = Math.cos(((lat1 + lat2) / 2) * Math.PI / 180);
    return Math.hypot((lon1 - lon2) * k, lat1 - lat2) * 111.32;
  }
  function chance(score) {
    if (score >= 60) return { label: 'sehr gut', color: '#7a1450' };
    if (score >= 40) return { label: 'gut', color: '#d63c23' };
    if (score >= 20) return { label: 'mäßig', color: '#f58025' };
    return { label: 'schwach', color: '#fec44f' };
  }

  function loadImageData(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        resolve(ctx.getImageData(0, 0, c.width, c.height).data);
      };
      img.onerror = () => reject(new Error('Bild nicht ladbar: ' + url));
      img.src = url;
    });
  }
  function grid(name) {
    if (!state.grids[name]) state.grids[name] = loadImageData(`data/${name}.png?v=${state.meta.erstellt}`);
    return state.grids[name];
  }
  function canvasUrl(fill) {
    const [w, h] = state.meta.groesse;
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const img = ctx.createImageData(w, h);
    fill(img.data, w, h);
    ctx.putImageData(img, 0, 0);
    return c.toDataURL();
  }
  function cellIndex(latlng) {
    const r = state.meta.raster;
    const x = R_EARTH * latlng.lng * Math.PI / 180;
    const y = R_EARTH * Math.log(Math.tan(Math.PI / 4 + latlng.lat * Math.PI / 360));
    const col = Math.floor((x - r.x0) / r.res), row = Math.floor((r.y1 - y) / r.res);
    const [w, h] = state.meta.groesse;
    return col >= 0 && col < w && row >= 0 && row < h ? row * w + col : -1;
  }
  function precomputeCoords() {
    const r = state.meta.raster, [w, h] = state.meta.groesse;
    state.lonOfCol = new Float32Array(w);
    state.latOfRow = new Float32Array(h);
    for (let c = 0; c < w; c++) state.lonOfCol[c] = ((r.x0 + (c + 0.5) * r.res) / R_EARTH) * 180 / Math.PI;
    for (let rr = 0; rr < h; rr++) state.latOfRow[rr] = (2 * Math.atan(Math.exp((r.y1 - (rr + 0.5) * r.res) / R_EARTH)) - Math.PI / 2) * 180 / Math.PI;
  }

  // ------------------------------------------------------------ Modell im Browser
  async function loadSpeciesGrids(sp) {
    const [fa, we, w2, info] = await Promise.all([grid('faktoren_' + sp.id), grid('wetter'), grid('wetter2'), grid('info')]);
    return { fa, we, w2, info };
  }
  const dec = (v) => (v - 1) / 250;

  /** alle Faktoren einer Zelle (0..1); null = kein Lebensraum */
  function cellFactors(g, i, sp) {
    const j = i * 4;
    if (g.fa[j] === 0) return null;
    const m = state.meta.modell;
    const t = m.temp[sp.id];
    const t20 = (g.we[j + 2] - 1) / 5 - 10;
    const sigma = t.sigma || m.sigma;
    return {
      H: dec(g.fa[j]), P: dec(g.fa[j + 1]), G: dec(g.fa[j + 2]),
      R: g.we[j] ? dec(g.we[j]) : 1, B: g.we[j + 1] ? dec(g.we[j + 1]) : 1,
      T: Math.exp(-((t20 - t.opt) ** 2) / (2 * sigma * sigma)),
      XF: (g.w2[j] ? dec(g.w2[j]) : 1) ** m.exponenten.hitze * (g.w2[j + 1] ? dec(g.w2[j + 1]) : 1),
      t20, prot: g.info[j] >> 4,
    };
  }
  function combine(f, sp, on) {
    const m = state.meta.modell, e = m.exponenten, fl = m.boden_min;
    let s = 100 * sp.saison;
    if (on.H) s *= f.H;
    if (on.P) s *= f.P;
    if (on.G) s *= f.G;
    if (on.R) s *= Math.max(f.R, fl) ** e.regen;
    if (on.B) s *= Math.max(f.B, fl) ** e.bodenwasser;
    if (on.T) s *= Math.max(f.T, fl) ** e.temperatur;
    if (on.XF) s *= f.XF;
    return f.prot === 2 ? 0 : clamp(s, 0, 100);
  }

  async function recompute() {
    const sp = state.species;
    const g = await loadSpeciesGrids(sp);
    if (state.species !== sp) return;           // inzwischen andere Art gewaehlt
    const [w, h] = state.meta.groesse, n = w * h;
    const score = new Float32Array(n).fill(-1);
    const view = state.view !== 'score' ? new Float32Array(n).fill(-1) : null;
    for (let i = 0; i < n; i++) {
      const f = cellFactors(g, i, sp);
      if (!f) continue;
      score[i] = combine(f, sp, state.on);
      if (view) view[i] = f[state.view];
    }
    state.score = score;
    state.g = g;
    drawOverlay(view);
    findSpots();
  }

  // ------------------------------------------------------------ Karte
  let map;
  function initMap() {
    const mobile = window.matchMedia('(max-width: 760px)').matches;
    map = L.map('map', { zoomControl: !mobile, minZoom: 7, maxZoom: 17, attributionControl: false }).setView([52.45, 13.4], 8);
    L.control.attribution({ position: mobile ? 'topleft' : 'bottomright', prefix: false }).addTo(map);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · UFZ, DWD, Thünen, LFB, DLR, LfU',
    }).addTo(map);
    map.createPane('scorePane').style.zIndex = 350;
    map.createPane('protPane').style.zIndex = 360;
    map.on('click', (e) => openWhy(e.latlng));
    state.layers.spots = L.layerGroup().addTo(map);
    state.layers.recent = L.layerGroup().addTo(map);
    state.layers.reach = L.layerGroup().addTo(map);
    state.mapReady = true;
    showProtected();
    initLive();
  }

  // Live-Standort: blauer Punkt mit Genauigkeitskreis, solange die Ortung läuft.
  // Zustände: aus -> folgen (Karte läuft mit) -> frei (Karte wurde verschoben, Antippen holt sie zurück)
  const live = { id: null, punkt: null, kreis: null, folgen: false, knopf: null, gpsKnopf: null, genau: false, erster: true };
  function initLive() {
    const Knopf = L.Control.extend({
      options: { position: 'topright' },
      onAdd() {
        const b = L.DomUtil.create('button', 'live-knopf');
        b.type = 'button'; b.title = 'Live-Standort'; b.setAttribute('aria-label', 'Live-Standort ein/aus'); b.textContent = '◎';
        L.DomEvent.disableClickPropagation(b);
        L.DomEvent.on(b, 'click', liveUmschalten);
        live.knopf = b;
        return b;
      },
    });
    map.addControl(new Knopf());
    try { live.genau = localStorage.getItem('hutab-gps') === '1'; } catch (e) { /* privat */ }
    const GpsKnopf = L.Control.extend({
      options: { position: 'topright' },
      onAdd() {
        const b = L.DomUtil.create('button', 'live-knopf live-gps');
        b.type = 'button'; b.textContent = 'GPS';
        L.DomEvent.disableClickPropagation(b);
        L.DomEvent.on(b, 'click', () => {
          live.genau = !live.genau;
          try { localStorage.setItem('hutab-gps', live.genau ? '1' : '0'); } catch (e) { /* privat */ }
          liveKnopf();
          if (live.id !== null) { navigator.geolocation.clearWatch(live.id); liveStarten(); }
        });
        live.gpsKnopf = b;
        return b;
      },
    });
    map.addControl(new GpsKnopf());
    liveKnopf();
    map.on('dragstart', () => { if (live.id !== null && live.folgen) { live.folgen = false; liveKnopf(); } });
  }
  function liveKnopf() {
    if (!live.knopf) return;
    live.knopf.classList.toggle('an', live.id !== null);
    live.knopf.classList.toggle('folgen', live.id !== null && live.folgen);
    live.gpsKnopf.classList.toggle('gps-an', live.genau);
    live.gpsKnopf.title = live.genau ? 'GPS genau (mehr Akkuverbrauch) – antippen für Sparmodus' : 'Sparmodus (Netzortung) – antippen für GPS genau';
  }
  function liveAus() {
    if (live.id !== null) navigator.geolocation.clearWatch(live.id);
    live.id = null; live.folgen = false; live.erster = true;
    if (live.punkt) { live.punkt.remove(); live.kreis.remove(); live.punkt = live.kreis = null; }
    liveKnopf();
  }
  function liveUmschalten() {
    if (!navigator.geolocation) { alert('Dieses Gerät kann keinen Standort liefern.'); return; }
    if (live.id !== null) {
      if (!live.folgen && live.punkt) { live.folgen = true; map.panTo(live.punkt.getLatLng()); liveKnopf(); return; }
      liveAus(); return;
    }
    live.folgen = true; live.erster = true;
    liveStarten();
  }
  function liveStarten() {
    live.id = navigator.geolocation.watchPosition((pos) => {
      const ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
      const r = pos.coords.accuracy;
      if (!live.punkt) {
        live.kreis = L.circle(ll, { radius: r, color: '#1a73e8', weight: 1, fillColor: '#1a73e8', fillOpacity: 0.12, interactive: false }).addTo(map);
        live.punkt = L.circleMarker(ll, { radius: 8, color: '#fff', weight: 3, fillColor: '#1a73e8', fillOpacity: 1, interactive: false }).addTo(map);
      } else {
        live.kreis.setLatLng(ll).setRadius(r);
        live.punkt.setLatLng(ll);
      }
      if (live.erster) { live.erster = false; map.setView(ll, Math.max(map.getZoom(), 13)); }
      else if (live.folgen) map.panTo(ll, { animate: true });
    }, (err) => {
      liveAus();
      alert(err.code === 1 ? 'Standort ist nicht freigegeben. Bitte die Ortung für diese Seite erlauben.' : 'Standort gerade nicht verfügbar.');
    }, live.genau ? { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 } : { enableHighAccuracy: false, maximumAge: 15000, timeout: 30000 });
    liveKnopf();
  }

  function drawOverlay(view) {
    const score = state.score;
    const url = canvasUrl((px) => {
      for (let i = 0, j = 0; i < score.length; i++, j += 4) {
        if (view) {
          const v = view[i];
          if (v < 0) continue;
          const [r, g, b] = colorFor(v * 100, STOPS_FACTOR);
          px[j] = r; px[j + 1] = g; px[j + 2] = b; px[j + 3] = 190;
        } else {
          const s = score[i];
          if (s < 0) continue;
          const [r, g, b] = colorFor(s, STOPS);
          px[j] = r; px[j + 1] = g; px[j + 2] = b;
          px[j + 3] = s < 3 ? 35 : Math.min(235, 110 + s * 2.6);
        }
      }
    });
    if (state.layers.score) state.layers.score.setUrl(url);
    else state.layers.score = L.imageOverlay(url, state.meta.bounds, { pane: 'scorePane', className: 'score-layer', opacity: 0.85 }).addTo(map);
    if (view) {
      const f = FACTORS.find((x) => x.id === state.view);
      $('legendTitle').textContent = `${f.icon} ${f.name} – einzeln`;
      $('legendBar').style.background = gradientCss(STOPS_FACTOR, 100);
      $('legendLo').textContent = 'ungünstig'; $('legendHi').textContent = 'günstig';
    } else {
      $('legendTitle').textContent = `Chance morgen – ${state.species.name}`;
      $('legendBar').style.background = gradientCss(STOPS, 80);
      $('legendLo').textContent = '0'; $('legendHi').textContent = '80+';
    }
  }

  async function showProtected() {
    const info = await grid('info');
    const url = canvasUrl((px, w) => {
      for (let i = 0, p = 0; i < info.length; i += 4, p++) {
        const prot = info[i] >> 4;
        if (!prot) continue;
        const stripe = (Math.floor(p / w) + (p % w)) % 4 < (prot === 2 ? 2 : 1);
        if (prot === 2) { px[i] = 192; px[i + 1] = 24; px[i + 2] = 42; px[i + 3] = stripe ? 200 : 60; }
        else if (stripe) { px[i] = 123; px[i + 1] = 63; px[i + 2] = 160; px[i + 3] = 150; }
      }
    });
    state.layers.prot = L.imageOverlay(url, state.meta.bounds, { pane: 'protPane', className: 'score-layer' });
    if ($('toggleProtected').checked) state.layers.prot.addTo(map);
  }

  function drawReach() {
    state.layers.reach.clearLayers();
    L.circle([state.start.lat, state.start.lon], {
      radius: state.radius * 1000, color: '#7a4a1f', weight: 1.5, dashArray: '6 6', fill: false, interactive: false,
    }).addTo(state.layers.reach);
    L.marker([state.start.lat, state.start.lon], {
      icon: L.divIcon({ className: '', html: '<div class="start-marker">🏠</div>', iconSize: [24, 24], iconAnchor: [12, 20] }),
      title: 'Start: ' + state.start.label, interactive: false,
    }).addTo(state.layers.reach);
  }

  function showRecent() {
    state.layers.recent.clearLayers();
    const sp = state.species;
    const funde = (state.recent && state.recent.arten[sp.id]) || [];
    if ($('toggleRecent').checked) {
      for (const f of funde) {
        L.circleMarker([f.lat, f.lon], { radius: 5, color: '#fff', weight: 1.5, fillColor: '#2b6cb0', fillOpacity: 0.9 })
          .bindPopup(`<div class="popup"><h4>${escapeHtml(sp.name)} gemeldet</h4>${new Date(f.datum).toLocaleDateString('de-DE')}
            ${f.bestaetigt ? '(bestätigt)' : '(unbestätigt)'}<br><a href="${escapeHtml(f.url)}" target="_blank" rel="noopener">Meldung auf iNaturalist</a></div>`)
          .addTo(state.layers.recent);
      }
    }
    $('recentInfo').textContent = state.recent
      ? `🔵 ${funde.length} Meldung${funde.length === 1 ? '' : 'en'} bei iNaturalist in den letzten ${state.recent.tage} Tagen.`
      : '';
  }

  // ------------------------------------------------------------ Top-Stellen im Umkreis
  const DIRS = ['N', 'NO', 'O', 'SO', 'S', 'SW', 'W', 'NW'];
  function describe(lat, lon) {
    let best = null, bv = Infinity;
    const k = Math.cos(lat * Math.PI / 180);
    for (const p of state.orte) {
      const d = Math.hypot((p[2] - lon) * k, p[1] - lat);
      const v = d / (1 + 0.3 * p[3]);              // groessere Orte bevorzugen
      if (v < bv) { bv = v; best = p; }
    }
    if (!best) return '';
    const dx = (lon - best[2]) * k * 111.32, dy = (lat - best[1]) * 111.32, d = Math.hypot(dx, dy);
    if (d < 0.7) return `bei ${best[0]}`;
    const deg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
    return `${d.toFixed(0)} km ${DIRS[Math.floor((deg + 22.5) / 45) % 8]} von ${best[0]}`;
  }

  function findSpots() {
    const score = state.score, info = state.g.info;
    const [w, h] = state.meta.groesse;
    const { lat: sLat, lon: sLon } = state.start;
    // Bounding-Box des Umkreises in Zeilen/Spalten
    const dLat = state.radius / 111.32, dLon = dLat / Math.cos(sLat * Math.PI / 180);
    const rowOf = (lat) => { const i = cellIndex({ lat: clamp(lat, 51.31, 53.59), lng: 13 }); return i < 0 ? 0 : Math.floor(i / w); };
    const colOf = (lon) => { const i = cellIndex({ lat: 52.5, lng: clamp(lon, 11.21, 14.79) }); return i < 0 ? 0 : i % w; };
    const rowA = rowOf(sLat + dLat), rowB = rowOf(sLat - dLat), colA = colOf(sLon - dLon), colB = colOf(sLon + dLon);
    const cand = [];
    for (let r = Math.max(1, rowA); r <= Math.min(h - 2, rowB); r++) {
      const lat = state.latOfRow[r];
      for (let c = Math.max(1, colA); c <= Math.min(w - 2, colB); c++) {
        const i = r * w + c;
        if (score[i] <= 0 || (info[i * 4] >> 4) !== 0) continue;   // kein Lebensraum oder Schutzgebiet
        // 3x3-Mittel glaettet Einzelpixel; nur zusammenhaengende Flaechen
        let sum = 0, cnt = 0;
        for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
          const v = score[i + dr * w + dc];
          if (v > 0) { sum += v; cnt++; }
        }
        if (cnt < 5) continue;
        const lon = state.lonOfCol[c];
        if (km(lat, lon, sLat, sLon) > state.radius) continue;
        cand.push([sum / 9, i, lat, lon]);
      }
    }
    cand.sort((a, b) => b[0] - a[0]);
    const spots = [];
    for (const [v, i, lat, lon] of cand) {
      if (spots.length >= 10) break;
      if (spots.some((s) => km(s.lat, s.lon, lat, lon) < 4)) continue;
      const dom = info[i * 4] & 15;
      spots.push({ lat, lon, score: Math.round(v), baum: dom ? TREE_NAMES[state.meta.baumarten[dom - 1]] : '',
        lage: describe(lat, lon), dist: km(lat, lon, sLat, sLon) });
    }
    state.spots = spots;
    renderSpots();
  }

  function renderSpots() {
    const sp = state.species, list = $('spotsList');
    state.layers.spots.clearLayers();
    list.innerHTML = '';
    const off = FACTORS.filter((f) => !state.on[f.id]);
    $('modeNote').hidden = !off.length;
    $('modeNote').textContent = off.length ? `Eigene Auswahl: ohne ${off.map((f) => f.name).join(', ')}.` : '';
    if (sp.saison === 0) {
      list.innerHTML = '<li class="empty">Keine Saison – für diese Art ist morgen nichts zu erwarten.</li>';
      return;
    }
    if (!state.spots.length) {
      list.innerHTML = `<li class="empty">Im Umkreis von ${state.radius} km keine geeigneten Flächen. Umkreis vergrößern?</li>`;
      return;
    }
    state.spots.forEach((s, k) => {
      const icon = L.divIcon({ className: '', html: `<div class="spot-marker">${k + 1}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });
      const m = L.marker([s.lat, s.lon], { icon, title: s.lage }).addTo(state.layers.spots);
      m.on('click', () => openWhy(L.latLng(s.lat, s.lon), k + 1));
      const li = document.createElement('li');
      li.tabIndex = 0;
      li.innerHTML = `<span class="num">${k + 1}</span>
        <span><div class="where">${escapeHtml(s.lage)}</div><div class="what">${s.baum ? 'v. a. ' + s.baum + ' · ' : ''}${s.dist.toFixed(0)} km von ${escapeHtml(state.start.label)}</div></span>
        <span class="val"><b>${s.score}</b><small>${chance(s.score).label}</small></span>`;
      const go = () => { map.setView([s.lat, s.lon], 14); openWhy(L.latLng(s.lat, s.lon), k + 1); collapseSheet(); };
      li.addEventListener('click', go);
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      list.appendChild(li);
    });
  }

  // ------------------------------------------------------------ "Warum hier?"
  function nearestWeather(latlng) {
    let best = null, bd = Infinity;
    const k = Math.cos(latlng.lat * Math.PI / 180);
    for (const p of state.weather) {
      const d = ((p[0] - latlng.lng) * k) ** 2 + (p[1] - latlng.lat) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  }
  function standortText(code) {
    if (!code) return '';
    const NK = { A: 'arm', Z: 'ziemlich arm', M: 'mittel', K: 'kräftig', R: 'reich' };
    const F = { 1: 'frisch', 2: 'mäßig frisch', 3: 'trocken' };
    const pre = 'NO+'.includes(code[0]) ? code[0] : '';
    const letter = [...code.slice(pre.length)].find((c) => NK[c]);
    const nk = letter ? NK[letter] : '';
    if (pre === 'O') return `Moor/organisch, ${nk}`;
    if (pre === 'N' || pre === '+') return `grundwassernah${pre === '+' ? ', sehr nass' : ''}, ${nk}`;
    return `${nk}, ${F[code.slice(-1)] || ''}`;
  }

  async function openWhy(latlng, rank) {
    const idx = cellIndex(latlng);
    if (idx < 0 || !state.g) return;
    const sp = state.species;
    const [daily, stdo] = await Promise.all([grid('daily'), grid('standort').catch(() => null)]);
    const g = state.g, j = idx * 4;
    const f = cellFactors(g, idx, sp);
    const forest = g.info[j + 2], dom = g.info[j] & 15, prot = g.info[j] >> 4;
    let head;
    if (prot === 2) head = '<div class="blocked">Kernzone – Betreten verboten</div>';
    else if (!f) head = `<div>Kein Lebensraum für ${escapeHtml(sp.name)} (kaum passende Bäume oder außerhalb des Gebiets).</div>`;
    else {
      const s = combine(f, sp, state.on);
      head = `<div class="big">${Math.round(s)} <small>/ 100 · ${chance(s).label}</small></div>`;
    }
    let bars = '';
    if (f) {
      bars = '<div class="why">' + FACTORS.map((fd) => {
        const v = f[fd.id];
        const [r, gg, b] = colorFor(v * 100, STOPS_FACTOR);
        return `<div class="why-row${state.on[fd.id] ? '' : ' off'}"><span>${fd.icon}</span><span>${fd.name}</span>
          <span class="b"><i style="width:${Math.round(v * 100)}%;background:rgb(${r},${gg},${b})"></i></span>
          <span class="v">${Math.round(v * 100)} %</span></div>`;
      }).join('') + `<div class="why-row"><span>📅</span><span>Saison</span><span class="b"><i style="width:${Math.round(sp.saison * 100)}%;background:#7a4a1f"></i></span><span class="v">${Math.round(sp.saison * 100)} %</span></div></div>`;
      const weakest = FACTORS.filter((fd) => state.on[fd.id]).map((fd) => [fd, f[fd.id]]).sort((a, b) => a[1] - b[1])[0];
      if (weakest && weakest[1] < 0.6) bars += `<p class="hint">Begrenzend: <b>${weakest[0].name}</b> (${Math.round(weakest[1] * 100)} %).</p>`;
    }
    const rows = [['Wald', forest ? `${forest} %` + (dom ? `, v. a. ${TREE_NAMES[state.meta.baumarten[dom - 1]]}` : '') : 'kein Wald']];
    if (stdo) {
      const code = state.meta.standort_codes[stdo[j]];
      if (code) rows.push(['Standort', `${standortText(code)} (${code})`]);
      if (stdo[j + 1] < 255) rows.push(['Bestand', `ca. ${stdo[j + 1]} m hoch` + (stdo[j + 2] < 255 ? `, Kronendeckung ${stdo[j + 2]} %` : '')]);
    }
    const sm = daily[j], nfk = daily[j + 1], dwd = daily[j + 2];
    if (dwd < 255) rows.push(['Bodenfeuchte', `${dwd} % nFK (DWD, Kiefer 0–30 cm)`]);
    if (sm < 6) rows.push(['Oberboden', SM_NAMES[sm] + (nfk < 100 ? `, ${nfk}–${nfk + 10} % nFK (UFZ)` : '')]);
    const w = nearestWeather(latlng);
    if (w) {
      // [lon, lat, regen_26, regentage, tmittel_20, tmittel_ziel, tmin_ziel, hitzetage, frostnaechte, kwb_26, tboden_ziel, dtheta]
      rows.push(['Regen', `${w[2]} l/m² in 26 Tagen · Bilanz ${w[9] > 0 ? '+' : ''}${w[9]} mm`]);
      rows.push(['Temperatur', `Ø 20 Tage ${w[4]} °C (Optimum ${state.meta.modell.temp[sp.id].opt} °C) · morgen ${w[5]} °C`]);
    }
    rows.push(['Schutz', prot === 1 ? 'Naturschutzgebiet – Sammeln meist verboten' : prot === 2 ? 'Kernzone' : 'kein NSG bekannt']);
    const nav = `https://www.openstreetmap.org/directions?to=${latlng.lat.toFixed(5)}%2C${latlng.lng.toFixed(5)}`;
    L.popup({ maxWidth: 340 }).setLatLng(latlng).setContent(`<div class="popup">
      <h4>${rank ? rank + '. ' : ''}${escapeHtml(sp.name)} morgen – warum hier?</h4>${head}${bars}
      <table>${rows.map(([k, x]) => `<tr><td>${k}</td><td>${escapeHtml(x)}</td></tr>`).join('')}</table>
      <p class="hint"><a href="geo:${latlng.lat.toFixed(5)},${latlng.lng.toFixed(5)}">In Karten-App öffnen</a> ·
        <a href="${nav}" target="_blank" rel="noopener">Route (OSM)</a></p></div>`).openOn(map);
  }

  // ------------------------------------------------------------ Faktoren-Liste
  function renderFactors() {
    const list = $('factorList');
    list.innerHTML = '';
    const total = document.createElement('div');
    total.className = 'factor total' + (state.view === 'score' ? ' viewing' : '');
    total.innerHTML = `<span class="f-icon">🍄</span><span class="f-name">Gesamtchance<span class="f-desc">alle eingeschalteten Faktoren zusammen</span></span>
      <span></span><input type="radio" class="f-eye" name="view" value="score" aria-label="Gesamtchance auf der Karte zeigen" ${state.view === 'score' ? 'checked' : ''}>`;
    list.appendChild(total);
    for (const f of FACTORS) {
      const row = document.createElement('div');
      row.className = 'factor' + (state.on[f.id] ? '' : ' off') + (state.view === f.id ? ' viewing' : '');
      row.innerHTML = `<span class="f-icon">${f.icon}</span>
        <span class="f-name">${f.name}<span class="f-desc">${f.desc}</span></span>
        <label class="f-switch" title="in die Gesamtchance einbeziehen"><input type="checkbox" data-f="${f.id}" ${state.on[f.id] ? 'checked' : ''} aria-label="${f.name} einbeziehen"><span></span></label>
        <input type="radio" class="f-eye" name="view" value="${f.id}" title="nur diesen Faktor auf der Karte zeigen" aria-label="${f.name} einzeln auf der Karte zeigen" ${state.view === f.id ? 'checked' : ''}>`;
      list.appendChild(row);
    }
    list.querySelectorAll('input[type="checkbox"][data-f]').forEach((cb) => cb.addEventListener('change', () => {
      state.on[cb.dataset.f] = cb.checked;
      renderFactors(); recompute();
    }));
    list.querySelectorAll('input[name="view"]').forEach((rb) => rb.addEventListener('change', () => {
      state.view = rb.value;
      renderFactors(); recompute();
    }));
  }

  // ------------------------------------------------------------ Startansicht
  function seasonBar(sp, month, big) {
    return sp.monate.map((v, i) => `<span class="${i === month ? 'now' : ''}" style="opacity:${big ? 0.2 + 0.8 * v : 0.15 + 0.85 * v}">${big ? MONTHS[i] : ''}</span>`).join('');
  }
  function renderStart() {
    const g = $('speciesGrid');
    const month = new Date(state.meta.zieltag + 'T12:00:00').getMonth();
    g.innerHTML = '';
    const sorted = [...state.meta.arten].sort((a, b) => (b.spots[0]?.score || 0) - (a.spots[0]?.score || 0));
    for (const sp of sorted) {
      const best = sp.spots[0]?.score || 0;
      const c = sp.saison === 0 ? { label: 'keine Saison', color: '#999' } : chance(best);
      const b = document.createElement('button');
      b.className = 'species-card' + (sp.saison === 0 ? ' off' : '');
      b.setAttribute('role', 'listitem');
      b.innerHTML = `<img src="img/arten/${sp.id}.jpg" alt="" loading="lazy">
        <span class="chance"><i class="dot" style="background:${c.color}"></i>${c.label}</span>
        <span class="card-body"><div class="card-name">${escapeHtml(sp.name)}</div>
          <div class="card-sub">${sp.saison === 0 ? 'außerhalb der Saison' : `beste Stelle: ${best}/100`}</div>
          <div class="seasonbar" aria-hidden="true">${seasonBar(sp, month, false)}</div></span>`;
      b.addEventListener('click', () => { location.hash = 'art=' + sp.id; });
      g.appendChild(b);
    }
  }

  // ------------------------------------------------------------ Art-Details
  function renderDetail(sp) {
    $('chipImg').src = `img/arten/${sp.id}.jpg`;
    $('chipName').textContent = sp.name;
    $('chipDate').textContent = `Prognose für ${fmtDate(state.meta.zieltag)}`;
    $('detailImg').src = `img/arten/${sp.id}.jpg`;
    $('detailImg').alt = sp.name;
    $('detailName').textContent = sp.name;
    $('detailLatin').textContent = sp.latein;
    const month = new Date(state.meta.zieltag + 'T12:00:00').getMonth();
    $('detailSeason').innerHTML = seasonBar(sp, month, true);
    $('detailInfo').textContent = sp.info;
    $('detailWarn').textContent = sp.vorsicht;
    const t = state.meta.modell.temp[sp.id];
    $('detailTemp').textContent = `Günstigste Temperatur (20-Tage-Mittel): ${t.opt} °C${t.quelle ? ' – ' + t.quelle : ''}. ` +
      `Hauptsaison: ${sp.monate.map((v, i) => (v >= 0.5 ? MONTHS_LONG[i] : null)).filter(Boolean).join(', ')}.`;
    const c = sp.bild;
    $('detailCredit').innerHTML = c
      ? `Foto: <a href="${escapeHtml(c.quelle)}" target="_blank" rel="noopener">${escapeHtml(c.urheber).slice(0, 80)}</a>, ${c.lizenz_url ? `<a href="${escapeHtml(c.lizenz_url)}" target="_blank" rel="noopener">${escapeHtml(c.lizenz)}</a>` : escapeHtml(c.lizenz)}, Wikimedia Commons`
      : '';
  }

  // ------------------------------------------------------------ Navigation
  async function route() {
    const m = location.hash.match(/art=([a-z_]+)/);
    const sp = m && state.meta.arten.find((a) => a.id === m[1]);
    $('viewStart').hidden = !!sp;
    $('viewMap').hidden = !sp;
    if (!sp) { document.title = 'Hut ab! – Pilzprognose Berlin/Brandenburg'; return; }
    document.title = `${sp.name} morgen – Hut ab!`;
    if (!state.mapReady) initMap();
    map.invalidateSize();
    state.species = sp;
    try { localStorage.setItem('hutab-art', sp.id); } catch (e) { /* privat */ }
    renderDetail(sp);
    renderFactors();
    showRecent();
    drawReach();
    await recompute();
  }
  window.addEventListener('hashchange', route);

  function selectTab(name) {
    document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', t.dataset.tab === name));
    document.querySelectorAll('.tabpane').forEach((p) => { p.hidden = p.dataset.pane !== name; });
    $('panel').classList.remove('collapsed');
  }
  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => selectTab(t.dataset.tab)));
  function collapseSheet() { if (window.matchMedia('(max-width: 760px)').matches) $('panel').classList.add('collapsed'); }
  $('sheetHandle').addEventListener('click', () => $('panel').classList.toggle('collapsed'));
  $('backBtn').addEventListener('click', () => { location.hash = ''; });

  // Reichweite
  let spotTimer;
  $('radius').addEventListener('input', (e) => {
    state.radius = +e.target.value;
    $('radiusOut').textContent = `${state.radius} km`;
    drawReach();
    clearTimeout(spotTimer);
    spotTimer = setTimeout(() => state.score && findSpots(), 120);
  });
  function setStart(s, locate) {
    state.start = s;
    $('btnLocate').setAttribute('aria-pressed', locate);
    $('btnBerlin').setAttribute('aria-pressed', !locate);
    try { localStorage.setItem('hutab-start', JSON.stringify(s)); } catch (e) { /* privat */ }
    drawReach();
    if (state.score) findSpots();
  }
  $('btnBerlin').addEventListener('click', () => setStart({ ...BERLIN }, false));
  $('btnLocate').addEventListener('click', () => {
    if (!navigator.geolocation) return;
    $('btnLocate').textContent = '📍 suche …';
    navigator.geolocation.getCurrentPosition((pos) => {
      $('btnLocate').textContent = '📍 Mein Standort';
      setStart({ lat: pos.coords.latitude, lon: pos.coords.longitude, label: 'deinem Standort' }, true);
      map.setView([pos.coords.latitude, pos.coords.longitude], 9);
    }, () => {
      $('btnLocate').textContent = '📍 nicht verfügbar';
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
  });

  $('btnReset').addEventListener('click', () => {
    FACTORS.forEach((f) => { state.on[f.id] = true; });
    state.view = 'score';
    renderFactors(); recompute();
  });
  $('toggleProtected').addEventListener('change', (e) => {
    if (!state.layers.prot) return;
    if (e.target.checked) state.layers.prot.addTo(map); else state.layers.prot.remove();
  });
  $('toggleRecent').addEventListener('change', showRecent);
  for (const id of ['infoBtn', 'infoBtnStart', 'infoLinkStart']) $(id).addEventListener('click', () => $('infoDialog').showModal());

  // ------------------------------------------------------------ Start
  async function init() {
    state.meta = await (await fetch('data/meta.json', { cache: 'no-cache' })).json();
    const v = state.meta.erstellt;
    const [weather, recent, orte] = await Promise.all([
      fetch(`data/weather.json?v=${v}`).then((r) => r.json()),
      fetch(`data/recent.json?v=${v}`).then((r) => r.json()).catch(() => null),
      fetch(`data/orte.json?v=${v}`).then((r) => r.json()).catch(() => []),
    ]);
    state.weather = weather; state.recent = recent; state.orte = orte;
    precomputeCoords();
    $('heroDay').textContent = fmtDate(state.meta.zieltag);
    $('buildInfo').textContent = `Stand: ${state.meta.erstellt.replace('T', ' ')} · Bodenfeuchte UFZ ${state.meta.ufz_datum}` +
      (state.meta.dwd_datum ? `, DWD ${state.meta.dwd_datum}` : '') + ` · Wetter abgerufen ${state.meta.wetter_abruf.replace('T', ' ')}`;
    try {
      const s = JSON.parse(localStorage.getItem('hutab-start') || 'null');
      if (s && s.lat) {
        state.start = s;
        $('btnLocate').setAttribute('aria-pressed', s.label !== 'Berlin');
        $('btnBerlin').setAttribute('aria-pressed', s.label === 'Berlin');
      }
    } catch (e) { /* privat */ }
    renderStart();
    await route();
  }
  init().catch((err) => {
    $('heroDay').textContent = 'morgen (Daten nicht ladbar)';
    console.error(err);
  });
})();
