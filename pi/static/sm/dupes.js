// dupes.js - Seite /musik/doppelte: doppelte Lieder vergleichen und aufraeumen (Wunsch von Markus, 07.11.2026).
// Die Gruppen und die Angaben je Datei kommen vom Mac (dupes.py in der Mixxx-Bruecke, /dupes), Shows und Kurven vom Pi.
// Je Gruppe wird die beste Datei behalten (MP3 vor MP4/WAV, Bitrate, Abtastrate, Cover, Tags, Hotcues, Energie, Mixxx,
// Show), die anderen werden zum Loeschen vorgeschlagen, aber nur, wenn sie direkt zur behaltenen passen (gleicher
// Fingerabdruck oder gleicher Name bzw. Interpret und Titel bei fast gleicher Laenge). Geloescht wird nur auf Klick, in den
// Papierkorb des Mac (/trash, wie der Mistkuebel), also wiederherstellbar.
(function (root) {
  'use strict';
  const DUR_TOL = 3;
  const numbered = p => /^\d{1,3}\s*[-._)]\s*/.test(String(p || '').split('/').pop());   // "11 - Lied.mp3", "03. Lied.mp3"
  const mmss = d => { d = Math.round(d || 0); return Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0'); };

  // Punkte einer Datei: je mehr, desto eher behalten
  function score(f, pi) {
    if (!f.exists) return -1000;
    let s = f.ext === 'mp3' ? 100 : 0;
    s += Math.min(f.kbps || 0, 320) / 10 + (f.rate >= 44100 ? 5 : 0) + (f.cover ? 20 : 0) + (f.tags || 0) * 3 + Math.min(f.cues || 0, 8) * 2;
    s += (f.lvl ? 5 : 0) + (f.mixxx ? 10 : 0);
    if (pi) s += (pi.show ? 30 : 0) + (pi.stems ? 10 : 0);
    s += Math.min(f.dur || 0, 10000) * 0.02 + (f.size || 0) / 1e9;   // bei sonst Gleichem: laenger (nicht abgeschnitten), dann groesser
    if (!numbered(f.path)) s += 0.01;                          // dann: Dateiname ohne Tracknummer vorne (Wunsch 07.11.2026)
    return s;
  }
  // passt direkt zur behaltenen Datei (nicht nur ueber eine Kette in derselben Gruppe)?
  const dirOf = p => String(p || '').replace(/\/[^/]*$/, '');
  // Gegenbeweis aus den Tags (Fehlerbericht 07.11.2026, Bellini "Samba De Janeiro (Reprise)": drei Lieder, gleiche Titel-Tags):
  // dasselbe Lied hat dieselbe Tonart und dasselbe Tempo; gleiches Album mit anderer Tracknummer ist ein anderes Stueck
  const PC = { C: 0, 'C#': 1, DB: 1, D: 2, 'D#': 3, EB: 3, E: 4, F: 5, 'F#': 6, GB: 6, G: 7, 'G#': 8, AB: 8, A: 9, 'A#': 10, BB: 10, B: 11, H: 11 };
  const CAM_MAJ = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1], CAM_MIN = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10];
  function camelot(v) {                                       // "8A", "Am", "A minor", "F#m" -> Camelot, sonst ''
    const t = String(v || '').trim().toUpperCase().replace('♯', '#').replace('♭', 'B');
    let m = /^(\d{1,2})([AB])$/.exec(t);
    if (m) return +m[1] + m[2];
    m = /^([A-H][#B]?)\s*(M|MIN|MINOR|MOLL)?(\s*(MAJ|MAJOR|DUR))?$/.exec(t);
    if (!m || PC[m[1]] == null) return '';
    return m[2] ? CAM_MIN[PC[m[1]]] + 'A' : CAM_MAJ[PC[m[1]]] + 'B';
  }
  function differs(a, k) {
    const at = a.tv || {}, kt = k.tv || {};
    const ka = camelot(at.key), kk = camelot(kt.key);
    if (ka && kk && ka !== kk) return true;
    const ba = parseFloat(at.bpm), bk = parseFloat(kt.bpm);
    if (ba > 0 && bk > 0) {
      const r = Math.max(ba, bk) / Math.min(ba, bk);
      if (Math.abs(r - 1) > 0.012 && Math.abs(r - 2) > 0.024) return true;   // mehr als gut 1 % (doppelt/halb zaehlt als gleich)
    }
    const tn = v => parseInt(String(v || '').split('/')[0], 10) || 0;
    const al = v => String(v || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
    if (al(at.album) && al(at.album) === al(kt.album) && tn(at.track) && tn(kt.track) && tn(at.track) !== tn(kt.track)) return true;
    return false;
  }
  function same(a, k) {
    if (a.fp && a.fp === k.fp) return 'gleich';
    if (dirOf(a.path) === dirOf(k.path) && a.sk !== k.sk) return '';   // Album mit gleichen Tags je Lied (01, 07, 08): verschiedene Lieder
    if (differs(a, k)) return '';                             // Tags widersprechen (Tonart, BPM, Track auf demselben Album)
    const near = !a.dur || !k.dur || Math.abs(a.dur - k.dur) <= DUR_TOL;
    if (near && ((a.sk && a.sk === k.sk) || (a.tk && a.tk === k.tk))) return 'dasselbe Lied';
    return '';
  }
  // Gruende, warum die behaltene besser ist (fuer die zu loeschende Datei)
  function reasons(a, k, pa, pk) {
    const r = [];
    if (k.ext === 'mp3' && a.ext !== 'mp3') r.push('MP3 statt ' + a.ext.toUpperCase());
    if ((k.kbps || 0) > (a.kbps || 0) + 16) r.push(k.kbps + ' statt ' + (a.kbps || '?') + ' kbit/s');
    if (a.rate && a.rate < 44100 && k.rate >= 44100) r.push((k.rate / 1000) + ' statt ' + (a.rate / 1000) + ' kHz');   // 48 gegen 44,1 kHz zaehlt nicht (klanglich gleich)
    if (k.cover && !a.cover) r.push('hat Cover');
    if ((k.tags || 0) > (a.tags || 0)) r.push('mehr Tags (' + k.tags + ' statt ' + (a.tags || 0) + ')');
    if ((k.cues || 0) > (a.cues || 0)) r.push(k.cues + ' statt ' + (a.cues || 0) + ' Hotcues');
    if (k.lvl && !a.lvl) r.push('hat Energiestufe');
    if (k.mixxx && !a.mixxx) r.push('steht in Mixxx');
    if (pk && pk.show && !(pa && pa.show)) r.push('hat Show');
    if (numbered(a.path) && !numbered(k.path) && Math.abs((k.dur || 0) - (a.dur || 0)) < 1) r.push('Dateiname ohne Tracknummer');
    if ((k.dur || 0) - (a.dur || 0) >= 1) r.push('länger (' + mmss(k.dur) + ' statt ' + mmss(a.dur) + ')');   // Wunsch 07.11.2026: vollstaendiger
    return r;
  }
  // Tag-Inhalte (Wunsch 07.11.2026): was die zu loeschende Datei mehr hat (wird vor dem Loeschen uebernommen) und was anders ist
  const TAGL = { title: 'Titel', artist: 'Interpret', album: 'Album', albumartist: 'Album-Interpret', year: 'Jahr', track: 'Track', disc: 'CD',
    genre: 'Genre', bpm: 'BPM', key: 'Tonart', composer: 'Komponist', publisher: 'Verlag', isrc: 'ISRC' };
  const tnorm = v => String(v || '').toLowerCase().replace(/[^a-z0-9äöüß]+/g, '');
  function tagDiff(a, k) {
    const at = a.tv || {}, kt = k.tv || {}, take = {}, diff = [];
    for (const key of Object.keys(TAGL)) {
      if (at[key] && !kt[key]) take[key] = at[key];
      else if (at[key] && kt[key] && tnorm(at[key]) !== tnorm(kt[key])) {
        if (key === 'bpm' && Math.abs(parseFloat(at[key]) - parseFloat(kt[key])) < 1) continue;   // 113.426 gegen 113.42: gleich
        diff.push(TAGL[key] + ': ' + at[key] + ' (behalten: ' + kt[key] + ')');
      }
    }
    if (!kt.track && !take.track && numbered(a.path)) {      // Nummer nur im Dateinamen ("11 - ..."): als Track uebernehmen (Wunsch 07.11.2026)
      const n = String(a.path).split('/').pop().match(/^(\d{1,3})/)[1];
      if (parseInt(n, 10) > 0) take.track = String(parseInt(n, 10));
    }
    return { take, diff };
  }
  // Empfehlung fuer eine Gruppe: {keep: Index, del: vorab angehakt, sug: Vorschlag ohne Haken (gleichwertig), why: {Index: Text}, rel}
  function plan(g, piOf, keep) {
    const sc = g.map(f => score(f, piOf(f.path)));
    if (keep == null) keep = sc.indexOf(Math.max.apply(null, sc));
    const k = g[keep], del = new Set(), sug = new Set(), why = {}, rel = {};
    g.forEach((f, i) => {
      if (i === keep) return;
      rel[i] = same(f, k);
      const pa = piOf(f.path);
      if (!f.exists) { why[i] = 'Datei fehlt im Ordner'; return; }
      if (!rel[i]) { why[i] = 'anderes Lied oder andere Länge, kein Vorschlag'; return; }
      if (pa && pa.show) { why[i] = 'hat eine Show, darum nicht vorgeschlagen'; return; }
      const r = reasons(f, k, pa, piOf(k.path));
      if (r.length || rel[i] === 'gleich') del.add(i);          // vorab angehakt nur, wenn die behaltene wirklich besser oder gleich ist
      else sug.add(i);
      why[i] = r.length ? 'Die behaltene ist besser: ' + r.join(', ') : rel[i] === 'gleich' ? 'genau dieselbe Musik' : 'gleichwertig: selbst entscheiden';
      if ((f.dur || 0) - (k.dur || 0) >= 1) why[i] += ' · Achtung: diese ist ' + Math.round(f.dur - k.dur) + ' s länger';   // vielleicht vollstaendiger
    });
    return { keep, del, sug, why, rel, score: sc };
  }
  const api = { score, same, reasons, plan, tagDiff, differs };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; return; }
  root.Dupes = api;

  // ---- Seite ----
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mb = n => (n / 1048576).toLocaleString('de-AT', { maximumFractionDigits: n < 10485760 ? 1 : 0 }) + ' MB';
  let music = '', groups = [], pi = {}, filt = 'sug', q = '', busy = false, page = 0;
  const PAGE = 20;                                            // Gruppen je Seite (Wunsch 07.11.2026: in Haeppchen abarbeiten)
  const keepOf = new Map(), mark = new Map(), gone = new Set();
  let done = 0;                                               // in dieser Sitzung abgearbeitete Gruppen   // Gruppe -> Index behalten; Pfad -> angehakt; geloeschte Pfade
  const audio = new Audio();
  const pbar = SM.playBar(audio);                            // Leiste unten: springen, Lautstaerke (09.11.2026)
  const piOf = p => pi[p];

  function gkey(g) { return g.map(f => f.path).sort().join('|'); }
  function groupPlan(g) { return plan(g, piOf, keepOf.has(gkey(g)) ? keepOf.get(gkey(g)) : null); }
  function isMarked(f, pl, i) { return mark.has(f.path) ? mark.get(f.path) : pl.del.has(i); }

  function fileRow(g, gi, f, i, pl) {
    const p = piOf(f.path) || {}, k = i === pl.keep, del = !k && isMarked(f, pl, i);
    const parts = f.path.split('/'), name = parts.pop(), dir = parts.join('/');   // ganzer Ordner (Wunsch 07.11.2026)
    const facts = [f.ext.toUpperCase(), f.kbps ? f.kbps + ' kbit/s' : '', f.rate ? (f.rate / 1000) + ' kHz' : '', mmss(f.dur),
      f.cover ? '<span class="good">Cover</span>' : '<span class="bad">kein Cover</span>', f.size ? mb(f.size) : '', 'Tags ' + (f.tags || 0) + '/8', (f.cues || 0) + ' Hotcues',
      f.lvl ? 'E' + f.lvl : '', f.mixxx ? 'Mixxx' : 'nur Ordner', p.show ? '<span class="good">Show</span>' : '', p.stems ? 'Kurven' : ''].filter(Boolean).join(' · ');
    return '<div class="frow' + (gone.has(f.path) ? ' gone' : k ? ' keep' : del ? ' del' : '') + '" data-g="' + gi + '" data-i="' + i + '">' +
      '<div><input type="radio" name="k' + gi + '" class="fkeep"' + (k ? ' checked' : '') + ' title="diese Datei behalten"><div class="klab">behalten</div></div>' +
      '<div style="text-align:center">' + (k ? '<span class="klab">–</span>' : '<input type="checkbox" class="fdel"' + (del ? ' checked' : '') + (f.exists && !gone.has(f.path) ? '' : ' disabled') + ' title="in den Papierkorb"><div class="klab">löschen</div>') + '</div>' +
      '<div class="fbtns"><button class="pb fplay" title="Anhören">▶</button>' + (f.ext === 'mp3' ? '<button class="pb ftag" title="Tag-Editor für diese Datei">Tag</button>' : '') + '</div>' +
      (f.cover ? '<div class="fcv"><img class="cvimg" src="' + esc(music + '/cover?p=' + encodeURIComponent(f.path)) + '" alt="Cover" loading="lazy"></div>'
        : '<div class="fcv none" title="kein Cover"></div>') +
      '<div class="fpath">' + esc(name) + (pl.rel[i] ? '<span class="tag same">' + esc(pl.rel[i]) + '</span>' : '') + '<br><small>' + esc(dir) + '</small><div class="facts">' + facts + '</div></div>' +
      '<div class="why">' + (k ? 'wird behalten' : esc(pl.why[i] || '')) + tagLine(f, g[pl.keep], k) + '</div></div>';
  }

  // angehakte Dateien nur der sichtbaren Gruppen (Filter und Suche): nie unbemerkt etwas aus ausgeblendeten Gruppen
  function markedIn(g, pl) { return g.filter((f, i) => i !== pl.keep && !gone.has(f.path) && f.exists && isMarked(f, pl, i)); }
  function pageItems() { const v = visible(); page = Math.max(0, Math.min(page, Math.ceil(v.length / PAGE) - 1)); return { v, shown: v.slice(page * PAGE, page * PAGE + PAGE) }; }
  function marked() {                                         // nur die gerade gezeigte Seite
    const out = [];
    pageItems().shown.forEach(({ g, pl }) => out.push(...markedIn(g, pl)));
    return out;
  }
  function tagLine(f, keep, isKeep) {
    if (isKeep || !f.tv || !keep.tv) return '';
    const t = tagDiff(f, keep), take = Object.keys(t.take);
    return (take.length ? '<div class="ttake">übernimmt beim Löschen: ' + esc(take.map(x => TAGL[x] + ' ' + t.take[x]).join(', ')) + '</div>' : '') +
      (t.diff.length ? '<div class="tdiff">anders: ' + esc(t.diff.join(' · ')) + '</div>' : '');
  }
  function takeText(g, pl, todo) {
    const keep = g[pl.keep], put = {};
    if (keep.ext !== 'mp3' || !keep.tv) return '';
    for (const f of todo) { const t = tagDiff(f, keep).take; for (const k of Object.keys(t)) if (!(k in put)) put[k] = t[k]; }
    const ks = Object.keys(put);
    return ks.length ? '\nSie übernimmt vorher: ' + ks.map(k => TAGL[k] + ' ' + put[k]).join(', ') : '';
  }
  // vor dem Loeschen: fehlende Angaben der behaltenen MP3 aus den geloeschten Dateien der Gruppe ergaenzen (nie ueberschreiben)
  async function transferTags(g, pl, todo) {
    const keep = g[pl.keep];
    if (keep.ext !== 'mp3' || !keep.tv) return;
    const put = {};
    for (const f of todo) { const t = tagDiff(f, keep).take; for (const k of Object.keys(t)) if (!(k in put)) put[k] = t[k]; }
    if (!Object.keys(put).length) return;
    const r = await fetch(music + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ p: keep.path, name: keep.path.split('/').pop(), fields: put }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) throw new Error('Tags übernehmen ging nicht: ' + (j.error || r.status));
    Object.assign(keep.tv, put);
  }
  function visible() {
    const qq = q.toLowerCase();
    return groups.map((g, gi) => ({ g, gi, pl: groupPlan(g) })).filter(({ g, pl }) => {
      if (g.filter(f => !gone.has(f.path)).length < 2) return false;   // abgearbeitet: nur noch eine Datei uebrig
      if (filt === 'sug' && !pl.del.size && !pl.sug.size) return false;
      if (filt === 'mp4' && !(g.some(f => f.ext === 'mp3') && g.some(f => f.ext !== 'mp3'))) return false;
      return !qq || g.some(f => (f.path + ' ' + f.artist + ' ' + f.title).toLowerCase().includes(qq));
    });
  }

  function pager(n) {
    const pages = Math.ceil(n / PAGE);
    if (pages <= 1) return '';
    return '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pages +
      ' · Gruppen ' + (page * PAGE + 1) + '–' + Math.min(n, page * PAGE + PAGE) + ' von ' + n + '</span><button class="pgnext"' + (page < pages - 1 ? '' : ' disabled') + '>Weiter ›</button></div>';
  }
  function draw() {
    const { v, shown } = pageItems();
    if (!audio.paused && !shown.some(({ g }) => g.some(f => f.path === audio.dataset.p && !gone.has(f.path)))) audio.pause();   // Zeile weg: Ton aus
    $('list').innerHTML = shown.length ? pager(v.length) + shown.map(({ g, gi, pl }) => {
      const m = markedIn(g, pl).length;
      return '<div class="grp" data-g="' + gi + '"><div class="ghead"><b>' + esc((g[pl.keep].artist ? g[pl.keep].artist + ' – ' : '') + (g[pl.keep].title || g[pl.keep].path.split('/').pop())) + '</b><span>' + g.length + ' Dateien</span>' +
        '<span class="gbtns"><button class="gdel"' + (m ? '' : ' disabled') + ' title="Nur in dieser Gruppe die angehakten Dateien in den Papierkorb, danach ist die Gruppe erledigt">' + (m ? m + ' markierte löschen' : 'nichts markiert') + '</button>' +
        '<button class="gkeep" title="Keine echten Doppelten oder bewusst alle behalten: die Gruppe kommt nicht wieder">Alle behalten</button></span></div>' +
        g.map((f, i) => gone.has(f.path) ? '' : fileRow(g, gi, f, i, pl)).join('') + '</div>';
    }).join('') + pager(v.length)
      : '<div class="empty">' + (groups.length ? 'Keine Gruppe passt zum Filter.' : 'Keine doppelten Lieder gefunden.') + '</div>';
    $('list').querySelectorAll('.fcv img').forEach(img => { img.onerror = () => { const d = img.parentElement; d.classList.add('none'); d.title = 'kein Cover'; img.remove(); }; });
    const n = marked().length;
    $('bdel').textContent = 'Alle Markierten dieser Seite löschen (' + n + ')';
    const open_ = groups.filter(g => g.filter(f => !gone.has(f.path)).length >= 2);
    const sug = open_.filter(g => { const p_ = groupPlan(g); return p_.del.size || p_.sug.size; }).length;
    $('dstat').innerHTML = '<b>' + open_.length + '</b> Gruppen doppelter Lieder offen · <b>' + sug + '</b> mit Vorschlag' + (done ? ' · <b>' + done + '</b> erledigt' : '');
  }

  async function load(fresh) {
    try {
      if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
      if (!music) { $('dstat').textContent = 'Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer? Nach einem Neustart dauert es bis zu einer Minute.'; return; }
      if (!Object.keys(pi).length) {
        const d = await fetch('/api/musik').then(r => r.json());
        for (const t of d.tracks || []) if (t.path) pi[t.path] = { show: t.show || '', stems: !!t.stems };
      }
      for (let n = 0; n < 200; n++) {
        const d = await fetch(music + '/dupes' + (fresh && n === 0 ? '?neu=1' : '')).then(r => r.json());
        if (d.state === 'off') { $('dstat').textContent = 'Diese Mixxx-Brücke kann noch keine Doppelten prüfen (install_launcher.sh erneut ausführen).'; return; }
        if (d.state === 'ok' || (d.groups && d.groups.length && !fresh)) { groups = d.groups || []; draw(); if (d.state === 'ok') return; }
        const p = d.progress || [0, 0];
        $('dstat').textContent = 'Der Musik-Rechner sieht die Bibliothek durch … ' + (p[1] ? p[0] + ' von ' + p[1] + ' Dateien' : '');
        await new Promise(r => setTimeout(r, 2000));
      }
    } catch (e) {
      $('dmsg').textContent = 'Keine Verbindung zum Musik-Rechner: ' + e.message;
    }
  }

  $('dtabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-f]');
    if (!b) return;
    filt = b.dataset.f; page = 0;
    document.querySelectorAll('#dtabs button').forEach(x => x.classList.toggle('on', x === b));
    draw();
  });
  $('dq').addEventListener('input', e => { q = e.target.value; page = 0; draw(); });
  $('bnew').onclick = () => { mark.clear(); keepOf.clear(); load(true); };
  $('list').addEventListener('change', e => {
    const r = e.target.closest('.frow');
    if (!r) return;
    const g = groups[+r.dataset.g], i = +r.dataset.i;
    if (e.target.classList.contains('fkeep')) { keepOf.set(gkey(g), i); g.forEach(f => mark.delete(f.path)); }
    if (e.target.classList.contains('fdel')) mark.set(g[i].path, e.target.checked);
    draw();
  });
  $('list').addEventListener('click', async e => {
    if (e.target.closest('.pgprev')) { page--; draw(); scrollTo(0, 0); return; }
    if (e.target.closest('.pgnext')) { page++; draw(); scrollTo(0, 0); return; }
    const gb = e.target.closest('.gdel, .gkeep');
    if (gb) {
      const g = groups[+gb.closest('.grp').dataset.g], pl = groupPlan(g);
      if (gb.classList.contains('gkeep')) {
        try {
          const r = await fetch(music + '/dupes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'keep', paths: g.map(f => f.path) }) });
          const j = await r.json().catch(() => ({}));
          if (!r.ok || !j.ok) throw new Error(j.error || ('Fehler ' + r.status));
          g.forEach(f => gone.add(f.path)); done++; draw();
        } catch (err) { $('dmsg').textContent = 'Merken ging nicht: ' + err.message; }
      } else {
        const todo = markedIn(g, pl);
        if (todo.length) {                 // ohne Nachfrage-Fenster (Wunsch 08.11.2026), im Finder zuruecklegbar
          SM.toast(todo.length + ' Datei' + (todo.length > 1 ? 'en' : '') + ' in den Papierkorb, behalten: ' + g[pl.keep].path.split('/').pop(), 3500);
          try { await transferTags(g, pl, todo); } catch (err) { $('dmsg').textContent = err.message + ' – nichts gelöscht.'; return; }
          const ok = await trashFiles(todo);
          if (ok === todo.length) done++;
          draw();
        }
      }
      return;
    }
    const tb = e.target.closest('.ftag');
    if (tb) {                                                 // Tag-Editor je Datei (Wunsch 07.11.2026)
      const r = tb.closest('.frow'), f = groups[+r.dataset.g][+r.dataset.i];
      SM.tagEdit({ path: f.path, dur: f.dur || 0 }, music, d => {
        const x = (d && d.fields) || {};
        if (d && 'cover' in d) f.cover = !!d.cover;
        f.tags = ['title', 'artist', 'album', 'year', 'genre', 'bpm', 'key', 'track'].filter(k => x[k]).length;
        if (x.artist !== undefined) f.artist = x.artist;
        if (x.title !== undefined) f.title = x.title;
        draw();
      });
      return;
    }
    const b = e.target.closest('.fplay');
    if (!b) return;
    const r = b.closest('.frow'), f = groups[+r.dataset.g][+r.dataset.i];
    const src = music + '/audio?p=' + encodeURIComponent(f.path);
    if (audio.dataset.p === f.path && !audio.paused) { audio.pause(); return; }
    audio.dataset.p = f.path; audio.src = src;
    audio.currentTime = 0;
    audio.play().catch(err => { $('dmsg').textContent = 'Abspielen ging nicht: ' + err.message; });
    pbar.show(f.name || String(f.path).split('/').pop());
  });
  $('bdel').onclick = async () => {
    if (busy) return;
    const todo = marked();
    if (!todo.length) return;
    if (!await SM.ask(todo.length + ' Dateien in den Papierkorb des Musik-Rechners legen?\n\nJe Gruppe bleibt die markierte Datei „behalten“; fehlende Angaben übernimmt sie vorher aus den gelöschten. Im Finder lassen sich die anderen mit „Zurücklegen“ wiederholen, bis du den Papierkorb leerst. Mixxx zeigt sie noch, bis es die Bibliothek neu einliest.', undefined, 'In den Papierkorb')) return;
    let ok = 0;
    for (const { g, pl } of pageItems().shown) {             // je Gruppe: erst fehlende Tags uebernehmen, dann loeschen
      const t = markedIn(g, pl);
      if (!t.length) continue;
      try { await transferTags(g, pl, t); } catch (err) { $('dmsg').textContent = err.message + ' – Gruppe übersprungen.'; continue; }
      ok += await trashFiles(t);
    }
    draw();
    SM.toast(ok + ' Dateien in den Papierkorb gelegt.', 5000);
  };
  async function trashFiles(todo) {                          // in den Papierkorb des Mac (/trash), Fehler gesammelt gemeldet
    busy = true;
    audio.pause();
    let ok = 0;
    const errs = [];
    for (const f of todo) {
      try {
        const r = await fetch(music + '/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ p: f.path, name: f.path.split('/').pop() }) });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) throw new Error(j.error || ('Fehler ' + r.status));
        gone.add(f.path); ok++;
        if (window.SM && SM.goneMark) SM.goneMark(f.path);   // auch die Musik-Datenbank zeigt sie nicht mehr
      } catch (e) {
        errs.push(f.path.split('/').pop() + ': ' + e.message);
        if (/Finder|Apple/i.test(e.message)) break;
      }
    }
    busy = false;
    if (errs.length) SM.ask('Nicht gelöscht: ' + errs.slice(0, 3).join('; ') + (errs.some(x => /Finder|Apple/i.test(x)) ? '\n\nBeim ersten Mal fragt macOS am Mac, ob die App den Finder steuern darf: dort erlauben.' : ''));
    return ok;
  }
  load(false);
})(typeof window !== 'undefined' ? window : globalThis);
