// titles.js - Seite /musik/titel: Nummern am Anfang des Titels finden und entfernen (Wunsch von Markus, 07.11.2026).
// "01 - Lied", "03. Lied", "(7) Lied" sind fast immer Tracknummern; "99 Luftballons", "7 Years" oder "5. Sinfonie" gehoeren
// zum Titel. Darum: sicher = vorab angehakt, sonst nur zur Frage gestellt. Gelesen und geschrieben wird der Tag der MP3 am Mac
// (music_serve /tags, wie das Fenster Tag bearbeiten), nur auf Klick, nur Titel und (wenn frei) Track. Aufs Licht wirkt nichts.
(function (root) {
  'use strict';
  // Nummer, Klammer, Trenner, Rest. Trenner: " - ", ". ", "_", ") ", ": " oder nur Leerzeichen
  const RX = /^\s*([(\[]?)(\d{1,3})([)\]]?)(\s*[-–—._:)]\s*|\s+)(.*\S)\s*$/;
  const tnum = v => { const m = String(v || '').match(/^\s*(\d+)/); return m ? parseInt(m[1], 10) : 0; };

  // {n, clean, sure, why} oder null (keine Nummer vorne). track = Inhalt des Track-Tags ('' = frei)
  function analyse(title, track) {
    const m = String(title || '').match(RX);
    if (!m) return null;
    const [, open, num, close, sep, rest] = m;
    if (!!open !== !!close) return null;                        // "(1 Mix)": keine Nummer in Klammern
    if (!/[A-Za-zÀ-ɏ]/.test(rest)) return null;                // "1 - 2", "24 7": kein Wort dahinter
    if (/^[(\[]/.test(rest)) return null;                       // "68 (Original Mix)": die Zahl ist der ganze Titel
    const dash = /[-–—_)]/.test(sep) || !!open;
    if (!dash && /^\d/.test(rest)) return null;                 // "1.5 Mix", "10:30 Uhr": Zahl geht weiter
    const n = parseInt(num, 10), zero = num.length > 1 && num[0] === '0';
    const tk = tnum(track);
    let sure = n > 0 && (dash || zero || (tk && tk === n));
    let why = '';
    if (tk && tk !== n) { sure = false; why = 'Track-Tag ist ' + tk + ', nicht ' + n; }
    else if (!sure) why = n === 0 ? 'Nummer 0' : sep.includes('.') ? 'Punkt nach der Zahl: vielleicht Teil des Titels („5. Sinfonie“)'
      : 'nur Leerzeichen nach der Zahl: vielleicht Teil des Titels („99 Luftballons“)';
    else why = tk === n ? 'passt zum Track-Tag' : zero ? 'führende Null' : 'Trenner nach der Zahl';
    return { n, clean: rest.trim(), sure, why };
  }
  // was geschrieben wuerde: Titel immer, Track nur wenn frei (Wunsch: "Nummer wenn Tag Track frei dort reinschreiben")
  function fields(a, track, title) {
    const f = { title: String(title || a.clean).trim() };
    if (!String(track || '').trim() && a.n > 0) f.track = String(a.n);
    return f;
  }
  // Gibt es den Titel mit der Zahl so? (Wunsch 07.11.2026: "10 Nackte Friseusen" im Internet nachsehen, dann nicht umbenennen)
  // suggest = Treffer der Internetsuche des Tag-Editors (music_serve /lookup: MusicBrainz, iTunes, Deezer)
  const words = s => String(s || '').normalize('NFC').toLowerCase().replace(/[^0-9a-zà-ɏ]+/g, ' ').trim();
  function netMatch(title, artist, suggest) {
    const full = words(title), ar = words(artist);
    if (!full) return false;
    return (suggest || []).some(s => {
      const st = words(s.title), sa = words(s.artist);
      const tOk = st === full || st.startsWith(full + ' ');                 // auch "10 Nackte Friseusen (Radio Edit)"
      const aOk = !ar || !sa || sa.includes(ar) || ar.includes(sa) || sa.split(' ')[0] === ar.split(' ')[0];
      return tOk && aOk;
    });
  }
  const api = { analyse, fields, netMatch };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; return; }
  root.TitleFix = api;
  if (typeof document === 'undefined' || !document.getElementById('tlist')) return;

  // ---- Seite ---------------------------------------------------------------------------------------------------------
  const $ = id => document.getElementById(id);
  const esc = SM.esc, PAGE = 50;
  let music = '', rows = [], filt = 'sure', page = 0, q = '', busy = false, skipped = 0, kept = {};

  function visible() {
    const qq = q.toLowerCase();
    if (filt === 'kept') return rows.filter(r => r.state === 'kept' && (!qq || (r.path + ' ' + r.artist + ' ' + r.title).toLowerCase().includes(qq)));
    return rows.filter(r => r.state !== 'clean' && r.state !== 'gone' && r.state !== 'kept' && (filt === 'all' || r.state === 'done' || r.state === 'err' || (filt === 'sure') === !!(r.a && r.a.sure)) &&
      (!qq || (r.path + ' ' + r.artist + ' ' + r.title).toLowerCase().includes(qq)));
  }
  function draw() {
    const v = visible(), pages = Math.max(1, Math.ceil(v.length / PAGE));
    page = Math.min(page, pages - 1);
    const pg = pages > 1 ? '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pages +
      '</span><button class="pgnext"' + (page < pages - 1 ? '' : ' disabled') + '>Weiter ›</button></div>' : '';
    $('tlist').innerHTML = !v.length ? '<p class="empty">' + (filt === 'kept' ? 'Noch nichts so gelassen.' : 'Nichts zu bereinigen' + (filt === 'sure' ? ' (sicher). Unter „hinterfragen“ stehen die unsicheren.' : '.')) + '</p>'
      : pg + v.slice(page * PAGE, page * PAGE + PAGE).map(r => {
        const i = rows.indexOf(r), a = r.a || {};
        const tr = r.state === 'wait' ? 'Tag wird gelesen …' : String(r.track || '').trim() ? 'Track ' + esc(r.track) + ' bleibt' : 'Track frei → <b>' + a.n + '</b>';
        const st = r.state === 'done' ? '<span class="ok">✓ bereinigt</span>' : r.state === 'err' ? '<span class="bad">' + esc(r.err || 'Fehler') + '</span>' : '';
        return '<div class="trow ' + (r.state === 'done' ? 'done' : a.sure ? 'sure' : 'ask') + '" data-i="' + i + '">' +
          '<input type="checkbox" class="tck"' + (r.ck ? ' checked' : '') + (r.state === 'done' || r.state === 'wait' || r.state === 'kept' ? ' disabled' : '') + '>' +
          '<div class="tmain">' + (r.state === 'kept' ? '<div><b>' + esc(r.title) + '</b> <span class="ok">· bleibt so' + (r.src === 'netz' ? ' (gibt es laut Internet so)' : '') + '</span></div>' : '<div><s>' + esc(r.title) + '</s> → <input class="tnew" value="' + esc(r.newt) + '"' + (r.state === 'done' ? ' disabled' : '') + '></div>') +
          '<div class="tinfo">' + esc(r.artist || '–') + (r.state === 'kept' ? '' : ' · ' + tr + ' · <span class="' + (a.sure ? 'why' : 'warn') + '">' + esc(a.why || '') + (r.net === 'nein' ? ' · im Internet nicht so gefunden' : '') + '</span> ' + st) + '</div>' +
          '<div class="tpath">' + esc(r.path) + '</div></div>' +
          (r.state === 'kept' ? '<div class="tbtns"><button class="tunkeep" title="Doch wieder zum Bereinigen anbieten">Nicht mehr behalten</button></div></div>'
            : '<div class="tbtns"><button class="tgo"' + (r.state !== 'ok' ? ' disabled' : '') + '>Bereinigen</button><button class="tkeep" title="Die Zahl gehört zum Titel: so lassen, das Lied kommt nicht wieder">So lassen</button><button class="ttag">Tag</button></div></div>');
      }).join('') + pg;
    const open_ = rows.filter(r => r.state !== 'clean' && r.state !== 'done' && r.state !== 'gone' && r.state !== 'kept');
    const nk = rows.filter(r => r.state === 'kept').length;
    const ng = rows.filter(r => r.state === 'gone').length;
    const ns = open_.filter(r => r.a && r.a.sure).length, nd = rows.filter(r => r.state === 'done').length, nc = rows.filter(r => r.state === 'clean').length;
    const wait = rows.filter(r => r.state === 'wait').length;
    $('tstat').innerHTML = '<b>' + open_.length + '</b> Titel mit Nummer am Anfang · <b>' + ns + '</b> sicher · <b>' + (open_.length - ns) + '</b> hinterfragen' +
      (nd ? ' · <b>' + nd + '</b> bereinigt' : '') + (nk ? ' · ' + nk + ' so gelassen' : '') + (nc ? ' · ' + nc + ' schon in der Datei sauber (Mixxx zeigt noch den alten Titel)' : '') +
      (ng ? ' · ' + ng + (ng > 1 ? ' Dateien fehlen' : ' Datei fehlt') + ' auf dem Stick (nur noch in Mixxx)' : '') + (skipped ? ' · ' + skipped + ' keine MP3 (nicht änderbar)' : '') + (wait ? ' · lese Tags … noch ' + wait : '') + (netTodo ? ' · <span class="warn">schaue im Internet nach: ' + netBusy + ' von ' + netTodo + '</span>' : '');
    $('bgo').textContent = 'Markierte bereinigen (' + rows.filter(r => r.ck && r.state === 'ok').length + ')';
  }

  async function readTag(r) {
    try {
      const d = await fetch(music + '/tags?p=' + encodeURIComponent(r.path)).then(x => x.json());
      if (d.error) throw new Error(d.error);
      const f = d.fields || {};
      r.track = f.track || '';
      const t = String(f.title || '').trim();
      if (t) r.title = t;                                       // der Tag in der Datei zaehlt, nicht die Liste aus Mixxx
      r.a = analyse(r.title, r.track);
      if (!t) { r.state = 'err'; r.err = 'Titel-Tag leer (Mixxx nimmt den Dateinamen): im Tag-Editor setzen'; r.ck = false; return; }
      if (!r.a) { r.state = 'clean'; r.ck = false; return; }
      r.newt = r.a.clean;
      const k = kept[r.path];
      if (k && k.t === r.title && (k.src === 'hand' || k.src === 'netz')) { r.state = 'kept'; r.src = k.src; r.ck = false; return; }   // "so lassen", Titel unveraendert
      r.net = k && k.t === r.title ? k.src : '';                              // 'nein' oder 'offen': nicht neu fragen
      r.ck = r.a.sure; r.state = 'ok';
    } catch (e) {                                               // Datei fehlt (nur noch in Mixxx, etwa bei den Doppelten geloescht): ausblenden
      r.state = /nicht erreichbar|nicht in der/.test(e.message) ? 'gone' : 'err'; r.err = e.message; r.ck = false;
    }
  }
  async function readAll() {
    let k = 0;
    for (const r of rows) {
      if (r.state !== 'wait') continue;
      await readTag(r);
      if (++k % 20 === 0) draw();
    }
    draw();
    netAll();
  }
  // Internetsuche fuer die unsicheren (nur die: "01 - Lied" gibt es nie so), eines nach dem anderen, Ergebnis am Pi gemerkt
  let netBusy = 0, netTodo = 0;
  async function netAll() {
    const todo = rows.filter(r => r.state === 'ok' && r.a && !r.a.sure && !r.net);
    netTodo = todo.length; netBusy = 0;
    for (const r of todo) {
      netBusy++; draw();
      try {
        const u = music + '/lookup?p=' + encodeURIComponent(r.path) + '&artist=' + encodeURIComponent(r.artist || '') + '&title=' + encodeURIComponent(r.title) + '&dur=0';
        const d = await fetch(u).then(x => x.json());
        if (d.error) throw new Error(d.error);
        if (!(d.suggest || []).length && (d.errors || []).length) throw new Error(d.errors[0]);   // offline: nichts merken
        const ok = netMatch(r.title, r.artist, d.suggest);
        kept = (await SM.cmd('title_keep', { path: r.path, title: r.title, src: ok ? 'netz' : 'nein' })).kept || kept;
        if (ok && r.state === 'ok') { r.state = 'kept'; r.src = 'netz'; r.ck = false; } else r.net = 'nein';
      } catch (e) { r.net = 'fehler'; }
    }
    netTodo = 0; draw();
  }
  async function fix(r) {
    const f = fields(r.a, r.track, r.newt);
    if (!f.title) throw new Error('Titel leer');
    const res = await fetch(music + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ p: r.path, name: r.path.split('/').pop(), fields: f }) });
    const j = await res.json().catch(() => ({}));
    if (!res.ok || !j.ok) throw new Error(j.error || ('Fehler ' + res.status));
    r.state = 'done'; r.ck = false; r.title = f.title; if (f.track) r.track = f.track;
  }

  async function load() {
    try {
      music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
      if (!music) { $('tstat').textContent = 'Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer? Nach einem Neustart dauert es bis zu einer Minute.'; return; }
      const d = await fetch('/api/musik').then(r => r.json());
      try { kept = (await SM.cmd('title_kept')).kept || {}; } catch (e) { kept = {}; }
      skipped = 0;
      rows = [];
      for (const t of d.tracks || []) {
        const a = analyse(t.name, '');
        if (!a || !t.path) continue;
        if (!/\.mp3$/i.test(t.path)) { skipped++; continue; }
        rows.push({ path: t.path, artist: t.artist || '', title: t.name, a, newt: a.clean, ck: false, state: 'wait', track: '' });
      }
      rows.sort((x, y) => x.path.localeCompare(y.path));
      draw();
      readAll();
    } catch (e) { $('tmsg').textContent = 'Keine Verbindung: ' + e.message; }
  }

  $('ttabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-f]');
    if (!b) return;
    filt = b.dataset.f; page = 0;
    $('ttabs').querySelectorAll('button[data-f]').forEach(x => x.classList.toggle('on', x === b));
    draw();
  });
  $('tq').addEventListener('input', e => { q = e.target.value; page = 0; draw(); });
  $('tlist').addEventListener('change', e => {
    const el = e.target.closest('.trow'); if (!el) return;
    const r = rows[+el.dataset.i];
    if (e.target.classList.contains('tck')) { r.ck = e.target.checked; draw(); }
    if (e.target.classList.contains('tnew')) r.newt = e.target.value;
  });
  $('tlist').addEventListener('input', e => {
    if (!e.target.classList.contains('tnew')) return;
    rows[+e.target.closest('.trow').dataset.i].newt = e.target.value;
  });
  $('tlist').addEventListener('click', async e => {
    if (e.target.closest('.pgprev')) { page--; draw(); window.scrollTo(0, 0); return; }
    if (e.target.closest('.pgnext')) { page++; draw(); window.scrollTo(0, 0); return; }
    const el = e.target.closest('.trow'); if (!el) return;
    const r = rows[+el.dataset.i];
    if (e.target.closest('.ttag')) {
      SM.tagEdit({ path: r.path, dur: 0 }, music, () => { r.state = 'wait'; readTag(r).then(draw); });
      return;
    }
    if (e.target.closest('.tkeep') || e.target.closest('.tunkeep')) {   // Zahl gehoert zum Titel (Wunsch 07.11.2026: "10 Nackte Friseusen")
      const keep = !!e.target.closest('.tkeep');
      try {
        kept = (await SM.cmd('title_keep', { path: r.path, title: r.title, src: keep ? 'hand' : 'offen' })).kept || {};
        r.state = keep ? 'kept' : 'ok'; r.src = 'hand'; r.net = keep ? '' : 'offen'; r.ck = keep ? false : !!(r.a && r.a.sure);
        SM.toast(keep ? 'Bleibt so: ' + r.title : 'Wird wieder angeboten: ' + r.title, 3000);
      } catch (x) { $('tmsg').textContent = 'Merken ging nicht: ' + x.message; }
      draw();
      return;
    }
    if (e.target.closest('.tgo') && !busy) {
      busy = true;
      try { await fix(r); SM.toast('Bereinigt: ' + r.title, 3000); } catch (x) { r.state = 'err'; r.err = x.message; }
      busy = false; draw();
    }
  });
  $('bgo').addEventListener('click', async () => {
    const todo = rows.filter(r => r.ck && r.state === 'ok');
    if (!todo.length || busy) return;
    if (!await SM.ask(todo.length + ' Titel bereinigen?\n\n' + todo.slice(0, 12).map(r => r.title + '  →  ' + r.newt).join('\n') + (todo.length > 12 ? '\n…' : '') +
      '\n\nGeschrieben wird nur der Titel und, wo er frei ist, der Track. Mixxx zeigt die neuen Titel erst nach „Metadaten aus Datei importieren“.', undefined, 'Bereinigen')) return;
    busy = true;
    let ok = 0;
    for (const r of todo) {
      try { await fix(r); ok++; } catch (x) { r.state = 'err'; r.err = x.message; }
      if (ok % 10 === 0) draw();
    }
    busy = false; draw();
    SM.toast(ok + ' Titel bereinigt.', 5000);
  });
  $('bnone').addEventListener('click', () => { for (const r of visible()) if (r.state === 'ok') r.ck = false; draw(); });
  load();
})(typeof window !== 'undefined' ? window : globalThis);
