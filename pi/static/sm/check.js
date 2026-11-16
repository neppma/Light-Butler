// Dateien pruefen (Wunsch von Markus, 08.11.2026): Datenmuell, sonstige Dateien und Dateinamen im Musikordner.
// Der Mac prueft (file_check.py ueber den Vorhoer-Server, Helfer oder Mixxx-App), die Seite zeigt nur und schickt Befehle.
// In den Papierkorb und Umbenennen nur auf Klick; Lieder mit Hotcues oder Kisten in Mixxx sind gelb markiert.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const PER = 50;
  const fmt = b => !b ? '0 B' : b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(b < 10240 ? 1 : 0).replace('.', ',') + ' KB'
    : b < 1073741824 ? (b / 1048576).toFixed(1).replace('.', ',') + ' MB' : (b / 1073741824).toFixed(2).replace('.', ',') + ' GB';   // Dateigroesse
  let jEdited = false;                                 // eigene Muell-Namen: Feld selbst geaendert
  let music = '', st = null, tab = 'muell', page = 0, poll = null, playing = '', seeking = false;
  // ---- Anhoeren (Wunsch 08.11.2026): Play je Lied, unten Leiste zum Spulen und Lautstaerke (gemeinsam mit der Musik-DB) ----
  const audio = new Audio();
  const tmss = t => { t = Math.max(0, Math.round(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
  let vol = 80;
  try { vol = Math.max(0, Math.min(100, parseInt(localStorage.getItem('musikvol') || '80', 10) || 0)); } catch (e) { /* privat */ }
  function playPath(p) {
    if (!music) return;
    if (playing === p) { if (audio.paused) audio.play().catch(() => {}); else audio.pause(); draw(); return; }
    playing = p;
    audio.src = music + '/audio?p=' + encodeURIComponent(p);
    audio.play().catch(err => { $('cmsg').textContent = 'Abspielen ging nicht: ' + err.message; });
    const it = st && st.namen.find(x => x.path === p);
    $('pt').textContent = it ? it.name : p.split('/').pop();
    $('pbar').classList.add('on'); document.body.classList.add('bar');
    draw();
  }
  function drawBar() {
    $('ppp').textContent = audio.paused ? '▶' : '❚❚';
    const d = audio.duration || 0;
    if (!seeking) $('ppos').value = d ? Math.round(1000 * audio.currentTime / d) : 0;
    $('ptm').textContent = tmss(audio.currentTime) + ' / ' + tmss(d);
  }
  const busy = new Set();

  async function mac(op, body) {
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht.');
    const r = await fetch(music + '/check', op ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ op }, body || {})) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
    if (r.status === 404 || !d || d.state === 'off') throw new Error('Am Musik-Rechner läuft noch die alte Fassung: Helfer oder Mixxx-App neu installieren (./deploy.sh alles).');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }

  async function load() {
    try {
      if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
      if (!music) { $('cstat').textContent = 'Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer?'; return; }
      st = await mac();
      $('cmsg').textContent = st.err || '';
      draw();
      clearTimeout(poll);
      if (st.state === 'scan' || st.state === 'wait' || st.job) poll = setTimeout(load, 1500);
    } catch (e) { $('cstat').textContent = e.message; }
  }

  function list() {
    const q = $('cq').value.trim().toLowerCase();
    const arr = (st && st[tab]) || [];
    return q ? arr.filter(x => ((x.rel || (x.rels || []).join(' ')) + ' ' + (x.want || '')).toLowerCase().includes(q)) : arr;
  }
  function split(rel) { const i = rel.lastIndexOf('/'); return [rel.slice(i + 1), rel.slice(0, i)]; }
  const full = rel => ((st && st.root) ? st.root + '/' : '') + rel;   // ganzer Pfad am Mac (Wunsch 08.11.2026)

  function draw() {
    const n = (st && st.n) || { muell: 0, sonstige: 0, namen: 0, gleich: 0, belassen: 0, leer: 0, kurz: 0 };
    for (const b of $('ctabs').querySelectorAll('button[data-t]')) {
      b.classList.toggle('on', b.dataset.t === tab);
      b.textContent = { muell: 'Datenmüll', sonstige: 'Sonstige', namen: 'Dateinamen', belassen: 'So gelassen', gleich: 'Gleiche Namen', leer: 'Leere Ordner', kurz: 'Kurze Stücke' }[b.dataset.t] + ' (' + (n[b.dataset.t] || 0) + (st && st.bytes && st.bytes[b.dataset.t] ? ' · ' + fmt(st.bytes[b.dataset.t]) : '') + ')';
    }
    const when = st && st.t ? new Date(st.t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
    $('cstat').innerHTML = !st ? 'Lade …' : st.state === 'wait' ? 'Warte, bis der Musik-Rechner die Tags der Dateien gelesen hat (nach einem Neustart ein paar Minuten) …'
      : st.state === 'scan' ? 'Prüfe … <b>' + st.done + '</b> Dateien angesehen'
      : st.state === 'idle' ? 'Noch nicht geprüft: <b>Prüfen</b> drücken.'
      : 'Geprüft ' + esc(when) + ' · Ordner <span class="dim">' + esc(st.root) + '</span>';
    if (st && st.job) $('cstat').innerHTML += ' · <b>In den Papierkorb: ' + st.job[0] + ' von ' + st.job[1] + '</b>';
    if (st && st.pending) $('cstat').innerHTML += ' · <b>' + st.pending + '</b> Umbenennung' + (st.pending > 1 ? 'en warten' : ' wartet') + ' auf den nächsten Start der Mixxx-App (in Mixxx bis dahin nicht „Bibliothek neu einlesen“)';
    if (st && st.blocked && st.pending) $('cmsg').innerHTML = '<b>Beim letzten Start der Mixxx-App ließ sich die Mixxx-Datenbank nicht ändern</b> (' + esc(st.blocked) + '). Die Umbenennungen warten und kommen beim nächsten Start dran; in Mixxx bis dahin nicht „Bibliothek neu einlesen“.';
    $('ball').hidden = !(st && tab === 'muell' && n.muell && !st.job);
    $('jbox').hidden = !(st && tab === 'muell');
    if (st && st.jnames && !jEdited) { $('jnames').value = st.jnames.join('\n'); }
    $('jcount').textContent = st && st.jnames ? st.jnames.length + ' Einträge' : '…';
    $('bdirs').hidden = !(st && tab === 'leer' && n.leer && !st.job);
    $('bdirs').textContent = '🗑 Alle ' + n.leer + ' leeren Ordner in den Papierkorb';
    $('bshort').hidden = !(st && tab === 'kurz' && n.kurz);
    $('bshort').textContent = 'Bei allen ' + n.kurz + ' leeren';
    $('ball').textContent = '🗑 Alle ' + n.muell + ' in den Papierkorb' + (st && st.bytes ? ' (' + fmt(st.bytes.muell) + ')' : '');
    const arr = list(), pages = Math.max(1, Math.ceil(arr.length / PER));
    page = Math.min(page, pages - 1);
    const cur = arr.slice(page * PER, page * PER + PER);
    const pager = arr.length > PER ? '<div class="pager"><button data-pg="-1"' + (page ? '' : ' disabled') + '>‹</button> Seite <b>' + (page + 1) + '</b> von <b>' + pages + '</b> <button data-pg="1"' + (page < pages - 1 ? '' : ' disabled') + '>›</button></div>' : '';
    const more = st && n[tab] > ((st[tab] || []).length) ? '<p class="dim">Gezeigt werden die ersten ' + st[tab].length + ' von ' + n[tab] + '.</p>' : '';
    if (!st || st.state !== 'ready') { $('clist').innerHTML = ''; return; }
    if (!cur.length) { $('clist').innerHTML = '<div class="empty">' + (tab === 'namen' ? 'Alle Dateinamen passen zum Schema.' : tab === 'gleich' ? 'Kein Dateiname kommt zweimal vor.' : tab === 'belassen' ? 'Noch nichts mit „So lassen“ behalten.' : tab === 'leer' ? 'Kein leerer Ordner.' : tab === 'kurz' ? 'Kein kurzes Stück mit BPM, Tonart oder geschätzter Energie.' : 'Nichts gefunden.') + '</div>'; return; }
    $('clist').innerHTML = pager + (tab === 'gleich' ? '<p class="dim">Diese Dateinamen gibt es mehrmals im Musikordner (Groß/klein zählt nicht). In getrennten Ordnern stört das nicht, in einem gemeinsamen Ordner schon. Die Datei mit dem kürzesten Pfad behält ihren Namen, die anderen bekommen den Ordner (Album) in Klammern: Vorschlag prüfen, „Umbenennen“. Gleich große Dateien sind vermutlich dasselbe Lied: die besser unter „Doppelte entfernen“ löschen.</p>' : '') + (tab === 'belassen' ? '<p class="dim">Diese Dateinamen hast du mit „So lassen“ behalten. Daneben steht, was die Namensregeln vorschlagen würden. „Doch umbenennen“ holt das Lied zurück in die Liste Dateinamen.</p>' : '') +
      cur.map(x => tab === 'leer' ? dirRow(x) : tab === 'kurz' ? shortRow(x) : tab === 'namen' ? nameRow(x) : tab === 'belassen' ? heldRow(x) : tab === 'gleich' ? sameRow(x) : fileRow(x)).join('') + pager + more;
  }
  function dirRow(x) {                  // leere Ordner (Wunsch 09.11.2026)
    const [f] = split(x.rel);
    return '<div class="crow"><div><div class="p">📁 ' + esc(f) + '</div><div class="d">' + esc(full(x.rel)) + ' · ' +
      (x.files ? x.files + ' Datei' + (x.files > 1 ? 'en' : '') + ' ohne Musik: ' + esc(x.ex.join(', ')) + (x.files > x.ex.length ? ' …' : '') : 'ganz leer') + '</div></div>' +
      '<div class="cbtns"><button class="del" data-ddel="' + esc(x.rel) + '" title="Ordner in den Papierkorb des Musik-Rechners"' + (busy.has(x.rel) ? ' disabled' : '') + '>🗑</button></div></div>';
  }
  function shortRow(x) {                // kurze Stuecke: BPM und Tonart sind nur geraten (Wunsch 09.11.2026)
    const [f] = split(x.rel);
    return '<div class="crow"><div><div class="p">' + esc(f) + ' <span class="dim">· ' + x.dur.toFixed(1).replace('.', ',') + ' s</span></div>' +
      '<div class="why" style="color:var(--dim)">Im Tag: ' + [x.bpm ? 'BPM ' + esc(x.bpm) : '', x.key ? 'Tonart ' + esc(x.key) : '', x.energy ? 'Energie ' + esc(x.energy) + ' (geschätzt)' : ''].filter(Boolean).join(', ') + '</div>' +
      '<div class="d">' + esc(full(x.rel)) + '</div></div>' +
      '<div class="cbtns"><button class="pb' + (playing === x.path && !audio.paused ? ' on' : '') + '" data-play="' + esc(x.path) + '" title="Anhören">' + (playing === x.path && !audio.paused ? '❚❚' : '▶') + '</button>' +
      '<button data-sclr="' + esc(x.rel) + '" title="BPM, Tonart und geschätzte Energie aus dem Tag entfernen (Musik bleibt)"' + (busy.has(x.rel) ? ' disabled' : '') + '>Leeren</button></div></div>';
  }
  function fileRow(x) {
    const rel = x.rel, [f] = split(rel);
    return '<div class="crow"><div><div class="p">' + esc(f) + '</div><div class="d">' + esc(full(rel)) + '</div></div>' +
      '<div class="cbtns"><span class="sz">' + fmt(x.size) + '</span><button class="del" data-del="' + esc(rel) + '" title="In den Papierkorb des Musik-Rechners"' + (busy.has(rel) ? ' disabled' : '') + '>🗑</button></div></div>';
  }
  function heldRow(x) {                 // "So gelassen" (Wunsch 08.11.2026): ansehen und doch noch umbenennen
    return '<div class="crow"><div><div class="p">' + esc(x.name) + '</div>' +
      (x.want ? '<div class="why" style="color:var(--dim)">Vorschlag: ' + esc(x.want) + '</div>' : '<div class="why">' + esc(x.why) + '</div>') +
      tagLine(x) + '<div class="d">' + esc(full(x.rel)) + '</div></div>' +
      '<div class="cbtns"><button class="pb' + (playing === x.path && !audio.paused ? ' on' : '') + '" data-play="' + esc(x.path) + '" title="Anhören">' + (playing === x.path && !audio.paused ? '❚❚' : '▶') + '</button><span class="sz">' + fmt(x.size) + '</span>' +
      '<button data-tag="' + esc(x.path) + '" title="Tags ansehen und bearbeiten (Tag-Editor)">🏷 Tags</button>' +
      '<button data-unkeep="' + esc(x.path) + '" title="Wieder in die Liste Dateinamen, dort umbenennen"' + (busy.has(x.path) ? ' disabled' : '') + '>Doch umbenennen</button></div></div>';
  }
  function sameRow(x) {                 // gleicher Dateiname an mehreren Stellen, mit Vorschlag je Datei (Wunsch 08.11.2026)
    const fl = x.files || x.rels.map(r => ({ rel: r, file: full(r), keep: false, want: '' }));
    return '<div class="crow"><div><div class="p">' + esc(x.name) + ' <span class="dim">· ' + fl.length + '×</span></div>' +
      fl.map(f => {
        const pb = '<button class="pb' + (playing === f.file && !audio.paused ? ' on' : '') + '" data-play="' + esc(f.file) + '" title="Anhören">' + (playing === f.file && !audio.paused ? '❚❚' : '▶') + '</button>';
        return '<div class="srow">' + pb + '<div><div class="d" style="margin:0">' + esc(full(f.rel)) + (f.size ? ' · ' + fmt(f.size) : '') +
          (f.twin ? ' · <span class="mx">gleich groß wie eine andere: vermutlich dasselbe Lied, besser unter „Doppelte entfernen“ löschen</span>' : '') + '</div>' +
          (f.keep ? '<div class="keepn">behält den Namen</div>'
            : f.want ? '<div class="srn"><span class="oldn">' + esc(f.rel.split('/').pop()) + '</span><input class="cnew" data-snew="' + esc(f.file) + '" value="' + esc(f.want) + '">' +
              '<button data-sren="' + esc(f.file) + '"' + (busy.has(f.file) ? ' disabled' : '') + '>Umbenennen</button></div>' : '') +
          '</div></div>';
      }).join('') + '</div><div></div></div>';
  }
  // Tags der Datei unter dem Vorschlag (Wunsch 08.11.2026): sehen, ob Titel, Album usw. im Tag stehen, bevor sie aus dem Namen verschwinden
  const TAGL = [['title', 'Titel'], ['artist', 'Interpret'], ['album', 'Album'], ['albumartist', 'Album-Interpret'], ['track', 'Track']];
  function tagLine(x) {
    const t = x.tags || {};
    if (!Object.keys(t).length) return '';
    return '<div class="tagl">' + TAGL.map(([k, l]) => '<span class="' + (t[k] ? 'tk' : 'tk none') + '"><b>' + l + ':</b> ' + esc(t[k] || 'fehlt') + '</span>').join('') + '</div>';
  }
  function nameRow(x) {
    const d = full(x.rel);
    return '<div class="crow"><div><div class="p"><span class="oldn" title="So heißt die Datei jetzt (fällt weg)">' + esc(x.name) + '</span></div>' +
      (x.want ? '<input class="cnew" data-new="' + esc(x.path) + '" value="' + esc(x.want) + '">' : '<div class="why">' + esc(x.why) +
        (/Alle Lieder dieser CD/.test(x.why || '') ? ' <a class="btn" href="/musik/cd?d=' + encodeURIComponent(split(x.rel)[1]) + '">💿 CD-Assistent</a>' : '') + '</div>') +
      tagLine(x) +
      '<div class="d">' + esc(d) + (x.clash ? ' · <span class="mx">Der einfache Name ist schon vergeben (' + esc(full(x.clash)) + '), darum mit Zusatz</span>' : '') + (x.mixxx ? ' · <span class="mx">hat in Mixxx Hotcues oder Kisten: sie bleiben, Mixxx übernimmt den neuen Namen beim nächsten Start der App</span>' : '') + '</div></div>' +
      '<div class="cbtns"><button class="pb' + (playing === x.path && !audio.paused ? ' on' : '') + '" data-play="' + esc(x.path) + '" title="Anhören">' + (playing === x.path && !audio.paused ? '❚❚' : '▶') + '</button><span class="sz">' + fmt(x.size) + '</span>' + (x.want ? '<button data-ren="' + esc(x.path) + '"' + (busy.has(x.path) ? ' disabled' : '') + '>Umbenennen</button>' : '') +
      '<button data-tag="' + esc(x.path) + '" title="Tags ansehen und bearbeiten (Tag-Editor)">🏷 Tags</button>' +
      '<button data-keep="' + esc(x.path) + '" title="Dateiname so lassen: das Lied kommt in dieser Liste nicht wieder"' + (busy.has(x.path) ? ' disabled' : '') + '>So lassen</button></div></div>';
  }

  $('ctabs').onclick = e => { const b = e.target.closest('button[data-t]'); if (!b) return; tab = b.dataset.t; page = 0; draw(); };
  $('cq').addEventListener('input', () => { page = 0; draw(); });
  // Eigene Muell-Namen (Wunsch 09.11.2026): Vorschau zaehlt nur, Speichern merkt die Liste am Mac und prueft neu
  $('jnames').addEventListener('input', () => { jEdited = true; });
  const jLines = () => $('jnames').value.split('\n').map(x => x.trim()).filter(Boolean);
  $('jprev').onclick = async () => {
    $('jout').textContent = 'Zähle …';
    try {
      const d = await mac('jnames_preview', { names: jLines() });
      $('jout').innerHTML = d.rows.length ? d.rows.map(r => '<div><code>' + esc(r.name) + '</code>: <b>' + r.n + '</b> Dateien' + (r.n ? ' (' + fmt(r.bytes) + '), z. B. ' + esc(r.ex.join(', ')) : '') +
        (r.kept ? ' · ' + r.kept + ' Bilder bleiben, ihr Ordner braucht sie' : '') + '</div>').join('') + '<div>Zusammen <b>' + d.total + '</b> Dateien.</div>' : 'Die Liste ist leer.';
    } catch (e) { $('jout').textContent = e.message; }
  };
  $('jsave').onclick = async () => {
    try {
      const d = await mac('jnames_set', { names: jLines() });
      jEdited = false; $('jnames').value = d.names.join('\n');
      $('jout').textContent = 'Gespeichert (' + d.names.length + ' Einträge), prüfe neu …';
      setTimeout(load, 400);
    } catch (e) { $('jout').textContent = e.message; }
  };
  $('bscan').onclick = async () => { try { await mac('scan'); setTimeout(load, 400); } catch (e) { $('cmsg').textContent = e.message; } };
  $('ball').onclick = async () => {
    const n = st.n.muell;
    if (!await SM.ask(n + ' Dateien (' + fmt((st.bytes || {}).muell || 0) + ') aus der Liste Datenmüll in den Papierkorb des Musik-Rechners legen?\n\n(Thumbs.db, desktop.ini, Cover-Kopien vom Media Player; keine Musik. Im Finder lassen sie sich zurücklegen, bis du den Papierkorb leerst.)', undefined, 'In den Papierkorb')) return;
    try { await mac('trash_all'); setTimeout(load, 500); } catch (e) { $('cmsg').textContent = e.message; }
  };
  $('bdirs').onclick = async () => {    // ohne Nachfrage wie die anderen 🗑 (Papierkorb, zuruecklegbar)
    const items = st.leer.map(x => x.rel);
    $('bdirs').disabled = true;
    try { const d = await mac('trash_dirs', { items }); SM.toast(d.gone + ' Ordner im Papierkorb', 3000); await mac('scan'); setTimeout(load, 400); } catch (e) { $('cmsg').textContent = e.message; }
    $('bdirs').disabled = false;
  };
  $('bshort').onclick = async () => {
    $('bshort').disabled = true;
    try { const d = await mac('clear_short'); st.kurz = []; st.n.kurz = 0; SM.toast('Geleert: ' + d.done + ' Dateien entfernt' + (d.bad ? ', ' + d.bad + ' gingen nicht' : ''), 3500); } catch (e) { $('cmsg').textContent = e.message; }
    $('bshort').disabled = false; draw();
  };
  $('clist').addEventListener('click', async e => {
    const dd = e.target.closest('button[data-ddel]');
    if (dd) {
      const rel = dd.dataset.ddel;
      busy.add(rel); draw();
      try {
        await mac('trash_dirs', { items: [rel] });
        st.leer = st.leer.filter(x => x.rel !== rel); st.n.leer = Math.max(0, st.n.leer - 1);
        SM.toast('Im Papierkorb: ' + split(rel)[0], 2500);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(rel); draw();
      return;
    }
    const sc = e.target.closest('button[data-sclr]');
    if (sc) {
      const rel = sc.dataset.sclr;
      busy.add(rel); draw();
      try {
        await mac('clear_short', { items: [rel] });
        st.kurz = st.kurz.filter(x => x.rel !== rel); st.n.kurz = Math.max(0, st.n.kurz - 1);
        SM.toast('Geleert: ' + split(rel)[0], 2500);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(rel); draw();
      return;
    }
    const pl = e.target.closest('button[data-play]');
    if (pl) { playPath(pl.dataset.play); return; }
    const pg = e.target.closest('button[data-pg]');
    if (pg) { page += +pg.dataset.pg; draw(); window.scrollTo(0, 0); return; }
    const del = e.target.closest('button[data-del]');
    if (del) {
      const rel = del.dataset.del;
      busy.add(rel); draw();
      try {
        await mac('trash', { items: [rel] });
        const gone = st[tab].find(x => x.rel === rel);
        st[tab] = st[tab].filter(x => x.rel !== rel); st.n[tab] = Math.max(0, st.n[tab] - 1);
        if (gone && st.bytes) st.bytes[tab] = Math.max(0, st.bytes[tab] - (gone.size || 0));
        SM.toast('Im Papierkorb: ' + split(rel)[0], 2500);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(rel); draw();
      return;
    }
    const tg = e.target.closest('button[data-tag]');
    if (tg) {                              // Tag-Editor (Wunsch 08.11.2026): danach Vorschlag neu
      const p = tg.dataset.tag;
      if (!music) { $('cmsg').textContent = 'Musik-Rechner nicht erreichbar'; return; }
      SM.tagEdit({ path: p, dur: 0 }, music, async () => {
        if (!st.namen.some(x => x.path === p)) { SM.toast('Tags gespeichert. Der Vorschlag kommt beim nächsten Prüfen neu.', 3000); return; }
        try {
          const d = await mac('retag', { p });
          if (d.gone) { st.namen = st.namen.filter(x => x.path !== p); st.n.namen = Math.max(0, st.n.namen - 1); SM.toast('Dateiname passt jetzt zu den Tags', 3000); }
          else if (d.item) st.namen = st.namen.map(x => x.path === p ? d.item : x);
        } catch (x) { $('cmsg').textContent = x.message; }
        draw();
      });
      return;
    }
    const ren = e.target.closest('button[data-ren]');
    if (ren) {
      const p = ren.dataset.ren, it = st.namen.find(x => x.path === p);
      const inp = $('clist').querySelector('input[data-new="' + CSS.escape(p) + '"]');
      const to = inp ? inp.value.trim() : it.want;
      // ohne Nachfrage-Fenster (Wunsch 08.11.2026): Hotcues und Kisten bleiben, Mixxx traegt den neuen Namen beim naechsten Start ein
      busy.add(p); draw();
      try {
        if (playing === p) { audio.pause(); playing = ''; $('pbar').classList.remove('on'); document.body.classList.remove('bar'); }   // Datei heisst gleich anders
        const d = await mac('rename', { p, to });
        if (d.path) SM.cmd('path_moved', { old: d.old_path || p, new: d.path }).catch(() => {});   // Cue-Punkte und Cover am Pi mitnehmen
        st.namen = st.namen.filter(x => x.path !== p); st.n.namen = Math.max(0, st.n.namen - 1);
        st.pending = (st.pending || 0) + 1;
        SM.toast('Umbenannt: ' + d.new + ' (Mixxx übernimmt es beim nächsten Start der App)', 4000);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(p); draw();
      return;
    }
    const sr = e.target.closest('button[data-sren]');
    if (sr) {                              // Gleiche Namen: sofort umbenennen, ohne Nachfrage
      const f = sr.dataset.sren, inp = $('clist').querySelector('input[data-snew="' + CSS.escape(f) + '"]');
      busy.add(f); draw();
      try {
        if (playing === f) { audio.pause(); playing = ''; $('pbar').classList.remove('on'); document.body.classList.remove('bar'); }
        const d = await mac('rename_file', { f, to: inp ? inp.value.trim() : '' });
        SM.toast('Umbenannt: ' + d.new + (d.mixxx ? ' (Mixxx übernimmt es beim nächsten Start der App)' : ''), 3500);
        if (d.mixxx) st.pending = (st.pending || 0) + 1;
        st.gleich = st.gleich.map(g => Object.assign({}, g, { files: (g.files || []).filter(x => x.file !== f) })).filter(g => (g.files || []).length > 1);
        st.n.gleich = st.gleich.length;
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(f); draw();
      return;
    }
    const uk = e.target.closest('button[data-unkeep]');
    if (uk) {
      const p = uk.dataset.unkeep;
      busy.add(p); draw();
      try {
        const d = await mac('unkeep', { p });
        const it = d.item || st.belassen.find(x => x.path === p);
        st.belassen = st.belassen.filter(x => x.path !== p); st.n.belassen = Math.max(0, st.n.belassen - 1);
        if (it && !d.gone) { st.namen.push(it); st.namen.sort((a, b) => a.rel.localeCompare(b.rel)); st.n.namen++; }
        SM.toast(d.gone ? 'Der Name passt inzwischen zu den Tags.' : 'Zurück in der Liste Dateinamen (mit Vorschlag).', 3000);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(p); draw();
      return;
    }
    const kp = e.target.closest('button[data-keep]');
    if (kp) {
      const p = kp.dataset.keep;
      busy.add(p); draw();
      try {
        await mac('keep', { p });
        const moved = st.namen.find(x => x.path === p);
        if (moved && st.belassen) { st.belassen.push(moved); st.n.belassen = (st.n.belassen || 0) + 1; }
        st.namen = st.namen.filter(x => x.path !== p); st.n.namen = Math.max(0, st.n.namen - 1);
        SM.toast('Bleibt so.', 2000);
      } catch (x) { $('cmsg').textContent = x.message; }
      busy.delete(p); draw();
    }
  });
  $('vol').value = vol; audio.volume = vol / 100;
  $('vol').addEventListener('input', () => {
    audio.volume = $('vol').value / 100;
    try { localStorage.setItem('musikvol', $('vol').value); } catch (e) { /* privat */ }
  });
  ['timeupdate', 'play', 'pause', 'loadedmetadata'].forEach(ev => audio.addEventListener(ev, drawBar));
  audio.addEventListener('playing', () => { if (/^Abspielen ging nicht/.test($('cmsg').textContent)) $('cmsg').textContent = ''; });   // alte Meldung weg
  audio.addEventListener('play', draw); audio.addEventListener('pause', draw);
  $('ppos').addEventListener('input', () => { seeking = true; const d = audio.duration || 0; $('ptm').textContent = tmss(d * $('ppos').value / 1000) + ' / ' + tmss(d); });
  $('ppos').addEventListener('change', () => { const d = audio.duration || 0; if (d) audio.currentTime = d * $('ppos').value / 1000; seeking = false; });
  $('ppp').onclick = () => { if (playing) playPath(playing); };
  $('pcl').onclick = () => { audio.pause(); playing = ''; $('pbar').classList.remove('on'); document.body.classList.remove('bar'); draw(); };
  const tq = new URLSearchParams(location.search).get('t');   // aus der Datenpflege: gleich der passende Reiter
  if (['muell', 'sonstige', 'namen', 'belassen', 'gleich', 'leer', 'kurz'].includes(tq)) tab = tq;
  load();
})();
