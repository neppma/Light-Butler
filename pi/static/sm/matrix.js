// matrix.js - Seite Pixel-Matrix (/matrix): Vorschau des Bildes, das der Light-Butler an die WLED-Matrix schickt,
// Adresse, Muster, Helligkeit, Groesse, Drehung. Rechnung und Versand am Licht-Rechner (wled_matrix.py).
(function () {
  'use strict';
  let EN = false, S = {}, ipDirty = false;
  const $ = id => document.getElementById(id);
  const PAT_EN = ['Auto', 'Plasma', 'Rings', 'Level', 'Sparks', 'Tunnel', 'Test picture', 'Snake', 'Grid', 'Scanner', 'Explosion', 'Kaleidoscope', 'Glitch'];

  async function cmd(d) {
    const r = await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) });
    if (!r.ok) { const j = await r.json().catch(() => ({})); alert(j.error || r.statusText); }
    poll();
  }
  const set = (k, v) => cmd({ set: { [k]: v } });

  function paintLang() {
    document.documentElement.lang = EN ? 'en' : 'de';
    document.querySelectorAll('[data-en]').forEach(el => {
      if (el.dataset.de === undefined) el.dataset.de = el.textContent;
      el.textContent = EN ? el.dataset.en : el.dataset.de;
    });
  }

  function buttons(m) {
    const pat = $('pat');
    if (!pat.children.length) {
      m.patterns.forEach((n, i) => {
        const b = document.createElement('button');
        b.textContent = EN ? PAT_EN[i] || n : n;
        b.onclick = () => set('pm_pattern', i);
        pat.appendChild(b);
      });
      ['0°', '90°', '180°', '270°'].forEach((n, i) => {
        const b = document.createElement('button');
        b.textContent = n;
        b.onclick = () => set('pm_rot', i);
        $('rot').appendChild(b);
      });
    }
    if (!$('txt').children.length) {
      (EN ? ['off', 'A one line', 'B three lines', 'C cover + band', 'D word by word', 'Auto'] : ['aus', 'A eine Zeile', 'B drei Zeilen', 'C Cover + Band', 'D Wort für Wort', 'Auto']).forEach((n, i) => {
        const b = document.createElement('button');
        b.textContent = n;
        b.onclick = () => set('pm_text', i);
        $('txt').appendChild(b);
      });
    }
    [...$('txt').children].forEach((b, i) => b.classList.toggle('on', i === Math.round(S.pm_text || 0)));
    if (!$('lyr').children.length) {          // Liedtext auf der Matrix (21.11.2026)
      (EN ? ['off', 'chorus: scroll', 'chorus: word by word', 'always: scroll', 'always: word by word'] : ['aus', 'Refrain: Laufschrift', 'Refrain: Wort für Wort', 'immer: Laufschrift', 'immer: Wort für Wort']).forEach((n, i) => {
        const b = document.createElement('button');
        b.textContent = n;
        b.onclick = () => set('pm_lyrics', i);
        $('lyr').appendChild(b);
      });
    }
    [...$('lyr').children].forEach((b, i) => b.classList.toggle('on', i === Math.round(S.pm_lyrics || 0)));
    if (document.activeElement !== $('tpx')) { $('tpx').value = S.pm_text_px || 8; $('tpxv').textContent = (S.pm_text_px || 8) + (EN ? ' px/beat' : ' px/Beat'); }
    [...pat.children].forEach((b, i) => b.classList.toggle('on', i === m.pattern));
    [...$('rot').children].forEach((b, i) => b.classList.toggle('on', i === S.pm_rot));
    $('on').classList.toggle('on', m.on); $('off').classList.toggle('on', !m.on);
    $('s1').classList.toggle('on', S.pm_serp > 0.5); $('s0').classList.toggle('on', !(S.pm_serp > 0.5));
  }

  function draw(m) {
    const cv = $('pv');
    if (cv.width !== m.w || cv.height !== m.h) { cv.width = m.w; cv.height = m.h; }
    const raw = atob(m.px), ctx = cv.getContext('2d'), img = ctx.createImageData(m.w, m.h);
    for (let i = 0, j = 0; i < raw.length; i += 3, j += 4) {
      img.data[j] = raw.charCodeAt(i); img.data[j + 1] = raw.charCodeAt(i + 1); img.data[j + 2] = raw.charCodeAt(i + 2); img.data[j + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  function status(m) {
    let t;
    if (m.dry) t = EN ? 'Dry run: preview only, nothing is sent' : 'Trockenlauf: nur Vorschau, es wird nichts gesendet';
    else if (!m.ip) t = EN ? 'No address yet: preview only' : 'Noch keine Adresse: nur Vorschau';
    else if (!m.on) t = (EN ? 'Preview only, sending is off · ' : 'Nur Vorschau, Senden ist aus · ') + m.ip;
    else if (m.reach === false) t = (EN ? 'Matrix does not answer (' : 'Matrix antwortet nicht (') + m.ip + (EN ? '): sending paused, checked every 5 s' : '): Senden pausiert, Prüfung alle 5 s');
    else t = (EN ? 'Sending to ' : 'Sendet an ') + m.ip + ' · ' + m.sent + (EN ? ' frames' : ' Bilder') + (m.errors ? ' · ' + m.errors + (EN ? ' errors' : ' Fehler') : '');
    if (m.pics) t += (EN ? ' · Pictures: ' : ' · Bilder zum Lied: ') + m.pics;
    $('st').textContent = t;
  }

  async function poll() {
    try {
      const [m, L] = await Promise.all([fetch('/api/matrix', { cache: 'no-store' }).then(r => r.json()),
        fetch('/api/settings', { cache: 'no-store' }).then(r => r.json())]);
      S = {};
      (L || []).forEach(g => (g.items || []).forEach(x => { S[x.key] = x.value; }));
      if (!ipDirty) $('ip').value = m.ip || '';
      if (document.activeElement !== $('br')) { $('br').value = Math.round((S.pm_bright || 0.5) * 100); $('brv').textContent = $('br').value + ' %'; }
      if (document.activeElement !== $('gm')) { $('gm').value = S.pm_gamma || 2.2; $('gmv').textContent = Number($('gm').value).toFixed(1); }
      if (document.activeElement !== $('ld')) { $('ld').value = S.pm_loud ?? 0.7; $('ldv').textContent = Math.round($('ld').value * 100) + ' %'; }
      if (document.activeElement !== $('w')) $('w').value = S.pm_w || 32;
      if (document.activeElement !== $('h')) $('h').value = S.pm_h || 32;
      buttons(m); draw(m); status(m);
    } catch (e) { $('st').textContent = EN ? 'Light-Butler not reachable' : 'Light-Butler nicht erreichbar'; }
  }

  async function frames() {
    try { const m = await fetch('/api/matrix', { cache: 'no-store' }).then(r => r.json()); draw(m); status(m); } catch (e) { /* naechster Versuch */ }
  }

  function init() {
    paintLang();
    fetch('/api/nav', { cache: 'no-store' }).then(r => r.json()).then(d => { EN = d.lang === 'en'; paintLang(); }).catch(() => {});
    $('on').onclick = () => set('pm_on', 1);
    $('off').onclick = () => set('pm_on', 0);
    $('s0').onclick = () => set('pm_serp', 0);
    $('s1').onclick = () => set('pm_serp', 1);
    $('ip').oninput = () => { ipDirty = true; };
    $('ipsave').onclick = () => { ipDirty = false; cmd({ matrix_ip: $('ip').value.trim() }); };
    // Geraetesuche (21.11.2026): WLEDs im Netz in einer Auswahl, Matrizen zuerst; Wahl traegt Adresse (und Groesse) ein
    let FOUND = [];
    $('scan').onclick = async () => {
      const b = $('scan'), st = $('scanst');
      b.disabled = true; st.textContent = EN ? 'Searching the network (a few seconds) …' : 'Suche im Netz (ein paar Sekunden) …';
      try {
        const d = await fetch('/api/matrix_scan', { cache: 'no-store' }).then(r => r.json());
        FOUND = d.found || [];
        const sel = $('found');
        sel.innerHTML = '';
        const head = document.createElement('option');
        head.value = ''; head.textContent = FOUND.length ? (EN ? '– choose (' + FOUND.length + ' found) –' : '– wählen (' + FOUND.length + ' gefunden) –') : (EN ? 'nothing found' : 'nichts gefunden');
        sel.appendChild(head);
        FOUND.forEach((x, i) => {
          const o = document.createElement('option');
          o.value = String(i);
          o.textContent = x.name + ' · ' + x.ip + (x.matrix ? ' · Matrix ' + x.w + '×' + x.h : ' · ' + x.leds + ' LEDs') + (x.ip === $('ip').value.trim() ? ' ✓' : '');
          sel.appendChild(o);
        });
        sel.style.display = '';
        st.textContent = d.error ? d.error : FOUND.length ? (EN ? 'Choose a device, then Save.' : 'Gerät wählen, dann Speichern.') : (EN ? 'No WLED answered. Is it switched on and in the same network?' : 'Kein WLED hat geantwortet. Ist es eingeschaltet und im selben Netz?');
      } catch (e) { st.textContent = e.message; }
      b.disabled = false;
    };
    $('found').onchange = () => {
      const x = FOUND[Number($('found').value)];
      if (!x || $('found').value === '') return;
      $('ip').value = x.ip; ipDirty = true;
      if (x.matrix && (x.w !== (S.pm_w || 32) || x.h !== (S.pm_h || 32))) {
        set('pm_w', x.w); set('pm_h', x.h);
        $('scanst').textContent = (EN ? 'Size taken from the device: ' : 'Größe vom Gerät übernommen: ') + x.w + '×' + x.h + (EN ? '. Now tap Save.' : '. Jetzt Speichern tippen.');
      } else {
        $('scanst').textContent = EN ? 'Address entered: tap Save.' : 'Adresse eingetragen: Speichern tippen.';
      }
    };
    $('br').oninput = () => { $('brv').textContent = $('br').value + ' %'; };
    $('br').onchange = () => set('pm_bright', Number($('br').value) / 100);
    $('gm').oninput = () => { $('gmv').textContent = Number($('gm').value).toFixed(1); };
    $('gm').onchange = () => set('pm_gamma', Number($('gm').value));
    $('ld').oninput = () => { $('ldv').textContent = Math.round($('ld').value * 100) + ' %'; };
    $('ld').onchange = () => set('pm_loud', Number($('ld').value));
    $('tpx').oninput = () => { $('tpxv').textContent = $('tpx').value + (EN ? ' px/beat' : ' px/Beat'); };
    $('tpx').onchange = () => set('pm_text_px', Number($('tpx').value));
    $('w').onchange = () => set('pm_w', Number($('w').value));
    $('h').onchange = () => set('pm_h', Number($('h').value));
    poll();
    setInterval(poll, 2000);
    setInterval(frames, 100);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
