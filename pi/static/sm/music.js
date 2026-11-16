// music.js - Musik-Datenbank (Seite /musik): alle Lieder aus Mixxx mit Liedtext, Show, Tonart, BPM, Energie, Genre, Bitrate. Nur Anzeige.
// Spalten ordnen und ausblenden: Knopf Spalten, je Browser gemerkt.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const STEP = 200;                       // Zeilen je Nachladen beim Scrollen
  const KEYS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  // Mixxx-Nummer 1..12 Dur ab C, 13..24 Moll ab C -> Camelot (Lancelot): Dur = B, Moll = A
  const CAMELOT_MAJ = { 0: '8B', 1: '3B', 2: '10B', 3: '5B', 4: '12B', 5: '7B', 6: '2B', 7: '9B', 8: '4B', 9: '11B', 10: '6B', 11: '1B' };
  const CAMELOT_MIN = { 0: '5A', 1: '12A', 2: '7A', 3: '2A', 4: '9A', 5: '4A', 6: '11A', 7: '6A', 8: '1A', 9: '8A', 10: '3A', 11: '10A' };
  let mp3s = new Set(), twin = () => false;
  let all = [], view = [], shown = 0, sortK = 'name', sortUp = true, energySel = new Set();
  let timer = null, music = '', cur = null, busy = false, dupOn = false, sameOn = false, longOn = false, nomp3On = false, prefix = '';   // prefix = gemeinsamer Anfang aller Pfade
  // Gruppen (Wunsch 08.11.2026): Ansicht Liste, Interpreten, Genres oder Energie; offen = aufgeklappt, zu = von Hand zugeklappt
  const GMODES = ['list', 'art', 'alb', 'gen', 'grp', 'lvl', 'kl'], GLIM = 50, GAUTO = 5;   // GLIM Lieder je Gruppe, dann "weitere"; bis GAUTO Gruppen gleich offen
  let gmode = 'list', groups = [], items = null, openG = new Set(), shutG = new Set(), glim = {};
  try { const m = localStorage.getItem('musikgruppe'); if (GMODES.includes(m)) gmode = m; } catch (e) { /* privates Fenster */ }
  if (SM.MXOFF && gmode === 'kl') gmode = 'list';              // Kisten/Listen gibt es nur mit Mixxx
  let stamp = '';                          // Kennung der zuletzt gezeichneten Liste: neu zeichnen nur, wenn sich etwas geaendert hat    // music = Adresse des Vorhoer-Servers am Mac ('' = Bruecke laeuft nicht)

  const norm = s => String(s || '').normalize('NFC').toLowerCase();
  // Titel gleich Interpret (Wunsch 07.11.2026): meist ein Fehler beim Taggen ("Nachtschicht15 / Nachtschicht15")
  const tkey = s => norm(s).replace(/[^0-9a-zà-ɏ]+/g, '');
  const sameTA = r => !!tkey(r.artist) && tkey(r.artist) === tkey(r.name);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mmss = d => { d = Math.round(d || 0); return Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0'); };
  function keyName(r) {
    if (r.kid >= 1 && r.kid <= 12) return KEYS[r.kid - 1];
    if (r.kid >= 13 && r.kid <= 24) return KEYS[r.kid - 13] + 'm';
    return r.key || '';
  }
  function camelot(r) {
    if (r.kid >= 1 && r.kid <= 12) return CAMELOT_MAJ[r.kid - 1];
    if (r.kid >= 13 && r.kid <= 24) return CAMELOT_MIN[r.kid - 13];
    return '';
  }

  // ---- Filter ------------------------------------------------------------------------------------------------
  function buildSelects() {
    const g = {}, k = {};
    for (const r of all) {
      if (r.genre) g[r.genre] = (g[r.genre] || 0) + 1;
      const kn = keyName(r);
      if (kn) k[kn] = { n: (k[kn] || { n: 0 }).n + 1, kid: r.kid };
    }
    const gs = $('genre'), ks = $('key');
    const gv = gs.value, kv = ks.value;
    const gopt = x => '<option value="' + esc(x) + '">' + (SM.favOf('genre', x) ? '♥ ' : '') + esc(x) + ' (' + g[x] + ')</option>';
    const gabc = Object.keys(g).sort((a, b) => a.localeCompare(b, 'de', { sensitivity: 'base' })), gfav = gabc.filter(x => SM.favOf('genre', x));   // alphabetisch (Wunsch 13.11.2026)
    gs.innerHTML = '<option value="">alle</option>' + (gfav.length ? '<optgroup label="♥ Lieblings-Genres">' + gfav.map(gopt).join('') + '</optgroup><optgroup label="alle Genres">' : '') +   // Lieblings-Genres oben (14.11.2026)
      gabc.map(gopt).join('') + (gfav.length ? '</optgroup>' : '');
    ks.innerHTML = '<option value="">alle</option>' + Object.keys(k).sort((a, b) => (k[a].kid || 99) - (k[b].kid || 99) || a.localeCompare(b))
      .map(x => '<option value="' + esc(x) + '">' + esc(x) + (k[x].kid ? ' · ' + camelot({ kid: k[x].kid }) : '') + ' (' + k[x].n + ')</option>').join('');
    gs.value = gv; ks.value = kv;
    const cs = $('crate'), cv0 = cs.value;          // Plattenkisten und Wiedergabelisten aus Mixxx
    cs.innerHTML = '<option value="">alle</option>' + MG.lists(all).map(g => '<option value="' + esc(g.key) + '">' + (g.kind === 'Liste' ? '▶ ' : '') + esc(g.name) + ' (' + g.n + ')</option>').join('');
    cs.value = cv0;
    const e = $('energy');
    if (!e.children.length) {
      for (let i = 1; i <= 9; i++) {
        const b = document.createElement('button');
        b.textContent = i; b.className = 'e' + i; b.title = 'Energie ' + i + ' (aus dem Tag)';
        b.onclick = () => { if (energySel.has(i)) energySel.delete(i); else energySel.add(i); b.classList.toggle('on', energySel.has(i)); apply(); };
        e.appendChild(b);
      }
      const b = document.createElement('button');
      b.textContent = '?'; b.className = 'e0'; b.title = 'ohne Energiestufe';
      b.onclick = () => { if (energySel.has(0)) energySel.delete(0); else energySel.add(0); b.classList.toggle('on', energySel.has(0)); apply(); };
      e.appendChild(b);
    }
  }

  function apply(keep) {
    const q = norm($('q').value).split(/\s+/).filter(Boolean);
    const genre = $('genre').value, key = $('key').value, crate = $('crate').value;
    const bmin = parseFloat($('bmin').value) || 0, bmax = parseFloat($('bmax').value) || 0;
    const lmin = parseFloat($('lmin').value), lmax = parseFloat($('lmax').value);   // Lautheit von-bis in LUFS (11.11.2026)
    const lfilt = !isNaN(lmin) || !isNaN(lmax) || $('lnone').checked;
    // hinzugefuegt (11.11.2026): heute / gestern (ab Mitternacht), seit N Tagen, oder von … bis … (Kalendertage, Ortszeit)
    const fav = $('fadd').value, mid = new Date(); mid.setHours(0, 0, 0, 0);
    const day = s => { if (!s) return 0; const d = new Date(s + 'T00:00:00'); return isNaN(d) ? 0 : d.getTime() / 1000; };
    let addFrom = 0, addTo = Infinity;
    if (fav === 'heute') addFrom = mid.getTime() / 1000;
    else if (fav === 'gestern') { addTo = mid.getTime() / 1000; addFrom = addTo - 86400; }
    else if (fav === 'datum') { addFrom = day($('faddv').value); addTo = $('faddb').value ? day($('faddb').value) + 86400 : Infinity; }
    else if (fav) addFrom = Date.now() / 1000 - (+fav) * 86400;
    const fadd = !!fav && (addFrom > 0 || addTo < Infinity);
    $('faddr').hidden = fav !== 'datum';
    const flyr = $('flyr').checked, fshow = $('fshow').checked, fana = $('fana').checked, fnoana = $('fnoana').checked, fbad = $('fbad').checked, fcue = $('fcue').checked, fnocue = $('fnocue').checked, fstems = $('fstems').checked, fsrc = $('fsrc').checked, fnocv = $('fnocv').checked, ffav = $('ffav').value, frat = +$('frat').value || 0;
    view = all.filter(r => {
      if (q.length) { const t = r._s; if (!q.every(w => t.includes(w))) return false; }
      if (genre && r.genre !== genre) return false;
      if (key && keyName(r) !== key) return false;
      if (crate && !MG.keysOf(r, 'kl').some(k => k[0] === crate)) return false;
      if (lfilt) {
        if ($('lnone').checked) { if (r.lufs) return false; }
        else if (!r.lufs || (!isNaN(lmin) && r.lufs < lmin) || (!isNaN(lmax) && r.lufs > lmax)) return false;
      }
      if (bmin && r.bpm < bmin) return false;
      if (bmax && r.bpm > bmax) return false;
      if (energySel.size && !energySel.has(Math.min(9, r.lvl || 0))) return false;
      if (flyr && r.lyr < 2) return false;
      if (fshow && !r.show) return false;
      if (fana && !r.ana) return false;
      if (fnoana && r.ana) return false;
      if (fbad && !r.bad) return false;
      if (fcue && !r.cues) return false;
      if (fnocue && r.cues) return false;                  // ohne Hotcues (11.11.2026)
      if (fstems && !r.stems) return false;
      if (fnocv && (r.cv !== 0 || !SM.canCover(r.path))) return false;
      if (fadd && (!r.added || r.added < addFrom || r.added >= addTo)) return false;   // hinzugefuegt (11.11.2026)   // WAV & Co. koennen kein Cover tragen                // ohne Cover (Wunsch 07.11.2026), noch nicht gepruefte nicht
      if (fsrc && !r.src) return false;
      if (ffav && SM.favOf('song', r.path) < +ffav) return false;
      if (frat && (r.rating || 0) < frat) return false;     // Sterne aus Mixxx (14.11.2026)   // Favoriten (14.11.2026): 2 = eigenes Herz, 1 = auch halbe
      if (dupOn && r._g < 0) return false;
      if (sameOn && !sameTA(r)) return false;
      if (longOn && !((r.dur || 0) > 600)) return false;                 // lange Dateien (Mitschnitte, Mixe) ueber 10 Minuten
      if (nomp3On && twin(r)) return false;   // keine MP3 und dasselbe Lied auch nicht als MP3 da (zum Umwandeln, Wunsch 08.11.2026)
      if (r._gone) return false;
      return true;
    });
    sortView();
    draw(true, keep === true);
    if (typeof drawSameAi === 'function') drawSameAi();
  }

  function sortView() {
    const k = sortK, dir = sortUp ? 1 : -1;
    const str = k === 'artist' || k === 'name' || k === 'genre' || k === 'album' || k === 'grp' || k === 'file' || k === 'show' || k === 'dir' || k === 'ext';
    view.sort((a, b) => {
      if (dupOn && a._g !== b._g) return a._g - b._g;      // Doppelte: Gruppe fuer Gruppe
      let x = a[k], y = b[k];
      if (str) { x = norm(x); y = norm(y); if (!x && y) return 1; if (x && !y) return -1; return dir * x.localeCompare(y) || norm(a.artist).localeCompare(norm(b.artist)) || norm(a.name).localeCompare(norm(b.name)); }
      if (k === 'track') { x = parseInt(x, 10); y = parseInt(y, 10); }   // "4/9" -> 4
      if (k === 'fav') { x = SM.favOf('song', a.path); y = SM.favOf('song', b.path); }
      x = +x || 0; y = +y || 0;
      if (x === y) return norm(a.artist).localeCompare(norm(b.artist)) || norm(a.name).localeCompare(norm(b.name));
      if (!x) return 1; if (!y) return -1;    // ohne Wert immer unten
      return dir * (x - y);
    });
  }

  // ---- Tabelle ----------------------------------------------------------------------------------------------------
  // Spalten: k = Kennung (auch Sortierschluessel, ausser play), th = Kopf, cls = Klassen fuer Kopf und Zelle
  // (wide/wide2: am schmalen Bildschirm ausgeblendet), td = Inhalt der Zelle. Reihenfolge und Sichtbarkeit waehlt
  // jeder Browser selbst (Knopf Spalten, gemerkt in localStorage).
  const fileWord = r => (r.ext ? String(r.ext).toUpperCase() + '-Datei' : 'Datei');   // Mistkuebel: MP3-Datei, MP4-Datei, WAV-Datei ...
  const yes = (on, t) => on ? '<span class="ok"' + (t ? ' title="' + t + '"' : '') + '>✓</span>' : '<span class="no">·</span>';
  const TINY_S = 30;                      // kurze Stuecke (Samples, Jingles): BPM und Tonart leer, kein ? (Wunsch 09.11.2026)
  const tiny = r => (r.dur || 0) > 0 && r.dur < TINY_S;
  const SHOW_MIN_S = 120;                 // + Show erst ab 2 Minuten (Wunsch 09.11.2026)
  const COLS = [
    { k: 'play', th: '▶', cls: 'act', title: 'Vorhören: die Datei kommt direkt vom Musik-Rechner (Mixxx-Brücke). 🗑 legt die Datei in den Papierkorb des Musik-Rechners. → MP3 wandelt MP4, WAV … am Musik-Rechner in eine MP3 um', name: 'Vorhören ▶, Löschen 🗑, → MP3, Tag', nosort: true, td: r => {
      const canPlay = music && r.path;
      return '<button class="pb" data-i="' + r._i + '"' + (canPlay ? '' : ' disabled title="Vorhören geht nur, solange die Mixxx-Brücke am Musik-Rechner läuft"') + '>▶</button>' +
        (r.path ? '<button class="pb nx" data-nx="' + r._i + '" title="Als Nächstes spielen (kommt im Auto-DJ als nächstes Lied in die Playlist)" aria-label="Als Nächstes spielen"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="1.4" fill="currentColor" opacity=".5"/><path d="M6.3 4.9v6.2L11.2 8z" fill="currentColor"/></svg></button>' : '') +
        '<button class="pb del" data-del="' + r._i + '"' + (canPlay ? ' title="' + fileWord(r) + ' am Musik-Rechner in den Papierkorb legen (sofort, im Finder zurücklegbar)"' : ' disabled title="Löschen geht nur, solange die Mixxx-Brücke am Musik-Rechner läuft"') + ' aria-label="Löschen">🗑</button>' +
        (CONV_EXT.includes(String(r.ext || '').toLowerCase()) && (r._cv || !hasMp3(r)) ? '<span class="cvw" data-cvw="' + r._i + '">' + convButton(r, canPlay) + '</span>' : '') +
        (String(r.ext || '').toLowerCase() === 'mp3' ? '<button class="pb tag" data-tag="' + r._i + '"' + (canPlay ? ' title="Tag bearbeiten: alle Felder der MP3 lesen und ändern, Cover und Vorschläge aus dem Internet"' : ' disabled title="Tags gehen nur, solange die Mixxx-Brücke am Musik-Rechner läuft"') + '>Tag</button>' : '');
    } },
    { k: 'fav', th: '♥', cls: 'c', name: 'Favorit (Herz)', title: 'Favorit: Herz antippen. Voll = Favorit, halb = Lied eines Lieblings-Albums oder -Interpreten. Alle auf der Seite Favoriten', td: r => r.path ? SM.favHtml('song', r.path) : '' },
    { k: 'cover', th: '', cls: 'cv', title: 'Cover aus der Datei (oder cover.jpg im Ordner), einmal vom Musik-Rechner geholt und am Light-Butler gemerkt', name: 'Cover', nosort: true, td: r =>
      r.path ? '<img class="cvimg" loading="lazy" alt="" src="/api/sm/cover?p=' + encodeURIComponent(r.path) + '&v=' + (r.cvv || 0) + '" onerror="this.style.visibility=&quot;hidden&quot;">' : '' },   // Platz bleibt: alle Zeilen gleich hoch
    { k: 'name', th: 'Titel', cls: 'artist', td: r => esc(r.name) + (dupOn && r._g >= 0 ? '<span class="dup" title="' + esc(r._why) + '">' + r._gn + '×</span>' : ''), tip: r => r.name },
    { k: 'artist', th: 'Interpret', td: r => r.artist ? '<a class="artl" href="/musik/interpreten?n=' + encodeURIComponent(r.artist) + '" title="Interpret mit Bild und allen Liedern">' + esc(r.artist) + '</a>' : '', tip: r => r.artist },
    { k: 'bpm', th: 'BPM', cls: 'num', td: r => tiny(r) ? '' : r.best === 2 ? '<span class="dim" title="BPM nicht bestimmbar">?</span>' : r.bpm ? Math.round(r.bpm) + (r.best === 1 ? '<span title="geschätzt (nicht aus Mixxx)">~</span>' : '') : '' },
    { k: 'kid', th: 'Tonart', cls: 'c', td: r => { if (tiny(r)) return ''; if (r.kest === 2) return '<span class="dim">?</span>'; const cam = camelot(r); return esc(keyName(r)) + (cam ? ' <span class="dim">' + cam + '</span>' : '') + (r.kest ? '~' : ''); }, tip: r => tiny(r) ? 'Kurzes Stück unter 30 Sekunden: keine Tonart' : r.kest === 2 ? 'Tonart nicht eindeutig bestimmbar (Geräusch, DJ-Set oder unsicher)' : (camelot(r) ? camelot(r) + ' (Camelot)' : '') + (r.kest ? ', geschätzt (nicht aus Mixxx)' : '') },
    { k: 'lvl', th: 'Energie', cls: 'c', td: r => { const lvl = Math.min(9, r.lvl || 0); return '<span class="chip e' + lvl + '"' + (r.est && lvl ? ' title="geschätzt (nicht aus dem Tag)"' : '') + '>' + (lvl || '–') + (r.est && lvl ? '~' : '') + '</span>'; } },
    // Spalte "E geschätzt" (Vergleich mit der Stufe im Tag) ausgeblendet, Wunsch 09.11.2026
    { k: 'track', th: 'Track', cls: 'num wide', title: 'Tracknummer auf der CD (Tag der Datei, sonst aus Mixxx)', name: 'Track', td: r => esc(r.track || '') },
    { k: 'album', th: 'Album', cls: 'genre wide', title: 'Album (Tag der Datei, sonst aus Mixxx)', name: 'Album', td: r => r.album ? '<a class="artl" href="/musik/alben?p=' + encodeURIComponent(r.path || '') + '" title="Album mit Cover und allen Liedern">' + esc(r.album) + '</a>' : '' },
    { k: 'genre', th: 'Genre', cls: 'genre wide', td: r => esc(r.genre) },
    { k: 'grp', th: 'Gruppe', cls: 'genre wide', title: 'Gruppe aus dem Tag (TIT1, in Mixxx „Gruppierung“), zum Beispiel Après-Ski', name: 'Gruppe', td: r => esc(r.grp || '') },
    { k: 'year', th: 'Jahr', cls: 'num wide', title: 'Erscheinungsjahr (aus Mixxx)', name: 'Jahr', td: r => r.year || '' },
    { k: 'added', th: 'Hinzugefügt', cls: 'num wide', title: 'Wann das Lied dazukam: Importdatum der Import-Seite, sonst wann Mixxx es aufgenommen hat, sonst wann die Datei auf den Stick kam', name: 'Hinzugefügt',
      td: r => r.added ? new Date(r.added * 1000).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '' },
    { k: 'plays', mx: 1, th: 'Gespielt', cls: 'num wide', name: 'Gespielt', title: 'Wie oft das Lied in Mixxx gespielt wurde (Mixxx zählt selbst; Vorhören und Auto-DJ im Browser zählen nicht)', td: r => r.plays || '' },
    { k: 'rating', th: '★', cls: 'c wide', name: 'Sterne (Mixxx)', title: 'Sterne 0 bis 5 wie in Mixxx: antippen setzt sie hier, beim nächsten Start der Mixxx-App kommen sie in Mixxx. 5 Sterne zählen als Favorit',
      td: r => r.path ? SM.starsHtml(r.path, r.rating) : '' },   // antippen setzt Sterne (14.11.2026)
    { k: 'lastp', mx: 1, th: 'Zuletzt gespielt', cls: 'num wide', name: 'Zuletzt gespielt', title: 'Wann das Lied zuletzt in Mixxx lief', td: r => r.lastp ? new Date(r.lastp * 1000).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '' },
    { k: 'lufs', th: 'LUFS', cls: 'num wide', name: 'Lautheit (LUFS)', title: 'Wie laut das Lied wirkt (EBU R128, am Musik-Rechner gemessen): -6 sehr laut, -14 wie Spotify, -20 leise. ʳ = ReplayGain steht schon in der Datei (ᴸ = vom Light-Butler)',
      td: r => r.lufs ? r.lufs.toFixed(1) + (r.rgt === 1 ? '<span class="dim" title="ReplayGain steht schon in der Datei (von einem anderen Programm)">ʳ</span>' : r.rgt === 2 ? '<span class="dim" title="ReplayGain vom Light-Butler geschrieben">ᴸ</span>' : '') : '' },
    { k: 'tp', th: 'Spitze', cls: 'num wide', name: 'Spitze (dBTP)', title: 'Höchster Ausschlag in dB (echte Spitze). Über 0: die Datei übersteuert', td: r => r.lufs ? (r.tp > 0 ? '<b style="color:#e8a33d" title="übersteuert">' + r.tp.toFixed(1) + '</b>' : r.tp.toFixed(1)) : '' },
    { k: 'dur', th: 'Länge', cls: 'num wide', td: r => mmss(r.dur) },
    { k: 'ext', th: 'Typ', cls: 'c wide', title: 'Art der Datei (Endung): MP3, MP4, WAV ...', name: 'Typ (Dateiendung)', td: r => esc(r.ext) },
    { k: 'kbps', th: 'kb/s', cls: 'num wide', title: 'Bitrate der Datei in kbit/s (aus Mixxx; leer: die Brücke am Musik-Rechner schickt sie noch nicht)', name: 'Bitrate (kb/s)', td: r => r.kbps || '' },
    { k: 'lyr', th: 'Text', cls: 'c', title: 'Liedtext: ✓ mit Zeiten, ~ nur Text, – nichts gefunden, leer: noch nie gesucht', name: 'Liedtext', td: r =>
      r.lyr === 2 ? '<span class="ok" title="Liedtext mit Zeiten">✓</span>' : r.lyr === 1 ? '<span class="so" title="gesucht, nur Text oder nichts gefunden">~</span>' : '<span class="no" title="noch nie gesucht">·</span>' },
    { k: 'show', th: 'Show', cls: 'c', td: r => {
      if (r._q) return '<span class="qst ' + r._q.cls + '" title="' + esc(r._q.tip || '') + '">' + esc(r._q.text) + '</span>' +
        (r._q.cls === 'err' ? ' <button class="mk quick" data-quick="' + r._i + '" title="' + esc(r._q.tip || '') + '">⚡ nochmal</button>' : '');
      const shs = r.shows && r.shows.length ? r.shows : (r.show ? [r.show] : []);
      const sh = shs.length ? '<a class="shlink" href="/shows/edit?show=' + encodeURIComponent(shs[0]) + '" title="' + esc(shs.join('\n')) + '">✓' + (shs.length > 1 ? ' ' + shs.length : '') + '</a>' : '<span class="no">·</span>';
      // Wunsch 09.11.2026: kurze Dateien (Samples, Jingles unter SHOW_MIN_S) ohne + Show und Quick
      const mk = !r.show && music && r.path && !((r.dur || 0) > 0 && r.dur < SHOW_MIN_S) ? '<button class="mk" data-mk="' + r._i + '" title="Neue Show zu diesem Lied anlegen: die MP3 kommt vom Musik-Rechner auf den Light-Butler, dann öffnet sich der Editor">+ Show</button>' +
        (r.stems && /\.mp3$/i.test(r.path) ? '<button class="mk quick" data-quick="' + r._i + '" title="Quick: Show anlegen und gleich vom Assistenten füllen lassen (Standardwerte, offline nach festen Regeln, ohne Claude). Geht, weil die Spur-Kurven schon da sind.">⚡ Quick</button>' : '') : '';
      return r.show ? sh : mk || sh;
    } },
    { k: 'stems', th: 'Kurven', cls: 'c wide2', title: 'Pegelkurven (Bass, Stimme, Schlagzeug ...) zur MP3 einer Show am Light-Butler, gerechnet am Musik-Rechner mit stems_show.py', td: r => yes(r.stems, 'Pegelkurven am Light-Butler') },
    { k: 'ana', th: 'Analyse', cls: 'c wide2', title: 'Analyse am Musik-Rechner (Aufbau, Drops) fertig; ✗ = die Datei ist nicht lesbar', td: r => r.bad ? '<span style="color:#ff6b6b;font-weight:700" title="Die Analyse am Musik-Rechner konnte diese Datei nicht lesen">✗</span>' : yes(r.ana) },
    { k: 'cues', mx: 1, th: 'Cues', cls: 'num wide2', title: 'Hotcues in Mixxx', name: 'Hotcues', td: r => r.cues || '' },
    { k: 'dir', th: 'Ordner', cls: 'file wide', title: 'Ordner am Musik-Rechner, ohne den Musikordner (aus den Einstellungen, sonst der häufigste Anfang); Lieder außerhalb zeigen den ganzen Pfad', td: r => esc(r.dir), tip: r => r.path },
    { k: 'file', th: 'Datei', cls: 'file wide', td: r => esc(r.file), tip: r => r.file },
    { k: 'src', mx: 1, th: 'Quelle', cls: 'c', title: 'Woher das Lied kommt: Mixxx-Bibliothek oder 📁 nur im Musikordner (die Brücke liest ihn ein, Einstellungen → Verbindungen)', td: r =>
      r.src ? '<span title="Nur im Musikordner, nicht in der Mixxx-Bibliothek">📁 Ordner</span>' : '<span class="dim">Mixxx</span>' },
  ];
  const BYK = Object.fromEntries(COLS.map(c => [c.k, c]));
  const COLS_KEY = 'musikspalten';
  let order = COLS.map(c => c.k), hidden = new Set();
  function loadCols() {
    try {
      const c = JSON.parse(localStorage.getItem(COLS_KEY) || 'null');
      if (c && Array.isArray(c.order)) {
        const known = c.order.filter(k => BYK[k]);
        order = known.slice();                                       // neue Spalten hinter ihrer Vorgaengerin dazu, sichtbar
        COLS.forEach((x, i) => { if (!order.includes(x.k)) { const at = i ? order.indexOf(COLS[i - 1].k) : -1; order.splice(at + 1, 0, x.k); } });
        hidden = new Set((c.hidden || []).filter(k => BYK[k]));
      }
    } catch (e) { /* privates Fenster: Standard */ }
  }
  function saveCols() { try { localStorage.setItem(COLS_KEY, JSON.stringify({ order, hidden: [...hidden] })); } catch (e) { /* privates Fenster */ } }
  const mxOff = k => SM.MXOFF && BYK[k] && BYK[k].mx;           // ohne Mixxx: Spalten nur aus Mixxx weg (14.11.2026)
  const shownCols = () => order.filter(k => !hidden.has(k) && !mxOff(k)).map(k => BYK[k]);
  // Breite der Spalten: am rechten Rand des Kopfes ziehen (Maus oder Finger), Doppelklick = Standard; je Browser gemerkt.
  // Die Spalte Ordner ist von Haus aus doppelt so breit (Wunsch von Markus: sonst abgeschnitten).
  const WIDTH_KEY = 'musikbreiten', WIDTH_DEF = { dir: 520 };
  let widths = {};
  try { widths = JSON.parse(localStorage.getItem(WIDTH_KEY) || '{}') || {}; } catch (e) { widths = {}; }
  function applyWidths() {
    let css = '';
    const w = Object.assign({}, WIDTH_DEF, widths);
    for (const k in w) if (BYK[k] && w[k] > 0) css += '#tbl th.k-' + k + ',#tbl td.k-' + k + '{width:' + w[k] + 'px;min-width:' + w[k] + 'px;max-width:' + w[k] + 'px}';
    let st = $('colwidths');
    if (!st) { st = document.createElement('style'); st.id = 'colwidths'; document.head.appendChild(st); }
    st.textContent = css;
  }
  function saveWidths() { try { localStorage.setItem(WIDTH_KEY, JSON.stringify(widths)); } catch (e) { /* privates Fenster */ } }
  function wireGrips() {
    for (const g of document.querySelectorAll('#tbl th .grip')) {
      const k = g.dataset.g;
      g.onclick = e => e.stopPropagation();                      // kein Sortieren beim Ziehen
      g.ondblclick = e => { e.stopPropagation(); delete widths[k]; saveWidths(); applyWidths(); };
      g.onpointerdown = e => {
        e.preventDefault(); e.stopPropagation();
        const th = g.parentElement, x0 = e.clientX, w0 = th.getBoundingClientRect().width;
        g.setPointerCapture(e.pointerId);
        g.onpointermove = ev => { widths[k] = Math.max(40, Math.min(1200, Math.round(w0 + ev.clientX - x0))); applyWidths(); };
        g.onpointerup = () => { g.onpointermove = null; g.onpointerup = null; saveWidths(); };
      };
    }
  }
  function buildHead() {
    $('headrow').innerHTML = shownCols().map(c => '<th' + (c.k === 'play' ? ' id="thplay"' : ' data-k="' + c.k + '"') + ' class="k-' + c.k + (c.cls ? ' ' + c.cls : '') + '"' +
      (c.title ? ' title="' + esc(c.title) + '"' : '') + '>' + esc(c.th) + '<span class="grip" data-g="' + c.k + '" title="Breite ziehen, Doppelklick = Standard"></span></th>').join('');
    applyWidths(); wireGrips();
    if ($('thplay')) $('thplay').style.opacity = music ? 1 : 0.35;
    for (const th of document.querySelectorAll('#tbl th')) if (th.dataset.k && !BYK[th.dataset.k].nosort) th.onclick = () => {
      if (sortK === th.dataset.k) sortUp = !sortUp;
      else { sortK = th.dataset.k; sortUp = !(sortK === 'year' || sortK === 'lvl' || sortK === 'elv' || sortK === 'lyr' || sortK === 'show' || sortK === 'ana' || sortK === 'cues' || sortK === 'kbps' || sortK === 'lufs' || sortK === 'tp' || sortK === 'plays' || sortK === 'lastp' || sortK === 'fav' || sortK === 'rating'); }
      sortView(); draw(true);
    };
  }
  function row(r) {
    return '<tr data-i="' + r._i + '"' + (dupOn && r._g >= 0 ? ' class="g' + (r._g % 2) + '"' : '') + '>' + shownCols().map(c => {
      const tip = c.tip ? c.tip(r) : '';
      return '<td class="k-' + c.k + (c.cls ? ' ' + c.cls : '') + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + c.td(r) + '</td>';
    }).join('') + '</tr>';
  }

  // Fenster Spalten: ein- und ausblenden, mit den Pfeilen verschieben
  function drawColBox() {
    $('collist').innerHTML = order.map((k, i) => { const c = BYK[k];
      return '<div class="colrow' + (c.mx ? ' mx' : '') + '"><label><input type="checkbox" data-ck="' + k + '"' + (hidden.has(k) ? '' : ' checked') + '> ' + esc(c.name || c.th) + '</label>' +
        '<button data-up="' + i + '" title="nach links"' + (i ? '' : ' disabled') + '>↑</button><button data-dn="' + i + '" title="nach rechts"' + (i < order.length - 1 ? '' : ' disabled') + '>↓</button></div>'; }).join('');
  }
  function colsChanged() { saveCols(); buildHead(); drawColBox(); draw(true, true); }
  $('collist').addEventListener('change', e => {
    const k = e.target.dataset.ck; if (!k) return;
    if (e.target.checked) hidden.delete(k); else hidden.add(k);
    if (hidden.size >= order.length) { hidden.delete(k); e.target.checked = true; return; }   // mindestens eine Spalte bleibt
    colsChanged();
  });
  $('collist').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const i = +(b.dataset.up != null ? b.dataset.up : b.dataset.dn), j = b.dataset.up != null ? i - 1 : i + 1;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    colsChanged();
  });
  $('bcols').onclick = () => { const on = $('colbox').hidden; $('colbox').hidden = !on; $('bcols').classList.toggle('on', on); if (on) drawColBox(); };
  $('colreset').onclick = () => { order = COLS.map(c => c.k); hidden = new Set(); widths = {}; try { localStorage.removeItem(COLS_KEY); localStorage.removeItem(WIDTH_KEY); } catch (e) { /* privat */ } colsChanged(); };
  $('colclose').onclick = () => { $('colbox').hidden = true; $('bcols').classList.remove('on'); };

  // ---- Gruppen: Kopfzeile je Interpret/Genre/Energie, darunter die Lieder, wenn aufgeklappt -------------------------
  const isOpen = g => openG.has(g.key) || (groups.length <= GAUTO && !shutG.has(g.key));
  function buildItems() {
    if (gmode === 'list') { items = null; groups = []; return; }
    groups = MG.group(view, gmode);
    items = [];
    for (const g of groups) {
      const op = isOpen(g);
      items.push({ g, op });
      if (!op) continue;
      const lim = glim[g.key] || GLIM;
      for (const r of g.songs.slice(0, lim)) items.push(r);
      if (g.n > lim) items.push({ more: g, rest: g.n - lim });
    }
  }
  function groupRow(x) {
    const g = x.g, span = shownCols().length;
    const extra = gmode === 'art' ? (g.top ? '<span class="gsub">' + esc(g.top) + '</span>' : '')
      : gmode === 'kl' ? (g.kind ? '<span class="gkind' + (g.kind === 'Liste' ? ' gl' : '') + '">' + g.kind + '</span>' : '')
      : gmode === 'gen' || gmode === 'grp' ? (g.top ? '<span class="gsub">' + g.top + ' Interpret' + (g.top > 1 ? 'en' : '') + '</span>' : '')
      : gmode === 'alb' ? (g.top ? '<span class="gsub">' + (typeof g.top === 'string' ? esc(g.top) : g.top + ' Interpreten') + '</span>' : '')
      : '<span class="chip e' + g.key + '">' + (+g.key || '?') + '</span>';
    return '<tr class="grp' + (x.op ? ' open' : '') + '" data-gk="' + esc(g.key) + '" data-l="' + g.letter + '"><td colspan="' + span + '">' +
      '<span class="gch">' + (x.op ? '▾' : '▸') + '</span>' + (gmode === 'lvl' || gmode === 'kl' ? extra + ' ' : '') + '<b>' + esc(g.name) + '</b>' + (gmode === 'lvl' || gmode === 'kl' ? '' : extra) +
      '<span class="gn">' + g.n + ' Lied' + (g.n > 1 ? 'er' : '') + ' · ' + MG.hm(g.dur) + '</span>' +
      '<button class="gexp" data-gexp="' + esc(g.key) + '" title="Nur die Lieder dieser Gruppe exportieren (die Filter oben gelten weiter)">⤓ Export</button>' +
      '<button class="gexp" data-gfade="' + esc(g.key) + '" title="Fade-in/-out für die MP3s dieser Gruppe (der Musik-Rechner bearbeitet sie der Reihe nach)">〰 Fade</button></td></tr>';
  }
  const item = x => x.g ? groupRow(x) : x.more ? '<tr class="gmore"><td colspan="' + shownCols().length + '"><button class="gbtn" data-gmore="' + esc(x.more.key) + '">… ' + x.rest + ' weitere von ' + esc(x.more.name) + ' zeigen</button></td></tr>' : row(x);
  function toggleGroup(k) {
    const g = groups.find(x => x.key === k); if (!g) return;
    if (isOpen(g)) { openG.delete(k); shutG.add(k); } else { openG.add(k); shutG.delete(k); }
    draw(true, true);
  }
  function setMode(m) {
    gmode = m; openG.clear(); shutG.clear(); glim = {};
    try { localStorage.setItem('musikgruppe', m); } catch (e) { /* privates Fenster */ }
    for (const b of $('gview').children) b.classList.toggle('on', b.dataset.gv === m);
    draw(true);
  }
  function drawAz() {
    const az = $('az');
    az.hidden = gmode !== 'art' && gmode !== 'alb';
    const gb = $('gall');
    gb.hidden = gmode === 'list';
    if (gmode === 'list') return;
    gb.textContent = groups.length && groups.every(isOpen) ? 'Alle zuklappen' : 'Alle aufklappen';
    if (gmode !== 'art' && gmode !== 'alb') return;
    const have = new Set(groups.map(g => g.letter));
    az.innerHTML = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ#'.split('').map(c => '<button data-az="' + c + '"' + (have.has(c) ? '' : ' disabled') + '>' + c + '</button>').join('');
  }

  function draw(reset, keep) {
    const tb = $('rows');
    const want = reset && keep ? Math.max(STEP, shown) : STEP;      // keep: nach dem Nachladen so viele Zeilen wie vorher
    if (reset) { tb.innerHTML = ''; shown = 0; buildItems(); drawAz(); }
    const list = items || view;
    const end = Math.min(list.length, reset ? want : shown + STEP);
    let html = '';
    for (let i = shown; i < end; i++) html += item(list[i]);
    tb.insertAdjacentHTML('beforeend', html);
    shown = end;
    $('more').textContent = shown < list.length ? (list.length - shown) + ' weitere ' + (items ? 'Zeilen' : '') + ' ... (scrollen)' : view.length ? '' : 'Nichts gefunden.';
    const sq = $('q').value.trim();                     // nichts gefunden: dieselbe Suche auf Spotify (Wunsch 14.11.2026)
    if (!view.length && sq) $('more').insertAdjacentHTML('beforeend', '<div class="spotq">' + SM.spotifyLink(sq, 'Auf Spotify suchen: „' + sq + '“') + SM.missBtn({ q: sq }) + '</div>');
    const n = all.length, nl = all.filter(r => r.lyr === 2).length, ns = all.filter(r => r.show).length, na = all.filter(r => r.ana).length;
    $('sum').innerHTML = '<b>' + view.length + '</b> von <b>' + n + '</b> Liedern' + (n ? ' · Liedtext <b>' + nl + '</b> · Show <b>' + ns + '</b> · analysiert <b>' + na + '</b>' : '')
      + (sameOn ? ' · nur Titel = Interpret' : '') + (longOn ? ' · nur über 10 min' : '') + (nomp3On ? ' · nur nicht MP3' : '') + (dupOn ? ' · <b>' + new Set(view.map(r => r._g)).size + '</b> Gruppen doppelt' : '') + (items ? ' · <b>' + groups.length + '</b> ' + (groups.length === 1 ? { art: 'Interpret', alb: 'Album', gen: 'Genre', grp: 'Gruppe', lvl: 'Energiestufe', kl: 'Kiste/Liste' } : { art: 'Interpreten', alb: 'Alben', gen: 'Genres', grp: 'Gruppen', lvl: 'Energiestufen', kl: 'Kisten/Listen' })[gmode] : '') + (prefix ? ' · Ordner ab <span class="dim">' + esc(prefix) + '</span>' : '');
    for (const th of document.querySelectorAll('#tbl th')) { th.classList.toggle('on', th.dataset.k === sortK); th.classList.toggle('up', th.dataset.k === sortK && sortUp); }
    if (cur) markRows();
  }

  function onScroll() {
    if (shown >= (items || view).length) return;
    const m = $('more').getBoundingClientRect();
    if (m.top < window.innerHeight + 400) draw(false);
  }

  // ---- Passt Mixxx noch zum Stick? (Wunsch von Markus 07.11.2026) -------------------------------------------------
  // Der Mac vergleicht Datei fuer Datei: Lieder in Mixxx, deren Datei fehlt, und MP3s im Musikordner, die Mixxx nicht kennt.
  let syncT = 0;
  async function loadSync() {
    if (SM.MXOFF) { $('syncbox').hidden = true; return; }   // ohne Mixxx: kein Abgleich Mixxx/Stick
    if (Date.now() - syncT < 55000) return;                  // der Mac rechnet hoechstens einmal pro Minute neu
    syncT = Date.now();
    try {
      const d = await fetch(music + '/sync').then(r => r.json());
      let ren = null;                      // umbenannte Dateien, die noch auf Mixxx warten (Fehlerbericht 08.11.2026)
      try { ren = await fetch(music + '/check').then(r => r.json()); } catch (e) { ren = null; }
      const pend = ren && ren.pending ? ren.pending : 0;
      const b = $('syncbox');
      const kn = d.known ? '<span class="synckn">' + d.known + ' Lied' + (d.known > 1 ? 'er führt' : ' führt') + ' Mixxx noch als fehlend. Endgültig weg sind sie, wenn du sie in Mixxx entfernst: in der Seitenleiste links (nicht im Menü oben) ganz oben bei „Titel“ (Tracks) auf den Pfeil ▸ klicken, dann „Fehlende Titel“ (Missing Tracks) → „Alle auswählen“ → „Bereinigen“ (Purge). Für das Licht ist das egal.</span>' : '';
      if (!b || d.off || (!d.gone && !d.new && !kn)) { if (b) b.hidden = true; return; }
      b.classList.toggle('soft', !d.gone && !d.new);
      if (!d.gone && !d.new) { b.innerHTML = '<b>Mixxx passt zum Stick.</b> ' + kn; b.hidden = false; return; }
      const list = (title, arr, n) => arr.length ? '<details><summary>' + title + ' (' + n + ')</summary><div class="synclist">' +
        arr.map(p => esc(p)).join('<br>') + (n > arr.length ? '<br>… und ' + (n - arr.length) + ' weitere' : '') + '</div></details>' : '';
      b.innerHTML = '<b>Mixxx ist nicht mehr aktuell.</b> ' +
        (d.gone ? d.gone + ' Lied' + (d.gone > 1 ? 'er' : '') + ' in Mixxx gibt es auf dem Stick nicht mehr' : '') + (d.gone && d.new ? ', ' : '') +
        (d.new ? d.new + ' Datei' + (d.new > 1 ? 'en' : '') + ' auf dem Stick kennt Mixxx noch nicht' : '') +
        (pend ? '. <b>' + pend + ' davon hast du umbenannt:</b> sie kommen beim nächsten Start der App „Light-Butler Mixxx“ mit Hotcues und Kisten in Mixxx. <b>Bis dahin in Mixxx NICHT „Bibliothek neu einlesen“</b>, sonst gehen Hotcues und Kisten dieser Lieder verloren.' +
          (ren.blocked ? ' Beim letzten Start ließ sich die Mixxx-Datenbank nicht ändern, beim nächsten Start versucht es die App wieder.' : '')
        : '. In Mixxx die Bibliothek neu einlesen (Bibliothek → Bibliothek neu einlesen), fehlende Titel danach dort entfernen.' +
        (!d.live ? ' Danach Mixxx schließen und über die App „Light-Butler Mixxx“ wieder öffnen.' : ' Danach verschwindet der Hinweis innerhalb einer Minute von selbst.')) + (kn ? '<br>' + kn : '') +
        list('In Mixxx, aber nicht auf dem Stick', d.gone_list || [], d.gone) + list('Auf dem Stick, aber nicht in Mixxx', d.new_list || [], d.new);
      b.hidden = false;
    } catch (e) { /* aeltere Bruecke ohne /sync: kein Hinweis */ }
  }

  // Fortschrittsbalken, solange der Mac die Bibliothek schickt (Wunsch 07.11.2026: man wusste nie, wann sie ganz da ist).
  // Restzeit aus dem Tempo seit dem ersten Blick auf diesen Durchgang.
  let progStart = null;
  function progText(have, n, t0, now) {
    const pct = Math.floor(100 * have / n);
    let rest = '';
    if (t0 && have > t0.have && now > t0.t) {
      const s = (n - have) * (now - t0.t) / (have - t0.have) / 1000;
      rest = s < 60 ? ', noch unter einer Minute' : ', noch etwa ' + Math.round(s / 60) + ' min';
    }
    return have + ' von ' + n + ' Teilen (' + pct + ' %' + rest + ')';
  }
  // Was der Mac gerade tut (Wunsch 07.11.2026: "alles so intransparent"): Tags lesen und Liste an den Pi schicken
  const mins = s => s < 60 ? 'unter einer Minute' : Math.round(s / 60) + ' min';
  const mini = (a, b) => '<span class="mini"><i style="width:' + (b ? Math.min(100, 100 * a / b) : 0) + '%"></i></span>';
  function bgText(st) {
    const out = [];
    const t = st.tags;
    if (t) out.push(t.busy ? (t.total ? '<span class="bsy">Musik-Rechner liest die Tags der MP3s:</span>' + mini(t.done, t.total) + t.done + ' von ' + t.total + ' Dateien'
      : '<span class="bsy">Musik-Rechner sucht die MP3s auf dem Stick …</span>')
      : t.ago >= 0 ? 'Musik-Rechner: Tags aus ' + t.files + ' MP3s gelesen vor ' + mins(t.ago) + ', nächster Durchgang in ' + mins(t.next) : 'Musik-Rechner: Tags der MP3s noch nicht gelesen');
    const s = st.send;
    const what = s && s.kind === 'geaenderte' ? ' (nur Geänderte)' : s && s.kind === 'fehlende' ? ' (nur verlorene)' : '';
    if (s && s.n) out.push(s.busy ? '<span class="bsy">Musik-Rechner schickt die Liste an den Light-Butler' + what + ':</span>' + mini(s.sent, s.n) + 'Teil ' + s.sent + ' von ' + s.n
      : s.same ? 'Musik-Rechner: Der Light-Butler hat die aktuelle Liste, nichts zu schicken (nächste Prüfung in ' + mins(s.next) + ')' + (s.kind ? ' · zuletzt ' + s.n + ' Teile' + what : '')
      : 'Musik-Rechner: zuletzt geschickt ' + s.n + ' Teile' + what + ', nächste Prüfung in ' + mins(s.next));
    return out.join('<br>');
  }
  async function pollStatus() {
    if (!music || document.hidden) return;
    try {
      const st = await fetch(music + '/status').then(r => r.json());
      if (st.off || st.error) return;                // Anzeige steht jetzt in der Datenpflege (Stand der Liedliste)
    } catch (e) { /* Bruecke aus oder aelter: nichts zeigen */ }
    pollChanged();
  }
  // ---- Geaenderte Tags -> Mixxx (Wunsch 08.11.2026): nur die vom Light-Butler geaenderten MP3s neu einlesen lassen ----
  let chgT = 0;
  async function pollChanged() {
    if (Date.now() - chgT < 30000) return;
    chgT = Date.now();
    try {
      const r = await fetch(music + '/changed');
      const d = r.ok ? JSON.parse(await r.text()) : null;
      $('bchg').disabled = !d;                               // ausgrauen statt verstecken: die Knoepfe bleiben an ihrem Platz (14.11.2026)
      $('bchg0').disabled = !d || !d.n;
      $('bchg').textContent = 'Geänderte → Mixxx (' + (d ? d.n || 0 : '–') + ')';
    } catch (e) { $('bchg').disabled = $('bchg0').disabled = true; }   // Musik-Rechner nicht erreichbar
  }
  $('bchg0').onclick = async () => {
    if (!await SM.ask('Zähler „Geänderte → Mixxx“ auf 0 setzen?\n\nWas bis jetzt geändert wurde, zählt dann nicht mehr, auch nicht die früheren Änderungen, die Mixxx noch nicht kennt. Neue Änderungen kommen wieder hinein.', undefined, 'Auf 0 setzen')) return;
    try {
      const r = await fetch(music + '/changed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'reset' }) });
      if (!r.ok) throw new Error('ging nicht (' + r.status + ')');
      chgT = 0; pollChanged(); SM.toast('Zähler auf 0.', 3000);
    } catch (e) { SM.toast('Zurücksetzen: ' + e.message, 5000); }
  };
  $('bchg').onclick = async () => {
    try {
      const r = await fetch(music + '/changed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'm3u' }) });
      const d = JSON.parse(await r.text());
      if (!r.ok) throw new Error(d.error || 'ging nicht');
      const done = await SM.ask(d.n + ' geänderte MP3s als Playlist abgelegt:\n\n' + d.file +
        '\n\nIn Mixxx: links Rechtsklick auf „Wiedergabelisten“ → „Wiedergabeliste importieren“, die Datei wählen. Dann die Playlist öffnen, alle markieren (Cmd+A), Rechtsklick → Metadaten → „Aus Datei importieren“.' +
        '\n\nDrin sind die Änderungen des Light-Butler und alles, was neuer ist als der letzte Abgleich in Mixxx (auch von früher). Bist du in Mixxx fertig, leere ich die Liste. Die Playlist in Mixxx kannst du dann löschen.', undefined, 'Fertig, Liste leeren');
      if (done) {
        await fetch(music + '/changed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'clear', before: d.t }) });
        SM.toast('Liste geleert.', 3000);
      }
      chgT = 0; pollChanged();
    } catch (e) { SM.toast('Geänderte → Mixxx: ' + e.message, 5000); }
  };
  setInterval(pollStatus, 5000);
  // Safari am iPad friert Seiten im Hintergrund und beim Zurueckblaettern (Seiten-Zwischenspeicher) ein: die Balken blieben
  // stehen (Fehlerbericht 07.11.2026). Beim Wiederanzeigen sofort neu nachfragen.
  const wake = () => { if (document.hidden) return; syncT = 0; load(true); pollStatus(); };   // load zeichnet nur bei Aenderung neu
  document.addEventListener('visibilitychange', wake);
  window.addEventListener('pageshow', e => { if (e.persisted) wake(); });

  // Lamperl (Wunsch 11.11.2026): gruen = die Liste am Pi ist vollstaendig (dem Filter kann man trauen), orange = sie wird
  // gerade vom Mac aufgebaut (Lieder koennen noch fehlen), grau = der Mac ist nicht verbunden (gespeicherte Liste).
  // Alle 10 s nur der Stand (/api/musik/stand, ohne Lieder); hat sich die Liste geaendert, wird sie neu geholt.
  let lampV = null;
  function showLamp(d) {
    const el = $('liblamp'), p = Array.isArray(d.prog) ? d.prog : null;
    if (!el) return;
    let cls, txt, tip;
    if (d.complete) { cls = 'ok'; txt = 'Liste vollständig'; tip = 'Der Light-Butler hat die ganze Liedliste vom Musik-Rechner: Filter und Zahlen stimmen.'; }
    else if (!d.connected) { cls = 'off'; txt = 'Musik-Rechner nicht verbunden'; tip = 'Der Light-Butler zeigt die zuletzt gespeicherte Liste. Neue oder geänderte Lieder fehlen vielleicht, bis der Helfer oder die Mixxx-App am Musik-Rechner läuft.'; }
    else {
      cls = 'build';
      const pct = p && p[1] > 0 ? Math.min(99, Math.floor(100 * p[0] / p[1])) : 0;
      txt = 'Liste im Aufbau' + (pct ? ' ' + pct + ' %' : ' …');
      tip = 'Der Musik-Rechner schickt die Liedliste gerade an den Light-Butler. Bis die Anzeige grün ist, können Lieder fehlen (zum Beispiel beim Filter „heute“).' + (p && p[2] ? ' Ein paar Teile gingen im WLAN verloren, der Musik-Rechner schickt sie gleich nach.' : '');
    }
    el.className = cls; $('liblampt').textContent = txt; el.title = tip;
  }
  async function pollLamp() {
    if (document.hidden) return;
    try {
      const d = await (await fetch('/api/musik/stand')).json();
      showLamp(d);
      if (lampV !== null && d.v !== lampV && d.complete && !timer) load(true);   // Liste fertig oder geaendert: neu holen
    } catch (e) { $('liblamp').className = 'off'; $('liblampt').textContent = 'Light-Butler nicht erreichbar'; }
  }
  setInterval(pollLamp, 10000);

  // Laufender Fade-Auftrag am Mac (Wunsch 11.11.2026): sichtbar, auch wenn das Fenster zu ist
  let fadeWas = false;
  async function pollFade() {
    if (!music || document.hidden) return;
    let s;
    try { s = await (await fetch(music + '/fade')).json(); } catch (e) { return; }
    const el = $('fadechip'), run = s.state === 'run';
    if (run) {
      el.className = ''; el.hidden = false; $('fadestop').disabled = false;
      $('fadechipt').textContent = '〰 Fade läuft: ' + ((s.done || 0) + 1) + ' von ' + s.total + (s.cur ? ' · ' + s.cur : '');
      el.title = 'Der Musik-Rechner rechnet Fade und Schnitt in die MP3s (Fade-in ' + s.fin + ' s, Fade-out ' + s.fout + ' s' + (s.ca ? ', vorne ' + s.ca + ' s weg' : '') + (s.cb ? ', hinten ' + s.cb + ' s weg' : '') + '). Die Originale kommen in den Papierkorb.' + ((s.errors || []).length ? ' Nicht gegangen: ' + s.errors.join('; ') : '');
    } else if (fadeWas && (s.state === 'ok' || s.state === 'stopped')) {
      el.className = 'done'; el.hidden = false; $('fadestop').disabled = true;
      $('fadechipt').textContent = (s.state === 'ok' ? '〰 Fade fertig: ' + (s.ok || 0) + ' von ' + s.total : '〰 Fade angehalten nach ' + (s.done || 0) + ' von ' + s.total) + ((s.errors || []).length ? ', ' + s.errors.length + ' nicht gegangen' : '');
      el.title = (s.errors || []).join('; ');
      setTimeout(() => { if ($('fadechip').className === 'done') $('fadechip').hidden = true; }, 60000);
    } else if (!fadeWas) el.hidden = true;
    fadeWas = run;
  }
  $('fadestop').onclick = async () => {
    if (!await SM.ask('Fade-Auftrag anhalten? Das Lied, an dem der Musik-Rechner gerade rechnet, wird noch fertig.', undefined, 'Anhalten')) return;
    try { await fetch(music + '/fade', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'stop' }) }); } catch (e) { /* Mac weg */ }
    pollFade();
  };
  setInterval(pollFade, 3000);

  function showProg(d) {
    const box = $('libprog');
    const p = Array.isArray(d.prog) ? d.prog : null;
    if (!box) return;
    if (true || d.complete || !d.connected || !p || !(p[1] > 0)) { box.hidden = true; progStart = null; return; }   // in die Datenpflege gewandert (11.11.2026)
    const now = Date.now();
    if (!progStart || p[0] < progStart.have || p[1] !== progStart.n) progStart = { have: p[0], n: p[1], t: now };
    $('lpfill').style.width = Math.min(100, 100 * p[0] / p[1]) + '%';
    $('lptxt').textContent = p[2] ? p[0] + ' von ' + p[1] + ' Teilen, ' + (p[1] - p[0]) + ' gingen im WLAN verloren, der Musik-Rechner schickt sie in ein paar Minuten nach.'
      : progText(p[0], p[1], progStart, now);
    box.hidden = false;
  }

  // ---- Laden -----------------------------------------------------------------------------------------------------
  async function load(again) {
    try {
      const r = await fetch('/api/musik');
      const d = await r.json();
      const gone = SM.goneSet();
      const tracks = (d.tracks || []).filter(t => !gone.has(t.path));   // gerade geloeschte nicht wieder zeigen
      music = d.music || '';
      if ($('thplay')) $('thplay').style.opacity = music ? 1 : 0.35;
      // Stand der Liedliste (Mac liest Tags, schickt die Liste) steht seit 11.11.2026 in der Datenpflege; hier nur, wenn gar nichts da ist
      const hint = !tracks.length ? (d.connected ? 'Die Mixxx-Brücke schickt die Bibliothek gerade, bitte kurz warten ...' : 'Noch keine Bibliothek am Light-Butler: Am Musik-Rechner die Mixxx-Brücke starten (App „Light-Butler Mixxx“), sie schickt die Liste innerhalb von ein paar Minuten.') : '';
      $('hint').textContent = hint;
      showProg(d);
      showLamp(d); lampV = d.v;
      pollFade();
      pollStatus();
      if (music) loadSync();
      // Der Mac schickt die Bibliothek alle 10 Minuten neu: nur neu zeichnen, wenn sich wirklich etwas geaendert hat (sonst springt die Tabelle)
      const st = tracks.length + '|' + JSON.stringify(tracks.map(t => [t.title, t.dur, t.bpm, t.lvl, t.est, t.elv, t.kest, t.kid, t.best, t.cv, t.lyr, t.show, t.stems, t.ana, t.path, t.kbps, t.src, t.year, t.album, t.track, t.grp, t.added, t.lufs, t.rgt, t.plays, t.lastp, t.cvv, (t.crates || []).length, (t.lists || []).length])).length + '|' + music + '|' + (d.root || '');
      if (st !== stamp) {
        stamp = st;
        all = tracks.map((r, i) => ({ ...r, _i: i, _g: -1, _s: norm(r.artist + ' ' + r.name + ' ' + (r.album || '') + ' ' + (r.grp || '') + ' ' + r.file + ' ' + r.genre + ' ' + keyName(r) + ' ' + (r.crates || []).join(' ') + ' ' + (r.lists || []).join(' ')) }));
        prefix = topPrefix(all.map(r => r.path).filter(Boolean), d.root || '');
        for (const r of all) { r.dir = r.path ? dirOf(r.path) : ''; r.ext = extOf(r.path || r.file); r._s += ' ' + norm(r.dir); }
        mp3s = new Set(all.filter(r => r.path && /\.mp3$/i.test(r.path)).map(r => r.path.toLowerCase()));   // fuer → MP3: gibt es die MP3 schon?
        twin = SM.mp3Twin(all);
        findDups();
        buildSelects();
        apply(again);
      }
      // im Aufbau nicht laufend die ganze Liste holen (sonst springt die Zahl, Fehlerbericht 11.11.2026): das Lamperl zeigt den Stand,
      // die Liste kommt neu, sobald sie komplett ist (pollLamp). Nur ganz ohne Lieder alle 5 s nachsehen.
      if (d.connected && !d.complete && !tracks.length && !timer) timer = setTimeout(() => { timer = null; load(true); }, 5000);
    } catch (e) {
      $('hint').textContent = 'Keine Verbindung zum Light-Butler: ' + e.message;
    }
  }

  // ---- Vorhoeren: die MP3 kommt direkt vom Mac, der Pi sieht den Ton nie ------------------------------------------
  const player = $('player');
  SM.missLoad();                                        // Merkliste Fehlt mir (Knopf bei leerer Suche)
  SM.preview(player, { pos: $('pos'), after: $('bpp'), end: $('bcl') });   // ab Hauptteil, ⏮ ⏭, Marken (14.11.2026)
  const src = r => music + '/audio?p=' + encodeURIComponent(r.path);
  function playRow(r) {
    if (!music || !r.path) return;
    if (cur && cur._i === r._i) { if (player.paused) player.play(); else player.pause(); return; }
    cur = r;
    player.src = src(r);
    setVol();
    player.play().catch(e => { $('bst').textContent = 'Abspielen geht nicht: ' + e.message + ' (Brücke am Musik-Rechner? Stick eingesteckt?)'; });
    $('bt').textContent = r.name + (r.artist ? ' · ' + r.artist : '');
    $('bst').textContent = '';
    $('bar').classList.add('on'); document.body.classList.add('bar');
    markRows();
  }
  function markRows() {
    for (const tr of $('rows').children) {
      const on = cur && +tr.dataset.i === cur._i;
      tr.classList.toggle('cur', !!on);
      const b = tr.querySelector('.pb');
      if (b) { b.classList.toggle('on', !!on); b.textContent = on && !player.paused ? '⏸' : '▶'; }
    }
    $('bpp').textContent = player.paused ? '▶' : '⏸';
  }
  function closeBar() {
    player.pause(); player.removeAttribute('src'); player.load(); cur = null;
    $('bar').classList.remove('on'); document.body.classList.remove('bar');
    markRows();
  }
  player.addEventListener('timeupdate', () => {
    const d = player.duration || (cur && cur.dur) || 0;
    $('pos').value = d ? Math.round(1000 * player.currentTime / d) : 0;
    $('tm').textContent = mmss(player.currentTime) + ' / ' + mmss(d);
  });
  player.addEventListener('play', markRows); player.addEventListener('pause', markRows);
  player.addEventListener('ended', markRows);
  player.addEventListener('error', () => { $('bst').textContent = 'Die MP3 kommt nicht vom Musik-Rechner (Brücke läuft? Stick eingesteckt? Pfad in Mixxx stimmt?)'; markRows(); });
  $('pos').addEventListener('input', () => { const d = player.duration || 0; if (d) player.currentTime = d * $('pos').value / 1000; });
  $('bpp').onclick = () => { if (!cur) return; if (player.paused) player.play(); else player.pause(); };
  // Lautstaerke: nur fuer das Vorhoeren in diesem Browser, der Browser merkt sich die Stellung
  let vol = 80;
  try { vol = Math.max(0, Math.min(100, parseInt(localStorage.getItem('musikvol') || '80', 10) || 0)); } catch (e) { /* privates Fenster */ }
  // gleich laut (11.11.2026): laute Lieder leiser auf -14 LUFS (der Browser kann ueber volume nur leiser), Haken im Balken
  let vnorm = true;
  try { vnorm = localStorage.getItem('musiknorm') !== '0'; } catch (e) { /* privates Fenster */ }
  $('vnorm').checked = vnorm;
  function setVol() {
    const db = vnorm && cur ? SM.loudDb(cur.lufs, cur.tp, false) : 0;
    player.volume = Math.max(0, Math.min(1, $('vol').value / 100 * SM.dbFactor(db)));
    $('vnormbox').title = 'Gleich laut: laute Lieder werden beim Vorhören leiser (Ziel ' + SM.LOUD_TARGET + ' LUFS, gemessen am Musik-Rechner)' + (cur && cur.lufs ? '. Dieses Lied: ' + cur.lufs.toFixed(1) + ' LUFS' + (db ? ', ' + db.toFixed(1) + ' dB' : '') : cur ? '. Dieses Lied ist noch nicht gemessen' : '');
  }
  $('vnorm').onchange = () => { vnorm = $('vnorm').checked; try { localStorage.setItem('musiknorm', vnorm ? '1' : '0'); } catch (e) { /* privates Fenster */ } setVol(); };
  $('vol').value = vol; setVol();
  $('vol').addEventListener('input', () => {
    setVol();
    $('volbox').firstChild.textContent = $('vol').value == 0 ? '🔇' : $('vol').value < 50 ? '🔉' : '🔊';
    try { localStorage.setItem('musikvol', $('vol').value); } catch (e) { /* privates Fenster */ }
  });
  $('volbox').firstChild.textContent = vol == 0 ? '🔇' : vol < 50 ? '🔉' : '🔊';
  $('bcl').onclick = closeBar;

  // ---- Show anlegen: MP3 vom Mac holen, auf den Pi schicken, Editor oeffnen ---------------------------------------
  async function cmd(op, data) {
    const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify(Object.assign({ op }, data || {})) });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    return j;
  }
  const showName = SM.showName;
  // quick: ohne Namensfrage (Interpret - Titel), danach fuellt der Editor die Show selbst mit dem Assistenten (Wunsch von Markus)
  async function makeShow(r, quick) {
    if (busy || !music || !r.path) return;
    const name = quick ? showName(r) : await SM.ask('Name der neuen Show (die MP3 kommt vom Musik-Rechner auf den Light-Butler, danach öffnet sich der Editor):', showName(r), 'Anlegen');
    if (name == null) return;
    const st = $('bst');
    $('bar').classList.add('on'); document.body.classList.add('bar');
    busy = true;
    let created = false;
    try {
      st.textContent = 'Lege Show „' + name + '“ an ...';
      await cmd('create', { name: name.trim(), title: r.title, dur: r.dur });
      created = true;
      st.textContent = 'Hole die MP3 vom Musik-Rechner ...';
      const resp = await fetch(src(r));
      if (!resp.ok) throw new Error('Die MP3 kommt nicht vom Musik-Rechner (' + resp.status + '): Brücke läuft? Stick eingesteckt?');
      const total = +resp.headers.get('Content-Length') || 0, parts = [];
      let got = 0;
      const rd = resp.body.getReader();
      for (;;) {
        const { done, value } = await rd.read();
        if (done) break;
        parts.push(value); got += value.length;
        st.textContent = 'Hole die MP3 vom Musik-Rechner ... ' + (got / 1048576).toFixed(1) + (total ? ' / ' + (total / 1048576).toFixed(1) : '') + ' MB';
      }
      const blob = new Blob(parts, { type: 'audio/mpeg' });
      st.textContent = 'Schicke die MP3 auf den Light-Butler (' + (blob.size / 1048576).toFixed(1) + ' MB) ...';
      const up = await fetch('/api/sm/audio?name=' + encodeURIComponent(name.trim()), { method: 'POST', body: blob });
      const uj = await up.json().catch(() => ({}));
      if (!up.ok || uj.error) throw new Error(uj.error || 'Hochladen fehlgeschlagen (' + up.status + ')');
      st.textContent = 'Fertig, öffne den Editor ...';
      location.href = '/shows/edit?show=' + encodeURIComponent(name.trim()) + '&import=1' + (quick ? '&quick=1' : '');
    } catch (e) {
      st.textContent = 'Show anlegen: ' + e.message;
      if (created) await cmd('delete', { name: name.trim() }).catch(() => {});   // halbe Show nicht liegen lassen
    } finally {
      busy = false;
    }
  }
  $('rows').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) { const gr = e.target.closest('tr.grp'); if (gr) toggleGroup(gr.dataset.gk); return; }
    if (b.dataset.gmore != null) { glim[b.dataset.gmore] = 1e9; draw(true, true); return; }
    if (b.dataset.gfade != null) {                      // Fade fuer diese Gruppe (Wunsch 11.11.2026)
      const g = groups.find(x => x.key === b.dataset.gfade);
      if (g) SM.fadeDlg(music, g.songs.map(r => r.path).filter(Boolean), g.name);
      return;
    }
    if (b.dataset.gexp != null) {                       // Export nur dieser Gruppe (Wunsch 10.11.2026)
      const g = groups.find(x => x.key === b.dataset.gexp);
      if (g) exportDlg(g.songs, g.name);
      return;
    }
    if (b.dataset.del != null) trashRow(all[+b.dataset.del]);
    else if (b.dataset.conv != null) convertRow(all[+b.dataset.conv]);
    else if (b.dataset.tag != null) {
      const r = all[+b.dataset.tag];
      SM.tagEdit(r, music, (d, fields) => {
        const f = (d && d.fields) || {};
        if ('artist' in fields) r.artist = f.artist || '';
        if ('title' in fields) r.name = f.title || '';
        if ('genre' in fields) r.genre = f.genre || '';
        if (d && 'cover' in d) { r.cv = d.cover ? 1 : 0; r.cvv = Date.now(); }   // Filter ohne Cover gleich richtig; neues Bild sofort (09.11.2026)
        redrawRow(r);
        $('hint').textContent = 'Tags in ' + r.path.split('/').pop() + ' geschrieben. Mixxx zeigt sie erst, wenn es die Tags neu einliest (Rechtsklick → Metadaten aus Datei importieren).';
      });
    }
    else if (b.dataset.nx != null) playNext(all[+b.dataset.nx]);
    else if (b.dataset.i != null) playRow(all[+b.dataset.i]);
    else if (b.dataset.mk != null) makeShow(all[+b.dataset.mk]);
    else if (b.dataset.quick != null) quickQueue(all[+b.dataset.quick]);
  });

  // ---- Als Naechstes spielen (Wunsch 08.11.2026): das Lied kommt im Auto-DJ als naechstes in die Playlist -----------------
  // Laeuft der Auto-DJ (eigenes Fenster), meldet er sich alle 2 s ueber den BroadcastChannel; sonst landet das Lied in einer
  // Warteliste (localStorage), und das Auto-DJ-Fenster geht auf und nimmt es beim Start.
  const adj = 'BroadcastChannel' in window ? new BroadcastChannel('lb_autodj') : null;
  let adjSeen = 0;
  if (adj) adj.onmessage = e => {
    const d = e.data || {};
    if (d.type === 'alive') adjSeen = Date.now();
    if (d.type === 'ok') SM.toast('Im Auto-DJ als Nächstes: ' + (d.name || ''), 3500);
  };
  function playNext(r) {
    const t = { path: r.path, title: r.title, artist: r.artist, name: r.name, dur: r.dur, bpm: r.bpm, kid: r.kid, lvl: r.lvl, est: r.est, elv: r.elv, genre: r.genre };
    if (adj && Date.now() - adjSeen < 5000) { adj.postMessage({ type: 'next', t }); return; }
    try {
      const q = JSON.parse(localStorage.getItem('autodj_next') || '[]');
      q.push(t);
      localStorage.setItem('autodj_next', JSON.stringify(q.slice(-50)));
    } catch (e) { /* privates Fenster */ }
    SM.toast('Kommt im Auto-DJ als Nächstes: ' + (r.name || r.title) + ' (Auto-DJ geht auf)', 4000);
    if (window.S2LNav && window.S2LNav.openAutoDJ) window.S2LNav.openAutoDJ();
  }

  // ---- In MP3 umwandeln (Wunsch von Markus, 07.11.2026): MP4, WAV ... am Mac mit ffmpeg, die MP3 kommt daneben ---------
  // Das Original bleibt. Die Bruecke liest den Musikordner danach gleich neu ein, die MP3 erscheint mit Quelle Ordner.
  const CONV_EXT = ['mp4', 'm4a', 'wav', 'aif', 'aiff', 'flac', 'aac', 'ogg'];
  // Die MP3 daneben gibt es schon (gleicher Ordner, gleicher Name): dann kein Knopf (Wunsch von Markus 07.11.2026)
  function hasMp3(r) { return !!r.path && mp3s.has(r.path.replace(/\.[^./]+$/, '.mp3').toLowerCase()); }
  function convButton(r, can) {
    const c = r._cv || {};
    if (c.state === 'wait' || c.state === 'run') return ' <span class="qst run" title="wird am Musik-Rechner umgewandelt">→ MP3 …</span>';
    if (c.state === 'ok') return ' <span class="qst ok" title="' + esc(c.name || '') + ' liegt neben dem Original">✓ MP3</span>';
    return '<button class="pb conv" data-conv="' + r._i + '"' + (can ? ' title="' + (c.state === 'err' ? 'Fehler: ' + esc(c.error || '') + ' – nochmal versuchen' : 'Am Musik-Rechner in eine MP3 umwandeln (320 kbit/s, Titel und Cover übernommen). Die MP3 kommt mit gleichem Namen daneben, das Original bleibt.') + '"' : ' disabled title="Umwandeln geht nur, solange die Mixxx-Brücke am Musik-Rechner läuft"') + '>' + (c.state === 'err' ? '✗ MP3' : '→ MP3') + '</button>';
  }
  async function convertRow(r) {
    if (!music || !r.path) return;
    const name = r.path.split('/').pop();
    try {
      const resp = await fetch(music + '/convert', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ p: r.path, name }) });
      const j = await resp.json().catch(() => ({}));
      if (!resp.ok && resp.status !== 202) throw new Error(j.error || ('Fehler ' + resp.status));
      r._cv = j; redrawConv(r);
      for (let i = 0; i < 1200 && (r._cv.state === 'wait' || r._cv.state === 'run'); i++) {
        await new Promise(res => setTimeout(res, 1500));
        const q = await fetch(music + '/convert?p=' + encodeURIComponent(r.path)).then(x => x.json()).catch(() => null);
        if (q && q.state && (q.state !== r._cv.state || q.name !== r._cv.name)) { r._cv = q; redrawConv(r); }   // nur bei Aenderung
      }
      if (r._cv.state === 'ok') $('hint').textContent = 'MP3 angelegt: ' + (r._cv.name || '') + '. Sie erscheint in ein paar Sekunden in der Liste (Quelle Ordner), in Mixxx nach dem Einlesen der Bibliothek.';
      else if (r._cv.state === 'err') SM.ask('Umwandeln ging nicht: ' + (r._cv.error || ''));
    } catch (e) {
      r._cv = { state: 'err', error: e.message }; redrawConv(r);
      SM.ask('Umwandeln ging nicht: ' + e.message);
    }
  }

  // ---- Muellkuebel: Datei (MP3, MP4, WAV ...) am Mac in den Papierkorb (Wunsch von Markus, zum Aufraeumen doppelter Dateien) ---------------
  // Nicht endgueltig: im Finder "Zuruecklegen". Mixxx behaelt den Eintrag, bis es die Bibliothek neu einliest; die Bruecke
  // schickt fehlende Dateien nicht mehr, nach spaetestens 10 Minuten ist das Lied auch am Pi weg.
  async function trashRow(r) {
    if (busy || !music || !r.path) return;
    // Wunsch 08.11.2026: ohne Nachfrage-Fenster, ein Klick legt in den Papierkorb (im Finder mit „Zurücklegen“ wieder da)
    SM.toast('In den Papierkorb: ' + r.path.split('/').pop() + ' (im Finder mit „Zurücklegen“ wieder da)', 3500);
    if (cur && cur._i === r._i) closeBar();
    try {
      const resp = await fetch(music + '/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ p: r.path, name: r.path.split('/').pop() }) });
      const j = await resp.json().catch(() => ({}));
      if (!resp.ok || !j.ok) throw new Error(j.error || ('Fehler ' + resp.status));
      r._gone = true;
      SM.goneMark(r.path);
      findDups(); apply(true);
      $('hint').textContent = 'In den Papierkorb gelegt: ' + r.path.split('/').pop() + '. Mixxx zeigt das Lied noch, bis es die Bibliothek neu einliest.';
    } catch (e) {
      SM.ask('Löschen ging nicht: ' + e.message + (/Finder|Apple/i.test(e.message) ? '\n\nBeim ersten Mal fragt macOS am Mac, ob die App den Finder steuern darf: dort erlauben.' : ''));
    }
  }

  // ---- Quick: Show anlegen und gleich vom Assistenten fuellen lassen, alles hier in der Liste (Wunsch von Markus) -------
  // Mehrere Klicks kommen in eine Warteschlange und laufen nacheinander; die Zeile zeigt, wo es steht. Nichts oeffnet sich.
  const quickTodo = [];
  let quickBusy = false;
  function quickState(r, text, cls, tip) { r._q = { text, cls: cls || 'run', tip }; redrawRow(r); }
  // Umwandeln: nur das kleine Feld neu, nicht die ganze Zeile (sonst lud das Cover alle 1,5 s neu und die Zeilen zitterten,
  // Fehlerbericht 07.11.2026)
  function redrawConv(r) {
    const el = $('rows').querySelector('span.cvw[data-cvw="' + r._i + '"]');
    if (el) el.innerHTML = convButton(r, !!(music && r.path));
    else redrawRow(r);
  }
  function redrawRow(r) {
    const tr = $('rows').querySelector('tr[data-i="' + r._i + '"]');
    if (tr) tr.outerHTML = row(r);
  }
  function quickQueue(r) {
    if (r._q && r._q.cls !== 'err') return;
    quickTodo.push(r);
    quickState(r, '⏳ wartet', 'wait');
    if (!quickBusy) quickRun();
  }
  async function quickRun() {
    quickBusy = true;
    while (quickTodo.length) {
      const r = quickTodo.shift();
      try { await quickOne(r); } catch (e) { quickState(r, '✗ Fehler', 'err', e.message + ' (nochmal Quick drücken versucht es neu)'); }
    }
    quickBusy = false;
  }
  async function quickOne(r) {
    const name = await SM.quickShow(r, music, text => quickState(r, text));
    r.show = name; r.shows = [name]; r._q = null;
    redrawRow(r);
  }

  // ---- Doppelte: gleicher Dateiname (dieselbe MP3 in mehreren Ordnern; die Analyse am Mac findet dann oft nur eine) ----
  // Musikordner, der in der Spalte Ordner wegfaellt: aus den Einstellungen (root), sonst der haeufigste Anfang (/Volumes/Stick/musik/)
  function topPrefix(paths, root) {
    if (root) return root.replace(/\/+$/, '') + '/';
    const cnt = {};
    for (const p of paths) { const k = p.split('/').slice(0, 4).join('/') + '/'; cnt[k] = (cnt[k] || 0) + 1; }
    let best = '', n = 0;
    for (const k in cnt) if (cnt[k] > n) { best = k; n = cnt[k]; }
    return best;
  }
  const extOf = p => { const m = /\.([A-Za-z0-9]{1,5})$/.exec(String(p || '')); return m ? m[1].toUpperCase() : ''; };   // Typ: MP3, MP4, WAV ...
  const dirOf = p => (p.startsWith(prefix) ? p.slice(prefix.length) : p).replace(/\/[^\/]*$/, '');
  function findDups() {
    const parent = all.map((_, i) => i);
    const find = i => { while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; } return i; };
    const why = all.map(() => new Set());
    const join = (keyOf, label) => {
      const seen = new Map();
      for (const r of all) {
        const k = keyOf(r);
        if (!k) continue;
        if (seen.has(k)) { const o = seen.get(k); parent[find(r._i)] = find(o); why[r._i].add(label); why[o].add(label); }
        else seen.set(k, r._i);
      }
    };
    join(r => r.file && !r._gone ? norm(r.file) : '', 'gleicher Dateiname');
    const size = {};
    for (const r of all) { const g = find(r._i); size[g] = (size[g] || 0) + 1; }
    let n = 0; const ids = {};
    for (const r of all) {
      const g = find(r._i);
      if (size[g] < 2) { r._g = -1; continue; }
      if (ids[g] == null) ids[g] = n++;
      r._g = ids[g]; r._gn = size[g]; r._why = [...why[r._i]].join(', ');
    }
    return n;
  }
  $('blong').onclick = () => { longOn = !longOn; $('blong').classList.toggle('on', longOn); apply(); };
  $('bnomp3').onclick = () => { nomp3On = !nomp3On; $('bnomp3').classList.toggle('on', nomp3On); apply(); };
  $('bsame').onclick = () => { sameOn = !sameOn; $('bsame').classList.toggle('on', sameOn); apply(); drawSameAi(); };
  // Titel = Interpret: Assistent (Wunsch 08.11.2026) - der Auto-Tagger am Mac recherchiert diese Lieder zuerst (Shazam, Dateiname)
  function drawSameAi() {
    const n = sameOn ? view.filter(r => r.path && sameTA(r)).length : 0;
    $('bsameai').hidden = !(sameOn && music && n);
    $('bsameai').textContent = 'Assistent: ' + n + ' prüfen';
  }
  $('bsameai').onclick = async () => {
    const paths = view.filter(r => r.path && sameTA(r)).map(r => r.path);
    if (!paths.length) return;
    if (!await SM.ask(paths.length + ' Lieder mit Titel = Interpret prüfen lassen?\n\nDer Musik-Rechner fragt Shazam (ein Ausschnitt des Liedes geht dafür an Shazam), sonst nimmt er den Dateinamen und sucht im Internet. Die Vorschläge stehen danach auf der Seite Tag-Vorschläge, Reiter „Titel = Interpret“; geschrieben wird nur auf Klick. Shazam fragt er höchstens alle 20 Sekunden, das dauert also ein paar Minuten.', undefined, 'Prüfen lassen')) return;
    try {
      const r = await fetch(music + '/autotag', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'research', paths }) });
      let d = null;
      try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
      if (!r.ok || !d) throw new Error((d && d.error) || 'Am Musik-Rechner noch die alte Fassung (Helfer neu installieren)');
      location.href = '/musik/vorschlaege?f=ti';
    } catch (e) { SM.toast('Assistent: ' + e.message, 6000); }
  };
  $('bdup').onclick = () => { dupOn = !dupOn; $('bdup').classList.toggle('on', dupOn); apply(); };

  // Export (Wunsch 10.11.2026): die gefilterte Liste flach in einen Ordner kopieren. Der Mac kopiert (export_files.py), die
  // Laufwerke am Mac kommen von /dirs, der zuletzt gewaehlte Ordner steht in localStorage exportziel.
  const GB = b => b == null ? '' : b >= 1e9 ? (b / 1e9).toFixed(1).replace('.', ',') + ' GB' : Math.round(b / 1e6) + ' MB';
  async function exportDlg(only, label) {
    if (!music) { SM.toast('Export geht nur, solange am Musik-Rechner der Helfer oder die Mixxx-App läuft.', 5000); return; }
    const rows = (Array.isArray(only) ? only : view).filter(r => r.path);
    if (!rows.length) { SM.toast('Die Liste ist leer.', 3000); return; }
    let cur = '';
    try { cur = localStorage.getItem('exportziel') || ''; } catch (e) { /* privates Fenster */ }
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = '<div class="box"><h2>Export' + (label ? ' „' + esc(label) + '“' : '') + ': ' + rows.length + ' Lied' + (rows.length > 1 ? 'er' : '') + '</h2>' +
      '<p class="dim" style="margin:-4px 0 8px">Alle in einen Ordner, ohne Unterordner. Es wird nur kopiert, nie überschrieben: gleiche Datei schon da = übersprungen, gleicher Name = „(2)“.</p>' +
      '<div id="xwhere" style="font-weight:600"></div><div id="xlist"></div>' +
      '<div class="row"><button id="xup">← zurück</button><button id="xnew">+ Neuer Ordner</button><button id="xre">↻ Laufwerke neu laden</button></div>' +
      '<div id="xmsg" class="dim" style="min-height:1.3em"></div><div id="xbar" hidden><i></i></div>' +
      '<div class="row"><button id="xgo" class="on" disabled>Hierher kopieren</button><button id="xstop" hidden>Anhalten</button><button id="xclose">Schließen</button></div></div>';
    document.body.appendChild(m);
    const q = s => m.querySelector(s);
    let info = null, poll = null;
    const close = () => { clearInterval(poll); m.remove(); };
    q('#xclose').onclick = close;
    async function show(p) {
      q('#xmsg').textContent = '';
      try {
        const r = await fetch(music + '/dirs?p=' + encodeURIComponent(p || ''));
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        info = d; cur = d.path;
      } catch (e) {
        if (p) { q('#xmsg').textContent = 'Ordner nicht erreichbar (' + e.message + '), zurück zu den Laufwerken.'; return show(''); }
        q('#xmsg').textContent = 'Fehler: ' + e.message; return;
      }
      const L = q('#xlist');
      if (!info.path) {
        q('#xwhere').textContent = 'Laufwerke am Musik-Rechner';
        L.innerHTML = info.drives.map((v, i) => '<button class="xdrv" data-i="' + i + '">' + (v.kind === 'net' ? '🗄' : v.kind === 'home' ? '🏠' : '💾') + ' ' + esc(v.name) +
          (v.kind === 'net' && v.host ? ' <span class="dim">(' + esc(v.host) + ')</span>' : '') + (v.music ? ' <span class="dim">(dein Musik-Stick)</span>' : '') +
          '<small>' + (v.free != null ? GB(v.free) + ' frei' : '') + '</small></button>').join('');
        L.querySelectorAll('.xdrv').forEach(b => b.onclick = () => show(info.drives[+b.dataset.i].path));
      } else {
        q('#xwhere').textContent = info.path + (info.free != null ? ' · ' + GB(info.free) + ' frei' : '');
        L.innerHTML = info.dirs.length ? info.dirs.map((n, i) => '<button class="xdir" data-i="' + i + '">📁 ' + esc(n) + '</button>').join('') : '<p class="dim">Keine Unterordner. „Hierher kopieren“ nimmt diesen Ordner.</p>';
        L.querySelectorAll('.xdir').forEach(b => b.onclick = () => show(info.path + '/' + info.dirs[+b.dataset.i]));
        if (info.music) q('#xmsg').textContent = 'Das ist dein Musikordner: dorthin geht kein Export (sonst entstehen Doppelte).';
      }
      q('#xup').disabled = !info.path;
      q('#xnew').disabled = !info.path;
      q('#xgo').disabled = !info.path || info.music;
    }
    q('#xup').onclick = () => show(info && info.parent ? info.parent : '');
    q('#xre').onclick = () => show('');
    q('#xnew').onclick = async () => {
      const name = await SM.ask('Name des neuen Ordners in ' + info.path + ':', '', 'Anlegen');
      if (!name) return;
      try {
        const r = await fetch(music + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'mkdir', parent: info.path, name }) });
        const d = await r.json(); if (d.error) throw new Error(d.error);
        show(d.path);
      } catch (e) { q('#xmsg').textContent = 'Ordner anlegen: ' + e.message; }
    };
    function state(s) {
      const done = s.done || 0, tot = s.total || 0;
      q('#xbar').hidden = false; q('#xbar i').style.width = (tot ? 100 * done / tot : 0) + '%';
      const extra = (s.skipped ? ' · ' + s.skipped + ' schon da' : '') + (s.renamed ? ' · ' + s.renamed + ' mit (2)' : '') + (s.missing ? ' · ' + s.missing + ' nicht erreichbar' : '') + ((s.errors || []).length ? ' · ' + s.errors.length + ' Fehler' : '');
      if (s.state === 'run') q('#xmsg').textContent = 'Kopiere ' + done + ' von ' + tot + (s.cur ? ': ' + s.cur : '') + extra;
      else if (s.state === 'ok') q('#xmsg').textContent = 'Fertig: ' + (s.copied || 0) + ' kopiert nach ' + s.dest + extra + ((s.errors || []).length ? ' (' + s.errors.slice(0, 3).join('; ') + ')' : '');
      else if (s.state === 'stopped') q('#xmsg').textContent = 'Angehalten nach ' + done + ' von ' + tot + extra + '. Nochmal starten setzt fort (vorhandene werden übersprungen).';
      else if (s.state === 'err') q('#xmsg').textContent = 'Abgebrochen: ' + (s.error || '') + extra;
      const run = s.state === 'run';
      q('#xstop').hidden = !run; q('#xgo').disabled = run; q('#xup').disabled = run; q('#xnew').disabled = run; q('#xlist').style.opacity = run ? .5 : 1;
      if (!run) clearInterval(poll);
    }
    const follow = () => { clearInterval(poll); poll = setInterval(async () => { try { state(await (await fetch(music + '/export')).json()); } catch (e) { /* kurz weg */ } }, 1000); };
    q('#xstop').onclick = () => fetch(music + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'stop' }) });
    q('#xgo').onclick = async () => {
      const bytes = rows.reduce((s, r) => s + (r.kbps && r.dur ? r.kbps * 125 * r.dur : 0), 0);
      if (!await SM.ask(rows.length + ' Lieder (etwa ' + GB(bytes) + ') nach' + String.fromCharCode(10) + info.path + String.fromCharCode(10) + 'kopieren?', undefined, 'Kopieren')) return;
      try { localStorage.setItem('exportziel', info.path); } catch (e) { /* privates Fenster */ }
      try {
        const r = await fetch(music + '/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'start', dest: info.path, paths: rows.map(r => r.path) }) });
        const d = await r.json(); if (d.error) throw new Error(d.error);
        state(d); follow();
      } catch (e) { q('#xmsg').textContent = 'Export: ' + e.message; }
    };
    try { const s = await (await fetch(music + '/export')).json(); if (s.state === 'run') { state(s); follow(); } } catch (e) { /* alter Mac ohne Export */ }
    show(cur);
  }

  function csv() {
    const cols = ['Interpret', 'Titel', 'BPM', 'Tonart', 'Camelot', 'Energie', 'Genre', 'Laenge', 'Typ', 'kb/s', 'Liedtext', 'Show', 'Kurven', 'Analyse', 'Hotcues', 'Ordner', 'Datei', 'Pfad', 'Kisten', 'Listen', 'Jahr', 'Album', 'Gruppe', 'Hinzugefuegt', 'LUFS', 'Spitze dBTP', 'Gespielt', 'Zuletzt gespielt'];
    const cell = v => { v = String(v == null ? '' : v); return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [cols.join(';')].concat(view.map(r => [r.artist, r.name, r.bpm || '', keyName(r), camelot(r), r.lvl || '', r.genre, mmss(r.dur), r.ext, r.kbps || '',
      r.lyr === 2 ? 'ja' : r.lyr === 1 ? 'nur Text' : '', r.show, r.stems ? 'ja' : '', r.ana ? 'ja' : '', r.cues || '', r.dir, r.file, r.path, (r.crates || []).join(', '), (r.lists || []).join(', '), r.year || '', r.album || '', r.grp || '', r.added ? new Date(r.added * 1000).toISOString().slice(0, 10) : '', r.lufs || '', r.lufs ? r.tp : '', r.plays || '', r.lastp ? new Date(r.lastp * 1000).toISOString().slice(0, 10) : ''].map(cell).join(';')));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    a.download = 'musik-datenbank.csv';
    document.body.appendChild(a); a.click(); a.remove();
  }

  function clearFilters() {
    $('q').value = ''; $('genre').value = ''; $('crate').value = ''; $('key').value = ''; $('bmin').value = ''; $('bmax').value = ''; $('lmin').value = ''; $('lmax').value = ''; $('lnone').checked = false;
    for (const id of ['flyr', 'fshow', 'fana', 'fnoana', 'fbad', 'fcue', 'fnocue', 'fstems', 'fsrc', 'fnocv']) $(id).checked = false;
    $('ffav').value = ''; $('frat').value = '';
    $('fadd').value = ''; $('faddv').value = ''; $('faddb').value = '';
    energySel.clear(); dupOn = false; $('bdup').classList.remove('on'); sameOn = false; $('bsame').classList.remove('on'); longOn = nomp3On = false; $('blong').classList.remove('on'); $('bnomp3').classList.remove('on');
    for (const b of $('energy').children) b.classList.remove('on');
    apply();
  }

  let deb = null;
  $('q').addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(apply, 120); });
  // Fruehere Suchen als Vorschlagsliste (Wunsch 09.11.2026, wie im Tag-Editor): gemerkt nach Enter, beim Verlassen des Feldes oder
  // nach 2,5 s ohne Tippen; Zwischenstaende beim Tippen ("ab", "abb") fallen weg. Nur in diesem Browser.
  const QH = 'musiksuche', QH_MAX = 40;
  let qh = [], qhLast = { t: '', at: 0 }, qhDeb = 0;
  try { qh = JSON.parse(localStorage.getItem(QH) || '[]').filter(x => typeof x === 'string').slice(0, QH_MAX); } catch (e) { qh = []; }
  const qhDraw = () => { $('qhist').innerHTML = qh.map(x => '<option value="' + esc(x) + '">').join(''); };
  function qhSave() {
    const t = $('q').value.trim();
    if (t.length < 2) return;
    const lo = t.toLowerCase(), now = Date.now();
    qh = qh.filter(x => x.toLowerCase() !== lo && !(qhLast.t && x === qhLast.t && now - qhLast.at < 15000 && lo.startsWith(x.toLowerCase())));
    qh.unshift(t); qh = qh.slice(0, QH_MAX); qhLast = { t, at: now };
    try { localStorage.setItem(QH, JSON.stringify(qh)); } catch (e) { /* privates Fenster */ }
    qhDraw();
  }
  $('q').addEventListener('change', qhSave);
  $('q').addEventListener('input', () => { clearTimeout(qhDeb); qhDeb = setTimeout(qhSave, 2500); });
  qhDraw();
  for (const id of ['fadd', 'faddv', 'faddb', 'genre', 'crate', 'key', 'bmin', 'bmax', 'lmin', 'lmax', 'lnone', 'flyr', 'fshow', 'fana', 'fnoana', 'fbad', 'fcue', 'fnocue', 'fstems', 'fsrc', 'fnocv', 'ffav', 'frat']) $(id).addEventListener('change', apply);
  SM.favLoad();                                          // Herzen (Favoriten, 14.11.2026)
  document.addEventListener('s2lstars', e => {             // Sterne gesetzt: Liste nachziehen (Filter und Sortieren)
    const set = new Set(e.detail.paths);
    for (const r of all) if (set.has(r.path)) r.rating = e.detail.r;
    if ($('frat').value || sortK === 'rating') apply(true);
  });
  document.addEventListener('s2lfav', () => { buildSelects(); if ($('ffav').value || sortK === 'fav') apply(true); });
  // Link von der Seite Statistik: /musik?f=nichtlesbar zeigt gleich die Dateien, die die Analyse nicht lesen konnte
  const fq = new URLSearchParams(location.search).get('f');
  const qq = new URLSearchParams(location.search).get('q');   // von der Seite Interpreten: gleich danach suchen (13.11.2026)
  if (qq) $('q').value = qq;
  if (fq === 'nichtlesbar') $('fbad').checked = true;
  if (fq === 'fav') $('ffav').value = '2';               // von der Seite Favoriten
  if (fq === 'nichtmp3') { nomp3On = true; $('bnomp3').classList.add('on'); }   // aus der Datenpflege
  if (fq === 'same') { sameOn = true; $('bsame').classList.add('on'); }
  if (fq === 'nocover') $('fnocv').checked = true;
  if (fq === 'neu') { $('fadd').value = '7'; sortK = 'added'; sortUp = false; }   // zuletzt hinzugekommene
  if (fq === 'heute') { $('fadd').value = 'heute'; sortK = 'added'; sortUp = false; }   // aus der Datenpflege: Lieder ohne Cover (dort Tag → Cover erzeugen)
  loadCols(); buildHead();
  $('bcsv').onclick = csv;
  $('bexp').onclick = () => exportDlg();
  // Gruppe fuer die gefilterte Liste setzen (Wunsch 11.11.2026): der Mac schreibt TIT1 Lied fuer Lied (POST /tags, wie das Tag-Fenster)
  $('bgrp').onclick = async () => {
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer oder die Mixxx-App?).', 5000); return; }
    const mp3 = view.filter(r => r.path && /\.mp3$/i.test(r.path)), other = view.length - mp3.length;
    if (!mp3.length) { SM.toast('Keine MP3s in der gefilterten Liste.', 4000); return; }
    const have = [...new Set(mp3.map(r => r.grp || '').filter(Boolean))];
    const g0 = await SM.ask('Gruppe für ' + mp3.length + ' MP3' + (mp3.length === 1 ? '' : 's') + ' der gefilterten Liste' + (other ? ' (' + other + ' andere Dateien können keine Gruppe tragen)' : '') + '.' +
      (have.length ? '\nJetzt eingetragen: ' + have.slice(0, 6).join(', ') + (have.length > 6 ? ' …' : '') : '') + '\n\nLeer lassen = Gruppe löschen. Mehrere mit „;“ trennen.', have.length === 1 ? have[0] : '', 'Weiter');
    if (g0 === null) return;
    const g = g0.replace(/\s+/g, ' ').trim().slice(0, 60);
    const todo = mp3.filter(r => (r.grp || '') !== g);
    if (!todo.length) { SM.toast('Alle haben schon diese Gruppe.', 4000); return; }
    if (!await SM.ask(todo.length + ' MP3' + (todo.length === 1 ? '' : 's') + (g ? ' bekommen die Gruppe „' + g + '“.' : ': Gruppe löschen.') +
      (mp3.length > todo.length ? ' (' + (mp3.length - todo.length) + ' haben sie schon.)' : '') + '\n\nGeschrieben wird nur das Feld Gruppe, Musik und alle anderen Tags bleiben gleich. Starten?', undefined, 'Schreiben')) return;
    $('bgrp').disabled = true;
    let ok = 0; const bad = [];
    for (let i = 0; i < todo.length; i++) {
      const r = todo[i];
      $('hint').textContent = '🏷 Gruppe schreiben: ' + (i + 1) + ' von ' + todo.length + ' · ' + r.path.split('/').pop();
      try {
        const resp = await fetch(music + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ p: r.path, name: r.path.split('/').pop(), fields: { grouping: g } }) });
        const j = await resp.json().catch(() => ({}));
        if (!resp.ok || !j.ok) throw new Error(j.error || resp.status);
        r.grp = g; ok++;
      } catch (e) { bad.push(r.path.split('/').pop() + ': ' + e.message); }
    }
    $('bgrp').disabled = false;
    $('hint').textContent = '🏷 Gruppe ' + (g ? '„' + g + '“' : 'gelöscht') + ': ' + ok + ' MP3' + (ok === 1 ? '' : 's') + ' geschrieben' + (bad.length ? ', ' + bad.length + ' nicht: ' + bad.slice(0, 3).join('; ') : '') +
      '. Mixxx zeigt es nach „Metadaten aus Datei importieren“ (Liste Geänderte → Mixxx).';
    buildSelects(); apply(true);
  };
  $('bfade').onclick = () => SM.fadeDlg(music, view.map(r => r.path).filter(Boolean), view.length === all.length ? 'alle' : 'gefilterte Liste');
  $('beject').onclick = () => SM.ejectStick(music, (t, k) => SM.toast(t, k === '' ? 2500 : 9000));
  $('breload').onclick = () => { stamp = ''; syncT = 0; load(); };   // auch den Abgleich mit Mixxx sofort neu
  $('bclear').onclick = clearFilters;
  $('gview').addEventListener('click', e => { const b = e.target.closest('button'); if (b && b.dataset.gv !== gmode) setMode(b.dataset.gv); });
  for (const b of $('gview').children) b.classList.toggle('on', b.dataset.gv === gmode);
  $('gall').onclick = () => {
    const open = !groups.every(isOpen);
    openG = open ? new Set(groups.map(g => g.key)) : new Set(); shutG = open ? new Set() : new Set(groups.map(g => g.key));
    draw(true, true);
  };
  $('az').addEventListener('click', e => {      // A-Z: zum ersten Interpreten mit diesem Buchstaben springen
    const b = e.target.closest('button'); if (!b) return;
    const i = items ? items.findIndex(x => x.g && x.g.letter === b.dataset.az) : -1; if (i < 0) return;
    while (shown <= i) draw(false);
    const tr = $('rows').querySelector('tr.grp[data-l="' + b.dataset.az + '"]');
    if (tr) tr.scrollIntoView({ block: 'start', behavior: 'smooth' });
  });
  window.addEventListener('scroll', onScroll, { passive: true });
  load();
})();
