// Musik-Datenbank: Lieder nach Interpret, Genre oder Energie gruppieren (Wunsch von Markus, 08.11.2026).
// Nur reine Funktionen ohne Seite, damit tests/test_musik_gruppen.py sie mit node pruefen kann.
// Eingabe sind die gefilterten und sortierten Lieder der Tabelle; jede Gruppe behaelt diese Reihenfolge.
(function (root) {
  const norm = s => String(s || '').normalize('NFC').toLowerCase().trim().replace(/\s+/g, ' ');

  // Hauptinterpret: "Avicii feat. Aloe Blacc" und "Avicii ft Aloe Blacc" -> "Avicii". "Simon & Garfunkel" bleibt ganz.
  function mainArtist(a) {
    let s = String(a || '').trim();
    s = s.replace(/\s*[(\[]\s*(feat\.?|ft\.?|featuring|with)\s.*$/i, '');               // "Lied (feat. X)" im Interpret
    s = s.replace(/\s+(feat\.?|ft\.?|featuring|vs\.?|x)\s+.*$/i, '');
    return s.trim();
  }

  // Buchstabe fuer die A-Z-Leiste: Umlaute zum Grundbuchstaben, "The " zaehlt nicht, Ziffern und Zeichen = "#"
  function letter(name) {
    const s = String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/^THE\s+/, '');
    const c = s.charAt(0);
    return c >= 'A' && c <= 'Z' ? c : '#';
  }
  const byName = (a, b) => (letter(a) === '#') - (letter(b) === '#') || plain(a).localeCompare(plain(b));   // Ziffern und Zeichen nach Z
  const plain = name => norm(String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/^the\s+/i, ''));

  const NONE = { art: '(ohne Interpret)', gen: '(ohne Genre)', lvl: 'ohne Energie', kl: '(in keiner Kiste oder Liste)', alb: '(ohne Album)', grp: '(ohne Gruppe)' };

  // Schluessel und Anzeigename eines Liedes in der Ansicht mode ('art', 'gen', 'lvl')
  function keyOf(r, mode) {
    if (mode === 'lvl') { const e = Math.min(9, +r.lvl || 0); return [String(e), e ? 'Energie ' + e : NONE.lvl]; }
    const raw = mode === 'art' ? mainArtist(r.artist) : mode === 'alb' ? String(r.album || '').trim() : String(r.genre || '').trim();
    const k = norm(raw);
    return k ? [k, raw] : ['', NONE[mode]];
  }

  // Kisten/Listen (08.11.2026): ein Lied steht in so vielen Gruppen, wie es Kisten und Wiedergabelisten in Mixxx hat.
  // Schluessel 'L:Name' = Wiedergabeliste, 'K:Name' = Plattenkiste.
  function keysOf(r, mode) {
    if (mode === 'grp') {                    // Gruppe aus dem Tag (10.11.2026): mehrere mit ";" getrennt, z. B. "Hopeful; Lizenzfrei"
      const seen = new Set(), out = [];
      for (const raw of String(r.grp || '').split(';').map(s => s.trim()).filter(Boolean)) { const k = norm(raw); if (!seen.has(k)) { seen.add(k); out.push([k, raw]); } }
      return out.length ? out : [['', NONE.grp]];
    }
    if (mode !== 'kl') return [keyOf(r, mode)];
    const out = (r.lists || []).map(n => ['L:' + norm(n), n]).concat((r.crates || []).map(n => ['K:' + norm(n), n]));
    return out.length ? out : [['', NONE.kl]];
  }
  const kind = k => k.slice(0, 2) === 'L:' ? 'Liste' : k.slice(0, 2) === 'K:' ? 'Kiste' : '';

  // Gruppen: [{key, name, letter, n, dur, songs, top}] - top = haeufigstes Genre (Interpreten) bzw. Zahl der Interpreten
  function group(rows, mode) {
    const by = new Map();
    for (const r of rows) {
      for (const [k, name] of keysOf(r, mode)) {
        let g = by.get(k);
        if (!g) { g = { key: k, names: {}, songs: [], dur: 0, sub: {} }; by.set(k, g); }
        if (g.songs[g.songs.length - 1] === r) continue;            // zweimal in derselben Kiste
        g.names[name] = (g.names[name] || 0) + 1;
        g.songs.push(r);
        g.dur += +r.dur || 0;
        const sub = mode === 'art' ? String(r.genre || '').trim() : mode === 'alb' ? mainArtist(r.artist) : norm(mainArtist(r.artist));
        if (sub) g.sub[sub] = (g.sub[sub] || 0) + 1;
      }
    }
    const out = [];
    for (const g of by.values()) {
      const name = Object.keys(g.names).sort((a, b) => g.names[b] - g.names[a] || (b !== b.toLowerCase()) - (a !== a.toLowerCase()) || a.localeCompare(b))[0];   // haeufigste Schreibweise, bei Gleichstand die mit Grossbuchstaben
      const subs = Object.keys(g.sub);
      // Alben (Wunsch 09.11.2026): Lieder nach CD und Track, dazu der Interpret (einer) oder die Zahl der Interpreten (Sampler)
      if (mode === 'alb') g.songs.sort((a, b) => (parseInt(a.disc, 10) || 0) - (parseInt(b.disc, 10) || 0) || (parseInt(a.track, 10) || 999) - (parseInt(b.track, 10) || 999));
      out.push({ key: g.key, name, kind: kind(g.key), letter: g.key ? letter(name) : '#', n: g.songs.length, dur: g.dur, songs: g.songs,
        top: mode === 'art' ? (subs.sort((a, b) => g.sub[b] - g.sub[a] || a.localeCompare(b))[0] || '') : mode === 'alb' && subs.length === 1 ? subs[0] : subs.length });
    }
    // Reihenfolge: Interpreten A-Z, Listen und Kisten A-Z, Genres A-Z (Wunsch 08.11.2026), Energie 9 bis 1; die Gruppe "ohne" immer unten
    out.sort((a, b) => {
      if (!a.key !== !b.key) return a.key ? -1 : 1;
      if (mode === 'art') return byName(a.name, b.name);
      if (mode === 'gen' || mode === 'alb' || mode === 'grp') return byName(a.name, b.name);
      if (mode === 'kl') return (a.kind === 'Kiste') - (b.kind === 'Kiste') || byName(a.name, b.name);   // erst Listen, dann Kisten
      return +b.key - +a.key;
    });
    if (mode === 'lvl') { const z = out.findIndex(g => g.key === '0'); if (z >= 0) out.push(out.splice(z, 1)[0]); }
    return out;
  }

  // Gesamtdauer kurz: "52 min", "4 h 12 min"
  function hm(sec) {
    const m = Math.round((sec || 0) / 60);
    return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
  }

  // Alle Kisten und Listen der Bibliothek fuer die Auswahl im Filter: [{key, name, kind, n}]
  const lists = rows => group(rows, 'kl').filter(g => g.key);

  root.MG = { mainArtist, letter, keyOf, keysOf, group, lists, hm, NONE };
})(typeof window !== 'undefined' ? window : globalThis);
