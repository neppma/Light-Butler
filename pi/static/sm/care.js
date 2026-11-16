// Datenpflege (Wunsch von Markus, 08.11.2026): alle Werkzeuge zum Bereinigen der Musik an einer Stelle, als Rezept in sinnvoller
// Reihenfolge. Die Seite zaehlt nur (Pi: /api/musik, Mac: Vorhoer-Server) und fuehrt zu den Werkzeugen; dort wird nur auf Klick
// geschrieben oder geloescht. Schritte ohne Zahl (Sicherung, Mixxx aufraeumen) hakt man selbst ab (dieser Browser merkt es sich).
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const RX_NR = /^\s*([(\[]?)(\d{1,3})([)\]]?)(\s*[-–—._:)]\s*|\s+)(.*\S)\s*$/;    // wie Titel bereinigen
  function hasNr(title) {                 // dieselben Ausnahmen wie analyse() in titles.js ("68 (Original Mix)", "8.00 Am", "20.000 Meilen")
    const m = String(title || '').match(RX_NR);
    if (!m) return false;
    const [, open, , close, sep, rest] = m;
    if (!!open !== !!close || !/[A-Za-zÀ-ɏ]/.test(rest) || /^[(\[]/.test(rest)) return false;
    return !(!(/[-–—_)]/.test(sep) || !!open) && /^\d/.test(rest));
  }
  const tkey = s => String(s || '').normalize('NFC').toLowerCase().replace(/[^0-9a-zà-ɏ]+/g, '');
  const DONE_KEY = 'pflege_erledigt';
  let music = '', V = {}, manual = {}, open = new Set();
  try { manual = JSON.parse(localStorage.getItem(DONE_KEY) || '{}') || {}; } catch (e) { manual = {}; }

  // Fehlerbericht 09.11.2026: Doppelte und Ordnerbilder sprangen von gruen auf blau ("wird gerechnet"), solange der Mac neu
  // rechnet (nach jedem Neustart des Helfers). Bis das neue Ergebnis da ist, gilt die letzte bekannte Zahl dieses Browsers.
  const LAST_KEY = 'pflege_letzte';
  let last = {};
  try { last = JSON.parse(localStorage.getItem(LAST_KEY) || '{}') || {}; } catch (e) { last = {}; }
  function keepLast(id, n) {
    if (n === null || n === undefined) return typeof last[id] === 'number' ? last[id] : null;
    if (last[id] !== n) { last[id] = n; try { localStorage.setItem(LAST_KEY, JSON.stringify(last)); } catch (e) { /* privat */ } }
    return n;
  }
  // Schritte: n = Zahl offen (null = unbekannt, undefined = keine Zahl, von Hand abhaken)
  const STEPS = [
    { grp: 'Vorbereitung', id: 'backup', t: 'Sicherung', d: 'den Musik-Stick sichern, bevor viel geändert wird', manual: true, note: () => V.mxbak, auto: () => V.stick,
      how: ['Den Musik-Stick auf eine andere Platte kopieren (Finder, Time Machine oder ein Synchronisationsprogramm), dann hier „Erledigt“ drücken. Sichert ihn dein NAS-Sync (Job mit dem Musikordner als Quelle), liest die Seite das Datum aus dessen Protokoll und hakt von selbst ab.',
        'Die Mixxx-Datenbank (Hotcues, Kisten, Playlists, die nicht in den MP3s stehen) sichert die App „Light-Butler Mixxx“ bei jedem Start selbst, die letzten fünf liegen in ~/Light-Butler-Daten/mixxx-sicherung. Dafür ist nichts zu tun.'] },
    { id: 'import', t: 'Neue Musik importieren', d: 'Lieder aus dem Wartebereich „musik-import“ neben dem Musikordner vorhören, taggen und an ihren Platz im Musikordner verschieben', href: '/musik/import',
      n: () => V.imp, unit: 'im Wartebereich', tool: true },
    { id: 'fehlt', t: 'Fehlt mir', d: 'Merkliste der Lieder, die dir fehlen („+ merken“ bei den Alben und bei leerer Suche in der Musik-Datenbank), mit Spotify-Suche; was in die Sammlung kommt, verschwindet von selbst', href: '/musik/fehlt',
      n: () => V.fehlt, unit: 'gemerkt', tool: true },
    { grp: 'Dateien', id: 'junk', t: 'Datenmüll', d: 'Thumbs.db, desktop.ini, Cover-Kopien vom Media Player, Logs und Ähnliches (die Hilfsdateien von macOS bleiben)', href: '/musik/pruefen?t=muell',
      n: () => V.check && V.check.state === 'ready' ? V.check.n.muell + V.check.n.sonstige : null, wait: 'noch nicht geprüft',
      // Wunsch 08.11.2026: auf derselben Seite warten noch Dateinamen, dann nicht gruen (rot mit Zahl, Link zum Reiter)
      extra: () => V.check && V.check.state === 'ready' && V.check.n.namen ? { n: V.check.n.namen, txt: ' Dateinamen offen', href: '/musik/pruefen?t=namen' } : null },
    { id: 'empty', t: 'Leere Ordner', d: 'Ordner ohne Musik (auch in keinem Unterordner): in den Papierkorb', href: '/musik/pruefen?t=leer',
      n: () => V.check && V.check.state === 'ready' && V.check.n.leer != null ? V.check.n.leer : null, wait: 'noch nicht geprüft' },
    { id: 'defekt', t: 'Beschädigte Dateien', d: 'Dateien, die macOS und damit Mixxx am Mac nicht öffnen kann („konnte nicht geladen werden“): MP3s ohne Neukodieren reparieren, Tags und Cover bleiben', href: '/musik/defekt',
      n: () => V.defekt, wait: 'wird geprüft' },
    { id: 'folders', t: 'Ordner umbenennen', d: 'Ordner umbenennen oder verschieben (etwa eine CD aus „Disc 2“ an die richtige Stelle), Mixxx übernimmt die neuen Pfade', href: '/musik/ordner', tool: true },
    { id: 'merge', t: 'Ordner auflösen', d: 'Einen Oberordner (zum Beispiel OLDIES) in einen anderen (U-MUSIK) einsortieren, nach Interpret; der Ordnername kommt in die Gruppe, Mixxx behält Hotcues und Playlists', href: '/musik/aufloesen', tool: true },
    { id: 'lose', t: 'Lose Album-Lieder', d: 'Lieder eines Albums, die lose im Interpreten-Ordner liegen, in ihren Album-Ordner verschieben (nie überschreiben, zurücknehmbar, Mixxx behält Hotcues und Playlists)', href: '/musik/lose', n: () => V.lose },
    { id: 'mp3', t: 'Alles in MP3', d: 'MP4, WAV, FLAC …, die es nicht auch als MP3 gibt: mit „→ MP3“ umwandeln (das Original bleibt erst liegen)', href: '/musik?f=nichtmp3', n: () => V.nomp3 },
    { id: 'dupes', t: 'Doppelte entfernen', d: 'gleiche Lieder vergleichen, die schlechtere Datei in den Papierkorb (auch die Originale nach dem Umwandeln)', href: '/musik/doppelte',
      n: () => V.dupes, wait: 'wird gerechnet' },
    { id: 'mixxx', mx: 1, t: 'Mixxx aufräumen', d: 'gelöschte Dateien aus Mixxx entfernen, neue einlesen', manual: true, n: () => V.sync, unit: 'abweichend', note: () => V.ueb,
      how: ['Zuerst die App „Light-Butler Mixxx“ einmal neu starten: sie überträgt Plattenkisten, Wiedergabelisten und Hotcues der fehlenden Titel auf das gleiche Lied, das noch da ist (steht hier unten, wenn noch etwas offen ist). Erst danach bereinigen, dann geht nichts verloren.','In Mixxx in der Seitenleiste links (nicht im Menü oben): ganz oben beim Eintrag „Titel“ (englisch „Tracks“) auf den kleinen Pfeil ▸ klicken, darunter erscheint „Fehlende Titel“ (Missing Tracks).',
        '„Fehlende Titel“ anklicken, dort „Alle auswählen“ (Select All) und „Bereinigen“ (Purge).',
        'Dann Bibliothek → „Bibliothek neu einlesen“, damit neue MP3s dazukommen.',
        'Danach hier „Erledigt“ drücken.'] },
    { grp: 'Tags und Cover', id: 'titles', t: 'Titel bereinigen', d: 'Nummern vorne im Titel („01 - Lied“) → in den Track', href: '/musik/titel', n: () => V.titles },
    { id: 'fnametags', t: 'Tags aus Dateinamen', d: 'Lieder ohne Tags (zum Beispiel lizenzfreie Musik): Interpret, Titel und Track aus dem Dateinamen eintragen, nach einem wählbaren Muster', href: '/musik/dateinamen', tool: true },
    { id: 'cd', t: 'CD-Assistent', d: 'Ganze CDs mit falschen Titeln: Trackliste aus dem Internet einfügen, zuordnen, Tags und Namen schreiben', href: '/musik/cd',
      n: () => V.check && V.check.state === 'ready' ? new Set((V.check.namen || []).filter(x => /Alle Lieder dieser CD/.test(x.why || '')).map(x => x.rel.split('/').slice(0, -1).join('/'))).size : null,
      unit: 'CDs', wait: 'noch nicht geprüft', tool: true },   // Werkzeug (Wunsch 09.11.2026): bei Bedarf, ohne Nummer
    { id: 'same', t: 'Titel = Interpret', d: 'Assistent: Shazam, sonst Dateiname; Vorschläge im Reiter „Titel = Interpret“', href: '/musik?f=same', n: () => V.same },
    { id: 'folder', t: 'Ordnerbilder in die MP3', d: 'Folder.jpg / AlbumArt.jpg in MP3s ohne eigenes Bild', href: '/musik/vorschlaege?f=ordner',
      n: () => V.folder, wait: 'noch nicht gesucht' },
    { id: 'tags', t: 'Tag-Vorschläge und Cover', d: 'fehlende Tags ergänzen; was danach ohne Cover ist: Cover erzeugen (die Zahl führt zu genau diesen Liedern)', href: '/musik/vorschlaege', n: () => V.nocover, unit: 'ohne Cover',
      nhref: '/musik?f=nocover' },   // Fehlerbericht 11.11.2026: 87 ohne Cover, die Vorschlags-Seite zeigte keins (nichts gefunden / abgelehnt)
    { id: 'genres', t: 'Genres', d: 'Doppelte Genres zusammenlegen, Lieder ohne Genre füllen (Interpret, Ordner, Internet); „Other“ gilt als vergeben', href: '/musik/genres', n: () => V.genres, wait: 'Musik-Rechner nicht erreichbar', note: () => V.genresNote },
    { id: 'energy', t: 'Energie eintragen', d: 'Lieder ab 30 Sekunden ohne Energie im Tag: die geschätzte Stufe ins Tag schreiben (nur die Zahl, nie über eine vorhandene Stufe)', action: 'energy',
      n: () => V.energy, wait: 'Musik-Rechner nicht erreichbar', note: () => V.energyNote },
    { id: 'short', t: 'Kurze Stücke', d: 'Samples und Jingles unter 30 Sekunden: BPM, Tonart und geschätzte Energie sind dort nur geraten, auf Knopfdruck leeren', href: '/musik/pruefen?t=kurz',
      n: () => V.check && V.check.state === 'ready' && V.check.n.kurz != null ? V.check.n.kurz : null, wait: 'noch nicht geprüft' },
    { id: 'changed', mx: 1, t: 'Geänderte → Mixxx', d: 'Playlist für Mixxx, dort alle markieren und Metadaten importieren', action: 'changed', n: () => V.changed },
    { grp: 'Zum Schluss', id: 'names', t: 'Dateinamen', d: '„Interpret - Titel“; danach die Mixxx-App neu starten (sie trägt die neuen Namen ein)', href: '/musik/pruefen?t=namen',
      n: () => V.check && V.check.state === 'ready' ? V.check.n.namen : null, wait: 'noch nicht geprüft' },
    { id: 'samename', t: 'Gleiche Dateinamen', d: 'derselbe Dateiname an mehreren Stellen; wichtig, falls alles einmal in einen Ordner kommt', href: '/musik/pruefen?t=gleich',
      n: () => V.check && V.check.state === 'ready' ? (V.check.n.gleich || 0) : null, wait: 'noch nicht geprüft' },
    { grp: 'Abschluss', id: 'mirror', t: 'Spiegeln', d: 'Wenn alles fertig ist: ein Laufwerk auf den Stand eines anderen bringen, etwa Stick → NAS, NAS → Stick oder Stick → Ersatzstick (Probelauf, dann spiegeln; Ersetztes und Gelöschtes kommt in den Papierkorb des Ziels)', href: '/musik/spiegeln', tool: true },
  ];
  if (SM.MXOFF) for (let i = STEPS.length - 1; i >= 0; i--) if (STEPS[i].mx) STEPS.splice(i, 1);   // ohne Mixxx: Schritte nur fuer Mixxx weg

  async function getJSON(url, opt) {
    const r = await fetch(url, opt);
    const t = await r.text();
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return JSON.parse(t);
  }
  const mac = path => music ? getJSON(music + path).catch(() => null) : Promise.resolve(null);

  let lastLib = null;
  async function load() {
    try {
      const d = await getJSON('/api/musik');
      lastLib = d;
      music = d.music || '';
      const tr = (d.tracks || []).filter(t => t.path);
      const tw = SM.mp3Twin(tr);           // WAV/MP4 mit MP3-Schwester zaehlen nicht (Wunsch 08.11.2026)
      V.nomp3 = tr.filter(t => !tw(t)).length;
      let tk = {};                         // "So lassen" zaehlt nicht (Fehlerbericht 08.11.2026: Datenpflege 48, Seite 0)
      try { tk = (await getJSON('/api/sm/cmd', { method: 'POST', body: JSON.stringify({ op: 'title_kept' }) })).kept || {}; } catch (e) { tk = {}; }
      V.titles = tr.filter(t => /\.mp3$/i.test(t.path) && hasNr(t.name) &&
        !(tk[t.path] && tk[t.path].t === t.name && (tk[t.path].src === 'hand' || tk[t.path].src === 'netz'))).length;
      V.same = tr.filter(t => tkey(t.artist) && tkey(t.artist) === tkey(t.name)).length;
      // nur Formate, die ein Cover tragen koennen (Wunsch 09.11.2026: WAV zaehlt nicht, "THX Intro.wav")
      V.nocover = tr.filter(t => t.cv === 0 && SM.canCover(t.path)).length;
      V.n = tr.length;
      const [chk, fa, ch, du, sy, st, mb, gn, en, im] = await Promise.all([mac('/check'), mac('/folderart'), mac('/changed'), mac('/dupes'), mac('/sync'),
        getJSON('/api/sm/cmd', { method: 'POST', body: JSON.stringify({ op: 'stems_bulk_status' }) }).catch(() => null), mac('/mixxxsicherung'), mac('/genres'), mac('/energie'), mac('/import?count=1')]);
      try { const fm = await getJSON('/api/sm/missing'); V.fehlt = (fm.items || []).length; } catch (e) { V.fehlt = null; }   // Fehlt mir (14.11.2026)
      const df = await mac('/defekt?count=1');
      V.defekt = df && typeof df.n === 'number' && df.state !== 'off' && (df.state === 'ok' || df.n) ? df.n : null;   // beschaedigte Dateien (14.11.2026)
      const lo = await mac('/lose?count=1');
      V.lose = lo && typeof lo.n === 'number' ? lo.n : null;   // lose Album-Lieder (14.11.2026)
      V.imp = im && typeof im.n === 'number' ? im.n : null;   // Lieder im Wartebereich musik-import (10.11.2026)
      V.energy = en && en.an ? en.offen : null;   // Energie in leere Tags (09.11.2026)
      V.energyNote = !en || !en.an ? '' : (en.laeuft ? '✎ Wird gerade geschrieben … ' : '') + (en.warten ? en.warten + ' Lieder werden noch gemessen, sie kommen danach dazu.' : '');
      // Genre-Editor (08.11.2026). "Other" gilt als vergebenes Genre (Wunsch 11.11.2026): offen sind nur Lieder ganz ohne Genre
      const fillEmpty = gn && gn.fill_empty != null ? gn.fill_empty : Math.max(0, (gn && gn.empty || 0) - (gn && gn.empty_sam || 0));
      V.genres = gn && gn.genres ? gn.suggest.filter(s => s.to).length + fillEmpty : null;
      // Wunsch 09.11.2026: woraus die Zahl besteht (Seite zeigt oben "0 ohne Genre", die 135 sind "Other")
      if (gn && gn.genres) {
        const sg = gn.suggest.filter(s => s.to).length;
        V.genresNote = [fillEmpty ? fillEmpty + ' ohne Genre' : '', sg ? sg + ' zum Zusammenlegen' : ''].filter(Boolean).join(', ');
      }
      const ub = mb && mb.ueb;               // Mixxx-Daten fehlender Tracks auf den Zwilling (09.11.2026)
      V.ueb = !ub || ub.fehlend == null ? '' : ub.offen > 0 ? '⚠ ' + ub.offen + ' Kisten-/Listen-/Hotcue-Einträge der ' + ub.fehlend + ' fehlenden Titel warten auf die Übertragung: erst „Light-Butler Mixxx“ neu starten, dann bereinigen.'
        : ub.fehlend > 0 ? '✓ Alles übertragen' + (ub.letzt ? ' (' + ub.letzt.n + ' Einträge am ' + new Date(ub.letzt.t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ')' : '') + ': die ' + ub.fehlend + ' fehlenden Titel in Mixxx jetzt gefahrlos bereinigen.' : '';
      V.mxbak = mb && mb.t ? 'Mixxx-Datenbank automatisch gesichert: ' + new Date(mb.t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
        : mb ? 'Mixxx-Datenbank: noch keine Sicherung (kommt beim nächsten Start der Mixxx-App)' : '';
      const fmtT = t => new Date(t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
      V.stick = mb && mb.stick && mb.stick.t ? { t: mb.stick.t, txt: 'Stick gesichert ' + fmtT(mb.stick.t) + ' (NAS-Sync)', old: Date.now() / 1000 - mb.stick.t > 7 * 86400 } : null;
      V.check = chk && chk.state !== 'off' ? chk : null;
      V.folder = keepLast('folder', fa && fa.state === 'ready' ? fa.n : null);
      V.changed = ch && typeof ch.n === 'number' ? ch.n : null;
      V.dupes = keepLast('dupes', du && du.state === 'ok' ? (du.groups || []).length : null);
      V.sync = sy && !sy.off ? (sy.gone || 0) + (sy.new || 0) + (sy.known || 0) : null;
      V.stems = st;
      $('cinfo').textContent = (music ? '' : 'Der Light-Butler erreicht den Musik-Rechner gerade nicht: die Zahlen vom Musik-Rechner fehlen. ') + V.n + ' Lieder in der Liste · Stand ' +
        new Date().toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' });
    } catch (e) { $('cinfo').textContent = 'Keine Verbindung zum Light-Butler: ' + e.message; }
    draw();
  }

  function state(s) {
    const au = s.auto && s.auto();
    if (au) return { done: !au.old, n: undefined, auto: au };   // aus dem Protokoll deiner Sicherung (aelter als 7 Tage: wieder offen)
    if (s.tool) return { done: true, n: s.n ? s.n() : undefined, tool: true };   // Werkzeug: zaehlt nicht als offener Schritt, ohne Nummer
    if (s.manual && manual[s.id]) return { done: true, n: s.n ? s.n() : undefined };
    if (!s.n) return { done: false, n: undefined };
    const n = s.n();
    if (n === null || n === undefined) return { done: false, n: null };
    const ex = s.extra ? s.extra() : null;
    return { done: !s.manual && n === 0 && !ex, n, ex };
  }

  function draw() {
    let html = '', next = false, k = 0;
    for (const s of STEPS) {
      const stt = state(s);
      if (s.grp) html += '<div class="grp">' + esc(s.grp) + '</div>';
      const isNext = !stt.done && !next;
      if (isNext) next = true;
      const cnt = stt.auto ? '<span class="cnt' + (stt.auto.old ? '' : ' ok') + '">' + esc(stt.auto.txt) + (stt.auto.old ? ', älter als 7 Tage' : '') + '</span>'
        : stt.n === undefined ? (s.manual && manual[s.id] ? '<span class="cnt ok">erledigt ' + esc(manual[s.id]) + '</span>' : '')
        : stt.n === null ? '<span class="cnt wait">' + esc(s.wait || 'unbekannt') + '</span>'
        : (s.nhref && stt.n ? '<a class="cnt" href="' + s.nhref + '" title="Genau diese Lieder zeigen">' + stt.n + (s.unit ? ' ' + esc(s.unit) : '') + ' →</a>'
          : '<span class="cnt' + (stt.n === 0 && !stt.ex ? ' ok' : '') + '">' + stt.n + (s.unit ? ' ' + esc(s.unit) : '') + '</span>') +
          (s.manual && manual[s.id] ? '<span class="cnt ok">erledigt ' + esc(manual[s.id]) + '</span>' : '') +
          (stt.ex ? '<a class="cnt bad" href="' + stt.ex.href + '">' + stt.ex.n + esc(stt.ex.txt) + '</a>' : '');
      const acts = (s.href ? '<a class="btn" href="' + s.href + '">Öffnen</a>' : '') +
        (s.action === 'changed' ? '<button data-act="changed">Erstellen</button>' : '') +
        (s.action === 'energy' && stt.n ? '<button data-act="energy">Eintragen</button>' : '') +
        (s.how ? '<button data-how="' + s.id + '">Anleitung</button>' : '') +
        (s.manual && !stt.auto ? '<button data-done="' + s.id + '">' + (manual[s.id] ? 'Wieder offen' : 'Erledigt') + '</button>' : '');
      html += '<div class="step"><div class="nr' + (stt.tool ? ' tool' : stt.done ? ' done' : isNext ? ' next' : '') + '">' + (stt.tool ? '⚙' : stt.done ? '✓' : k) + '</div>' +
        '<div><div class="t">' + esc(s.t) + cnt + '</div><div class="d">' + esc(s.d) + (s.note && s.note() ? '<br>' + esc(s.note()) : '') + '</div></div><div class="acts">' + acts + '</div>' +
        (s.how ? '<ol class="how"' + (open.has(s.id) ? '' : ' hidden') + '>' + s.how.map(x => '<li>' + esc(x) + '</li>').join('') + '</ol>' : '') + '</div>';
      if (!stt.tool) k++;                  // Werkzeuge bekommen keine Nummer, die Schritte zaehlen ohne Luecke weiter
    }
    const st = V.stems;
    html += '<div class="grp">Läuft von selbst (nur Anzeige)</div><div class="step"><div class="nr">↻</div><div><div class="t">Analyse, Energie, Tonart, Kurven, Cover und Liedtexte vorab' +
      (st ? '<span class="cnt' + (st.done >= st.total ? ' ok' : ' wait') + '">' + st.done + ' / ' + st.total + ' Kurven</span>' : '') +
      '</div><div class="d">im Hintergrund am Musik-Rechner und am Light-Butler; Liedtexte, Cue-Punkte, Cover und Spur-Kurven vorab starten und anhalten</div></div><div class="acts"><a class="btn" href="/musik/vorab">Öffnen</a></div></div>';
    $('steps').innerHTML = html;
  }

  $('steps').addEventListener('click', async e => {
    const how = e.target.closest('button[data-how]');
    if (how) { const id = how.dataset.how; if (open.has(id)) open.delete(id); else open.add(id); draw(); return; }
    const dn = e.target.closest('button[data-done]');
    if (dn) {
      const id = dn.dataset.done;
      if (manual[id]) delete manual[id]; else manual[id] = new Date().toLocaleDateString('de-AT');
      try { localStorage.setItem(DONE_KEY, JSON.stringify(manual)); } catch (x) { /* privat */ }
      draw(); return;
    }
    const eb = e.target.closest('button[data-act="energy"]');
    if (eb) {                              // Energie in leere Tags (09.11.2026): ohne Nachfrage, nur leere Felder, im Hintergrund
      if (!music) return SM.toast('Der Light-Butler erreicht den Musik-Rechner gerade nicht.', 4000);
      eb.disabled = true;
      try {
        const r = await fetch(music + '/energie', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const d = JSON.parse(await r.text());
        if (!r.ok || d.error) throw new Error(d.error || 'ging nicht');
        SM.toast(d.started ? 'Schreibe die Energie in ' + d.n + ' MP3s (im Hintergrund, ein paar Minuten) …' : 'Nichts zu tun.', 4000);
        setTimeout(load, 3000);
      } catch (x) { SM.toast('Energie eintragen: ' + x.message, 5000); eb.disabled = false; }
      return;
    }
    if (e.target.closest('button[data-act="changed"]')) {          // wie in der Musik-Datenbank: Playlist der geaenderten MP3s
      if (!music) return SM.toast('Der Light-Butler erreicht den Musik-Rechner gerade nicht.', 4000);
      try {
        const r = await fetch(music + '/changed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'm3u' }) });
        const d = JSON.parse(await r.text());
        if (!r.ok) throw new Error(d.error || 'ging nicht');
        const ok = await SM.ask(d.n + ' geänderte MP3s als Playlist abgelegt:\n\n' + d.file +
          '\n\nIn Mixxx: links Rechtsklick auf „Wiedergabelisten“ → „Wiedergabeliste importieren“, die Datei wählen. Dann die Playlist öffnen, alle markieren (Cmd+A), Rechtsklick → Metadaten → „Aus Datei importieren“.\n\nBist du in Mixxx fertig, leere ich die Liste.', undefined, 'Fertig, Liste leeren');
        if (ok) await fetch(music + '/changed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'clear', before: d.t }) });
        load();
      } catch (x) { SM.toast('Geänderte → Mixxx: ' + x.message, 5000); }
    }
  });
  load();
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  // Stand der Liedliste (11.11.2026, vorher oben in der Musik-Datenbank): alle 5 s vom Mac, die Liste vom Pi mit load()
  async function libStat() {
    if (document.hidden) return;
    let st = null;
    try { st = music ? await getJSON(music + '/status') : null; } catch (e) { st = null; }
    const el = document.getElementById('libstat');
    if (!el) return;
    el.innerHTML = SM.libStatusHtml(lastLib, st && !st.off ? st : null);
    el.hidden = !el.innerHTML;
  }
  setInterval(libStat, 5000);
  setTimeout(libStat, 2000);
})();
