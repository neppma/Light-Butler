// CD-Assistent (Wunsch von Markus, 09.11.2026): Trackliste einfuegen, den Dateien eines Ordners zuordnen, Vorschau, schreiben.
// Zerlegen und Zuordnen hier im Browser (reine Funktionen in window.CD, test_cd_assistent.py prueft sie mit node); Lesen des
// Ordners und Schreiben macht der Mac (music_serve /cd, cd_assist.py).
(function () {
  'use strict';
  const W = typeof window !== 'undefined' ? window : globalThis;

  // ---- Zerlegen -------------------------------------------------------------------------------------------------------
  // Trenner zwischen Interpret und Titel: zuerst langer Strich (" – ", Discogs "Interpret–<Tab>Titel"), sonst Tabulator, sonst " - "
  // (ein " - " im Titel wie "Lied - Remix" bleibt so ganz, wenn es einen langen Strich gibt)
  function split2(rest) {
    for (const re of [/\s*[–—]\s*\t+|\s+[–—]\s+/, /\t+/, /\s+-\s+/]) {
      const m = re.exec(rest);
      if (m) return [rest.slice(0, m.index).trim(), rest.slice(m.index + m[0].length).replace(/\t+/g, ' ').trim()];
    }
    return null;
  }
  function cleanText(s) {
    return String(s || '').replace(/\[\[\d+\]\([^)]*\)\]|\[\d+\]/g, '')     // Fussnoten [[1](https://...)]
      .replace(/\*(?=\s|$|[–—-])/g, '')                                         // Discogs: "Pfaffendorf*"
      .replace(/ /g, ' ').trim();
  }
  // Zusaetze von Haendlern hinter dem Titel weg ("RARITÄT!", "WORLD PREMIERE RECORDING …", "PREVIOUSLY UNRELEASED"), Klammern
  // nur in Grossbuchstaben ("(TANZ DER VAMPIRE)") normal geschrieben (Musical Stars, 09.11.2026)
  const EXTRA = /\s+(?:RARIT[ÄA]T|RARE|RAR|WORLD PREMIERE RECORDING|PREVIOUSLY UNRELEASED|UNVER[ÖO]FFENTLICHTER EDIT|BONUS TRACK)\b.*$/u;
  const cap = w => w.length > 1 && !/^(?:[IVX]+|DJ|USA|UK|ABBA)$/.test(w) ? w.charAt(0) + w.slice(1).toLowerCase() : w;
  function tidyTitle(t) {
    t = String(t || '').replace(EXTRA, '').trim();
    t = t.replace(/\(([^()]*)\)/g, (all, inner) => /\p{Ll}/u.test(inner) || !/\p{Lu}{3}/u.test(inner) ? all : '(' + inner.split(/(\s+|-)/).map(cap).join('') + ')');
    if (!/\p{Ll}/u.test(t.replace(/\([^()]*\)/g, '')) && /\p{Lu}{3}/u.test(t)) t = t.split(/(\s+|-)/).map(w => /^\(/.test(w) ? w : cap(w)).join('');   // ganzer Titel in Grossbuchstaben
    return t;
  }
  function secs(t) { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ''); return m ? +m[1] * 60 + +m[2] : 0; }

  // Zeilen: "1. Titel – Interpret", "1 Interpret – Titel 5:42", Discogs "1-01<Tab>Interpret–<Tab>Titel<Tab>3:45" (Doppel-CD:
  // CD-Nummer vor dem Strich, oder Ueberschriften "CD 1:", "CD2:"). Mitwirkende ("Remix – Gizeh", "Vocals – Inka") und eine
  // Laenge in eigener Zeile gehoeren zur Zeile davor (Discogs, Wunsch 09.11.2026).
  function parseList(text) {
    const rows = [], other = [], head = [];
    let disc = 0, last = null;
    for (let line of String(text || '').split(/\r?\n/)) {
      line = cleanText(line);
      if (!line) continue;
      const h = /^(?:[\p{L} ]{0,30}\s)?(?:CD|Disc|Disk|Teil)\s*(\d{1,2})\s*:?\s*$/iu.exec(line);   // auch "TRACKLISTING CD 1" (09.11.2026)
      if (h) { disc = +h[1]; last = null; continue; }
      const lone = /^\(?(\d{1,2}:\d{2})\)?$/.exec(line);
      if (lone) { if (last && !last.dur) last.dur = secs(lone[1]); continue; }
      const m = /^(?:(\d{1,2})[-./](?=\d))?([A-Da-d]?\d{1,3})(?:\.|\)|:|\s|\t)+\s*(.+)$/.exec(line);
      if (!m) { other.push(line); if (!rows.length) head.push(line); continue; }
      let rest = m[3].trim(), dur = 0;
      const d = /[\s\t(]+(\d{1,2}:\d{2})\)?\s*$/.exec(rest);
      if (d) { dur = secs(d[1]); rest = rest.slice(0, d.index).trim().replace(/\s*[–—-]\s*$/, ''); }   // "Titel – 4:08"
      const parts = split2(rest);
      const n = parseInt(m[2].replace(/^[A-Da-d]/, ''), 10);
      if (!parts || !parts[0] || !parts[1]) {
        // nur ein Titel (CD eines Interpreten, Xavier Naidoo 09.11.2026): Interpret kommt aus "Album-Interpret"
        if (!/\p{L}/u.test(rest)) { other.push(line); continue; }
        last = { n, disc: m[1] ? +m[1] : disc, a: '', b: tidyTitle(rest), dur, solo: true };
        rows.push(last);
        continue;
      }
      last = { n, disc: m[1] ? +m[1] : disc, a: parts[0].replace(/[–—]\s*$/, '').trim(), b: tidyTitle(parts[1]), dur };
      rows.push(last);
    }
    const discs = new Set(rows.map(r => r.disc).filter(Boolean));
    if (discs.size < 2) for (const r of rows) r.disc = 0;        // nur eine CD: keine CD-Nummer schreiben
    const all = other.join(' ');
    // Album: in Anfuehrungszeichen, sonst "Album:/Titel:/Title: ...", sonst die erste eigene Zeile vor den Tracks (Discogs: erste
    // Zeile "GRAND PRIX Der Volkstuemlichen Musik 1994", Fehlerbericht 09.11.2026); Zeilen wie "Genre: ...", "Year: ..." zaehlen nicht
    const qm = /[„“"]([^“”"]{3,80})[“”"]/.exec(all);
    const unq = s => String(s || '').trim().replace(/^[„“"']+|[“”"']+$/g, '').trim();
    // Angaben mit Namen (Xavier Naidoo Live, 09.11.2026): "Interpret: „…“", "Album: „…“", "Jahr: 1999"; ein Ordnerpfad als eigene Zeile
    const field = re => { for (const l of other) { const x = re.exec(l); if (x) return unq(x[1]); } return ''; };
    const labArtist = field(/^(?:interpret|künstler|kuenstler|artist)\s*:\s*(.{2,100})$/i);
    const labAlbum = field(/^(?:album)\s*:\s*(.{2,120})$/i);
    const dir = (head.find(l => /^[^\s:]+(?:\/[^/]+)+$/.test(l) || /^[\p{L}\d -]+\/.+\/.+$/u.test(l)) || '').replace(/^\/+|\/+$/g, '');
    const lab = labAlbum ? [0, labAlbum] : head.map(l => /^(?:album|titel|title)\s*[:–-]\s*(.{2,100})$/i.exec(l)).find(Boolean);
    const first = head.find(l => !/^[\p{L} ]{2,20}\s*:/u.test(l) && !/:\s*$/.test(l) && l.length <= 100 && !/^(?:CD|Disc|Disk)\s*\d/i.test(l) && l !== dir && !l.includes('/'));
    const q = lab ? [0, lab[1]] : qm && unq(qm[1]) !== labArtist ? qm : first ? [0, first] : null;
    const yl = field(/^(?:jahr|jahre|year|erschienen)\s*:?\s*((?:19|20)\d\d)\b/i);   // "Jahr: 1999" vor einer Jahreszahl im Ordnernamen
    const y = yl ? [0, yl] : /\b(19[4-9]\d|20[0-4]\d)\b/.exec(other.filter(l => l !== dir).join(' '));
    const perf = /\bvon\s+(.+?)\s+\((?:erschienen|\d{4})/i.exec(all) || /\bby\s+(.+?)\s+\((?:released|\d{4})/i.exec(all);
    return { rows, discs: discs.size >= 2 ? Math.max(...discs) : 0, album: q ? unq(q[1]) : '', year: y ? y[1] : '', performer: perf ? perf[1].trim() : '',
             artist: labArtist, dir, albumSure: !!(lab || (qm && unq(qm[1]) !== labArtist)) };   // Album ausdruecklich genannt
  }

  // Reihenfolge erraten: welche Spalte enthaelt mehr bekannte Interpreten (aus der Bibliothek)?
  // Vergleich ohne Gross/klein, Akzente und Satzzeichen, ß = ss (Fehlerbericht 09.11.2026: "Woaßt" und "Woasst")
  const key = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/ß/g, 'ss').replace(/[^\p{L}\p{N}]+/gu, '');
  function titleFirst(rows, artists) {
    let a = 0, b = 0;
    for (const r of rows) { if (artists.has(key(r.a))) a++; if (artists.has(key(r.b))) b++; }
    return b > a;
  }

  // Zuordnen (09.11.2026, auch Doppel-CDs mit durcheinander geratenen Nummern): je Datei und Zeile Punkte fuer
  //   Titel (der Titel der Zeile steckt im Dateinamen oder im Titel-Tag) 10, Laenge hoechstens 4 s daneben 4 (bis 10 s: 2), gleiche
  //   Nummer (und CD, wenn die Datei eine hat) 5; dann die besten Paare zuerst, jede Datei und jede Zeile einmal.
  //   ok (angehakt): Titel und Laenge passen, oder Nummer und Laenge, oder Nummer ohne Laengen. Nur die Laenge: Vorschlag, nicht angehakt.
  const core = s => key(String(s || '').replace(/\([^)]*\)/g, ' '));
  function assign(files, rows) {
    const anyDur = rows.some(r => r.dur);
    // Teile, die in mehreren Zeilen vorkommen (der Interpret einer CD eines Interpreten), unterscheiden nicht: nicht als Titeltreffer
    // zaehlen (Xavier Naidoo Live, 09.11.2026: "Xavier Naidoo" steht in jedem Dateinamen)
    const many = new Map();
    for (const r of rows) for (const t of new Set([core(r.a), core(r.b)])) if (t) many.set(t, (many.get(t) || 0) + 1);
    const uniq = t => t && (many.get(t) || 0) <= 1;
    const pairs = [];
    files.forEach((f, fi) => {
      const fk = key((f.name || '') + ' ' + (f.title || ''));
      rows.forEach((r, ri) => {
        const ta0 = core(r.a), tb0 = core(r.b), ta = uniq(ta0) ? ta0 : '', tb = uniq(tb0) ? tb0 : '';
        const tm = [ta, tb].some(t => t.length >= 4 && fk.includes(t)) && [ta, tb].filter(t => t.length >= 3 && fk.includes(t)).length >= 1;
        const both = [ta, tb].every(t => t.length >= 2 && fk.includes(t));
        const diff = r.dur && f.dur ? Math.abs(f.dur - r.dur) : null;
        const dm = diff != null && diff <= 4;
        // Fehlerbericht 09.11.2026 (Grand Prix 1994): Dateien bis 7 s laenger als die Liste; mit passendem Titel oder Tracknummer
        // gilt die Laenge bis 10 s (bei langen Liedern 6 %) noch als passend
        const near = diff != null && diff <= Math.max(10, 0.06 * r.dur);
        const nm = !!f.track && f.track === r.n && (!f.disc || !r.disc || f.disc === r.disc);
        // Tracknummer (5) geht vor einem Treffer nur ueber die Laenge (hoechstens 4 + 1,5), der Titel (10) vor allem
        // Musical Stars (09.11.2026): eine Datei desselben Albums mit passender Nummer geht vor einem Titeltreffer aus einem fremden Album
        const score = (both ? 12 : tm ? 10 : 0) + (dm ? 4 : near ? 2 : 0) + (nm ? (f.local !== false ? 11 : 5) : 0) - (diff != null && !near ? 6 : 0);
        // Lieder aus der ganzen Bibliothek (f.local === false) nur ueber den Titel, nie nur ueber Laenge oder Nummer
        if ((score >= 4 || (nm && (!anyDur || near))) && (f.local !== false || tm || both)) pairs.push({ fi, ri, score, diff, tm: tm || both, dm, nm, near });
      });
    });
    // Die Dateien sind oft gleichmaessig ein paar Sekunden laenger als die Liste (Stille am Ende, Kodierung): den typischen Versatz
    // aus den sicheren Paaren (Titel passt) nehmen; Paare nur ueber die Laenge zaehlen dann nur, wenn sie hoechstens 1,5 s davon abweichen
    const sure = pairs.filter(p => p.tm && p.dm).map(p => files[p.fi].dur - rows[p.ri].dur).sort((x, y) => x - y);
    const off = sure.length >= 3 ? sure[Math.floor(sure.length / 2)] : null;
    for (const p of pairs) if (!p.tm && !p.nm && p.dm && off != null) {
      p.adj = Math.abs(files[p.fi].dur - rows[p.ri].dur - off);
      if (p.adj > 1.5) p.score = -1; else p.score += 1.5 - p.adj;
    }
    pairs.sort((x, y) => y.score - x.score || (x.adj == null ? x.diff == null ? 99 : x.diff : x.adj) - (y.adj == null ? y.diff == null ? 99 : y.diff : y.adj));
    for (let i = pairs.length - 1; i >= 0; i--) if (pairs[i].score < 0) pairs.splice(i, 1);
    const fUsed = new Set(), rDone = new Map();
    for (const p of pairs) if (!fUsed.has(p.fi) && !rDone.has(p.ri)) { fUsed.add(p.fi); rDone.set(p.ri, p); }
    return rows.map((r, ri) => {
      const p = rDone.get(ri), f = p ? files[p.fi] : null;
      const away = !!f && f.local === false;            // aus einem fremden Album (Titel passt): nur Vorschlag, nicht angehakt
      const ok = !!p && !away && ((p.tm && (p.near || p.diff == null)) || (p.nm && (p.near || p.diff == null)));
      const len = p && p.diff != null ? (p.dm ? ' und Länge' : p.near ? ', Länge ' + Math.round(p.diff) + ' s daneben' : '') : '';
      return { row: r, file: f, diff: p ? p.diff : null, ok, why: !p ? '' : (p.tm ? 'Titel' + len : p.nm ? 'Nummer' + len : 'nur die Länge') + (away ? ' (anderes Album)' : '') };
    });
  }

  // Kandidaten aus der ganzen Bibliothek (Wunsch 09.11.2026: die Lieder einer CD liegen oft verstreut): gleiches Album im Tag
  // (local, darf auch nur ueber die Laenge passen) oder Titel und Interpret einer Zeile im Titel/Dateinamen.
  // lib = Lieder wie /api/musik (path, file, name, artist, dur, album, track), root = Musikordner.
  function libCandidates(lib, rows, album, root, skip) {
    // Album ohne "Vol."/"Volume" vergleichen: "Future Trance Vol. 13" = "Future Trance 13"
    const ak0 = s => key(String(s || '').replace(/\b(vol(ume)?|teil|part)\b\.?/gi, ' '));
    const ak = ak0(album), out = [], R = String(root || '').replace(/\/+$/, '');
    const keys = rows.map(r => [core(r.a), core(r.b)]);
    for (const t of lib || []) {
      if (!t.path || (skip && skip.has(t.path))) continue;
      const K = key((t.name || '') + ' ' + (t.file || '')), KA = key((t.artist || '') + ' ' + (t.file || ''));
      const same = ak.length >= 4 && ak0(t.album) === ak;
      const hit = !same && keys.some(([a, b]) => (a.length >= 4 && K.includes(a) && b.length >= 3 && KA.includes(b.slice(0, 6))) ||
                                                 (b.length >= 4 && K.includes(b) && a.length >= 3 && KA.includes(a.slice(0, 6))));
      if (!same && !hit) continue;
      const rel = R && t.path.startsWith(R + '/') ? t.path.slice(R.length + 1) : t.path;
      out.push({ path: t.path, rel, name: t.file || rel.split('/').pop(), dur: t.dur || 0, track: parseInt(t.track, 10) || 0, disc: 0,
        title: t.name || '', artist: t.artist || '', album: t.album || '', mp3: /\.mp3$/i.test(t.path), local: same, elsewhere: true });
    }
    return out;
  }

  // Das Album, aus dem die meisten Titeltreffer stammen (mindestens 3 und ein Drittel der Zeilen), sonst ''
  function albumGuess(match, n) {
    const c = new Map();
    for (const x of match) if (x.file && x.file.album && /^Titel/.test(x.why || '')) {
      const k = key(x.file.album); const e = c.get(k) || { name: x.file.album, n: 0 }; e.n++; c.set(k, e);
    }
    const best = [...c.values()].sort((a, b) => b.n - a.n)[0];
    return best && best.n >= Math.max(3, n / 3) ? best.name : '';
  }

  // Erste Zeile "Xavier Naidoo Nicht Von Dieser Welt": bekannten Interpreten vorne abtrennen -> [Interpret, Album] oder null
  function splitArtist(line, artists) {
    const w = String(line || '').trim().split(/\s+/);
    for (let i = Math.min(w.length - 1, 6); i >= 1; i--) {
      const a = w.slice(0, i).join(' ');
      if (artists.has(key(a))) return [a, w.slice(i).join(' ').replace(/^[-–—:\s]+/, '')];
    }
    return null;
  }
  // Zeilen ohne Interpret bekommen den Album-Interpreten (fuer Zuordnen und Schreiben)
  const withArtist = (rows, aa) => rows.map(r => r.a ? r : Object.assign({}, r, { a: aa || '' }));

  function plan(match, o) {
    // o = {swap, cover, perf, artist}: Interpret und Titel je Zeile; artist = Interpret fuer Zeilen ohne Interpret
    return match.map(m => {
      if (m.row.solo) return Object.assign({}, m, { artist: o.artist || m.row.a || '', title: m.row.b });
      let artist = o.swap ? m.row.b : m.row.a, title = o.swap ? m.row.a : m.row.b;
      artist = artist.replace(/\s+\(\d+\)$/, '');                 // Discogs: "Sunchild (2)" = zweiter Interpret dieses Namens
      if (o.cover && o.perf) { title = title + ' (' + artist + ')'; artist = o.perf; }
      return Object.assign({}, m, { artist, title });
    });
  }
  W.CD = { parseList, titleFirst, assign, plan, cleanText, key, libCandidates, albumGuess, splitArtist, withArtist };
  if (typeof document === 'undefined') return;

  // ---- Seite ------------------------------------------------------------------------------------------------------------
  const $ = id => document.getElementById(id), esc = SM.esc;
  let music = '', folder = null, parsed = null, rowsP = [], artists = new Set(), on = new Set(), lib = [], root = '', playing = '', ready = false, chkMsg = '';
  const audio = new Audio();
  const pbar = SM.playBar(audio, { onclose: () => { playing = ''; draw(); } });   // Leiste unten: springen, Lautstaerke (09.11.2026)
  const mmss = s => s ? Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0') : '';
  const dirOf = rel => String(rel || '').split('/').slice(0, -1).join('/');
  async function mac(path, body) {
    if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer?');
    const r = await fetch(music + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
    if (r.status === 404 || !d || d.state === 'off') throw new Error('Am Musik-Rechner läuft noch die alte Fassung: Helfer oder Mixxx-App neu installieren (./deploy.sh alles).');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }
  async function loadLib() {
    try {
      const d = await fetch('/api/musik').then(r => r.json());
      lib = (d.tracks || []).filter(t => t.path);
      root = d.root || '';
      if (!music) music = d.music || '';
      artists = new Set(lib.map(t => key(t.artist)).filter(Boolean));     // Reihenfolge der Liste erraten
    } catch (e) { $('cmsg').textContent = 'Liedliste vom Light-Butler nicht geladen: ' + e.message; }
    try {
      const d = await mac('/cd');
      if (!root && d.root) root = d.root;        // Musikordner, wenn er am Pi nicht eingestellt ist
      $('dirs').innerHTML = (d.dirs || []).map(([p, n]) => '<option value="' + esc(p) + '">' + n + ' Lieder</option>').join('');
    } catch (e) { /* Ordnerauswahl ist Beiwerk */ }
  }
  async function loadFolder() {
    const d = $('dir').value.trim();
    folder = null;
    $('finfo').textContent = d ? '' : 'Ohne Ordner sucht der Assistent in der ganzen Bibliothek.';
    if (!d) { if (parsed) build(); return; }
    $('cmsg').textContent = '';
    try {
      folder = await mac('/cd?d=' + encodeURIComponent(d));
      const fs = folder.files || [];
      const ex = fs.filter(f => f.elsewhere).length;
      $('finfo').innerHTML = fs.length ? '<b>' + (fs.length - ex) + '</b> Lieder im Ordner' + (ex ? ' und <b>' + ex + '</b> mit demselben Album in anderen Ordnern' : '') +
        (fs[0] && fs[0].album ? ' · Album im Tag: ' + esc(fs[0].album) : '') : 'Keine Lieder der Bibliothek in diesem Ordner.';
      if (!$('album').value && fs[0] && fs[0].album) $('album').value = fs[0].album;
      if (parsed) build();
    } catch (e) { $('cmsg').textContent = e.message; }
  }
  function destTop() {                         // oberster Ordner fuer den neuen Ordner: der gewaehlte, sonst der haeufigste der Lieder
    if (folder && folder.dir) return folder.dir.split('/')[0];
    const c = {};
    for (const x of rowsP) if (x.file && on.has(rowsP.indexOf(x))) { const t = (x.file.rel || '').split('/')[0]; c[t] = (c[t] || 0) + 1; }
    return Object.keys(c).sort((a, b) => c[b] - c[a])[0] || '';
  }
  function destName() { const t = destTop(), a = $('album').value.trim(); return t && a ? t + '/Compilations/' + a : ''; }
  function build() {
    if (!parsed) return;
    // Dateien im gewaehlten Ordner zaehlen voll; die mit gleichem Album aus anderen Ordnern nur ueber den Titel und nicht angehakt
    // (Xavier Naidoo Live, 09.11.2026: das Studio-Album im Ordner darueber hat dasselbe Album im Tag)
    const own = (folder && folder.files || []).map(f => Object.assign({}, f, { local: !f.elsewhere }));
    const skip = new Set(own.map(f => f.path));
    const aa = $('aart').value.trim(), rows = CD.withArtist(parsed.rows, /^various artists$/i.test(aa) ? '' : aa);
    let more = CD.libCandidates(lib, rows, $('album').value.trim() || parsed.album, root, skip);
    let m = CD.assign(own.concat(more), rows);
    // Album selbst finden (Musical Stars, 09.11.2026): stammen viele Titeltreffer aus einem Album, das anders heisst als im
    // Feld ("MUSICAL STARS Volume 1" statt "Musical Stars Mit Den Deutschen Original-Künstlern"), dieses Album nehmen
    // nur wenn das Album nicht ausdruecklich in der Liste steht ("Album: Live" bleibt, Xavier Naidoo 09.11.2026)
    const guess = parsed.albumSure ? '' : CD.albumGuess(m, parsed.rows.length);
    if (guess && key(guess) !== key($('album').value)) {
      $('album').value = guess;
      more = CD.libCandidates(lib, rows, guess, root, skip);
      m = CD.assign(own.concat(more), rows);
      $('pinfo').textContent += ' · Album aus deinen Dateien übernommen: ' + guess;
    }
    rowsP = CD.plan(m, { swap: $('swap').checked, cover: $('cover').checked, perf: $('perf').value.trim(), artist: /^various artists$/i.test(aa) ? '' : aa });
    on = new Set(rowsP.map((x, i) => x.ok ? i : -1).filter(i => i >= 0));
    draw();
  }
  function draw() {
    $('meta').hidden = $('prev').hidden = !rowsP.length;
    $('mdest').textContent = destName() || '(Album fehlt)';
    const nf = rowsP.filter(x => x.file).length, bad = rowsP.filter(x => x.file && !x.ok).length;
    const dirs = new Set(rowsP.filter(x => x.file).map(x => dirOf(x.file.rel)));
    $('sum').innerHTML = '<b>' + nf + '</b> von ' + rowsP.length + ' Liedern gefunden' + (dirs.size > 1 ? ', in <b>' + dirs.size + '</b> Ordnern' : '') +
      (bad ? ' · <span class="warn">' + bad + ' nur über die Länge oder unsicher: erst anhören (nicht angehakt)</span>' : '');
    $('tb').innerHTML = rowsP.map((x, i) => {
      const f = x.file, pl = f && playing === f.path && !audio.paused;
      const name = (x.artist + ' - ' + x.title).replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim() + '.mp3';
      return '<tr class="' + (on.has(i) ? '' : 'off') + '"><td><input type="checkbox" data-on="' + i + '"' + (on.has(i) ? ' checked' : '') + (f ? '' : ' disabled') + '></td>' +
        '<td class="num">' + (x.row.disc ? x.row.disc + '-' : '') + x.row.n + (x.why ? '<div class="' + (x.ok ? 'dim' : 'warn') + '" style="font-size:11px">' + esc(x.why) + '</div>' : '') + '</td>' +
        '<td>' + (f ? '<button class="pb' + (pl ? ' on' : '') + '" data-play="' + esc(f.path) + '" title="Anhören">' + (pl ? '❚❚' : '▶') + '</button>' : '') + '</td>' +
        '<td>' + (f ? '<div class="old">' + esc(f.name) + (f.mp3 ? '' : ' <span class="warn">keine MP3: nur umbenennen</span>') + '</div><div class="dir">' + esc(dirOf(f.rel)) + '</div>'
          : '<span class="dim">nicht in der Bibliothek gefunden</span>') + '</td>' +
        '<td class="num">' + (f ? mmss(f.dur) : '') + (x.row.dur ? '<div class="' + (x.ok ? 'dim' : 'warn') + '">Liste ' + mmss(x.row.dur) + '</div>' : '') + '</td>' +
        '<td><input type="text" data-a="' + i + '" value="' + esc(x.artist) + '"></td><td><input type="text" data-t="' + i + '" value="' + esc(x.title) + '"></td>' +
        '<td><span class="new">' + esc(name) + '</span></td></tr>';
    }).join('');
    $('ginfo').textContent = on.size + ' angehakt' + (ready ? '' : ' · ' + (chkMsg || 'Vorbereitung läuft …'));
    $('bgo').disabled = !on.size;      // fehlt die Pruefung beim Schreiben, macht der Mac sie selbst (09.11.2026)
  }
  // Vor dem Schreiben muss die Dateipruefung fertig sein (sonst koennten Namen doppelt werden). Wunsch 09.11.2026: nicht erst
  // auf einer anderen Seite "Pruefen" druecken, der Assistent startet sie selbst und wartet.
  async function ensureCheck() {
    try {
      let st = await mac('/check');
      if (st.state === 'idle') { await mac('/check', { op: 'scan' }); st = await mac('/check'); }
      ready = st.state === 'ready';
      chkMsg = ready ? '' : st.state === 'wait' ? 'Vorbereitung: der Musik-Rechner liest noch die Tags der Dateien …' : 'Vorbereitung: Dateinamen werden geprüft (' + (st.done || 0) + ' Dateien) …';
      if (!ready) setTimeout(ensureCheck, 2000);
    } catch (e) { chkMsg = e.message; ready = false; setTimeout(ensureCheck, 10000); }
    if ($('prev') && !$('prev').hidden) draw();
  }
  function playPath(p) {
    if (!music) return;
    if (playing === p && !audio.paused) { audio.pause(); draw(); return; }
    if (playing !== p) { playing = p; audio.src = music + '/audio?p=' + encodeURIComponent(p); }
    audio.play().catch(e => { $('cmsg').textContent = 'Abspielen ging nicht: ' + e.message; });
    pbar.show(String(p).split('/').pop());
  }
  audio.addEventListener('play', draw); audio.addEventListener('pause', draw); audio.addEventListener('ended', draw);
  $('bload').onclick = loadFolder;
  $('dir').addEventListener('change', loadFolder);
  $('bparse').onclick = async () => {
    parsed = CD.parseList($('list').value);
    if (!parsed.rows.length) { $('pinfo').textContent = 'Keine Zeilen mit Tracknummer gefunden (Form: „1. Titel – Interpret“ oder „1 Interpret – Titel 5:42“).'; return; }
    if (!lib.length) await loadLib();
    $('swap').checked = CD.titleFirst(parsed.rows, artists);
    if (parsed.album) $('album').value = parsed.album;
    if (parsed.dir && !$('dir').value.trim()) { $('dir').value = parsed.dir; folder = null; }   // Ordner aus der Liste
    if (parsed.artist) $('aart').value = parsed.artist;
    else if (parsed.rows.every(r => r.solo)) {           // CD eines Interpreten: Interpret aus der ersten Zeile abtrennen
      const sp = CD.splitArtist(parsed.album, artists);
      if (sp) { $('aart').value = sp[0]; $('album').value = sp[1] || parsed.album; }
      else if (/^various artists$/i.test($('aart').value)) $('aart').value = '';
    }
    if (parsed.year) $('year').value = parsed.year;
    if (parsed.performer) $('perf').value = parsed.performer;
    $('pinfo').textContent = parsed.rows.length + ' Zeilen erkannt' + (parsed.discs ? ' auf ' + parsed.discs + ' CDs' : '') + ($('swap').checked ? ', zuerst Titel (erraten, unten änderbar)' : ', zuerst Interpret');
    if ($('dir').value.trim() && !folder) await loadFolder();
    build();
  };
  for (const id of ['swap', 'cover', 'perf']) $(id).addEventListener(id === 'perf' ? 'input' : 'change', build);
  $('album').addEventListener('input', () => { if (parsed) parsed.albumSure = true; });   // selbst getippt: nie mehr erraten (09.11.2026, „Live“)
  $('album').addEventListener('change', build);
  $('aart').addEventListener('change', build);          // Interpret fuer Zeilen ohne Interpret (CD eines Interpreten)
  $('tb').addEventListener('click', e => { const b = e.target.closest('button[data-play]'); if (b) playPath(b.dataset.play); });
  $('tb').addEventListener('change', e => {
    const c = e.target.closest('input[data-on]');
    if (c) { if (c.checked) on.add(+c.dataset.on); else on.delete(+c.dataset.on); draw(); }
  });
  $('tb').addEventListener('input', e => {
    const a = e.target.closest('input[data-a]'), t = e.target.closest('input[data-t]');
    if (a) rowsP[+a.dataset.a].artist = a.value;
    if (t) rowsP[+t.dataset.t].title = t.value;
  });
  $('bgo').onclick = async () => {
    const per = d => parsed.rows.filter(r => r.disc === d).length;   // Tracks je CD (Doppel-CD: 1/20, CD 1/2)
    const items = rowsP.filter((x, i) => on.has(i) && x.file).map(x => ({ path: x.file.path, artist: x.artist.trim(), title: x.title.trim(), track: x.row.n,
      total: per(x.row.disc), disc: x.row.disc || 0, discs: parsed.discs || 0 }));
    if (!items.length) { $('cmsg').textContent = 'Nichts angehakt.'; return; }
    if ($('move').checked && !destName()) { $('cmsg').textContent = 'Für den eigenen Ordner fehlt das Album.'; return; }
    const b = $('bgo');
    b.disabled = true; b.textContent = ready ? 'Schreibe …' : 'Prüfe und schreibe … (ein, zwei Minuten)';
    audio.pause();
    try {
      const d = await mac('/cd', { plan: { dir: folder ? folder.dir : '', top: destTop(), move: $('move').checked, album: $('album').value.trim(), albumartist: $('aart').value.trim(),
        year: $('year').value.trim(), genre: $('genre').value.trim(), items } });
      for (const x of d.done || []) {
        if (x.new_path !== x.old_path) SM.cmd('path_moved', { old: x.old_path, new: x.new_path }).catch(() => {});   // Cover, Cue-Punkte am Pi mit
        SM.cmd('cover_refresh', { path: x.new_path }).catch(() => {});
      }
      $('cmsg').innerHTML = '✓ ' + (d.done || []).length + ' Lieder geschrieben' + (d.errors && d.errors.length ? ', <span class="bad">' + d.errors.length + ' Fehler: ' +
        esc(d.errors.map(x => x.error).join('; ')) + '</span>' : '') + (d.dir ? '. Ordner: ' + esc(d.dir) : '') + '. Mixxx übernimmt die Namen beim nächsten Start der App.';
      rowsP = []; draw();
      // fertig (Wunsch 09.11.2026): Eingaben fuer die naechste CD leeren
      if ((d.done || []).length && !(d.errors || []).length) {
        $('list').value = ''; parsed = null; folder = null; $('dir').value = ''; $('pinfo').textContent = '';
        for (const id of ['album', 'year', 'genre', 'perf']) $(id).value = '';
        $('aart').value = 'Various Artists';
        for (const id of ['swap', 'cover', 'move']) $(id).checked = false;
        $('finfo').textContent = 'Bereit für die nächste CD.';
      }
    } catch (e) { $('cmsg').textContent = e.message; }
    b.disabled = false; b.textContent = 'Angehakte schreiben';
  };
  const dq = new URLSearchParams(location.search).get('d');
  if (dq) $('dir').value = dq;
  ensureCheck();
  loadLib().then(() => { if (dq) loadFolder(); else $('finfo').textContent = 'Freiwillig. Ohne Ordner sucht der Assistent die Lieder in der ganzen Bibliothek (über Titel und Interpret oder das Album).'; });
})();
