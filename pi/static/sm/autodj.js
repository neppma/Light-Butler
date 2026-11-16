// autodj.js - Seite /musik/autodj: Auto-DJ (Wunsch von Markus, 07.11.2026).
// 1. Playlist: der Pi rechnet sie (showman/autodj.py, nach Regeln oder mit Claude), hier nur anzeigen, umstellen, merken.
// 2. Auflegen: zwei <audio> am Vorhoer-Server des Mac, ueber WebAudio gemischt. Ueberblenden mit gleicher Lautstaerke
//    (cos/sin), Tempo des neuen Liedes ueber playbackRate angeglichen (Tonhoehe bleibt: preservesPitch), Beats mit dem
//    Beat-Raster der Mac-Analyse (/marks: bpm, fb = erster Beat) in Phase gebracht und waehrend der Ueberblendung nachgeregelt
//    (wie ein DJ am Jogwheel). Ohne Raster schaetzt die Seite den ersten Beat aus den ersten 50 s der MP3.
//    Aufs Licht wirkt nichts davon.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mmss = d => { d = Math.max(0, Math.round(d || 0)); return Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0'); };
  const hm = d => { d = Math.round((d || 0) / 60); return Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0') + ' h'; };

  // ---- reine Rechnungen (auch fuer die Tests, window.ADJ) ---------------------------------------------------------
  const ADJ = {};
  // Rate fuer das neue Lied, damit es im Tempo des alten laeuft (auch halbes/doppeltes Tempo). max = erlaubte Abweichung.
  ADJ.rateFor = (bpmOut, bpmIn, max) => {
    if (!(bpmOut > 0) || !(bpmIn > 0) || !(max > 0)) return { rate: 1, sync: false };
    let best = 1, bd = 9;
    for (const f of [0.5, 1, 2]) { const r = bpmOut * f / bpmIn; if (Math.abs(r - 1) < bd) { bd = Math.abs(r - 1); best = r; } }
    return bd <= max + 1e-9 ? { rate: best, sync: true } : { rate: 1, sync: false };
  };
  // Ende, an dem die Musik wirklich aufhoert: letzte Stelle der Lautstaerkekurve (en, 0..100) ueber einem Viertel des Hoechsten.
  ADJ.musicEnd = (en, du) => {
    if (!en || !en.length || !(du > 0)) return du;
    const top = Math.max.apply(null, en) || 1;
    let i = en.length - 1;
    while (i > 0 && en[i] < top * 0.25) i--;
    return Math.min(du, Math.max(du * 0.6, (i + 1) / en.length * du));
  };
  // Erste hoerbare Stelle (Lautstaerke ueber 10 %), damit kein langes Schweigen am Anfang mitlaeuft
  ADJ.musicStart = (en, du) => {
    if (!en || !en.length || !(du > 0)) return 0;
    const top = Math.max.apply(null, en) || 1;
    let i = 0;
    while (i < en.length - 1 && en[i] < top * 0.1) i++;
    return Math.min(du * 0.3, i / en.length * du);
  };
  // Wo die Ueberblendung im alten Lied beginnt (Zeit im Lied) und wie lang sie dort ist (Sekunden im Lied).
  // a = {bpm, fb, end}; now = aktuelle Stelle. Mit Raster auf einem Takt (fb + 4n Beats), sonst einfach end - Laenge.
  ADJ.mixPoint = (a, bars, now, sync) => {
    if (sync && a.bpm > 0 && a.fb != null) {
      const beat = 60 / a.bpm, bar = 4 * beat;
      for (let b = bars; b >= 2; b = b / 2) {
        const len = b * bar;
        const t = a.fb + Math.floor((a.end - len - a.fb) / bar) * bar;
        if (t >= now + 2) return { t, len, bars: b };
      }
      const t = a.fb + Math.ceil((now + 1 - a.fb) / bar) * bar;   // zu spaet fuer eine lange: auf dem naechsten Takt, 2 Takte
      return { t, len: 2 * bar, bars: 2 };
    }
    const len = Math.min(12, Math.max(4, (a.end - now) - 1));
    return { t: Math.max(now + 0.5, a.end - len), len, bars: 0 };
  };
  // Phasenfehler in Beats (-0,5..0,5): wie weit B gegenueber A vor (+) oder nach (-) liegt.
  ADJ.phaseErr = (ta, fa, bpmA, tb, fb, bpmB) => {
    const pa = (ta - fa) * bpmA / 60, pb = (tb - fb) * bpmB / 60;
    let e = (pb - pa) % 1;
    if (e < -0.5) e += 1;
    if (e >= 0.5) e -= 1;
    return e;
  };
  // Nachregeln: Rate fuer B, damit der Fehler in rund 1,5 s weg ist; hoechstens 3 % neben der Grundrate, kleine Fehler ruhen.
  ADJ.nudge = (base, err, bpmB) => {
    if (Math.abs(err) < 0.015) return base;
    const d = err * (60 / bpmB) / 1.5;
    return base - Math.max(-0.03, Math.min(0.03, d));
  };
  // B zaehlt halb oder doppelt so viele Beats wie A (64 zu 128 BPM): Faktor fuer B, damit die Beats vergleichbar sind
  ADJ.beatMult = (bpmA, bpmB) => (bpmA > 0 && bpmB > 0 ? Math.pow(2, Math.round(Math.log2(bpmA / bpmB))) : 1);
  // Lautstaerke beim Ueberblenden, p = 0..1: gleiche Leistung (cos/sin)
  ADJ.gains = p => { p = Math.max(0, Math.min(1, p)); return [Math.cos(p * Math.PI / 2), Math.sin(p * Math.PI / 2)]; };
  // Erster Beat aus einer Huellkurve der Bass-Einsaetze (100 Werte je Sekunde) bei bekanntem Tempo
  ADJ.phaseFromFlux = (flux, rate, bpm) => {
    const T = rate * 60 / bpm;
    let best = -1, bs = 0;
    for (let ph = 0; ph < T; ph += 0.5) {
      let s = 0;
      for (let x = ph; x < flux.length - 1; x += T) { const i = Math.floor(x), f = x - i; s += flux[i] * (1 - f) + flux[i + 1] * f; }
      if (s > best) { best = s; bs = ph; }
    }
    return bs / rate;
  };
  // Uebergangs-Effekte (Wunsch 07.11.2026): weich, Filter, Echo, Bremse; "passend" waehlt selbst
  const ELECTRO = /house|edm|dance|techno|trance|electro|club|dubstep|drum|bass|hardstyle/i;
  ADJ.pickTrans = (choice, a, b, sync) => {
    if (choice && choice !== 'auto') return choice;
    if (!sync) return 'echo';                                  // Tempo zu weit weg oder kein Raster: Echo verdeckt den Bruch
    if (ELECTRO.test((a && a.genre) || '') && ELECTRO.test((b && b.genre) || '')) return 'filter';
    return 'soft';
  };
  // p = 0..1 durch die Ueberblendung: Lautstaerke alt (a), neu (b), Echo-Anteil vom alten (send), Hochpass am alten in Hz (hp)
  ADJ.transGains = (kind, p) => {
    p = Math.max(0, Math.min(1, p));
    const g = ADJ.gains(p);
    if (kind === 'filter') return { a: g[0], b: g[1], send: 0, hp: 20 * Math.pow(75, Math.min(1, p * 1.25)) };   // 20 Hz -> 1,5 kHz
    if (kind === 'echo') return { a: Math.max(0, 1 - p * 4), b: Math.sin(Math.min(1, p * 1.3) * Math.PI / 2), send: p < 0.3 ? 1 : 0, hp: 20 };
    return { a: g[0], b: g[1], send: 0, hp: 20 };
  };
  // Bremse wie am Plattenspieler, w = 0..1 ueber BRAKE_MS: Tempo des alten faellt, das neue setzt am Ende hart ein
  ADJ.BRAKE_MS = 900;
  ADJ.brake = w => { w = Math.max(0, Math.min(1, w)); return { rate: Math.max(0.06, 1 - w * w), a: w < 0.9 ? 1 : 0, b: w >= 0.85 ? 1 : 0 }; };
  window.ADJ = ADJ;
  if (!document.getElementById('items')) return;           // nur die Rechnungen (Test ohne Seite)

  // ---- Zustand ---------------------------------------------------------------------------------------------------
  let music = '', items = [], note = '', seed = 0, info = null, lib = null, busy = false;
  let sel = -1;                                              // angetipptes Lied: Play beginnt dort
  let ctx = null, master = null;
  const decks = [0, 1].map(() => ({ a: null, node: null, gain: null, low: null, item: null, info: null, ready: false, base: 1 }));
  let cur = -1, live = 0;                                    // cur = Index des laufenden Liedes in items, live = sein Deck
  let mix = null;                                            // laufende oder geplante Ueberblendung
  let glide = null, playing = false, lastNudge = 0, lastErr = null;

  const toast = t => SM.toast(t, 4000);
  async function cmd(op, data) {
    const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify(Object.assign({ op }, data || {})) });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    return d;
  }
  const wish = () => ({ theme: $('wtheme').value, audience: $('waud').value, genres: $('wgen').value, crates: $('wcrate').value, notes: $('wnotes').value,
    minutes: +$('wmin').value || 240, start: $('wstart').value || '20:00', e_lo: +$('welo').value || 4, e_hi: +$('wehi').value || 8, bpm_lo: +$('wblo').value || 0, bpm_hi: +$('wbhi').value || 0,
    y_lo: +$('wylo').value || 0, y_hi: +$('wyhi').value || 0, fav: +$('wfav').value || 0 });
  function setWish(w) {
    w = w || {};
    $('wtheme').value = w.theme || ''; $('waud').value = w.audience || ''; $('wgen').value = w.genres || ''; $('wcrate').value = w.crates || ''; $('wnotes').value = w.notes || '';
    if (w.minutes) $('wmin').value = w.minutes; if (w.e_lo) $('welo').value = w.e_lo; if (w.e_hi) $('wehi').value = w.e_hi;
    $('wblo').value = +w.bpm_lo || ''; $('wbhi').value = +w.bpm_hi || '';
    $('wylo').value = +w.y_lo || ''; $('wyhi').value = +w.y_hi || '';
    $('wfav').value = String(Math.max(0, Math.min(2, +w.fav || 0)));
    if (w.start) $('wstart').value = w.start;
    drawGenres(); drawCrates();
  }
  try { const w = JSON.parse(localStorage.getItem('autodj_wish') || 'null'); if (w) setWish(w); } catch (e) { /* privates Fenster */ }

  // Genres einzeln antippen statt Auswahlliste (Wunsch 07.11.2026); gewaehlt stehen sie mit Komma in #wgen
  function gsel() { return new Set($('wgen').value.split(',').map(x => x.trim().toLowerCase()).filter(Boolean)); }   // auch vor dem Laden nutzbar
  function drawGenres() {
    const g = ((info && info.genres) || []).slice().sort((a, b) => String(a[0]).localeCompare(String(b[0]), 'de', { sensitivity: 'base' })), on = gsel();   // alphabetisch
    const extra = $('wgen').value.split(',').map(x => x.trim()).filter(x => x && !g.some(y => y[0].toLowerCase() === x.toLowerCase()));   // gemerkt, nicht in der Liste
    $('gchips').innerHTML = g.map(x => '<button type="button" data-g="' + esc(x[0]) + '"' + (on.has(x[0].toLowerCase()) ? ' class="on"' : '') + '>' + esc(x[0]) + '<small>' + x[1] + '</small></button>').join('') +
      extra.map(x => '<button type="button" class="on" data-g="' + esc(x) + '">' + esc(x) + '</button>').join('') || '<span class="dim2">Genres kommen vom Musik-Rechner (Mixxx-Brücke oder Helfer).</span>';
  }
  $('gchips').onclick = e => {
    const b = e.target.closest('button[data-g]'); if (!b) return;
    const name = b.dataset.g, on = gsel(), cur_ = $('wgen').value.split(',').map(x => x.trim()).filter(Boolean);
    $('wgen').value = (on.has(name.toLowerCase()) ? cur_.filter(x => x.toLowerCase() !== name.toLowerCase()) : cur_.concat([name])).join(', ');
    drawGenres(); drawSum();
  };
  $('gclr').onclick = () => { $('wgen').value = ''; drawGenres(); drawSum(); };
  // Plattenkisten und Wiedergabelisten aus Mixxx (Wunsch 08.11.2026): gewaehlt stehen sie als "K:Name|L:Name" in #wcrate
  // dazu Gruppen aus dem Tag (TIT1) als "G:Name" (Wunsch 11.11.2026)
  const kicon = k => k === 'L' ? '▶ ' : k === 'G' ? '🏷 ' : '';
  function ksel() { return $('wcrate').value.split('|').map(x => x.trim()).filter(x => /^[KLG]:./.test(x)); }
  const klow = x => x.slice(0, 2) + x.slice(2).toLowerCase();
  function drawCrates() {
    const c = (info && info.crates) || [], on = new Set(ksel().map(klow));
    if (!c.length && !on.size) return;
    const extra = ksel().filter(x => !c.some(y => klow(y[0]) === klow(x)));   // gemerkt, aber in Mixxx nicht (mehr) da
    $('kchips').innerHTML = c.map(x => '<button type="button" data-k="' + esc(x[0]) + '"' + (on.has(klow(x[0])) ? ' class="on"' : '') + '>' + kicon(x[2]) + esc(x[1]) + '<small>' + x[3] + '</small></button>').join('') +
      extra.map(x => '<button type="button" data-k="' + esc(x) + '" class="on">' + kicon(x[0]) + esc(x.slice(2)) + '</button>').join('');
  }
  $('kchips').onclick = e => {
    const b = e.target.closest('button[data-k]'); if (!b) return;
    const k = b.dataset.k, cur_ = ksel();
    $('wcrate').value = (cur_.some(x => klow(x) === klow(k)) ? cur_.filter(x => klow(x) !== klow(k)) : cur_.concat([k])).join('|');
    drawCrates(); drawSum();
  };
  $('kclr').onclick = () => { $('wcrate').value = ''; drawCrates(); drawSum(); };

  // ---- 1. Event einrichten: Assistent in Schritten, zugeklappt nur die Zusammenfassung (Wunsch 07.11.2026) -----------
  let step = 0;
  const NSTEP = 5;
  function showStep(k) {
    step = Math.max(0, Math.min(NSTEP - 1, k));
    document.querySelectorAll('.step').forEach(el => el.classList.toggle('on', +el.dataset.s === step));
    document.querySelectorAll('#steps button').forEach(b => { const s = +b.dataset.s; b.classList.toggle('on', s === step); b.classList.toggle('done', s < step); });
    $('wback').disabled = step === 0;
    $('wnext').hidden = step === NSTEP - 1;
  }
  function drawSum() {
    const w = wish(), parts = [];
    if (w.theme) parts.push(w.theme);
    if (w.audience) parts.push(w.audience);
    const kl = ksel().map(x => kicon(x[0]) + x.slice(2));
    parts.push(w.genres || kl.length ? [w.genres].concat(kl).filter(Boolean).join(', ') : 'alle Genres');
    parts.push('ab ' + w.start);
    parts.push(hm(w.minutes * 60).replace(':00 h', ' h'));
    parts.push('Energie ' + w.e_lo + ' → ' + w.e_hi);
    if (w.bpm_lo || w.bpm_hi) parts.push((w.bpm_lo || '…') + '–' + (w.bpm_hi || '…') + ' BPM');
    if (w.y_lo || w.y_hi) parts.push((w.y_lo || '…') + '–' + (w.y_hi || '…'));
    if (+w.fav) parts.push('♥ ' + (+w.fav === 2 ? 'stark' : 'etwas'));
    $('wsum').innerHTML = parts.map(t => '<span>' + esc(t) + '</span>').join('') + (items.length ? '' : '<span class="e">noch keine Playlist</span>');
  }
  $('steps').onclick = e => { const b = e.target.closest('button'); if (b) showStep(+b.dataset.s); };
  $('wnext').onclick = () => showStep(step + 1);
  $('wback').onclick = () => showStep(step - 1);
  $('wtog').onclick = e => { e.preventDefault(); $('wiz').open = !$('wiz').open; };
  $('wiz').addEventListener('toggle', () => { $('wtog').textContent = $('wiz').open ? 'Zuklappen ▴' : 'Ändern ▾'; drawSum(); });
  document.querySelectorAll('.chips').forEach(c => c.onclick = e => {      // Vorlagen: ein Tipp fuellt das Feld
    const b = e.target.closest('button'); if (!b) return;
    $(c.dataset.for).value = b.textContent; drawSum();
  });
  ['wtheme', 'waud', 'wnotes', 'wmin', 'welo', 'wehi', 'wblo', 'wbhi', 'wylo', 'wyhi', 'wfav', 'wstart'].forEach(id => $(id).addEventListener('input', () => { drawSum(); if (id === 'wstart') draw(); }));
  showStep(0);

  // ---- Playlist ----------------------------------------------------------------------------------------------------
  async function loadInfo() {
    try {
      info = await cmd('autodj_info');
      music = info.music || music;
      $('genlist').innerHTML = (info.genres || []).slice().sort((a, b) => String(a[0]).localeCompare(String(b[0]), 'de', { sensitivity: 'base' })).map(g => '<option value="' + esc(g[0]) + '">' + esc(g[0]) + ' (' + g[1] + ')</option>').join('');
      drawGenres(); drawCrates();
      $('cinfo').textContent = (info.has_key ? 'Claude bisher ca. ' + (info.spent.usd || 0).toFixed(2) + ' $' : 'Kein Claude-Schlüssel: im Show-Assistenten eintragen') + ' · ' + info.n + ' Lieder';
      drawSaved(info.saved);
      if (!music) $('pstat').textContent = 'Der Light-Butler erreicht den Musik-Rechner gerade nicht (Mixxx-App oder Light-Butler Helfer starten): ohne Musik-Rechner lässt sich nichts abspielen.';
    } catch (e) { $('err').textContent = e.message; }
  }
  function drawSaved(list) {
    const v = $('ssel').value;
    $('ssel').innerHTML = '<option value="">Gemerkte Playlists …</option>' + (list || []).map(x => '<option value="' + esc(x.name) + '">' + esc(x.name) + ' (' + x.n + ')</option>').join('');
    $('ssel').value = v;
  }
  async function makePlan(claude) {
    if (busy) return;
    busy = true;
    const w = wish();
    try { localStorage.setItem('autodj_wish', JSON.stringify(w)); } catch (e) { /* privates Fenster */ }
    $('err').textContent = '';
    $('note').textContent = claude ? 'Claude stellt die Playlist zusammen … (bis zu einer Minute)' : 'Rechne …';
    ['brules', 'bclaude', 'breroll'].forEach(id => { $(id).disabled = true; });
    try {
      const locked = mix && mix.started ? mix.idx : cur;
      const keep = playing && locked >= 0 ? items.slice(0, locked + 1) : [];        // was schon lief und gerade laeuft, bleibt
      w.exclude = keep.map(x => x.path);
      const d = await cmd('autodj_plan', { wish: w, seed, claude: !!claude });
      items = keep.concat(d.items || []); resume = null;
      note = d.note || (d.claude ? '' : 'Nach Regeln: Energie steigend, Tempo in kleinen Schritten, Tonarten nach Camelot.');
      if (d.claude && d.cost_usd) note += ' (ca. ' + d.cost_usd.toFixed(2) + ' $)';
      if (d.bpm && !w.bpm_lo) note += ' Tempo ' + d.bpm[0] + ' bis ' + d.bpm[1] + ' BPM.';
      if (d.music) music = d.music;
      sel = -1;
      $('wiz').open = false;                                 // fertig eingerichtet: zuklappen, das Mischpult rueckt nach oben
      draw();
    } catch (e) { $('err').textContent = e.message; $('note').textContent = ''; }
    ['brules', 'bclaude', 'breroll'].forEach(id => { $(id).disabled = false; });
    busy = false;
  }
  $('brules').onclick = () => makePlan(false);
  $('bclaude').onclick = () => makePlan(true);
  $('breroll').onclick = () => { seed++; makePlan($('bclaude').dataset.last === '1'); };
  $('bclaude').addEventListener('click', () => { $('bclaude').dataset.last = '1'; });
  $('brules').addEventListener('click', () => { $('bclaude').dataset.last = '0'; });

  const keyDist = (a, b) => {
    const c = k => (k >= 1 && k <= 12) ? [[8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1][k - 1], 'B'] : (k >= 13 && k <= 24) ? [[5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10][k - 13], 'A'] : null;
    const x = c(a), y = c(b);
    if (!x || !y) return 1.5;
    const d = Math.min((x[0] - y[0] + 12) % 12, (y[0] - x[0] + 12) % 12);
    return x[1] === y[1] ? (d === 0 ? 0 : d === 1 ? 1 : d === 2 ? 2 : 3) : (d === 0 ? 1 : d === 1 ? 2 : 3);
  };
  function transText(a, b) {
    const r = ADJ.rateFor(a.bpm, b.bpm, +$('orate').value);
    const k = keyDist(a.kid, b.kid);
    const kt = k <= 1 ? '<span class="ok">Tonart passt</span>' : k === 1.5 ? 'Tonart unbekannt' : k === 2 ? '<span class="meh">Tonart geht</span>' : '<span class="meh">Tonart passt nicht</span>';
    const rt = !(a.bpm > 0 && b.bpm > 0) ? 'BPM fehlt: nur überblenden' : r.sync ? '<span class="ok">taktgenau</span>' + (Math.abs(r.rate - 1) > 0.001 ? ', Tempo ' + (r.rate > 1 ? '+' : '') + ((r.rate - 1) * 100).toFixed(1) + ' %' : '') : '<span class="meh">Tempo zu weit weg: nur überblenden</span>';
    return '↓ ' + kt + ' · ' + rt;
  }
  // Wann laeuft welches Lied? Fest ab dem Beginn des Events (Ueberblendung ~30 s): die Skala bleibt stehen, auch wenn ein
  // spaeteres Lied gespielt wird (Wunsch 08.11.2026); wie weit man vor oder hinter dem Plan ist, zeigt der Strich "jetzt".
  const hhmm = s => { s = ((Math.round(s / 60) % 1440) + 1440) % 1440; return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); };
  function startTimes() {
    const m = /^(\d{1,2}):(\d{2})/.exec(($('wstart') && $('wstart').value) || '20:00');
    let t = m ? (+m[1]) * 3600 + (+m[2]) * 60 : 20 * 3600;
    return items.map(x => { const s = t; t += Math.max(1, (x.dur || 0) - 30); return s; });
  }
  function draw() {
    const total = items.reduce((s, x) => s + (x.dur || 0), 0) - 30 * Math.max(0, items.length - 1);
    $('lhead').textContent = 'Playlist' + (items.length ? ' · ' + items.length + ' Lieder, ' + hm(Math.max(0, total)) : '');
    $('note').textContent = note;
    drawSum(); drawPos();
    if (!items.length) { $('items').innerHTML = '<div class="dim" style="padding:12px 0">Noch keine Playlist. Links „Event einrichten“ ausfüllen und im letzten Schritt „Mit Claude vorschlagen“ oder „Nach Regeln“ drücken.</div>'; $('curve').innerHTML = ''; $('axis').innerHTML = ''; return; }
    const nx = mix ? mix.idx : (cur >= 0 ? cur + 1 : -1);
    const st = startTimes();
    $('items').innerHTML = items.map((x, i) => {
      const cls = i === cur ? ' cur' : i === nx ? ' nx' : i < cur ? ' done' : '';
      // Cover kommen vom Pi (Ablage), nicht vom Musik-Rechner: gleich laden, auch bevor dessen Adresse bekannt ist (Fehlerbericht
      // 14.11.2026: beim Oeffnen schwarze Kaestchen, erst mit Play kamen die Bilder)
      const cv = x.path ? '<img loading="lazy" src="/api/sm/cover?p=' + encodeURIComponent(x.path) + '" onerror="this.style.visibility=\'hidden\'" alt="">' : '<div class="nocv"></div>';
      return (i > 0 ? '<div class="tr">' + transText(items[i - 1], x) + '</div>' : '') +
        '<div class="it' + cls + '" data-i="' + i + '"><span class="dim">' + (i === cur ? '▶' : i + 1) + '</span>' + cv +
        '<div class="t"><div>' + esc((x.artist ? x.artist + ' – ' : '') + (x.name || x.title)) + (i === nx ? '<span class="nxl">als Nächstes</span>' : '') + '</div>' +
        '<div class="why">' + esc([(x.bpm ? Math.round(x.bpm) + ' BPM' : '– BPM'), x.cam || '–', mmss(x.dur), x.genre, x.why].filter(Boolean).join(' · ')) + '</div></div>' +
        '<span><span class="chip e' + (x.e || 0) + '">' + (x.e ? 'E' + x.e + (x.est ? '~' : '') : '?') + '</span></span><span class="clk" title="Beginn dieses Liedes">' + hhmm(st[i]) + '</span>' +
        '<span class="bt"><button data-a="play" title="Ab hier abspielen (sofort)">▶</button><button data-a="next" title="Als Nächstes spielen">⤴</button><button data-a="up" title="Nach oben">↑</button><button data-a="down" title="Nach unten">↓</button><button data-a="del" class="danger" title="Aus der Playlist nehmen">✕</button></span></div>';
    }).join('');
    drawCurve();
  }
  function drawCurve() {
    let t = 0;
    const pts = items.map(x => { const p = [t, x.e || 5, x.bpm || 0]; t += Math.max(1, (x.dur || 0) - 30); return p; });
    const T = Math.max(1, t), bs = pts.map(p => p[2]).filter(b => b > 0);
    const bl = Math.min.apply(null, bs.length ? bs : [100]), bh = Math.max.apply(null, bs.length ? bs : [140]);
    const X = v => (v / T * 1000).toFixed(1), YE = e => (86 - (e - 1) / 8 * 78).toFixed(1), YB = b => (86 - (b - bl) / Math.max(1, bh - bl) * 78).toFixed(1);
    const pe = pts.map(p => X(p[0]) + ',' + YE(p[1])).join(' '), pb = pts.filter(p => p[2] > 0).map(p => X(p[0]) + ',' + YB(p[2])).join(' ');
    $('curve').innerHTML = '<polyline fill="none" stroke="#e8710a" stroke-width="2.5" vector-effect="non-scaling-stroke" points="' + pe + '"/>' +
      '<polyline fill="none" stroke="#4aa8ff" stroke-width="1.5" stroke-dasharray="4 3" vector-effect="non-scaling-stroke" points="' + pb + '"/>' +
      '<text x="4" y="12" fill="#e8710a" font-size="11">Energie</text><text x="60" y="12" fill="#4aa8ff" font-size="11">BPM ' + Math.round(bl) + '–' + Math.round(bh) + '</text>' +
      '' + (cur >= 0 && pts[cur] ? '<line x1="' + X(pts[cur][0]) + '" x2="' + X(pts[cur][0]) + '" y1="0" y2="90" stroke="#9fd0ff" stroke-width="2" vector-effect="non-scaling-stroke"/>' : '');   // wo das Event gerade steht
    drawAxis(T);                                             // danach: setzt auch den Strich "jetzt" in die Kurve
  }
  function drawAxis(T) {                                   // Zeitachse unter der Energiekurve: Uhrzeit ab dem Beginn
    const st = startTimes(), t0 = st.length ? st[0] : 0, step = T > 3 * 3600 ? 3600 : T > 3600 ? 1800 : 900, lab = [];
    const first = Math.ceil(t0 / step) * step;
    lab.push('<span style="left:0">' + hhmm(t0) + '</span>');
    for (let t = first; t < t0 + T - step * 0.4; t += step) if (t - t0 > step * 0.4) lab.push('<span style="left:' + ((t - t0) / T * 100).toFixed(2) + '%">' + hhmm(t) + '</span>');
    lab.push('<span style="left:100%;transform:translateX(-100%)">' + hhmm(t0 + T) + '</span>');
    $('axis').innerHTML = lab.join('');
    const now = new Date();                                  // echte Uhrzeit auf der Skala (auch nach Mitternacht)
    let nowS = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    if (nowS < t0 - 6 * 3600) nowS += 86400;
    const nl = $('curve').querySelector('#nowl');
    if (nl) nl.remove();
    if (nowS >= t0 && nowS <= t0 + T) {
      const x = ((nowS - t0) / T * 1000).toFixed(1);
      $('curve').insertAdjacentHTML('beforeend', '<line id="nowl" x1="' + x + '" x2="' + x + '" y1="0" y2="90" stroke="#8fe0a5" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"><title>jetzt</title></line>');
    }
  }
  function drawPos() {                                      // "Lied 7 von 32 · noch 1:24 h"
    if (!items.length) { $('pos').textContent = ''; return; }
    if (cur < 0) { $('pos').textContent = items.length + ' Lieder bereit'; return; }
    const a = decks[live] && decks[live].a, left = items.slice(cur + 1).reduce((s, x) => s + Math.max(0, (x.dur || 0) - 30), 0) +
      Math.max(0, ((decks[live].info && decks[live].info.du) || items[cur].dur || 0) - (a ? a.currentTime : 0));
    $('pos').textContent = 'Lied ' + (cur + 1) + ' von ' + items.length + ' · noch ' + hm(left);
  }
  $('items').onclick = e => {
    const row = e.target.closest('.it');
    if (!row) return;
    const i = +row.dataset.i, b = e.target.closest('button');
    if (!b) { sel = i; [...document.querySelectorAll('.it')].forEach(r => r.style.outline = +r.dataset.i === i ? '1px solid #e8710a' : ''); return; }
    const a = b.dataset.a;
    if (a === 'play') { playFrom(i); return; }
    const locked = mix ? Math.max(cur, mix.idx) : cur;    // laufendes Lied und das, in das gerade geblendet wird, bleiben
    if (i <= locked && a !== 'next') return toast('Dieses Lied läuft schon.');
    if (a === 'del') items.splice(i, 1);
    else if (a === 'up' && i > locked + 1) [items[i - 1], items[i]] = [items[i], items[i - 1]];
    else if (a === 'down' && i < items.length - 1) [items[i + 1], items[i]] = [items[i], items[i + 1]];
    else if (a === 'next' && i > locked + 1) items.splice(locked + 1, 0, items.splice(i, 1)[0]);
    draw();
  };

  // Lied hinzufuegen: Suche in der ganzen Liedliste (einmal geholt)
  $('addq').oninput = async () => {
    const q = $('addq').value.normalize('NFC').toLowerCase().trim();
    if (q.length < 2) { $('addres').hidden = true; return; }
    if (!lib) {
      try { lib = ((await fetch('/api/musik').then(r => r.json())).tracks || []).filter(t => t.path); } catch (e) { lib = []; }
    }
    const hit = lib.filter(t => ((t.artist || '') + ' ' + (t.name || t.title)).normalize('NFC').toLowerCase().includes(q)).slice(0, 12);
    $('addres').innerHTML = hit.map((t, k) => '<div><span>' + esc((t.artist ? t.artist + ' – ' : '') + (t.name || t.title)) + ' <span class="dim">' + (t.bpm ? Math.round(t.bpm) + ' BPM' : '') + '</span></span><button data-k="' + k + '" data-w="next">als Nächstes</button><button data-k="' + k + '" data-w="end">ans Ende</button></div>').join('') || '<div class="dim">nichts gefunden</div>';
    $('addres').hidden = false;
    $('addres').onclick = e => {
      const b = e.target.closest('button'); if (!b) return;
      const t = hit[+b.dataset.k];
      const it = trackItem(t);
      const at = b.dataset.w === 'next' ? nextPos() : items.length;
      items.splice(at, 0, it);
      $('addres').hidden = true; $('addq').value = '';
      draw();
    };
  };
  document.addEventListener('click', e => { if (!e.target.closest('#add')) $('addres').hidden = true; });

  function trackItem(t, why) {                              // Lied der Bibliothek -> Eintrag der Playlist
    const cams = { maj: [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1], min: [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10] };
    const cam = t.kid >= 1 && t.kid <= 12 ? cams.maj[t.kid - 1] + 'B' : t.kid >= 13 && t.kid <= 24 ? cams.min[t.kid - 13] + 'A' : '';
    return { path: t.path, title: t.title, artist: t.artist, name: t.name, dur: t.dur, bpm: t.bpm, kid: t.kid, cam, e: t.lvl || t.elv || 0, est: t.lvl && !t.est ? 0 : 1, genre: t.genre, why: why || 'von Hand' };
  }
  function nextPos() { return Math.max(cur, mix ? mix.idx : -1, resume && cur < 0 ? resume.i : -1) + 1; }

  $('bsave').onclick = async () => {
    const name = $('sname').value.trim() || $('wtheme').value.trim();
    if (!name) return toast('Erst einen Namen eintragen.');
    if (!items.length) return toast('Die Playlist ist leer.');
    try { drawSaved((await cmd('autodj_save', { name, items, wish: wish(), note })).saved); $('ssel').value = name; toast('Gemerkt: ' + name); } catch (e) { toast(e.message); }
  };
  $('bload').onclick = async () => {
    const name = $('ssel').value; if (!name) return;
    try { const d = await cmd('autodj_load', { name }); stopAll(); items = d.items || []; resume = null; note = d.note || ''; setWish(d.wish); $('sname').value = name; draw(); } catch (e) { toast(e.message); }
  };
  $('bmixxx').onclick = async () => {                      // Auto-DJ -> Mixxx als M3U8 am Mac (Wunsch 08.11.2026)
    if (!items.length) return toast('Die Playlist ist leer.');
    if (!music) return toast('Der Light-Butler erreicht den Musik-Rechner gerade nicht.');
    const name = ($('sname').value.trim() || $('ssel').value || 'Auto-DJ ' + new Date().toLocaleDateString('de-AT'));
    try {
      const r = await fetch(music + '/m3u', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, items: items.map(x => ({ p: x.path, t: (x.artist ? x.artist + ' - ' : '') + (x.name || x.title || ''), d: x.dur })) }) });
      let d = null;
      try { d = JSON.parse(await r.text()); } catch (e) { d = null; }   // alte Bruecke antwortet mit Text "nicht gefunden"
      if (r.status === 404 || !d) throw new Error('Am Musik-Rechner läuft noch die alte Fassung. Nach dem nächsten Start der Mixxx-App am Musik-Rechner geht es.');
      if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
      await SM.ask('Playlist für Mixxx abgelegt (' + d.n + ' Lieder' + (d.missing ? ', ' + d.missing + ' nicht gefunden' : '') + '):\n\n' + d.file +
        '\n\nIn Mixxx: in der linken Leiste Rechtsklick auf „Wiedergabelisten“ → „Wiedergabeliste importieren“ und diese Datei wählen.', undefined, 'OK');
    } catch (e) { toast('→ Mixxx: ' + e.message); }
  };
  $('bren').onclick = async () => {                         // umbenennen: unter neuem Namen merken, alten loeschen (Wunsch 08.11.2026)
    const old = $('ssel').value;
    if (!old) return toast('Erst eine gemerkte Playlist wählen.');
    const neu = ((await SM.ask('Neuer Name für „' + old + '“:', old, 'Umbenennen')) || '').trim();
    if (!neu || neu === old) return;
    const list = [...$('ssel').options].map(o => o.value);
    if (list.includes(neu) && !(await SM.ask('Es gibt schon eine Playlist „' + neu + '“. Überschreiben?', undefined, 'Überschreiben'))) return;
    try {
      const d = await cmd('autodj_load', { name: old });     // nur lesen: die laufende Playlist bleibt, wie sie ist
      await cmd('autodj_save', { name: neu, items: d.items || [], wish: d.wish || {}, note: d.note || '' });
      drawSaved((await cmd('autodj_delete', { name: old })).saved);
      $('ssel').value = neu;
      if ($('sname').value.trim() === old) $('sname').value = neu;
      toast('Umbenannt: ' + neu);
    } catch (e) { toast(e.message); }
  };
  $('bdel').onclick = async () => {
    const name = $('ssel').value; if (!name) return toast('Erst eine gemerkte Playlist wählen.');
    if (!(await SM.ask('Playlist „' + name + '“ löschen?', undefined, 'Löschen'))) return;   // eigene Rueckfrage: Safari blockiert Browser-Dialoge manchmal
    try { drawSaved((await cmd('autodj_delete', { name })).saved); toast('Gelöscht: ' + name); } catch (e) { toast(e.message); }
  };

  // ---- Abspielen ---------------------------------------------------------------------------------------------------
  function ensureCtx() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return; }
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = (+$('ovol').value) / 100;
    master.connect(ctx.destination);
    musicBus = ctx.createGain(); musicBus.connect(master);   // Musik (Decks, Echo) getrennt von den Samples: beim Sample leiser
    makeEcho();
    decks.forEach(d => {
      d.a = new Audio();
      d.a.crossOrigin = 'anonymous';                         // der Vorhoer-Server erlaubt das (CORS): sonst bliebe WebAudio stumm
      d.a.preload = 'auto';
      d.a.preservesPitch = true; d.a.webkitPreservesPitch = true;   // Tempo aendern ohne Mickey-Maus
      d.node = ctx.createMediaElementSource(d.a);
      d.low = ctx.createBiquadFilter(); d.low.type = 'lowshelf'; d.low.frequency.value = 180; d.low.gain.value = 0;
      d.hp = ctx.createBiquadFilter(); d.hp.type = 'highpass'; d.hp.frequency.value = 20;   // Filter-Uebergang
      d.gain = ctx.createGain(); d.gain.gain.value = 0;
      d.norm = ctx.createGain(); d.norm.gain.value = 1;     // gleich laut (11.11.2026): je Lied auf -14 LUFS, vor der Ueberblendung
      d.send = ctx.createGain(); d.send.gain.value = 0;      // Anteil ins Echo (Echo-Uebergang)
      d.node.connect(d.low); d.low.connect(d.hp); d.hp.connect(d.norm); d.norm.connect(d.gain); d.gain.connect(musicBus);
      d.hp.connect(d.send); d.send.connect(echo.inp);
      d.a.onended = () => onEnded(d);
    });
  }
  let musicBus = null;
  const echo = {};                                           // Echo im Takt: Verzoegerung mit Rueckkopplung, klingt aus
  function makeEcho() {
    echo.inp = ctx.createGain();
    echo.dl = ctx.createDelay(2.0); echo.dl.delayTime.value = 0.5;
    echo.fb = ctx.createGain(); echo.fb.gain.value = 0.55;
    echo.lp = ctx.createBiquadFilter(); echo.lp.type = 'lowpass'; echo.lp.frequency.value = 3500;   // jedes Echo etwas dumpfer
    echo.out = ctx.createGain(); echo.out.gain.value = 0.8;
    echo.inp.connect(echo.dl); echo.dl.connect(echo.lp); echo.lp.connect(echo.fb); echo.fb.connect(echo.dl); echo.lp.connect(echo.out); echo.out.connect(musicBus);
  }
  $('ovol').oninput = () => { if (master) master.gain.value = (+$('ovol').value) / 100; };
  const setGain = (d, v) => d.gain.gain.setTargetAtTime(v, ctx.currentTime, 0.03);

  async function fetchMarks(it) {
    try {
      const r = await fetch(music + '/marks?p=' + encodeURIComponent(it.path));
      if (r.ok) return await r.json();
    } catch (e) { /* ohne Analyse */ }
    return null;
  }
  // Erster Beat ohne Analyse: die ersten ~50 s holen und dekodieren, Bass-Einsaetze gegen das bekannte Tempo legen
  async function estimateFb(it, bpm) {
    try {
      const r = await fetch(music + '/audio?p=' + encodeURIComponent(it.path), { headers: { Range: 'bytes=0-1999999' } });
      const buf = await ctx.decodeAudioData(await r.arrayBuffer());
      const x = buf.getChannelData(0), sr = buf.sampleRate, hop = Math.round(sr / 100), a = 1 - Math.exp(-2 * Math.PI * 150 / sr);
      const env = new Float32Array(Math.floor(x.length / hop));
      let y = 0;
      for (let k = 0; k < env.length; k++) { let s = 0; for (let j = k * hop; j < (k + 1) * hop; j++) { y += a * (x[j] - y); s += y * y; } env[k] = Math.sqrt(s / hop); }
      const flux = new Float32Array(env.length);
      for (let k = 1; k < env.length; k++) flux[k] = Math.max(0, env[k] - env[k - 1]);
      return ADJ.phaseFromFlux(flux, 100, bpm);
    } catch (e) { return null; }
  }
  async function prepare(deck, idx) {
    const it = items[idx];
    deck.item = it; deck.ready = false; deck.info = null; deck.base = 1; deck.marks = null;
    deck.a.src = music + '/audio?p=' + encodeURIComponent(it.path);
    deck.a.playbackRate = 1;
    if (deck.norm) deck.norm.gain.value = $('onorm').checked ? SM.dbFactor(SM.loudDb(it.lufs, it.tp, true)) : 1;
    const m = await fetchMarks(it);
    if (deck.item !== it) return;
    deck.marks = m;                                          // fuer den Pi: derselbe Plan wie bei Mixxx
    const du = (m && m.du) || it.dur, bpm = (m && m.bpm) || it.bpm || 0;
    const nf = { bpm, fb: m && m.fb != null ? m.fb : null, du, end: ADJ.musicEnd(m && m.en, du), start: ADJ.musicStart(m && m.en, du), grid: m && m.fb != null ? 'Analyse' : '' };
    if (nf.fb == null && bpm > 0) { nf.fb = await estimateFb(it, bpm); nf.grid = nf.fb != null ? 'geschätzt' : ''; }
    if (deck.item !== it) return;
    deck.info = nf;
    deck.startPos = nf.fb != null && bpm > 0 ? nf.fb + Math.max(0, Math.floor((nf.start - nf.fb) / (240 / bpm))) * (240 / bpm) : nf.start;   // auf einem Takt, ab Musik
    deck.ready = true;
  }

  async function playFrom(i, pos) {
    if (!music) return toast('Der Musik-Rechner ist nicht verbunden.');
    if (i < 0 || i >= items.length) return;
    ensureCtx();
    const old = playing ? decks[live] : null;
    mix = null; glide = null;
    const d = decks[old ? 1 - live : live];
    d.a.pause();
    $('pstat').textContent = 'Lade ' + (items[i].name || items[i].title) + ' …';
    await prepare(d, i);
    if (old) { setGain(old, 0); setTimeout(() => old.a.pause(), 400); }  // von Hand gewechselt: kurz ausblenden
    resume = null;
    d.a.currentTime = pos > 0 ? pos : (d.startPos || 0);    // pos: weiter an der Stelle von vorhin (nach einem Seitenwechsel)
    d.gain.gain.value = 0;
    d.low.gain.value = 0;
    try { await d.a.play(); } catch (e) { toast('Abspielen ging nicht: ' + e.message); return; }
    setGain(d, 1);
    live = decks.indexOf(d); cur = i; playing = true; sel = -1;
    $('bplay').textContent = '❚❚';
    draw();
    prepNext();
  }
  function prepNext() {
    const nd = decks[1 - live];
    const idx = cur + 1;
    if (idx >= items.length) { nd.item = null; return; }
    if (nd.item === items[idx] && (nd.ready || nd.loading)) return;
    nd.loading = true;
    prepare(nd, idx).finally(() => { nd.loading = false; });
  }
  function stopAll() {
    decks.forEach(d => { if (d.a) { d.a.pause(); if (d.gain) d.gain.gain.value = 0; } d.item = null; d.ready = false; });
    playing = false; mix = null; glide = null; cur = -1;
    $('bplay').textContent = '▶';
    draw();
  }
  $('bstop').onclick = stopAll;
  // Warteschlange leeren (Wunsch 12.11.2026): das laufende Lied spielt zu Ende, danach nichts mehr; sonst ganz leer
  $('bclear').onclick = async () => {
    if (!items.length) return;
    const keepNow = playing && cur >= 0 && cur < items.length;
    const n = keepNow ? items.length - 1 : items.length;
    if (!n) { toast('Nach dem laufenden Lied ist die Playlist schon leer.'); return; }
    if (!(await SM.ask(keepNow ? n + ' Lied' + (n === 1 ? '' : 'er') + ' nach dem laufenden aus der Playlist nehmen? Das laufende spielt zu Ende.'
      : 'Die Playlist leeren (' + n + ' Lied' + (n === 1 ? '' : 'er') + ')? Gemerkte Playlists bleiben.', undefined, 'Leeren'))) return;
    if (keepNow) {
      const now = items[cur];
      decks.forEach((d, k) => { if (k !== live && d.a) { d.a.pause(); if (d.gain) d.gain.gain.value = 0; d.item = null; d.ready = false; } });   // vorbereitetes naechstes Lied weg
      mix = null; items = [now]; cur = 0; sel = -1;
    } else {
      stopAll(); items = []; note = ''; sel = -1;
    }
    resume = null; saveRun(); draw();
    toast(keepNow ? 'Playlist geleert, das laufende Lied spielt zu Ende.' : 'Playlist geleert.');
  };
  $('bplay').onclick = () => {
    ensureCtx();
    if (!playing) {
      const a = decks[live];
      if (cur >= 0 && a.item === items[cur] && a.a.paused && a.a.currentTime > 0 && sel < 0) {   // Pause: weiter
        a.a.play(); if (mix && mix.started) decks[1 - live].a.play();
        playing = true; $('bplay').textContent = '❚❚'; return;
      }
      if (resume && sel < 0 && cur < 0) { const r = resume; playFrom(r.i, r.pos); return; }   // nach einem Seitenwechsel: dort weiter
      playFrom(sel >= 0 ? sel : Math.max(0, cur));
      return;
    }
    decks.forEach(d => d.a && d.a.pause());
    playing = false; $('bplay').textContent = '▶';
  };
  $('bmix').onclick = () => {
    if (!playing || mix && mix.started) return;
    const nd = decks[1 - live];
    if (!nd.ready || nd.item !== items[cur + 1]) return toast('Das nächste Lied lädt noch.');
    planMix(true);
  };

  // Ueberblendung planen: wann im laufenden Lied, wie lang, mit welcher Rate
  function planMix(now) {
    const A = decks[live], B = decks[1 - live];
    if (!A.info || !B.ready || B.item !== items[cur + 1]) { mix = null; return; }
    const r = ADJ.rateFor(A.info.bpm * A.base, B.info.bpm, +$('orate').value);
    const sync = r.sync && A.info.fb != null && B.info.fb != null;
    const bars = now ? Math.min(8, +$('obars').value) : +$('obars').value;
    const a = { bpm: A.info.bpm, fb: A.info.fb, end: now ? A.a.currentTime + bars * 240 / (A.info.bpm || 120) + 4 : A.info.end };
    const kind = ADJ.pickTrans($('otrans').value, A.item, B.item, sync);
    const p = ADJ.mixPoint(a, kind === 'brake' ? 2 : kind === 'echo' ? Math.min(bars, 4) : bars, A.a.currentTime, sync);
    mix = { idx: cur + 1, t: p.t, len: p.len, bars: p.bars, rate: sync ? r.rate : (r.sync ? r.rate : 1), sync, started: false, forced: !!now, kind };
    if (kind === 'brake') { mix.t = p.t + p.len - 0.2; mix.len = 0.2; }   // Bremse kurz vor dem Ende der Musik, nicht lange davor
  }
  function startMix() {
    const A = decks[live], B = decks[1 - live];
    glide = null;
    B.base = mix.rate;
    B.a.playbackRate = mix.rate;
    if (Math.abs(B.a.currentTime - (B.startPos || 0)) > 0.05) B.a.currentTime = B.startPos || 0;
    B.gain.gain.value = 0;
    B.low.gain.value = $('obass').checked && mix.kind !== 'brake' ? -24 : 0;
    if (mix.kind === 'echo') echo.dl.delayTime.value = Math.min(1.5, (60 / (A.info.bpm || 120)) * 0.75);   // punktierte Achtel
    if (mix.kind === 'brake') {                              // Plattenspieler: Tonhoehe faellt mit, das neue Lied startet erst am Ende
      A.a.preservesPitch = false; A.a.webkitPreservesPitch = false;
      mix.t0 = performance.now();
    } else B.a.play().catch(e => toast('Abspielen ging nicht: ' + e.message));
    mix.started = true; lastErr = null;
    draw();
  }
  function endMix() {
    const A = decks[live], B = decks[1 - live];
    A.a.pause(); A.gain.gain.value = 0; A.low.gain.value = 0;
    A.hp.frequency.value = 20; A.send.gain.value = 0; A.a.preservesPitch = true; A.a.webkitPreservesPitch = true;   // fuer das naechste Mal
    if (B.a.paused && playing) { B.a.currentTime = B.startPos || 0; B.a.play().catch(() => {}); }
    B.gain.gain.value = 1; B.low.gain.value = 0;
    live = 1 - live; cur = mix.idx; mix = null;
    if (Math.abs(B.base - 1) > 0.001) glide = { from: B.base, t0: performance.now(), ms: 30000 };   // in 30 s wieder Originaltempo
    draw();
    prepNext();
  }
  function onEnded(d) {
    if (d !== decks[live]) return;
    if (mix && mix.started) { endMix(); return; }
    if (cur + 1 < items.length) playFrom(cur + 1);           // keine Ueberblendung zustande gekommen: einfach weiter
    else { playing = false; $('bplay').textContent = '▶'; $('pstat').textContent = 'Playlist zu Ende.'; draw(); }
  }

  function tick() {
    if (!playing || !ctx) return;
    const A = decks[live], B = decks[1 - live];
    if (!A.info) return;
    if (B.item !== items[cur + 1] && !(mix && mix.started)) { mix = null; prepNext(); }
    if (glide) {
      const u = Math.min(1, (performance.now() - glide.t0) / glide.ms);
      A.base = glide.from + (1 - glide.from) * u;
      A.a.playbackRate = A.base;
      if (u >= 1) glide = null;
    }
    if (!mix || !mix.started) {
      if (!mix || (!mix.forced && mix.t - A.a.currentTime > 5)) planMix(false);   // kurz davor nicht mehr verschieben
      if (!mix) return;
      if (B.a.paused && Math.abs(B.a.currentTime - (B.startPos || 0)) > 0.05 && mix.t - A.a.currentTime < 20) B.a.currentTime = B.startPos || 0;   // vorspulen
      const left = (mix.t - A.a.currentTime) / A.a.playbackRate;
      if (left <= 0.01) startMix();
      else if (left < 0.12 && !mix.sched) { mix.sched = true; const m = mix; setTimeout(() => { if (mix === m && !m.started && playing) startMix(); }, left * 1000); }
      return;
    }
    if (mix.kind === 'brake') {                              // nach der Uhr: das alte Lied wird ja langsamer
      const w = (performance.now() - mix.t0) / ADJ.BRAKE_MS, bk = ADJ.brake(w);
      A.a.playbackRate = Math.max(0.0625, bk.rate);
      setGain(A, bk.a);
      if (bk.b && B.a.paused) { B.a.currentTime = B.startPos || 0; B.gain.gain.value = 1; B.a.play().catch(() => {}); }
      if (w >= 1) endMix();
      return;
    }
    const p = (A.a.currentTime - mix.t) / mix.len;
    const tg = ADJ.transGains(mix.kind, p);
    setGain(A, tg.a); setGain(B, tg.b);
    A.send.gain.setTargetAtTime(tg.send, ctx.currentTime, 0.02);
    A.hp.frequency.setTargetAtTime(tg.hp, ctx.currentTime, 0.05);
    if ($('obass').checked && mix.kind !== 'echo') {                               // Baesse in der Mitte tauschen: nie zwei Bassdrums zugleich voll
      const sw = Math.max(0, Math.min(1, (p - 0.45) / 0.1));
      A.low.gain.setTargetAtTime(-24 * sw, ctx.currentTime, 0.05); B.low.gain.setTargetAtTime(-24 * (1 - sw), ctx.currentTime, 0.05);
    }
    if (mix.sync && performance.now() - lastNudge > 200) {
      lastNudge = performance.now();
      const bb = B.info.bpm * ADJ.beatMult(A.info.bpm * A.base, B.info.bpm * mix.rate);   // halbes/doppeltes Tempo: in Beats von A zaehlen
      const e = ADJ.phaseErr(A.a.currentTime, A.info.fb, A.info.bpm, B.a.currentTime, B.info.fb, bb);
      lastErr = e;
      const nr = ADJ.nudge(B.base, e, bb);
      if (Math.abs(nr - B.a.playbackRate) > 0.0005) B.a.playbackRate = nr;
    }
    if (p >= 1) endMix();
  }
  setInterval(tick, 50);                                     // ein Tab, der Ton spielt, wird vom Browser nicht gebremst

  // ---- Licht folgt dem Auto-DJ (Wunsch 08.11.2026) ------------------------------------------------------------------
  // Wie die Mixxx-Bruecke: je Deck (am Pi 11 = A, 12 = B) Stelle, Laenge, spielt, Lautstaerke, Tempo, Beat; dazu einmal je Lied
  // der Plan aus der Analyse am Mac (/marks). Pause: noch PAUSE_S lang "spielt nicht" (Ruhemodus wie bei Mixxx), dann nichts mehr,
  // der Pi faellt nach ein paar Sekunden auf die eigene Erkennung zurueck. Fenster zu: ebenso.
  const LICHT_MS = 400, PAUSE_S = 30;
  let lichtOn = true, lastPlay = 0;
  const planSent = ['', ''], planT = [0, 0];
  try { lichtOn = localStorage.getItem('autodj_licht') !== '0'; } catch (e) { /* privat */ }
  $('olicht').checked = lichtOn;
  $('olicht').onchange = () => {
    lichtOn = $('olicht').checked;
    try { localStorage.setItem('autodj_licht', lichtOn ? '1' : '0'); } catch (e) { /* privat */ }
    if (!lichtOn) sendLicht(decks.map((d, k) => ({ d: 11 + k, pl: 0, tl: 0, vo: 0 })));   // sofort: kein Deck mehr hoerbar
  };
  function sendLicht(msgs) { cmd('autodj_feed', { msgs }).catch(() => {}); }
  function deckMsg(d, k) {
    const a = d.a, it = d.item, inf = d.info || {};
    const du = inf.du || (a && a.duration) || (it && it.dur) || 0, t = a ? a.currentTime : 0, rate = a ? a.playbackRate : 1;
    const bpm = inf.bpm || 0, fb = inf.fb;
    return { d: 11 + k, tl: it ? 1 : 0, pl: a && it && !a.paused ? 1 : 0, pp: du ? t / du : 0, du, rr: rate,
      vo: d.gain ? d.gain.gain.value : 0, bp: bpm * rate, bd: bpm > 0 && fb != null ? ((((t - fb) * bpm / 60) % 1) + 1) % 1 : 0,
      fb: bpm, fk: (it && it.kid) || 0 };
  }
  function planMsg(d, k) {
    const it = d.item, m = d.marks;
    if (!m || !m.du) return { type: 'plan', d: 11 + k, key: '', info: 'Keine Analyse am Musik-Rechner' };
    return { type: 'plan', d: 11 + k, key: String(it.path).slice(-60), title: m.title || ((it.artist ? it.artist + ' - ' : '') + (it.name || '')),
      du: m.du, ev: m.ev || [], en: m.en || [], cu: m.cu || [], se: m.se || [], genre: m.genre || it.genre || '', fp: m.fp || '',
      lvl: m.lvl || undefined, le: m.le || undefined, ki: it.kid || undefined };
  }
  function lichtTick() {
    if (!lichtOn || !ctx) return;
    const now = performance.now();
    if (decks.some(d => d.a && d.item && !d.a.paused)) lastPlay = now;
    if (!lastPlay || now - lastPlay > PAUSE_S * 1000) return;
    const msgs = [];
    decks.forEach((d, k) => {
      const key = d.item && d.marks !== undefined && (d.ready || d.marks) ? d.item.path : '';
      if (key && (planSent[k] !== key || now - planT[k] > 5000)) { msgs.push(planMsg(d, k)); planSent[k] = key; planT[k] = now; }
      msgs.push(deckMsg(d, k));
    });
    sendLicht(msgs);
  }
  setInterval(lichtTick, LICHT_MS);

  // ---- Seitenwechsel (Wunsch 08.11.2026) ----------------------------------------------------------------------------
  // Der Browser beendet beim Verlassen der Seite den Ton; die Playlist und die Stelle merkt sich die Seite aber (dieser Browser)
  // und bietet beim Zurueckkommen an, dort weiterzuspielen. Solange er spielt, fragt der Browser vor dem Verlassen nach.
  const RUN_KEY = 'autodj_lauf';
  let resume = null;
  function saveRun() {
    try {
      const a = cur >= 0 ? decks[live].a : null;
      localStorage.setItem(RUN_KEY, JSON.stringify({ items, note, cur, pos: a ? a.currentTime : 0, t: Date.now() }));
    } catch (e) { /* privates Fenster oder zu gross */ }
  }
  setInterval(saveRun, 2000);
  window.addEventListener('pagehide', saveRun);
  window.addEventListener('beforeunload', e => {
    saveRun();
    if (playing) { e.preventDefault(); e.returnValue = ''; }   // Browser fragt: Seite verlassen? (der Ton hoert sonst auf)
  });
  try {
    const st = JSON.parse(localStorage.getItem(RUN_KEY) || 'null');
    if (st && Array.isArray(st.items) && st.items.length && !items.length) {
      items = st.items; note = st.note || '';
      if (st.cur >= 0 && st.cur < items.length) {
        resume = { i: st.cur, pos: +st.pos || 0 };
        const it = items[st.cur];
        $('pstat').textContent = 'Weiter mit „' + (it.name || it.title || '') + '“ bei ' + mmss(resume.pos) + ': ▶ drücken.';
      }
      draw();
    }
  } catch (e) { /* nichts gemerkt */ }

  // ---- Als Naechstes aus der Musik-Datenbank (Wunsch 08.11.2026): BroadcastChannel zwischen den Fenstern, sonst Warteliste --
  function takeNext(t) {
    if (!t || !t.path) return '';
    items.splice(nextPos(), 0, trackItem(t, 'aus der Musik-Datenbank'));
    draw();
    if (playing) prepNext();
    return t.name || t.title || '';
  }
  try {
    const q = JSON.parse(localStorage.getItem('autodj_next') || '[]');   // wie beim Klick: das zuletzt gewaehlte spielt zuerst
    localStorage.removeItem('autodj_next');
    if (Array.isArray(q) && q.length) { q.forEach(takeNext); toast('Als Nächstes aus der Musik-Datenbank: ' + q.length + ' Lied' + (q.length > 1 ? 'er' : '')); }
  } catch (e) { /* privat */ }
  // Ganze Liste hinten anhaengen (Wunsch 14.11.2026: "Alle in den Auto-DJ" bei Interpreten, Alben, Favoriten); was schon
  // in der Playlist steht, kommt nicht doppelt
  function takeAdd(list, src) {
    const have = new Set(items.map(x => x.path));
    let n = 0;
    for (const t of Array.isArray(list) ? list : []) {
      if (!t || !t.path || typeof t.path !== 'string' || have.has(t.path)) continue;
      items.push(trackItem(t, src || 'hinzugefügt'));
      have.add(t.path);
      n++;
    }
    if (n) { draw(); if (playing) prepNext(); }
    return n;
  }
  try {
    const q = JSON.parse(localStorage.getItem('autodj_add') || '[]');
    localStorage.removeItem('autodj_add');
    if (Array.isArray(q) && q.length) {
      let n = 0;
      for (const b of q) n += takeAdd(b && b.ts, b && b.src);
      toast(n + ' Lied' + (n === 1 ? '' : 'er') + ' hinten an die Playlist angehängt');
    }
  } catch (e) { /* privat */ }
  const adjBc = 'BroadcastChannel' in window ? new BroadcastChannel('lb_autodj') : null;
  if (adjBc) {
    adjBc.onmessage = e => {
      const d = e.data || {};
      if (d.type === 'next') { const n = takeNext(d.t); if (n) adjBc.postMessage({ type: 'ok', name: n }); }
      if (d.type === 'add') { const n = takeAdd(d.ts, d.src); adjBc.postMessage({ type: 'added', n, skip: (Array.isArray(d.ts) ? d.ts.length : 0) - n }); }
    };
    const alive = () => adjBc.postMessage({ type: 'alive' });
    alive(); setInterval(alive, 2000);
  }

  // Farbe ohne Cover nach der Energie (wie beim erzeugten Cover): ruhig blau bis wild rot
  const deckColor = e => (!e ? '#1c2233' : e <= 3 ? '#0c2f55' : e <= 5 ? '#0b3b32' : e <= 6 ? '#4a2e08' : e <= 8 ? '#4a1b0c' : '#501313');
  function drawDecks() {
    decks.forEach((d, k) => {
      const el = $('deck' + k), it = d.item, a = d.a;
      el.classList.toggle('live', playing && k === live);
      const key = it ? it.path : '';
      if (el.dataset.p !== key) {                            // anderes Lied: Cover als Hintergrund (oder Farbe nach Energie)
        el.dataset.p = key;
        el.style.backgroundColor = deckColor(it && it.e);
        el.style.backgroundImage = ''; el.classList.remove('hascv');
        if (it && music) {
          const img = new Image();
          img.onload = () => { if (el.dataset.p === key) { el.style.backgroundImage = 'url("' + img.src + '")'; el.classList.add('hascv'); } };
          img.src = '/api/sm/cover?p=' + encodeURIComponent(it.path);
        }
      }
      el.querySelector('.lab').textContent = 'Deck ' + 'AB'[k] + (playing && k === live ? ' · spielt' : mix && mix.started && k !== live ? ' · blendet ein' : it ? ' · bereit' : '');
      el.querySelector('.ti').textContent = it ? (it.name || it.title) : '–';
      el.querySelector('.ar').textContent = it ? [it.artist, it.e ? 'E' + it.e + (it.est ? '~' : '') : ''].filter(Boolean).join(' · ') : '';
      const nf = d.info;
      el.querySelector('.bk').textContent = !it ? '–' : (nf && nf.bpm ? (nf.bpm * (a ? a.playbackRate : 1)).toFixed(1) + ' BPM' : 'BPM ?') + ' · ' + (it.cam || '–');
      el.querySelector('.meta').textContent = !it ? '' : !nf ? 'lädt …' :
        (a && Math.abs(a.playbackRate - 1) > 0.001 ? 'Tempo ' + (a.playbackRate > 1 ? '+' : '') + ((a.playbackRate - 1) * 100).toFixed(1) + ' % · ' : '') +
        (nf.grid ? 'Raster ' + nf.grid : nf.bpm ? 'ohne Raster' : 'BPM unbekannt');
      el.querySelector('.t0').textContent = it && a ? mmss(a.currentTime) : '';
      el.querySelector('.t1').textContent = it && nf && a ? '-' + mmss(Math.max(0, nf.du - a.currentTime)) : '';
      const du = nf ? nf.du : 1;
      el.querySelector('.f').style.width = (a && du ? Math.min(100, a.currentTime / du * 100) : 0) + '%';
      const mm = el.querySelector('.m');
      if (mix && k === live && du) { mm.style.left = (mix.t / du * 100) + '%'; mm.style.width = (mix.len / du * 100) + '%'; } else mm.style.width = '0';
    });
    let xp = live;                                           // Ueberblend-Anzeige: 0 = ganz A, 1 = ganz B
    if (mix && mix.started && decks[live].a) xp = live === 0 ? Math.max(0, Math.min(1, (decks[live].a.currentTime - mix.t) / mix.len)) : 1 - Math.max(0, Math.min(1, (decks[live].a.currentTime - mix.t) / mix.len));
    document.querySelector('#xf .knob').style.left = (xp * 100) + '%';
    drawPos();
    if (!playing) return;
    const A = decks[live];
    let s = '';
    const TN = { soft: 'weich', filter: 'mit Filter', echo: 'mit Echo', brake: 'mit Bremse' };
    if (mix && mix.started) s = 'Überblende ' + (TN[mix.kind] || '') + (mix.sync ? ' taktgenau' + (lastErr != null ? ' (Versatz ' + Math.round(lastErr * 60000 / (decks[1 - live].info.bpm || 120)) + ' ms)' : '') : ' ohne Takt') + ' …';
    else if (mix) s = 'Nächstes Lied in ' + mmss((mix.t - A.a.currentTime) / A.base) + ' · Übergang ' + (TN[mix.kind] || 'weich') + (mix.sync ? ', ' + mix.bars + ' Takte taktgenau' : ', ohne Takt (' + (decks[1 - live].info && decks[1 - live].info.bpm ? 'Tempo zu weit weg' : 'BPM oder Raster fehlt') + ')');
    else if (cur + 1 >= items.length) s = 'Letztes Lied der Playlist.';
    else s = 'Nächstes Lied lädt …';
    $('pstat').textContent = s;
  }
  setInterval(drawDecks, 250);
  decks.forEach((d, k) => { $('deck' + k).querySelector('.prog').onclick = e => {
    if (!d.a || !d.info || k !== live || (mix && mix.started)) return;
    const r = e.currentTarget.getBoundingClientRect();
    d.a.currentTime = Math.max(0, (e.clientX - r.left) / r.width * d.info.du);
    mix = null;                                              // neu planen ab der neuen Stelle
  }; });

  // ---- Sample-Tasten (Wunsch 07.11.2026): vier Tasten, belegt mit Dateien aus dem Ordner SAMPLES am Stick ---------------
  let samples = [], pads = [];
  const padAudio = [];
  try { pads = JSON.parse(localStorage.getItem('autodj_pads') || '[]') || []; } catch (e) { pads = []; }   // je Browser gemerkt
  const sname = p => String(p || '').split('/').pop().replace(/\.[^.]+$/, '');
  async function loadSamples() {
    try { samples = ((await fetch('/api/musik').then(r => r.json())).tracks || []).filter(t => t.path && /\/(TEST)?SAMPLES\//i.test(t.path)); } catch (e) { samples = []; }
    samples.sort((a, b) => sname(a.path).localeCompare(sname(b.path)));
    const short = samples.filter(t => (t.dur || 0) >= 1.5 && t.dur <= 15 && !/stille|silence/i.test(sname(t.path)));      // vorbelegen nur mit kurzen (keine Testtoene, keine Klangraeume)
    for (let k = 0; k < 4; k++) if (!pads[k] && short[k] && !pads.includes(short[k].path)) pads[k] = short[k].path;
    drawPads();
  }
  function drawPads() {
    document.querySelectorAll('#pads .pad').forEach(b => { const p = pads[+b.dataset.k]; b.textContent = p ? sname(p) : '–'; b.title = p || 'nicht belegt: ✎'; });
  }
  function playPad(k) {
    const p = pads[k];
    if (!p) { $('padcfg').hidden = false; drawPadCfg(); return; }
    if (!music) return toast('Der Musik-Rechner ist nicht verbunden.');
    ensureCtx();
    let pa = padAudio[k];
    if (!pa || pa.path !== p) {
      if (pa) pa.a.pause();
      const a = new Audio(); a.crossOrigin = 'anonymous'; a.preload = 'auto';
      const g = ctx.createGain(); g.gain.value = 0.9;
      ctx.createMediaElementSource(a).connect(g); g.connect(master);
      pa = padAudio[k] = { a, path: p };
      a.src = music + '/audio?p=' + encodeURIComponent(p);
    }
    pa.a.currentTime = 0;                                    // Taste wie am Sampler: jeder Druck spielt von vorne (Wunsch 08.11.2026)
    pa.a.play().catch(e => toast('Sample ging nicht: ' + e.message));
    duck(true);
    drawPadGlow();
  }
  function stopPads() { padAudio.forEach(pa => { if (pa) pa.a.pause(); }); drawPadGlow(); }
  function drawPadGlow() {                                // leuchtet nur, solange das Sample wirklich spielt
    document.querySelectorAll('#pads .pad').forEach(b => { const pa = padAudio[+b.dataset.k]; b.classList.toggle('on', !!(pa && !pa.a.paused && !pa.a.ended)); });
    if (!padAudio.some(pa => pa && !pa.a.paused && !pa.a.ended)) duck(false);
  }
  // Musik leiser, solange ein Sample spielt (Wunsch 08.11.2026: sonst hoert man es kaum); Stufe je Browser gemerkt
  let duckLevel = 0.3, ducked = false;
  try { const v = parseFloat(localStorage.getItem('autodj_duck')); if (v >= 0 && v <= 1) duckLevel = v; } catch (e) { /* privat */ }
  $('pduck').value = String(duckLevel);
  $('pduck').onchange = () => {
    duckLevel = +$('pduck').value;
    try { localStorage.setItem('autodj_duck', String(duckLevel)); } catch (e) { /* privat */ }
    if (ducked) { ducked = false; duck(true); }
  };
  function duck(on) {
    if (!musicBus || on === ducked) return;
    ducked = on;
    musicBus.gain.setTargetAtTime(on ? duckLevel : 1, ctx.currentTime, on ? 0.06 : 0.35);   // schnell runter, weich wieder hoch
  }
  setInterval(drawPadGlow, 200);
  function drawPadCfg() {
    const o = t => '<option value="' + esc(t.path) + '">' + esc(sname(t.path)) + (t.dur ? ' (' + mmss(t.dur) + ')' : '') + '</option>';
    const opts = '<option value="">– frei –</option><optgroup label="kurz (bis 15 s)">' + samples.filter(t => t.dur && t.dur <= 15).map(o).join('') +
      '</optgroup><optgroup label="länger">' + samples.filter(t => !(t.dur && t.dur <= 15)).map(o).join('') + '</optgroup>';
    $('padcfg').innerHTML = [0, 1, 2, 3].map(k => '<label class="dim2">Taste ' + (k + 1) + ' <select data-k="' + k + '">' + opts + '</select></label>').join('') ||
      '<span class="dim2">Keine Samples gefunden (Ordner SAMPLES am Stick).</span>';
    $('padcfg').querySelectorAll('select').forEach(s => { s.value = pads[+s.dataset.k] || ''; });
  }
  $('pads').onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.id === 'padstop') { stopPads(); return; }
    if (b.id === 'padset') { $('padcfg').hidden = !$('padcfg').hidden; if (!$('padcfg').hidden) drawPadCfg(); return; }
    playPad(+b.dataset.k);
  };
  $('padcfg').onchange = e => {
    const s = e.target.closest('select'); if (!s) return;
    pads[+s.dataset.k] = s.value;
    try { localStorage.setItem('autodj_pads', JSON.stringify(pads)); } catch (x) { /* privates Fenster */ }
    if (padAudio[+s.dataset.k]) { padAudio[+s.dataset.k].a.pause(); padAudio[+s.dataset.k] = null; }
    drawPads();
  };
  document.addEventListener('keydown', e => {                // Tasten 1 bis 4 spielen die Samples (nicht beim Tippen in Feldern)
    if (/INPUT|SELECT|TEXTAREA/.test((e.target.tagName || '')) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key >= '1' && e.key <= '4') { playPad(+e.key - 1); e.preventDefault(); }
    if (e.key === 'Escape') stopPads();
  });

  loadInfo();
  loadSamples();
  draw();
  if (!items.length) $('wiz').open = true;                   // noch nichts eingerichtet: Assistent offen
  setInterval(() => { if (items.length) drawCurve(); }, 30000);   // Strich "jetzt" nachfuehren
})();
