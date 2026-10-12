/* Hut ab! – Pilzprognose Berlin/Brandenburg
 * Laedt data/meta.json und die Raster-PNGs, faerbt den Score der gewaehlten Art im Browser ein
 * und liest bei Klick die Rasterwerte (Score, Baumart, pH, Bodenfeuchte, Wetter) aus. */
(() => {
  'use strict';

  const TREE_NAMES = {
    birke: 'Birke', buche: 'Buche', douglasie: 'Douglasie', eiche: 'Eiche', erle: 'Erle', fichte: 'Fichte',
    kiefer: 'Kiefer', laerche: 'Lärche', tanne: 'Tanne', laub_lang: 'sonst. Laubholz', laub_kurz: 'Pappel/Weide u. a.',
  };
  const SM_NAMES = ['keine Dürre', 'ungewöhnlich trocken', 'moderate Dürre', 'schwere Dürre', 'extreme Dürre', 'außergewöhnliche Dürre'];
  const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  // Sequenzielle Farbskala (hellgelb -> orange -> rotbraun -> dunkelviolett) fuer Score 0..100,
  // bewusst warm, damit sie sich vom Gruen der OSM-Waelder abhebt
  const STOPS = [[0, [255, 237, 160]], [10, [254, 196, 79]], [20, [245, 128, 37]], [35, [214, 60, 35]], [50, [150, 20, 60]], [100, [84, 10, 72]]];
  const R = 6378137;

  const $ = (id) => document.getElementById(id);
  const state = { meta: null, species: null, grids: {}, scoreLayer: null, protLayer: null, spotLayer: null, weather: [] };

  const mobile = window.matchMedia('(max-width: 760px)').matches;
  const map = L.map('map', { zoomControl: true, minZoom: 7, maxZoom: 17, attributionControl: false }).setView([52.45, 13.4], 8);
  // Auf dem Handy liegt unten das Menue -> Quellenangabe nach oben rechts
  L.control.attribution({ position: mobile ? 'topright' : 'bottomright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | UFZ, Thünen, ISRIC, LfU BB, Open-Meteo',
  }).addTo(map);
  map.createPane('scorePane').style.zIndex = 350;
  map.createPane('protPane').style.zIndex = 360;

  function colorFor(v) {
    for (let i = 1; i < STOPS.length; i++) {
      if (v <= STOPS[i][0]) {
        const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i];
        const t = (v - a) / (b - a);
        return ca.map((c, k) => Math.round(c + t * (cb[k] - c)));
      }
    }
    return STOPS[STOPS.length - 1][1];
  }
  $('legendBar').style.background = `linear-gradient(90deg, ${STOPS.map(([v, c]) => `rgb(${c}) ${v}%`).join(',')})`;
  $('legendBar').title = 'Score 0 – 10 – 20 – 35 – 50 – 100';

  function loadImageData(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        resolve(ctx.getImageData(0, 0, c.width, c.height));
      };
      img.onerror = () => reject(new Error('Bild nicht ladbar: ' + url));
      img.src = url;
    });
  }

  async function grid(name) {
    if (!state.grids[name]) state.grids[name] = loadImageData(`data/${name}.png?v=${state.meta.erstellt}`);
    return state.grids[name];
  }

  function toCanvasUrl(w, h, fill) {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const out = ctx.createImageData(w, h);
    fill(out.data);
    ctx.putImageData(out, 0, 0);
    return c.toDataURL();
  }

  function pixelAt(latlng) {
    const r = state.meta.raster;
    const x = R * latlng.lng * Math.PI / 180;
    const y = R * Math.log(Math.tan(Math.PI / 4 + latlng.lat * Math.PI / 360));
    const col = Math.floor((x - r.x0) / r.res), row = Math.floor((r.y1 - y) / r.res);
    const [w, h] = state.meta.groesse;
    return col >= 0 && col < w && row >= 0 && row < h ? row * w + col : -1;
  }

  // ------------------------------------------------------------ Ebenen
  async function showScore(sp) {
    const data = await grid('score_' + sp.id);
    const [w, h] = state.meta.groesse;
    const url = toCanvasUrl(w, h, (px) => {
      const src = data.data;
      for (let i = 0, j = 0; i < src.length; i += 4, j += 4) {
        const v = src[i];
        if (v === 0) continue;                       // kein Lebensraum
        const s = v - 1;
        const [r, g, b] = colorFor(s);
        px[j] = r; px[j + 1] = g; px[j + 2] = b;
        px[j + 3] = s < 3 ? 40 : Math.min(235, 120 + s * 4);
      }
    });
    if (state.scoreLayer) state.scoreLayer.setUrl(url);
    else state.scoreLayer = L.imageOverlay(url, state.meta.bounds, { pane: 'scorePane', className: 'score-layer', opacity: 0.85 }).addTo(map);
  }

  async function showProtected() {
    const info = await grid('info');
    const [w, h] = state.meta.groesse;
    const url = toCanvasUrl(w, h, (px) => {
      const src = info.data;
      for (let i = 0, p = 0; i < src.length; i += 4, p++) {
        const prot = src[i] >> 4;
        if (!prot) continue;
        const row = Math.floor(p / w), col = p % w;
        const stripe = (row + col) % 4 < (prot === 2 ? 2 : 1);
        if (prot === 2) { px[i] = 192; px[i + 1] = 24; px[i + 2] = 42; px[i + 3] = stripe ? 200 : 60; }
        else if (stripe) { px[i] = 123; px[i + 1] = 63; px[i + 2] = 160; px[i + 3] = 150; }
      }
    });
    state.protLayer = L.imageOverlay(url, state.meta.bounds, { pane: 'protPane', className: 'score-layer' });
    if ($('toggleProtected').checked) state.protLayer.addTo(map);
  }

  function showSpots(sp) {
    if (state.spotLayer) state.spotLayer.remove();
    state.spotLayer = L.layerGroup().addTo(map);
    const list = $('spotsList');
    list.innerHTML = '';
    $('spotsTitle').textContent = `Beste Sammelstellen morgen – ${sp.name}`;
    if (!sp.spots.length) {
      list.innerHTML = `<li class="empty">${sp.saison === 0 ? 'Keine Saison – morgen ist für diese Art nichts zu erwarten.' : 'Morgen keine Flächen mit guten Bedingungen.'}</li>`;
      return;
    }
    sp.spots.forEach((s, i) => {
      const trees = s.baeume.map((t) => TREE_NAMES[t] || t).join(', ');
      const icon = L.divIcon({ className: '', html: `<div class="spot-marker">${i + 1}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
      const m = L.marker([s.lat, s.lon], { icon, title: s.lage }).addTo(state.spotLayer);
      m.bindPopup(spotPopup(sp, s, i, trees));
      const li = document.createElement('li');
      li.tabIndex = 0;
      li.innerHTML = `<span class="num">${i + 1}</span><span><div class="where">${s.lage}</div>
        <div class="what">${trees || 'Wald'} · ca. ${s.flaeche_ha} ha</div></span><span class="val">${s.score}</span>`;
      const go = () => { map.setView([s.lat, s.lon], 14); m.openPopup(); collapseSheetOnMobile(); };
      li.addEventListener('click', go);
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      list.appendChild(li);
    });
  }

  function spotPopup(sp, s, i, trees) {
    const nav = `https://www.openstreetmap.org/directions?to=${s.lat}%2C${s.lon}`;
    return `<div class="popup"><h4>${i + 1}. ${sp.name}</h4>
      <div class="big">${s.score} <small>/ 100</small></div>
      <table><tr><td>Lage</td><td>${s.lage}</td></tr>
      <tr><td>Fläche</td><td>ca. ${s.flaeche_ha} ha (Spitzenwert ${s.max})</td></tr>
      <tr><td>Bäume</td><td>${trees || '–'}</td></tr>
      <tr><td>Koordinaten</td><td>${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}</td></tr></table>
      <p><a href="geo:${s.lat},${s.lon}">In Karten-App öffnen</a> · <a href="${nav}" target="_blank" rel="noopener">Route (OSM)</a></p></div>`;
  }

  // ------------------------------------------------------------ Klick-Info
  function nearestWeather(latlng) {
    let best = null, bd = Infinity;
    const k = Math.cos(latlng.lat * Math.PI / 180);
    for (const p of state.weather) {
      const d = ((p[0] - latlng.lng) * k) ** 2 + (p[1] - latlng.lat) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  }

  map.on('click', async (e) => {
    const idx = pixelAt(e.latlng);
    if (idx < 0 || !state.species) return;
    const [score, info, daily] = await Promise.all([grid('score_' + state.species.id), grid('info'), grid('daily')]);
    const v = score.data[idx * 4];
    const ir = info.data[idx * 4], ph = info.data[idx * 4 + 1], forest = info.data[idx * 4 + 2];
    const prot = ir >> 4, dom = ir & 15;
    const sm = daily.data[idx * 4], nfk = daily.data[idx * 4 + 1];
    const w = nearestWeather(e.latlng);
    const sp = state.species;
    let head;
    if (prot === 2) head = '<div class="blocked">Kernzone – Betreten verboten</div>';
    else if (v === 0) head = `<div>Kein Lebensraum für ${sp.name} (kaum passende Bäume).</div>`;
    else head = `<div class="big">${v - 1} <small>/ 100</small></div>`;
    const rows = [
      ['Wald', forest ? `${forest} %` + (dom ? `, v. a. ${TREE_NAMES[state.meta.baumarten[dom - 1]]}` : '') : 'kein Wald'],
      ['Schutz', prot === 1 ? 'Naturschutzgebiet – Sammeln meist verboten' : prot === 2 ? 'Kernzone' : 'kein NSG bekannt (Berlin noch nicht erfasst)'],
      ['Boden-pH', ph ? (ph / 10).toFixed(1) + ' (SoilGrids)' : '–'],
      ['Oberboden', sm < 6 ? SM_NAMES[sm] + (nfk < 100 ? `, ${nfk}–${nfk + 10} % nFK` : '') : '–'],
    ];
    if (w) {
      // [lon, lat, regen_26, regentage, tmittel_20, tmittel_ziel, tmin_ziel, hitzetage, frostnaechte]
      rows.push(['Regen', `${w[2]} l/m² in 26 Tagen (${w[3]} Regentage)`]);
      rows.push(['Temperatur', `Ø 20 Tage ${w[4]} °C · morgen Ø ${w[5]} °C, Tiefst ${w[6]} °C`]);
      if (w[8] > 0) rows.push(['Frost', `${w[8]} Frostnacht/-nächte in 10 Tagen`]);
    }
    L.popup().setLatLng(e.latlng).setContent(`<div class="popup"><h4>${sp.name} morgen</h4>${head}
      <table>${rows.map(([k, x]) => `<tr><td>${k}</td><td>${x}</td></tr>`).join('')}</table></div>`).openOn(map);
  });

  // ------------------------------------------------------------ Menue
  function chanceLabel(sp) {
    if (sp.saison === 0) return 'keine Saison';
    if (!sp.spots.length) return 'schwach';
    const s = sp.spots[0].score;
    return s >= 50 ? 'sehr gut' : s >= 35 ? 'gut' : s >= 20 ? 'mäßig' : 'schwach';
  }

  function renderSpeciesGrid() {
    const g = $('speciesGrid');
    g.innerHTML = '';
    for (const sp of state.meta.arten) {
      const b = document.createElement('button');
      b.className = 'species-card' + (sp.saison === 0 ? ' off' : '');
      b.setAttribute('role', 'option');
      b.dataset.id = sp.id;
      b.innerHTML = `<img src="img/arten/${sp.id}.jpg" alt="${sp.name}" loading="lazy">
        <span class="chance">${chanceLabel(sp)}</span>
        <div class="label">${sp.name}</div>`;
      b.addEventListener('click', () => select(sp.id));
      g.appendChild(b);
    }
  }

  function renderDetail(sp) {
    $('speciesDetail').hidden = false;
    $('detailImg').src = `img/arten/${sp.id}.jpg`;
    $('detailImg').alt = sp.name;
    $('detailName').textContent = sp.name;
    $('detailLatin').textContent = sp.latein;
    const months = sp.monate.map((v, i) => (v >= 0.5 ? MONTHS[i] : null)).filter(Boolean);
    $('detailSeason').textContent = `Hauptsaison: ${months[0]}–${months[months.length - 1]}`;
    $('detailInfo').textContent = sp.info;
    $('detailWarn').textContent = sp.vorsicht;
    const c = sp.bild;
    $('detailCredit').innerHTML = c
      ? `Foto: <a href="${c.quelle}" target="_blank" rel="noopener">${escapeHtml(c.urheber).slice(0, 80)}</a>, ${c.lizenz_url ? `<a href="${c.lizenz_url}" target="_blank" rel="noopener">${c.lizenz}</a>` : c.lizenz}, Wikimedia Commons`
      : '';
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  }

  async function select(id) {
    const sp = state.meta.arten.find((a) => a.id === id) || state.meta.arten[0];
    state.species = sp;
    document.querySelectorAll('.species-card').forEach((b) => b.setAttribute('aria-selected', b.dataset.id === sp.id));
    try { localStorage.setItem('hutab-art', sp.id); } catch (e) { /* privat */ }
    history.replaceState(null, '', '#' + sp.id);
    renderDetail(sp);
    showSpots(sp);
    await showScore(sp);
  }

  function collapseSheetOnMobile() {
    if (window.matchMedia('(max-width: 760px)').matches) $('panel').classList.add('collapsed');
  }
  $('sheetHandle').addEventListener('click', () => $('panel').classList.toggle('collapsed'));

  $('toggleProtected').addEventListener('change', (e) => {
    if (!state.protLayer) return;
    if (e.target.checked) state.protLayer.addTo(map); else state.protLayer.remove();
  });
  $('infoBtn').addEventListener('click', () => $('infoDialog').showModal());

  // ------------------------------------------------------------ Start
  const fmtDate = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });

  async function init() {
    const res = await fetch('data/meta.json', { cache: 'no-cache' });
    state.meta = await res.json();
    state.weather = await (await fetch(`data/weather.json?v=${state.meta.erstellt}`)).json();
    $('forecastDate').textContent = `Prognose für ${fmtDate(state.meta.zieltag)}`;
    $('buildInfo').textContent = `Stand: ${state.meta.erstellt.replace('T', ' ')} · Bodenfeuchte vom ${state.meta.ufz_datum} · Wetter abgerufen ${state.meta.wetter_abruf.replace('T', ' ')}`;
    renderSpeciesGrid();
    let start = location.hash.slice(1);
    if (!start) { try { start = localStorage.getItem('hutab-art'); } catch (e) { /* privat */ } }
    await select(start || 'steinpilz');
    showProtected();
  }
  init().catch((err) => {
    $('forecastDate').textContent = 'Daten konnten nicht geladen werden.';
    console.error(err);
  });
})();
