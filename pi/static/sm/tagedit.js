// tagedit.js - Fenster "Tag bearbeiten" der Musik-Datenbank (Wunsch von Markus, 07.11.2026).
// Liest alle ID3-Felder der MP3 am Mac (music_serve /tags), macht die ueblichen editierbar, holt auf Knopfdruck Vorschlaege
// und Cover aus dem Internet (/lookup: MusicBrainz, iTunes, Deezer, Cover Art Archive) und schreibt in die MP3 (POST /tags).
// Vorschlaege stehen blau neben dem Feld, nichts wird von selbst uebernommen. Ins Internet gehen nur Interpret, Titel, Laenge.
(function () {
  'use strict';
  const SM = window.SM = window.SM || {};
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // Titel, Interpret, Track und Album aus Dateiname und Ordner (Wunsch 12.11.2026, Knopf "Aus Dateiname").
  // "01 - Interpret - Titel.mp3", "Interpret - Titel (2).mp3", ohne " - " nur der Titel. Album: der Ordner, in dem die Datei liegt,
  // ausser er heisst wie der Interpret oder ist ein Sammelordner (Artists, U-MUSIK ...); "Interpret - Album" -> Album.
  const NOT_ALBUM = /^(artists?|interpreten|u-musik|e-musik|musik|music|musik-import|neu|nicht mp3|samples|testsamples|compilations|singles|diverse|various|unsortiert|chillout|filmmusik|klassik|meditation|musical|synthesizer|weihnachten|gibt es schon.*|gleicher titel.*)$/i;
  SM.nameTags = path => {
    const parts = String(path || '').normalize('NFC').split('/').filter(Boolean);
    let stem = (parts.pop() || '').replace(/[.][a-z0-9]{2,4}$/i, '').replace(/[ ]*[(][0-9]{1,2}[)]$/, '').replace(/_pn$/, '').replace(/_/g, ' ').trim();
    const out = {};
    // Tracknummer nur mit Trenner ("03 - ", "3. ", "(03)") oder fuehrender Null ("03 Lied"): "99 Luftballons" bleibt ganz
    const m = stem.match(/^[(]?([0-9]{1,3})[)]?[ ]*[-.)][ ]*(.+)$/) || stem.match(/^[(]([0-9]{1,3})[)][ ]*(.+)$/) || stem.match(/^(0[0-9])[ ]+(.+)$/);
    if (m && !/^[0-9]+[ ]*$/.test(m[2])) { out.track = String(parseInt(m[1], 10)); stem = m[2]; }
    const bits = stem.split(/[ ]+-[ ]+/).map(x => x.trim()).filter(Boolean);
    if (bits.length >= 2) { out.artist = bits[0]; out.title = bits.slice(1).join(' - '); } else if (bits.length) out.title = bits[0];
    let dir = (parts.pop() || '').replace(/_/g, ' ').trim();
    if (/^(cd|disc|disk)[ ]*[0-9]+$/i.test(dir)) dir = (parts.pop() || '').replace(/_/g, ' ').trim();   // "Album/CD 1/..." -> Album
    const low = s => String(s || '').toLowerCase();
    if (out.artist && low(dir).startsWith(low(out.artist) + ' - ')) dir = dir.slice(out.artist.length + 3).trim();
    dir = dir.replace(/^[(]?(19|20)[0-9]{2}[)]?[ ]*-[ ]*/, '').replace(/[ ]*[(\[](19|20)[0-9]{2}[)\]]$/, '').trim();
    if (dir && !NOT_ALBUM.test(dir) && low(dir) !== low(out.artist) && !/^(cd|disc)[ ]*[0-9]+$/i.test(dir)) out.album = dir;
    return out;
  };
  const SUGGEST = ['title', 'artist', 'album', 'albumartist', 'year', 'track', 'disc', 'genre'];   // Felder, fuer die es Vorschlaege gibt
  const MAIN = ['title', 'artist', 'album', 'albumartist', 'year', 'track', 'disc', 'genre', 'grouping', 'bpm', 'key', 'comment'];

  // ---- Selbst erzeugtes Cover (Entwurf C "Wellenform", Wunsch von Markus 07.11.2026): fuer Eigenmischungen ohne Cover ----
  // Hintergrund nach der Energiestufe (ruhig blau bis wild rot), oben BPM und Tonart, in der Mitte die echte Wellenform,
  // unten Titel und Interpret. 600 x 600 Pixel, JPEG.
  const COVER_COLORS = [['#042C53', '#85B7EB', '#E6F1FB'], ['#04342C', '#5DCAA5', '#E1F5EE'], ['#412402', '#EF9F27', '#FAEEDA'],
    ['#4A1B0C', '#F0997B', '#FAECE7'], ['#501313', '#F09595', '#FCEBEB']];   // Hintergrund, Welle, Schrift
  SM.coverColors = energy => { const e = parseInt(energy, 10) || 0; return COVER_COLORS[!e ? 1 : e <= 3 ? 0 : e <= 5 ? 1 : e <= 6 ? 2 : e <= 8 ? 3 : 4]; };
  SM.coverPeaks = (buf, n) => {                               // n Pegelwerte (0..1) ueber das ganze Lied: Durchschnitt (RMS),
    const d = buf.getChannelData(0), step = Math.max(1, Math.floor(d.length / n)), out = [];   // Spitzen waeren bei lauter
    for (let i = 0; i < n; i++) {                                                            // Musik ueberall gleich hoch
      let sum = 0, k = 0;
      for (let j = i * step, e = Math.min(d.length, j + step); j < e; j += 32) { sum += d[j] * d[j]; k++; }
      out.push(Math.sqrt(sum / Math.max(1, k)));
    }
    const top = Math.max(1e-6, ...out);
    return out.map(v => Math.pow(v / top, 1.6));                // etwas spreizen: leise Stellen deutlich kleiner
  };
  // Bilddatei -> quadratisches JPEG (data:-Adresse): die Mitte ausschneiden, auf hoechstens max Pixel verkleinern, nie vergroessern
  SM.squareCover = (file, max) => new Promise((resolve, reject) => {
    if (!/^image\//.test(file.type || 'image/')) { reject(new Error('keine Bilddatei')); return; }
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const w = img.naturalWidth, h = img.naturalHeight, side = Math.min(w, h);
      if (!side) { reject(new Error('Bild leer')); return; }
      const out = Math.min(max || 1000, side), c = document.createElement('canvas');
      c.width = c.height = out;
      const g = c.getContext('2d');
      g.fillStyle = '#fff'; g.fillRect(0, 0, out, out);          // durchsichtige PNG: weiss statt schwarz
      g.drawImage(img, (w - side) / 2, (h - side) / 2, side, side, 0, 0, out, out);
      resolve(c.toDataURL('image/jpeg', 0.9));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Bild nicht lesbar (Format?)')); };
    img.src = url;
  });
  SM.makeCover = o => {
    const W = 600, c = document.createElement('canvas');
    c.width = c.height = W;
    const g = c.getContext('2d'), [bg, wave, txt] = SM.coverColors(o.energy);
    g.fillStyle = bg; g.fillRect(0, 0, W, W);
    const font = (size, weight) => (weight || 500) + ' ' + size + 'px Inter, -apple-system, "Helvetica Neue", Arial, sans-serif';
    const fit = (text, size, max, weight) => { let s = size; g.font = font(s, weight); while (s > 18 && g.measureText(text).width > max) { s -= 2; g.font = font(s, weight); } return s; };
    const top = [o.bpm ? Math.round(parseFloat(String(o.bpm).replace(',', '.'))) + ' BPM' : '', o.key || '', o.energy ? 'E' + o.energy : ''].filter(Boolean).join('  ·  ');
    g.fillStyle = wave; g.globalAlpha = 0.9; g.font = font(26, 500); g.textBaseline = 'top';
    if (top) g.fillText(top, 44, 44);
    g.globalAlpha = 1;
    const peaks = o.peaks || [], mid = 270, amp = 120, bw = (W - 88) / Math.max(1, peaks.length);
    g.fillStyle = wave;
    peaks.forEach((v, i) => { const h = Math.max(3, v * amp); g.fillRect(44 + i * bw, mid - h, Math.max(2, bw * 0.62), h * 2); });
    g.fillStyle = txt; g.textBaseline = 'alphabetic';
    const title = String(o.title || '').trim() || 'Ohne Titel', artist = String(o.artist || '').trim();
    let size = fit(title, 56, W - 88, 600);
    g.font = font(size, 600);
    const words = title.split(/\s+/), lines = [];                // Titel auf hoechstens zwei Zeilen
    let line = '';
    for (const w of words) { const t = line ? line + ' ' + w : w; if (g.measureText(t).width > W - 88 && line) { lines.push(line); line = w; } else line = t; }
    lines.push(line);
    const shown = lines.slice(0, 2);
    if (lines.length > 2) shown[1] = shown[1].replace(/\s*\S*$/, '') + ' …';
    let y = W - 44 - (artist ? 40 : 0) - (shown.length - 1) * (size + 6);
    for (const l of shown) { g.fillText(l, 44, y); y += size + 6; }
    if (artist) { g.globalAlpha = 0.8; g.font = font(fit(artist, 30, W - 88, 500), 500); g.fillText(artist, 44, W - 44); g.globalAlpha = 1; }
    return c.toDataURL('image/jpeg', 0.9);
  };

  // Sehr lange Dateien (Mitschnitte ueber 3 Stunden, Fehlerbericht 07.11.2026 "La Dune"): nicht die ganze MP3 holen und
  // dekodieren (der Browser schafft das nicht), sondern kurze Stuecke ueber die Laenge verteilt (Range-Anfragen an den Mac).
  const BIG = 40 * 1024 * 1024, SLICE = 1024 * 1024;
  SM.audioSize = async (music, q) => {
    const r = await fetch(music + '/audio?' + q, { headers: { Range: 'bytes=0-0' } });
    const m = /\/(\d+)/.exec(r.headers.get('Content-Range') || '');
    return m ? parseInt(m[1], 10) : 0;
  };
  SM.decodeRange = async (music, q, a, b) => {
    const r = await fetch(music + '/audio?' + q, { headers: { Range: 'bytes=' + a + '-' + b } });
    if (!r.ok) throw new Error('Die MP3 kommt nicht vom Musik-Rechner (' + r.status + ')');
    const C = window.AudioContext || window.webkitAudioContext;
    const ac = new C();
    try { return await ac.decodeAudioData(await r.arrayBuffer()); } finally { if (ac.close) ac.close(); }
  };
  // n Pegelwerte ueber das ganze Lied; bei grossen Dateien aus k Stuecken (je n/k Werte), sonst wie bisher aus der ganzen Datei
  SM.peaksFor = async (music, q, n, whole) => {
    const size = await SM.audioSize(music, q);
    if (!size || size <= BIG) {                                 // normal grosse Datei (oder Groesse unbekannt): ganz dekodieren
      if (whole) return SM.coverPeaks(await whole(), n);
      const r = await fetch(music + '/audio?' + q);
      if (!r.ok) throw new Error('Die MP3 kommt nicht vom Musik-Rechner (' + r.status + ')');
      const C = window.AudioContext || window.webkitAudioContext;
      const ac = new C();
      try { return SM.coverPeaks(await ac.decodeAudioData(await r.arrayBuffer()), n); } finally { if (ac.close) ac.close(); }
    }
    const k = 18, per = Math.ceil(n / k), raw = [];
    for (let i = 0; i < k; i++) {
      const a = Math.floor((size - SLICE) * i / (k - 1));
      try {
        const buf = await SM.decodeRange(music, q, a, a + SLICE - 1), d = buf.getChannelData(0), step = Math.max(1, Math.floor(d.length / per));
        for (let j = 0; j < per; j++) { let s = 0, c = 0; for (let x = j * step, e = Math.min(d.length, x + step); x < e; x += 32) { s += d[x] * d[x]; c++; } raw.push(Math.sqrt(s / Math.max(1, c))); }
      } catch (e) { for (let j = 0; j < per; j++) raw.push(0); }   // ein Stueck nicht lesbar: dort flach
    }
    const top = Math.max(1e-6, ...raw);
    return raw.slice(0, n).map(v => Math.pow(v / top, 1.6));
  };

  // Cover zu einer Datei erzeugen, nur aus dem, was schon in ihren Tags steht (Seite Tag-Vorschlaege, links bei "jetzt":
  // die Vorschlaege sind bei Eigenmischungen oft falsch, darum hier nie aus ihnen, Wunsch von Markus 07.11.2026). DataURL.
  SM.coverFor = async (music, path) => {
    const q = 'p=' + encodeURIComponent(path);
    const t = await fetch(music + '/tags?' + q).then(r => r.json());
    if (t.error) throw new Error(t.error);
    const peaks = await SM.peaksFor(music, q, 90);
    const f = t.fields || {};
    return SM.makeCover({ title: f.title || path.split('/').pop().replace(/\.[^.]+$/, ''), artist: f.artist, bpm: f.bpm, key: f.key, energy: f.energy, peaks });
  };

  // preset (Seite Tag-Vorschlaege): {fields: {Feld: Wert}, cover: Adresse}, schon eingetragen, geschrieben wird erst mit dem Knopf
  // Wellenform mit Fade-in/-out (Wunsch 11.11.2026): ziehen oder Zahlen eintippen, probehoeren mit Lautstaerke-Verlauf im Browser
  // (WebAudio), Speichern rechnet die MP3 am Mac neu (SM.fadeDlg, audio_fade.py). Dazu vorne/hinten abschneiden (11.11.2026),
  // in einem Durchgang: vorne weg, Fade-in, Fade-out, hinten weg.
  SM.fadeEditor = async (music, path, name) => {
    if (document.querySelector('.modal.fademodal')) return;
    const m = document.createElement('div');
    m.className = 'modal fademodal';
    m.style.zIndex = 70;
    m.innerHTML = '<div class="box" style="width:min(820px,100%)"><h2>〰 Fade und Schnitt: ' + esc(name || path.split('/').pop()) + '</h2>' +
      '<p class="dim" style="margin:-4px 0 8px">Ins Bild tippen: links setzt das Ende des Fade-in (oder wie viel vorne wegkommt), rechts den Beginn des Fade-out (oder ab wo hinten weggeschnitten wird). Oder Sekunden eintippen. Probehören spielt mit Schnitt und Verlauf, geändert wird erst mit „In die MP3 rechnen“, alles in einem Durchgang.</p>' +
      '<div class="row" style="margin-bottom:4px"><span class="dim">Tippen setzt:</span><label><input type="radio" name="fmode" value="fade" checked> Fade</label><label><input type="radio" name="fmode" value="cut"> Schnitt</label></div>' +
      '<canvas id="fwave" width="780" height="140" style="width:100%;height:140px;background:#0d0f16;border-radius:8px;cursor:crosshair"></canvas>' +
      '<div class="row"><label>Fade-in <input type="number" id="ffin" min="0" max="60" step="0.5" value="0" style="width:5em"> s</label>' +
      '<label>Fade-out <input type="number" id="ffout" min="0" max="60" step="0.5" value="0" style="width:5em"> s</label></div>' +
      '<div class="row"><label title="So viele Sekunden kommen am Anfang weg, der Fade-in beginnt danach">vorne weg <input type="number" id="fca" min="0" max="600" step="0.5" value="0" style="width:5em"> s</label>' +
      '<label title="So viele Sekunden kommen am Ende weg, der Fade-out endet davor">hinten weg <input type="number" id="fcb" min="0" max="600" step="0.5" value="0" style="width:5em"> s</label><span id="fdur" class="dim"></span></div>' +
      '<div id="fcutw" class="dim" hidden>Schnitt vorne: Hotcues und Beat-Raster in Mixxx verschieben sich um diese Sekunden (Mixxx analysiert das Lied neu, Hotcues bitte prüfen). Eine Show zu diesem Lied passt danach nicht mehr genau.</div>' +
      '<div class="row"><button id="fpa">▶ Anfang</button><button id="fpe">▶ Ende</button><button id="fps">■ Stopp</button><span style="flex:1"></span>' +
      '<button id="fclose">Schließen</button><button id="fsave" class="on">In die MP3 rechnen</button></div><div id="fmsg" class="dim"></div></div>';
    document.body.appendChild(m);
    const q = s => m.querySelector(s), cv = q('#fwave'), g = cv.getContext('2d');
    const audio = new Audio(); audio.crossOrigin = 'anonymous'; audio.src = music + '/audio?p=' + encodeURIComponent(path);
    const bar = SM.playBar(audio, { start: false, onclose: () => { audio.pause(); } });   // Leiste unten: springen, Lautstaerke (wie ueberall)
    let ac = null, gain = null, raf = 0, peaks = [], dur = 0;
    const fin = () => Math.max(0, +q('#ffin').value || 0), fout = () => Math.max(0, +q('#ffout').value || 0);
    const ca = () => Math.max(0, +q('#fca').value || 0), cb = () => Math.max(0, +q('#fcb').value || 0);
    const t0 = () => Math.min(ca(), dur), t1 = () => Math.max(t0(), dur - cb());   // was bleibt
    const showLen = () => { if (!dur) return; const l = t1() - t0(), mm = s => Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');
      q('#fdur').textContent = 'Länge ' + mm(dur) + (ca() || cb() ? ' → ' + mm(l) : ''); q('#fcutw').hidden = !ca(); };
    function draw() {
      const W = cv.width, H = cv.height;
      g.clearRect(0, 0, W, H);
      const n = peaks.length;
      g.fillStyle = '#4c8bf5';
      for (let i = 0; i < n; i++) { const x = i * W / n, v = peaks[i] * (H / 2 - 4); g.fillRect(x, H / 2 - v, Math.max(1, W / n - 0.5), 2 * v); }
      if (dur) {
        const xa = t0() / dur * W, xb = t1() / dur * W;
        g.fillStyle = 'rgba(13,15,22,.82)';                  // was wegkommt: abgedunkelt
        if (ca()) g.fillRect(0, 0, xa, H);
        if (cb()) g.fillRect(xb, 0, W - xb, H);
        g.strokeStyle = '#e05050'; g.lineWidth = 2;
        if (ca()) { g.beginPath(); g.moveTo(xa, 0); g.lineTo(xa, H); g.stroke(); }
        if (cb()) { g.beginPath(); g.moveTo(xb, 0); g.lineTo(xb, H); g.stroke(); }
        const xi = (t0() + fin()) / dur * W, xo = (t1() - fout()) / dur * W;
        g.fillStyle = 'rgba(240,160,48,.28)';
        if (fin()) { g.beginPath(); g.moveTo(xa, 0); g.lineTo(xi, 0); g.lineTo(xa, H); g.closePath(); g.fill(); }
        if (fout()) { g.beginPath(); g.moveTo(xo, 0); g.lineTo(xb, 0); g.lineTo(xb, H); g.closePath(); g.fill(); }
        g.strokeStyle = '#f0a030'; g.lineWidth = 2;
        if (fin()) { g.beginPath(); g.moveTo(xi, 0); g.lineTo(xi, H); g.stroke(); }
        if (fout()) { g.beginPath(); g.moveTo(xo, 0); g.lineTo(xo, H); g.stroke(); }
        if (!audio.paused) { const xp = audio.currentTime / dur * W; g.strokeStyle = '#fff'; g.lineWidth = 1; g.beginPath(); g.moveTo(xp, 0); g.lineTo(xp, H); g.stroke(); }
      }
    }
    const level = t => {
      if (t < t0() || t >= t1()) return 0;
      let v = 1; const a = t - t0(), b = t1() - t;
      if (fin() && a < fin()) v = Math.min(v, a / fin()); if (fout() && b < fout()) v = Math.min(v, Math.max(0, b / fout())); return v;
    };
    function tick() {
      if (dur && cb() && audio.currentTime >= t1()) audio.pause();   // hinten weg: dort ist Schluss
      if (gain) gain.gain.value = level(audio.currentTime); draw(); if (!audio.paused) raf = requestAnimationFrame(tick);
    }
    function play(from) {
      try {
        if (!ac) { const C = window.AudioContext || window.webkitAudioContext; ac = new C(); gain = ac.createGain(); ac.createMediaElementSource(audio).connect(gain).connect(ac.destination); }
        if (ac.state === 'suspended') ac.resume();
      } catch (e) { /* ohne WebAudio: ohne Verlauf */ }
      audio.currentTime = Math.max(t0(), from); gain && (gain.gain.value = level(audio.currentTime));
      audio.play().then(() => { cancelAnimationFrame(raf); tick(); bar.show((name || path.split('/').pop()) + ' (mit Fade)'); }).catch(e => { q('#fmsg').textContent = 'Abspielen ging nicht: ' + e.message; });
    }
    const close = () => { audio.pause(); bar.hide(); cancelAnimationFrame(raf); if (ac && ac.close) ac.close(); m.remove(); };
    q('#fclose').onclick = close;
    q('#fps').onclick = () => { audio.pause(); draw(); };
    q('#fpa').onclick = () => play(t0());
    q('#fpe').onclick = () => play(t1() - fout() - 6);
    q('#ffin').oninput = q('#ffout').oninput = draw;
    q('#fca').oninput = q('#fcb').oninput = () => { showLen(); draw(); };
    cv.onclick = e => {
      if (!dur) return;
      const r = cv.getBoundingClientRect(), t = (e.clientX - r.left) / r.width * dur, half = Math.round(t * 2) / 2;
      const cut = (m.querySelector('input[name=fmode]:checked') || {}).value === 'cut';
      if (cut) { if (t < dur / 2) q('#fca').value = Math.min(600, half); else q('#fcb').value = Math.min(600, Math.round((dur - t) * 2) / 2); }
      else if (t < dur / 2) q('#ffin').value = Math.min(60, Math.max(0, Math.round((t - t0()) * 2) / 2));
      else q('#ffout').value = Math.min(60, Math.max(0, Math.round((t1() - t) * 2) / 2));
      showLen(); draw();
    };
    q('#fsave').onclick = () => {
      if (!fin() && !fout() && !ca() && !cb()) { q('#fmsg').textContent = 'Erst Fade oder Schnitt setzen.'; return; }
      if (dur && t1() - t0() < 5) { q('#fmsg').textContent = 'Nach dem Schnitt bliebe fast nichts übrig.'; return; }
      audio.pause();
      SM.fadeDlg(music, [path], name || path.split('/').pop(), { fin: fin(), fout: fout(), ca: ca(), cb: cb(), autostart: true, done: () => { q('#fmsg').textContent = 'Fertig. Die MP3 ist neu gerechnet, das Original liegt im Papierkorb.'; } });
    };
    audio.addEventListener('loadedmetadata', () => { dur = audio.duration || 0; showLen(); draw(); });
    q('#fmsg').textContent = 'Lade die Wellenform …';
    try { peaks = await SM.peaksFor(music, 'p=' + encodeURIComponent(path), 390); q('#fmsg').textContent = ''; } catch (e) { q('#fmsg').textContent = 'Wellenform: ' + e.message; }
    draw();
  };

  SM.tagEdit = async function (r, music, onSaved, preset) {
    if (!music || !r || !r.path) return;
    // Nur ein Fenster: ein zweiter Klick auf "Tag" oeffnete ein zweites, das nach dem Schreiben mit dunklem Hintergrund
    // liegen blieb und die Liste sperrte (Fehlerbericht 07.11.2026).
    if (document.querySelector('.modal.tagmodal')) return;
    const name = r.path.split('/').pop();
    const q = 'p=' + encodeURIComponent(r.path);
    const m = document.createElement('div');
    m.className = 'modal tagmodal';
    m.innerHTML = '<div class="box tagbox"><h2>Tag bearbeiten</h2><p class="dim" id="tgsub">' + esc(name) + ' · wird gelesen …</p></div>';
    document.body.appendChild(m);
    const box = m.querySelector('.box');
    const close = () => {
      document.querySelectorAll('.modal.tagmodal audio').forEach(a => a.pause());
      document.querySelectorAll('.modal.tagmodal').forEach(x => x.remove());   // sicher alle, nie ein Rest, der die Liste sperrt
      document.removeEventListener('keydown', onKey);
    };
    m.addEventListener('mousedown', e => { if (e.target === m) m._down = true; });
    m.addEventListener('click', e => { if (e.target === m && m._down) close(); m._down = false; });   // Klick daneben schliesst
    const onKey = e => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    let tags;
    try {
      const resp = await fetch(music + '/tags?' + q);
      tags = await resp.json();
      if (!resp.ok) throw new Error(tags.error || ('Fehler ' + resp.status));
    } catch (e) {
      box.innerHTML = '<h2>Tag bearbeiten</h2><p>Lesen ging nicht: ' + esc(e.message) + '</p><div class="row"><button id="tgclose">Schließen</button></div>';
      box.querySelector('#tgclose').onclick = close;
      return;
    }
    const orig = Object.assign({}, tags.fields);
    let coverOwn = false;                                     // coverData ist ein Bild vom eigenen Rechner (nicht erzeugt)
    let coverUrl = '', coverData = '', removeCover = false, sugg = [], covers = [], decoded = null;
    const keys = Object.keys(tags.labels);
    const rest = keys.filter(k => !MAIN.includes(k));

    function field(k) {
      return '<label class="tglab" for="tg_' + k + '">' + esc(tags.labels[k]) + '</label>' +
        (k === 'comment' ? '<textarea id="tg_' + k + '" rows="2">' + esc(tags.fields[k]) + '</textarea>'
          : k === 'genre' ? '<div class="tggenre"><input id="tg_genre" value="' + esc(tags.fields[k]) + '">' +   // eine Zelle im Raster: Feld, darunter Hausliste und Claude, darunter die Antwort (Fehlerbericht 11.11.2026)
            '<div class="tgg2"><select id="tg_gsel" hidden title="Genre aus deiner Hausliste"></select><button type="button" id="tg_gai" hidden title="Claude fragen, welches Genre aus deiner Hausliste passt (kommt nur ins Feld, geschrieben wird erst mit Speichern)">🤖 Claude</button></div>' +
            '<div id="tg_gaimsg" class="dim"></div></div>'
          : '<input id="tg_' + k + '" value="' + esc(tags.fields[k]) + '">') +
        '<span class="tgsug" id="tgs_' + k + '"></span>';
    }
    if (SM.favLoad) await SM.favLoad();                       // Herz im Fenster (Favoriten, 14.11.2026): wirkt sofort, ohne Speichern
    const fav = SM.favHtml ? SM.favHtml('song', r.path, { cls: 'hbig', name: tags.fields.title || '', artist: tags.fields.artist || '' }) : '';
    box.innerHTML = '<h2>Tag bearbeiten' + fav + '<span id="tgstars"></span></h2><p class="dim" style="margin:-6px 0 10px">' + esc(tags.file || name) + ' · ID3v2.' + tags.ver +
      (tags.fav ? ' · Bewertung in der MP3: 5 Sterne' : '') + '</p>' +
      '<div class="tggrid"><div class="tgfields">' + MAIN.map(field).join('') +
      '<details class="tgmore"><summary>Weitere Felder (' + (rest.length + tags.other.length) + ')</summary><div class="tgfields">' + rest.map(field).join('') +
      tags.other.map(o => '<span class="tglab">' + esc(o.name) + '</span><span class="dim tgro" title="nur anzeigen, bleibt unverändert">' + esc(o.value) + '</span><span></span>').join('') +
      '</div></details></div>' +
      '<div class="tgside"><audio id="tgplay" controls preload="none" src="' + esc(music + '/audio?' + q) + '"></audio>' +
      '<div class="tgcover" id="tgcover"></div><div class="dim" id="tgcvinfo"></div>' +
      '<div class="row"><button id="tgcvrm">Cover entfernen</button><button id="tggen" title="Eigenes Cover aus Titel, Interpret, BPM, Tonart und der Wellenform des Liedes (für Eigenmischungen ohne Cover), ohne Internet">Cover erzeugen</button>' +
      '<button id="tgfile" title="Ein Bild (JPEG, PNG, HEIC …) von diesem Rechner, Handy oder iPad nehmen: wird quadratisch zugeschnitten (Mitte) und auf höchstens 1000 × 1000 Pixel verkleinert">Bild vom Rechner …</button><input type="file" id="tgfilein" accept="image/*" hidden>' +
      '<button id="tgsavecv" title="Das gezeigte Cover als Bilddatei auf diesem Rechner, Handy oder iPad speichern (Downloads), etwa um es mit „Bild vom Rechner …“ einem anderen Lied zu geben">Cover speichern …</button></div>' +
      '<div class="dim" style="margin-top:8px">Cover-Vorschläge</div><div class="tgcvs" id="tgcvs"><span class="dim">Erst „Im Internet suchen“.</span></div></div></div>' +
      '<div class="dim" id="tgmsg" style="margin:8px 0 0"></div>' +
      '<div class="row tgbtns"><button id="tgshazam" title="Erkennt das Lied am Klang: 12 Sekunden aus der Mitte gehen über den Light-Butler an Shazam (SongRec), nur auf Knopfdruck">Shazam</button>' +
      '<button id="tgname" title="Titel und Interpret aus dem Dateinamen („Interpret - Titel.mp3“, Tracknummer vorne), das Album aus dem Ordner. Kommt nur in die Felder, geschrieben wird erst mit „In die MP3 schreiben“">Aus Dateiname</button>' +
      '<button id="tgsearch" title="Fragt MusicBrainz, iTunes und Deezer nach Interpret und Titel (keine Musik, nur auf Knopfdruck)">Im Internet suchen</button>' +
      (/\.mp3$/i.test(r.path) ? '<button id="tgwave" title="Wellenform: Fade-in und Fade-out setzen, probehören und in die MP3 rechnen">〰 Wellenform</button>' : '') +
      '<select id="tgcand" hidden></select><button id="tgall" hidden>Alle Vorschläge übernehmen</button><span style="flex:1"></span>' +
      '<button id="tgcancel">Abbrechen</button><button id="tgsave" class="on">In die MP3 schreiben</button></div>';
    const $ = id => box.querySelector('#' + id);
    const val = k => $('tg_' + k).value;
    if ($('tgwave')) $('tgwave').onclick = () => SM.fadeEditor(music, r.path, name);
    (async () => {                                            // Genre: Auswahl aus der Hausliste (Genre-Editor), Eintippen geht weiter
      try {
        const h = ((await (await fetch(music + '/genres?house=1')).json()) || {}).house || [];
        const s = $('tg_gsel');
        if (!s || !h.length) return;
        const cur = ($('tg_genre').value || '').toLowerCase();
        s.innerHTML = '<option value="">Hausliste …</option>' + h.slice().sort((a, b) => a.localeCompare(b, 'de')).map(g => '<option' + (g.toLowerCase() === cur ? ' selected' : '') + '>' + esc(g) + '</option>').join('');
        s.hidden = false;
        s.onchange = () => { if (s.value) { $('tg_genre').value = s.value; $('tg_genre').dispatchEvent(new Event('input', { bubbles: true })); } markOut(); };
        // Claude-Knopf (Wunsch 11.11.2026): passt das Genre nicht in die Hausliste, ist das Feld markiert; Claude schlaegt eins vor
        const inHouse = () => { const v = ($('tg_genre').value || '').trim().toLowerCase(); return !v || h.some(g => g.toLowerCase() === v); };
        function markOut() {
          const out = !inHouse();
          $('tg_genre').style.outline = out ? '2px solid #e8a33d' : '';
          $('tg_genre').title = out ? 'Dieses Genre steht nicht in deiner Hausliste' : '';
        }
        $('tg_genre').addEventListener('input', markOut); markOut();
        const b = $('tg_gai'); b.hidden = false;
        b.onclick = async () => {
          b.disabled = true; $('tg_gaimsg').textContent = 'Claude denkt nach …';
          try {
            const song = { artist: val('artist'), title: val('title') || name, genre: val('genre') };
            const d = await (await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify({ op: 'genre_song_ai', house: h, songs: [song] }) })).json();
            if (d.error) throw new Error(d.error);
            const s0 = (d.songs || [])[0] || {};
            if (s0.to) { $('tg_genre').value = s0.to; $('tg_genre').dispatchEvent(new Event('input', { bubbles: true })); s.value = s0.to; }
            $('tg_gaimsg').textContent = '🤖 ' + (s0.to ? '→ ' + s0.to + ' (im Feld, noch nicht gespeichert)' : 'kein Genre der Hausliste passt sicher') + (s0.why ? ' · ' + s0.why : '');
          } catch (x) { $('tg_gaimsg').textContent = '🤖 ' + x.message; }
          b.disabled = false; b.textContent = '🤖 Claude';
        };
      } catch (e) { /* alter Mac oder keine Hausliste: nur das Textfeld */ }
    })();

    function drawCover() {
      const c = $('tgcover');
      if ($('tgsavecv')) $('tgsavecv').disabled = !coverData && !coverUrl && (removeCover || !tags.cover);   // ausgrauen statt verstecken
      if (coverData) { c.innerHTML = '<img src="' + coverData + '" alt="neues Cover">'; $('tgcvinfo').textContent = (coverOwn ? 'Eigenes Bild, quadratisch zugeschnitten' : 'Erzeugtes Cover') + ' (wird beim Schreiben gespeichert)'; return; }
      if (coverUrl) { c.innerHTML = '<img src="' + esc(coverUrl) + '" alt="neues Cover">'; $('tgcvinfo').textContent = 'Neues Cover (wird beim Schreiben geholt)'; return; }
      if (removeCover || !tags.cover) { c.innerHTML = '<span class="dim">kein Cover</span>'; $('tgcvinfo').textContent = removeCover ? 'Cover wird entfernt' : ''; return; }
      c.innerHTML = '<img src="' + esc(music + '/cover?' + q + '&t=' + Date.now()) + '" alt="Cover">';
      $('tgcvinfo').textContent = (tags.cover.mime || 'Bild') + ', ' + Math.round(tags.cover.size / 1024) + ' KB';
    }
    function drawSuggest() {
      const s = sugg[+$('tgcand').value || 0] || {};
      for (const k of SUGGEST) {
        const el = $('tgs_' + k);
        if (!el) continue;
        const v = s[k] || '';
        el.innerHTML = v && v !== val(k) ? '<button class="tgpick" data-k="' + k + '" title="Vorschlag von ' + esc(s.source || '') + ' übernehmen">← ' + esc(v) + '</button>' : '';
      }
    }
    function drawCovers() {
      const el = $('tgcvs');
      if (!covers.length) { el.innerHTML = '<span class="dim">Kein Cover gefunden.</span>'; return; }
      el.innerHTML = covers.map((c, i) => '<button class="tgcv" data-i="' + i + '" title="' + esc(c.source + (c.album ? ': ' + c.album : '')) + '"><img src="' + esc(c.url) + '" alt="" loading="lazy"></button>').join('');
      el.querySelectorAll('img').forEach(img => { img.onerror = () => img.parentElement.remove(); });
    }
    box.addEventListener('click', e => {
      const p = e.target.closest('.tgpick');
      if (p) { $('tg_' + p.dataset.k).value = (sugg[+$('tgcand').value || 0] || {})[p.dataset.k] || ''; drawSuggest(); return; }
      const c = e.target.closest('.tgcv');
      if (c) { coverUrl = covers[+c.dataset.i].url; coverData = ''; removeCover = false; drawCover(); }
    });
    $('tgcvrm').onclick = () => { coverUrl = ''; coverData = ''; removeCover = true; drawCover(); };
    $('tgcancel').onclick = close;
    $('tgcand').onchange = drawSuggest;
    $('tgall').onclick = () => { const s = sugg[+$('tgcand').value || 0] || {}; for (const k of SUGGEST) if (s[k] && $('tg_' + k)) $('tg_' + k).value = s[k]; drawSuggest(); };
    // Shazam: 12 s aus der Mitte (dort laeuft das Lied sicher), Mono, 22050 Hz, als WAV an den Pi (SongRec, wie die Live-Erkennung)
    function wavOf(buf, from, secs) {
      const rate = 22050, n = Math.floor(secs * rate), src = buf.sampleRate, ch = buf.numberOfChannels;
      const out = new Int16Array(n);
      const data = []; for (let c = 0; c < ch; c++) data.push(buf.getChannelData(c));
      let peak = 1e-9;
      const mono = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const j = Math.min(buf.length - 1, Math.floor((from + i / rate) * src));
        let v = 0; for (let c = 0; c < ch; c++) v += data[c][j];
        mono[i] = v / ch; peak = Math.max(peak, Math.abs(mono[i]));
      }
      const g = Math.min(0.9 / peak, 100);
      for (let i = 0; i < n; i++) out[i] = Math.max(-32767, Math.min(32767, Math.round(mono[i] * g * 32767)));
      const b = new ArrayBuffer(44 + n * 2), v = new DataView(b);
      const str = (o, t) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
      str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true);
      v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true);
      v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, n * 2, true);
      new Int16Array(b, 44).set(out);
      return new Blob([b], { type: 'audio/wav' });
    }
    async function decode() {                                  // die MP3 einmal vom Mac holen und dekodieren (Shazam und Cover)
      if (decoded) return decoded;
      const size = await SM.audioSize(music, q);
      if (size > BIG) {                                         // sehr lang: fuer Shazam reicht ein Stueck aus der Mitte
        const a = Math.floor(size / 2);
        decoded = await SM.decodeRange(music, q, a, a + 3 * SLICE - 1);
        decoded.partial = true;
        return decoded;
      }
      const resp = await fetch(music + '/audio?' + q);
      if (!resp.ok) throw new Error('Die MP3 kommt nicht vom Musik-Rechner (' + resp.status + ')');
      const C = window.AudioContext || window.webkitAudioContext;
      const ac = new C();
      decoded = await ac.decodeAudioData(await resp.arrayBuffer());
      if (ac.close) ac.close();
      return decoded;
    }
    // Bild vom eigenen Rechner (Wunsch 09.11.2026): Mitte quadratisch ausschneiden, hoechstens 1000 px, als JPEG
    $('tgfile').onclick = () => $('tgfilein').click();
    // Cover lokal speichern (Wunsch 14.11.2026): das gezeigte Bild (aus der MP3, gewaehlter Vorschlag oder erzeugtes) als Datei
    $('tgsavecv').onclick = async () => {
      const b = $('tgsavecv');
      const src = coverData || coverUrl || (tags.cover && !removeCover ? music + '/cover?' + q : '');
      if (!src) return;
      b.disabled = true;
      try {
        const blob = await (await fetch(src)).blob();
        if (!/^image\//.test(blob.type)) throw new Error('kein Bild');
        const ext = /png/.test(blob.type) ? 'png' : 'jpg';
        const base = ((val('artist') ? val('artist') + ' - ' : '') + (val('title') || name.replace(/\.[^.]+$/, ''))).replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120) || 'Cover';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = base + '.' + ext;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 10000);
        $('tgmsg').textContent = 'Cover gespeichert als „' + base + '.' + ext + '“ (Ordner Downloads). Beim anderen Lied mit „Bild vom Rechner …“ wählen.';
      } catch (e) {
        $('tgmsg').textContent = 'Cover speichern ging nicht (' + e.message + '). Mit Rechtsklick auf das Bild → „Bild sichern unter …“ geht es auch.';
      } finally { drawCover(); }
    };
    $('tgfilein').onchange = async () => {
      const f = $('tgfilein').files && $('tgfilein').files[0];
      $('tgfilein').value = '';
      if (!f) return;
      try {
        coverData = await SM.squareCover(f, 1000);
        coverOwn = true; coverUrl = ''; removeCover = false;
        drawCover();
      } catch (e) { $('tgmsg').textContent = 'Bild ging nicht: ' + e.message; }
    };
    $('tggen').onclick = async () => {
      const b = $('tggen');
      b.disabled = true; b.textContent = 'Erzeuge …';
      try {
        const peaks = await SM.peaksFor(music, q, 90, decode);   // grosse Dateien: aus Stuecken ueber die ganze Laenge
        coverData = SM.makeCover({ title: val('title') || name.replace(/\.[^.]+$/, ''), artist: val('artist'), bpm: val('bpm'), key: val('key'),
          energy: val('energy'), peaks });
        coverUrl = ''; removeCover = false; coverOwn = false;
        drawCover();
      } catch (e) {
        $('tgmsg').textContent = 'Cover erzeugen ging nicht: ' + e.message;
      } finally {
        b.disabled = false; b.textContent = 'Cover erzeugen';
      }
    };
    $('tgshazam').onclick = async () => {
      const b = $('tgshazam');
      b.disabled = true; $('tgmsg').textContent = '';
      try {
        b.textContent = 'Lade MP3 …';
        const buf = await decode();
        const secs = Math.min(12, buf.duration);
        const from = Math.max(0, Math.min(buf.duration * 0.4, buf.duration - secs));
        b.textContent = 'Shazam …';
        const up = await fetch('/api/sm/recognize', { method: 'POST', body: wavOf(buf, from, secs) });
        const d = await up.json().catch(() => ({}));
        if (!up.ok || d.error) throw new Error(d.error || ('Fehler ' + up.status));
        if (d.kind !== 'ok' || !d.song) {
          $('tgmsg').textContent = d.kind === 'nomatch' ? 'Shazam kennt dieses Lied nicht.' : d.kind === 'offline' ? 'Der Light-Butler hat kein Internet.' :
            d.kind === 'missing' ? 'SongRec fehlt am Light-Butler.' : 'Shazam ging nicht: ' + (d.msg || d.kind);
          return;
        }
        const s = { source: 'Shazam', title: d.song.title, artist: d.song.artist, genre: d.song.genre || '' };
        sugg = [s].concat(sugg.filter(x => x.source !== 'Shazam'));
        const sel = $('tgcand');
        sel.innerHTML = sugg.map((x, i) => '<option value="' + i + '">' + esc(x.source + ': ' + (x.source === 'Shazam' ? x.artist + ' - ' + x.title : (x.album || x.title || '?')) + (x.year ? ' (' + x.year + ')' : '')) + '</option>').join('');
        sel.value = '0'; sel.hidden = false; $('tgall').hidden = false;
        drawSuggest();
        $('tgmsg').innerHTML = 'Shazam: <b>' + esc(s.artist + ' - ' + s.title) + '</b>' + (s.genre ? ' (' + esc(s.genre) + ')' : '') +
          ' <button id="tgshuse">Übernehmen und im Internet suchen</button>';
        $('tgshuse').onclick = () => {
          $('tg_title').value = s.title; $('tg_artist').value = s.artist;
          if (s.genre && !val('genre')) $('tg_genre').value = s.genre;
          $('tgsearch').click();
        };
      } catch (e) {
        $('tgmsg').textContent = 'Shazam ging nicht: ' + e.message;
      } finally {
        b.disabled = false; b.textContent = 'Shazam';
      }
    };
    $('tgname').onclick = () => {                             // Aus Dateiname (Wunsch 12.11.2026): nur in die Felder
      const got = SM.nameTags(r.path), done = [];
      for (const k of ['title', 'artist', 'track', 'album']) {
        if (!got[k] || !$('tg_' + k) || val(k) === got[k]) continue;
        $('tg_' + k).value = got[k]; $('tg_' + k).dispatchEvent(new Event('input', { bubbles: true }));
        done.push(tags.labels[k] + ' „' + got[k] + '“');
      }
      $('tgmsg').textContent = done.length ? 'Aus dem Dateinamen eingetragen: ' + done.join(', ') + '. Geschrieben wird erst mit „In die MP3 schreiben“.'
        : 'Der Dateiname gibt nichts Neues her' + (got.title ? '' : ' (erwartet: „Interpret - Titel.mp3“)') + '.';
    };
    $('tgsearch').onclick = async () => {
      const b = $('tgsearch');
      b.disabled = true; b.textContent = 'Suche …'; $('tgmsg').textContent = '';
      try {
        const resp = await fetch(music + '/lookup?' + q + '&artist=' + encodeURIComponent(val('artist')) + '&title=' + encodeURIComponent(val('title')) + '&dur=' + (r.dur || 0));
        const d = await resp.json();
        if (!resp.ok) throw new Error(d.error || ('Fehler ' + resp.status));
        sugg = sugg.filter(x => x.source === 'Shazam').concat(d.suggest || []); covers = d.covers || [];
        const sel = $('tgcand');
        sel.innerHTML = sugg.map((s, i) => '<option value="' + i + '">' + esc(s.source + ': ' + (s.source === 'Shazam' ? s.artist + ' - ' + s.title : (s.album || s.title || '?')) + (s.year ? ' (' + s.year + ')' : '')) + '</option>').join('');
        if (sugg.length > 1 && sugg[0].source === 'Shazam') sel.value = '1';   // nach der Suche zuerst die Internet-Vorschlaege
        sel.hidden = !sugg.length; $('tgall').hidden = !sugg.length;
        drawSuggest(); drawCovers();
        $('tgmsg').textContent = (sugg.length ? sugg.length + ' Vorschläge' : 'Keine Vorschläge gefunden') + (d.errors && d.errors.length ? ' · nicht erreichbar: ' + d.errors.join(', ') : '') + '. Übernehmen mit ←, dann „In die MP3 schreiben“.';
      } catch (e) {
        $('tgmsg').textContent = 'Suche ging nicht: ' + e.message;
      } finally {
        b.disabled = false; b.textContent = 'Im Internet suchen';
      }
    };
    $('tgsave').onclick = async () => {
      const fields = {};
      for (const k of keys) if ($('tg_' + k) && val(k) !== (orig[k] || '')) fields[k] = val(k);
      if (tags.genre_num && $('tg_genre') && val('genre') && !('genre' in fields)) fields.genre = val('genre');   // "(148)" -> Name in die Datei (09.11.2026)
      if (!Object.keys(fields).length && !coverUrl && !coverData && !removeCover) { close(); return; }
      const b = $('tgsave');
      b.disabled = true; b.textContent = 'Schreibe …';
      try {
        const resp = await fetch(music + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ p: r.path, name, fields, cover_url: coverUrl || undefined, cover_data: coverData ? coverData.split(',')[1] : undefined, cover_src: coverData && coverOwn ? 'datei' : undefined,
            remove_cover: removeCover || undefined }) });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok || !d.ok) throw new Error(d.error || ('Fehler ' + resp.status));
        if (coverUrl || coverData || removeCover) {
          try { await SM.cmd('cover_refresh', { path: r.path }); } catch (e) { /* Cover kommt dann spaeter */ }
        }
        close();
        if (onSaved) onSaved(d, fields);
      } catch (e) {
        b.disabled = false; b.textContent = 'In die MP3 schreiben';
        $('tgmsg').textContent = 'Schreiben ging nicht: ' + e.message;
      }
    };
    box.addEventListener('input', drawSuggest);
    if (preset) {
      for (const [k, v] of Object.entries(preset.fields || {})) if ($('tg_' + k) && v) $('tg_' + k).value = v;
      if (preset.cover) { coverUrl = preset.cover; removeCover = false; }
      $('tgmsg').textContent = 'Vorschlag des Auto-Taggers eingetragen. Prüfen, ändern, dann „In die MP3 schreiben“.';
    }
    drawCover();
    if (SM.starsHtml) {                                       // Sterne im Fenster (14.11.2026): wirken sofort, kommen beim naechsten Start der Mixxx-App in Mixxx
      fetch('/api/sm/stars?p=' + encodeURIComponent(r.path)).then(x => x.json()).then(d => { if ($('tgstars')) $('tgstars').innerHTML = SM.starsHtml(r.path, d.r, 'big'); }).catch(() => {});
    }
  };

  if (typeof module !== 'undefined') module.exports = SM;
})();
