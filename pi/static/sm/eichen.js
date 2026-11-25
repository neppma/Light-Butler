// Eichstueck (Seite /eichen, Wunsch von Markus 23.11.2026): ein kuenstliches Stueck mit festen Abschnitten abspielen, dabei
// /api/takt und /api/state jede Viertelsekunde lesen und mit den Sollwerten (eichstueck.SECTIONS) vergleichen.
// Nur lesen und Ton im Browser; das Ergebnis geht als eich_result an den Pi (nur im Speicher). Aufs Licht wirkt das nie.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const POLL_MS = 250;
  const FIELDS = [['spielt', 'Musik erkannt', 'music detected'], ['aktiv', 'Tempo bekannt', 'tempo known'],
    ['bpm', 'Tempo (BPM)', 'tempo (BPM)'], ['abschnitt', 'Abschnitt', 'section'], ['einsatz', 'Einsatz', 'onset']];
  let EN = false, INFO = null, samples = [], timer = null, startT = 0, busy = false;
  const L = (de, en) => EN ? en : de;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = t => Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0');

  const audio = new Audio('/eichen/eichstueck.mp3');
  audio.preload = 'auto';
  const bar = SM.playBar(audio, { start: false });   // ohne "ab Hauptteil": das Eichstueck beginnt immer vorn

  function secAt(t) { return INFO ? INFO.sections.find(s => t >= s.a && t < s.b) || null : null; }
  function close(v, w) { return v > 0 && Math.abs(v - w) / w <= 0.03; }

  // Ein Messwert gegen einen Sollwert: 'ok', 'bad' oder null (kein Sollwert). note = Zusatz (halb/doppelt).
  function judge(s, key, want) {
    if (want === undefined || want === null) return { r: null };
    if (key === 'bpm') {
      if (!s.aktiv) return { r: 'bad', note: L('kein Tempo', 'no tempo') };
      if (close(s.bpm, want)) return { r: 'ok' };
      if (close(s.bpm, want * 2) || close(s.bpm, want / 2)) return { r: 'bad', note: L('halb/doppelt', 'half/double') };
      return { r: 'bad' };
    }
    if (key === 'einsatz') return { r: s.abschnitt === want ? 'ok' : null };   // Einsatz: nur wo er erkannt ist, sonst grau
    return { r: s[key] === want ? 'ok' : 'bad' };
  }

  async function poll() {
    if (busy) return;
    busy = true;
    const t = audio.currentTime;
    try {
      const [tk, st] = await Promise.all([fetch('/api/takt', { cache: 'no-store' }).then(r => r.json()),
        fetch('/api/state', { cache: 'no-store' }).then(r => r.json())]);
      const s = { t: Math.round(t * 100) / 100, spielt: !!tk.spielt, aktiv: !!tk.aktiv, bpm: +tk.bpm || 0,
        abschnitt: tk.abschnitt || '', dynamik: tk.dynamik || '', energie: +tk.energie || 0,
        beat_bpm: +st.beat_bpm || 0, bpm_unsure: !!st.bpm_unsure, beat_clear: typeof st.beat_clear === 'number' && st.beat_clear >= 0 ? st.beat_clear : null,
        state: st.state || '', db: st.lvl && typeof st.lvl.rms_db === 'number' ? st.lvl.rms_db : null,
        src: st.tempo_src === 'Mixxx' && st.mx && st.mx.deck !== null ? 'mixxx' : (st.lvsrc || '') };
      if (!audio.paused) samples.push(s);
      drawLive(s, t);
      drawStrips();
    } catch (e) {
      $('state').textContent = L('Keine Antwort vom Light-Butler', 'No answer from the Light-Butler');
    } finally { busy = false; }
  }

  function drawLive(s, t) {
    const sec = secAt(t);
    const w = sec ? sec.want : {};
    const cell = (key, val) => {
      const j = judge(s, key, w[key]);
      const cls = j.r === 'ok' ? 'ok' : j.r === 'bad' ? 'bad' : 'dim';
      return '<td class="' + cls + '">' + esc(val) + (j.note ? ' (' + esc(j.note) + ')' : '') + (j.r === 'ok' ? ' ✓' : j.r === 'bad' ? ' ✗' : '') + '</td>';
    };
    const yn = v => v ? L('ja', 'yes') : L('nein', 'no');
    const want = (k, v) => v === undefined ? '–' : k === 'spielt' || k === 'aktiv' ? yn(v) : String(v);
    let h = '<tr><th>' + L('Stelle', 'Position') + '</th><td colspan="2">' + fmt(t) + (sec ? ' · ' + esc(sec.name) : '') + '</td></tr>';
    h += '<tr><th></th><th>' + L('Soll', 'Target') + '</th><th>' + L('Ist', 'Measured') + '</th></tr>';
    h += '<tr><th>' + L('Musik erkannt', 'Music detected') + '</th><td>' + want('spielt', w.spielt) + '</td>' + cell('spielt', yn(s.spielt)) + '</tr>';
    h += '<tr><th>' + L('Tempo bekannt', 'Tempo known') + '</th><td>' + want('aktiv', w.aktiv) + '</td>' + cell('aktiv', yn(s.aktiv)) + '</tr>';
    h += '<tr><th>' + L('Tempo', 'Tempo') + '</th><td>' + want('bpm', w.bpm) + '</td>' + cell('bpm', s.aktiv ? s.bpm.toFixed(1) : '--') + '</tr>';
    h += '<tr><th>' + L('Abschnitt', 'Section') + '</th><td>' + want('abschnitt', w.abschnitt !== undefined ? w.abschnitt : (w.einsatz !== undefined ? L('Einsatz: ', 'onset: ') + w.einsatz : undefined)) + '</td>' + cell(w.einsatz !== undefined ? 'einsatz' : 'abschnitt', s.abschnitt || '–') + '</tr>';
    h += '<tr><th>' + L('Schlag-Klarheit', 'Beat clarity') + '</th><td></td><td>' + (s.beat_clear === null ? '–' : s.beat_clear.toFixed(2)) + (s.bpm_unsure ? L(' (Tempo noch unsicher)', ' (tempo not certain yet)') : '') + '</td></tr>';
    h += '<tr><th>' + L('Pegel, Eingang', 'Level, input') + '</th><td></td><td>' + (s.db === null ? '–' : s.db.toFixed(0) + ' dB') + ' · ' + esc(s.src) + ' · ' + esc(s.state) + '</td></tr>';
    $('live').innerHTML = h;
    $('state').textContent = s.src === 'mixxx' ? L('Achtung: Mixxx spielt, dessen Tempo zählt statt des Eichstücks.', 'Note: Mixxx is playing, its tempo counts instead of the test piece.') : '';
    document.querySelectorAll('#res tr[data-k]').forEach(tr => tr.classList.toggle('cur', !!sec && tr.dataset.k === sec.key));
  }

  // je Sekunde und Feld: Mehrheit der Messwerte
  function perSecond() {
    const n = Math.ceil(INFO.dur), out = FIELDS.map(() => new Array(n).fill(null));
    const acc = FIELDS.map(() => Array.from({ length: n }, () => [0, 0]));
    for (const s of samples) {
      const i = Math.floor(s.t);
      if (i < 0 || i >= n) continue;
      const sec = secAt(s.t);
      if (!sec) continue;
      FIELDS.forEach(([k], f) => { const j = judge(s, k, sec.want[k]); if (j.r) acc[f][i][j.r === 'ok' ? 0 : 1]++; });
    }
    for (let i = 0; i < n; i++) {
      const sec = secAt(i + 0.5);
      FIELDS.forEach((_, f) => {
        const [o, b] = acc[f][i];
        if (!sec || o + b === 0) return;
        const grace = i + 0.5 - sec.a < INFO.grace;
        out[f][i] = o >= b ? 'ok' : grace ? 'grace' : 'bad';
      });
    }
    return out;
  }

  function drawStrips() {
    if (!INFO) return;
    const ps = perSecond();
    $('strips').innerHTML = FIELDS.map(([k, de, en], f) => '<span>' + L(de, en) + '</span><div class="cells">' +
      ps[f].map((r, i) => '<i class="' + (r === 'ok' ? 'c-ok' : r === 'bad' ? 'c-bad' : r === 'grace' ? 'c-grace' : 'c-none') + '" title="' + fmt(i) + '"></i>').join('') + '</div>').join('');
  }

  function result() {
    return INFO.sections.map(sec => {
      const inS = samples.filter(s => s.t >= sec.a && s.t < sec.b);
      const row = { sec, fields: {} };
      for (const [k] of FIELDS) {
        if (sec.want[k] === undefined) continue;
        if (k === 'einsatz') {                        // ein Einsatz muss in den ersten Sekunden beginnen
          const lim = INFO.einsatz || 4;
          const hit = inS.find(s => s.abschnitt === sec.want[k] && s.t - sec.a <= lim);
          row.fields[k] = { pct: inS.length ? (hit ? 100 : 0) : null, from: hit ? hit.t - sec.a : null, notes: hit ? [] : [L('nicht in den ersten ', 'not within the first ') + lim + ' s'] };
          continue;
        }
        const after = inS.filter(s => s.t - sec.a >= INFO.grace);
        const okN = after.filter(s => judge(s, k, sec.want[k]).r === 'ok').length;
        // richtig ab: erster Zeitpunkt, ab dem es bis zum Ende des Abschnitts (hoechstens 1 s Ausnahme) richtig bleibt
        let from = null;
        for (let i = inS.length - 1, badRun = 0; i >= 0; i--) {
          if (judge(inS[i], k, sec.want[k]).r === 'ok') { badRun = 0; from = inS[i].t - sec.a; } else { badRun += POLL_MS / 1000; if (badRun > 1.0) break; }
        }
        const notes = new Set(after.map(s => judge(s, k, sec.want[k]).note).filter(Boolean));
        row.fields[k] = { pct: after.length ? Math.round(okN * 100 / after.length) : null, from, notes: [...notes] };
      }
      const act = inS.filter(s => s.aktiv && s.bpm > 0).map(s => s.bpm).sort((a, b) => a - b);
      row.bpm = act.length ? act[Math.floor(act.length / 2)] : null;
      const cl = inS.map(s => s.beat_clear).filter(v => typeof v === 'number').sort((a, b) => a - b);
      row.clear = cl.length ? cl[Math.floor(cl.length / 2)] : null;
      row.n = inS.length;
      return row;
    });
  }

  function drawResult() {
    if (!INFO) return;
    const R = result();
    let h = '<tr><th>' + L('Zeit', 'Time') + '</th><th>' + L('Abschnitt', 'Section') + '</th>' +
      FIELDS.map(([, de, en]) => '<th>' + L(de, en) + '</th>').join('') + '<th>' + L('gemessen', 'measured') + '</th></tr>';
    for (const r of R) {
      h += '<tr data-k="' + esc(r.sec.key) + '"><td class="n">' + fmt(r.sec.a) + '–' + fmt(r.sec.b) + '</td><td>' + esc(r.sec.name) + '</td>';
      for (const [k] of FIELDS) {
        const f = r.fields[k];
        if (!f) { h += '<td class="dim">–</td>'; continue; }
        if (f.pct === null) { h += '<td class="dim">' + L('noch nicht gespielt', 'not played yet') + '</td>'; continue; }
        const cls = f.pct >= 90 ? 'ok' : f.pct >= 60 ? 'mid' : 'bad';
        h += '<td class="n ' + cls + '">' + f.pct + ' %' + (f.from !== null ? '<br><span class="dim">' + (k === 'einsatz' ? L('bei +', 'at +') : L('richtig ab ', 'right from ')) + f.from.toFixed(1) + ' s</span>' : '<br><span class="dim">' + L('nie stabil', 'never steady') + '</span>') +
          (f.notes.length ? '<br><span class="dim">' + esc(f.notes.join(', ')) + '</span>' : '') + '</td>';
      }
      h += '<td class="n dim">' + (r.bpm ? r.bpm.toFixed(1) + ' BPM' : '--') + (r.clear !== null ? '<br>' + L('Klarheit ', 'clarity ') + r.clear.toFixed(2) : '') + '</td></tr>';
    }
    $('res').innerHTML = h;
  }

  function drawSecs() {
    $('secs').innerHTML = INFO.sections.map(s => '<span class="' + (s.key.startsWith('stille') ? 'sil' : '') + '" style="flex:' + (s.b - s.a) + ' 1 0" title="' + esc(fmt(s.a) + ' ' + s.name) + '">' + esc(s.name) + '</span>').join('');
  }

  async function send() {
    try {
      const r = await fetch('/api/sm/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ op: 'eich_result', samples, start: startT, version: INFO.version, ua: navigator.userAgent.slice(0, 40) }) }).then(x => x.json());
      $('sent').textContent = L('An den Light-Butler geschickt (', 'Sent to the Light-Butler (') + (r.n || 0) + L(' Messwerte).', ' measurements).');
    } catch (e) { $('sent').textContent = L('Konnte nicht an den Light-Butler schicken.', 'Could not send to the Light-Butler.'); }
  }

  function stopRun(done) {
    if (timer) { clearInterval(timer); timer = null; }
    if (!done) audio.pause();
    $('start').disabled = false; $('stop').disabled = true;
    drawStrips(); drawResult();
    $('dl').disabled = !samples.length;
    if (samples.length) send();
  }

  $('start').onclick = () => {
    samples = []; startT = Date.now();
    audio.currentTime = 0;
    audio.play().catch(() => { $('state').textContent = L('Abspielen wurde vom Browser verhindert.', 'The browser blocked playback.'); });
    bar.show(L('Eichstück', 'Test piece'));
    $('start').disabled = true; $('stop').disabled = false; $('sent').textContent = '';
    if (!timer) timer = setInterval(poll, POLL_MS);
  };
  $('stop').onclick = () => stopRun(false);
  audio.addEventListener('ended', () => stopRun(true));
  audio.addEventListener('timeupdate', () => { if (!timer) return; const r = Math.floor(audio.currentTime); if (r % 5 === 0) drawResult(); });
  $('dl').onclick = () => {
    const blob = new Blob([JSON.stringify({ version: INFO.version, start: startT, sections: INFO.sections, samples }, null, 1)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'eichstueck-' + new Date(startT || Date.now()).toISOString().slice(0, 16).replace(/[:T]/g, '-') + '.json';
    document.body.appendChild(a); a.click(); a.remove();
  };

  (async () => {
    try {
      const nav = await fetch('/api/nav').then(r => r.json());
      EN = nav.lang === 'en';
      if (EN) { document.documentElement.lang = 'en'; document.querySelectorAll('[data-en]').forEach(e => { e.textContent = e.dataset.en; }); }
    } catch (e) { /* bleibt deutsch */ }
    INFO = await fetch('/api/sm/eichen').then(r => r.json());
    drawSecs(); drawStrips(); drawResult();
    poll();
    setInterval(() => { if (!timer) poll(); }, 2000);   // ohne Abspielen nur gelegentlich, fuer die Anzeige Jetzt
  })();
  window.EICH = { judge: (s, k, w) => judge(s, k, w), close };
})();
