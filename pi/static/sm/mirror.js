// Spiegeln zwischen Laufwerken am Musik-Rechner (Wunsch 10.11.2026 Stick -> NAS, 12.11.2026 Quelle und Ziel frei waehlbar).
// Der Mac rechnet und kopiert (mac/mixxx_bridge/nas_mirror.py, music_serve /mirror), die Seite zeigt Vorlagen, Quelle -> Ziel mit
// Auswahllisten aller Laufwerke, Platz am Ziel, Ordner, Probelauf, geschaetzte Dauer, Fortschritt und Ergebnis.
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const GB = b => b >= 1e12 ? (b / 1e12).toFixed(1).replace('.', ',') + ' TB' : b >= 1e9 ? (b / 1e9).toFixed(1).replace('.', ',') + ' GB' : Math.round((b || 0) / 1e6) + ' MB';
  const hm = s => s == null ? '' : s >= 3600 ? Math.floor(s / 3600) + ' h ' + Math.round((s % 3600) / 60) + ' min' : Math.max(1, Math.round(s / 60)) + ' min';
  const clock = s => new Date(Date.now() + s * 1000).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' });
  let music = '', st = null, timer = null, pick = null, pickSide = '', selTimer = null, ejecting = false;

  async function mac(path, body) {
    if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort der Light-Butler Helfer oder die Mixxx-App?');
    const r = await fetch(music + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
    if (r.status === 404 || !d) throw new Error('Am Musik-Rechner läuft noch die alte Fassung: Helfer oder Mixxx-App neu installieren (./deploy.sh alles).');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }
  const fail = e => { $('msg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; };
  async function op(body) { try { st = await mac('/mirror', body); draw(); } catch (e) { fail(e); } }

  const busyNow = () => st && (st.state === 'plan' || st.state === 'run');
  const drv = p => (st.drives || []).find(d => d.path === p);
  const kindTxt = d => d.kind === 'net' ? 'Netzlaufwerk' + (d.host ? ' (' + d.host + ')' : '') : d.kind === 'int' ? 'interne Festplatte (Benutzerordner)' : 'Laufwerk ' + (d.fs_name || '');
  const icon = d => d.kind === 'net' ? '🗄' : d.kind === 'int' ? '🖥' : '💾';
  function options(side) {
    const cur = side === 'src' ? st.src_drive : st.dst_drive, path = side === 'src' ? st.src : st.dst;
    let h = '';
    if (!cur) h += '<option value="" selected>' + (path ? '— nicht verbunden: ' + esc(path) + ' —' : '— bitte wählen —') + '</option>';
    for (const d of st.drives || []) {
      const ro = side === 'dst' && d.ro;
      const sz = d.free != null ? (side === 'dst' ? GB(d.free) + ' frei' : GB((d.total || 0) - d.free) + ' belegt') + (d.total ? ' von ' + GB(d.total) : '') : '';
      h += '<option value="' + esc(d.path) + '"' + (d.path === cur ? ' selected' : '') + (ro ? ' disabled' : '') + '>' + icon(d) + ' ' + esc(d.name) + ' · ' + esc(kindTxt(d)) +
        (d.music ? ' · dein Musik-Stick' : '') + (sz ? ' · ' + sz : '') + (ro ? ' · schreibgeschützt' : d.ro ? ' · nur lesen' : '') + '</option>';
    }
    return h;
  }
  function setSel(id, html) {                         // nicht neu bauen, solange man darin auswaehlt
    const el = $(id);
    if (document.activeElement === el || el.dataset.h === html) return;
    el.innerHTML = html;
    el.dataset.h = html;
  }
  const nameOf = (p, dp) => { const d = drv(dp); return d ? d.name : (p ? p.split('/').filter(Boolean).pop() : '?'); };

  function draw() {
    if (!st) return;
    const busy = busyNow(), same = !!st.same, planned = st.state === 'planned' && same;
    // Vorlagen
    const cur = (st.pairs || []).find(p => p.id === st.pair) || {};
    const ph = '<span class="dim">Vorlage:</span>' + (st.pairs || []).map(p => '<button data-p="' + esc(p.id) + '"' + (p.id === st.pair ? ' class="cur"' : '') + (busy ? ' disabled' : '') + '>' + esc(p.name) + '</button>').join('') +
      '<button id="padd"' + (busy ? ' disabled' : '') + '>+ eigene</button><button id="pren"' + (busy || cur.preset ? ' disabled title="Die festen Vorlagen behalten ihren Namen"' : '') + '>Umbenennen</button><button id="pdel"' + (busy || cur.preset ? ' disabled title="Die festen Vorlagen bleiben"' : '') + '>Vorlage löschen</button>';
    if ($('pairs').dataset.h !== ph) { $('pairs').innerHTML = ph; $('pairs').dataset.h = ph; }   // nur bei Aenderung neu (sonst geht ein Klick verloren)
    // Quelle und Ziel
    setSel('ssrc', options('src'));
    setSel('sdst', options('dst'));
    $('ssrc').disabled = $('sdst').disabled = $('bsrc').disabled = $('bdst').disabled = busy;
    $('fsrc').textContent = (st.src || '–') + (st.src_music ? '  (dein Musikordner)' : '');
    $('fdst').textContent = (st.dst || '–') + (st.dst_music ? '  (dein Musikordner)' : '');
    const av = st.avail || [], nsel = (st.sel || []).length;
    $('isrc').textContent = st.src ? av.length + ' Ordner, ' + nsel + ' davon gewählt' + (st.src_size != null ? ', zusammen ' + GB(st.src_size) : st.sizing ? ', Größe wird gezählt …' : '') : '';
    const dd = drv(st.dst_drive) || {}, total = st.dst_total || dd.total || 0, free = st.dst_free;
    const pre = !planned && st.pre_need != null;           // vor dem Probelauf: Mindestbedarf aus den Ordnergroessen (13.11.2026)
    const need = planned ? (st.need || 0) : pre ? st.pre_need : 0;
    const noFit = planned ? !st.fits : pre && st.pre_fits === false;
    if (total && free != null) {
      const u = 100 * (total - free) / total, a = Math.min(100 - u, 100 * need / total), over = noFit;
      $('space').innerHTML = '<i class="used" style="width:' + u.toFixed(1) + '%"></i><i class="' + (over ? 'over' : 'add') + '" style="width:' + (over ? 100 - u : a).toFixed(1) + '%"></i>';
      $('space').hidden = false;
    } else $('space').hidden = true;
    $('idst').innerHTML = free == null ? (st.dst ? 'Platz unbekannt' : '') : 'frei ' + GB(free) + (total ? ' von ' + GB(total) : '') +
      (planned ? ' · braucht etwa ' + GB(need) + (st.fits ? ' · <span class="ok">passt</span>' : ' · <span class="bad">passt nicht</span>')
        : pre ? ' · braucht mindestens ' + GB(need) + (st.pre_fits ? ' · <span class="ok">passt voraussichtlich</span> (genau sagt es der Probelauf)' : ' · <span class="bad">passt sicher nicht</span>: weniger Ordner anhaken oder Platz schaffen')
        : st.sizing ? ' · zähle, wie viel dazukommt …' : ' · wie viel dazukommt, zeigt der Probelauf');
    $('arrow').classList.toggle('no', !!noFit);
    $('arrow').title = noFit ? 'Passt nicht: am Ziel ist zu wenig Platz' : '';
    const sn = nameOf(st.src, st.src_drive), dn = nameOf(st.dst, st.dst_drive);
    $('dir').innerHTML = st.pair_err ? '<span class="warn">' + esc(st.pair_err) + '</span>' :
      '<b>' + esc(sn) + ' ➜ ' + esc(dn) + '</b>: Neues und Geändertes kommt von ' + esc(sn) + ' nach ' + esc(dn) + ', was in den gewählten Ordnern am Ziel zu viel ist, kommt in den Papierkorb von ' + esc(dn) + ' (' + esc(st.trash_name || '') + '). ' + esc(sn) + ' bleibt, wie es ist.';
    // Ordner
    $('foldsum').textContent = 'Ordner: ' + nsel + ' von ' + av.length + ' gewählt (antippen zum Ändern)';
    const fh = av.map(f => '<label><input type="checkbox" value="' + esc(f.name) + '"' + (f.sel ? ' checked' : '') + (busy ? ' disabled' : '') + '> ' + esc(f.name) + (f.there ? '' : ' <span class="warn">(am Ziel neu)</span>') + '</label>').join('') || '<span class="dim">Die Quelle hat keine Ordner.</span>';
    if (!$('folders').contains(document.activeElement) && $('folders').dataset.h !== fh) { $('folders').innerHTML = fh; $('folders').dataset.h = fh; }
    $('fall').disabled = $('fnone').disabled = busy;
    // Auswerfen je Seite (Wunsch 12.11.2026): fester Platz, ausgegraut, wenn es nicht geht
    for (const side of ['src', 'dst']) {
      const d = drv(side === 'src' ? st.src_drive : st.dst_drive), b = $('ej' + side);
      const why = !d ? 'nicht verbunden' : d.kind === 'net' ? 'Netzlaufwerk: trennt der Finder' : d.kind === 'int' ? 'interne Festplatte' : busy ? 'erst nach dem Spiegeln' : ejecting ? 'werfe aus …' : '';
      b.disabled = !!why;
      b.title = why || '„' + d.name + '“ am Musik-Rechner auswerfen';
      $('ejt' + side).textContent = why && why !== 'nicht verbunden' ? why : d ? d.name + (d.music ? ' (Musik-Stick)' : '') : '';
    }
    // NAS (nur wenn sie beteiligt ist)
    $('nasrow').hidden = !st.nas;
    if (st.nas) {
      $('nasinfo').innerHTML = 'NAS ' + (st.host ? esc(st.host) : '<span class="warn">nicht eingetragen</span>') + ': ' +
        (st.online ? '<span class="ok">läuft</span>' : '<span class="warn">nicht erreichbar</span>') + ' · schaltet ab um ' + (st.off_at || '–');
      $('left').textContent = st.left_s != null ? '(noch ' + hm(st.left_s) + ')' : '';
      $('bwake').hidden = !!st.online || !st.host;            // wecken nur, wenn sie schlaeft (Wunsch 10.11.2026)
      const w = st.wake || {};
      $('wake').textContent = w.state === 'wait' ? 'Wecke die NAS … (bis zu 4 Minuten)' : w.state === 'ok' ? '✓ NAS ist wach, Freigabe verbunden' : w.state === 'nomount' ? 'NAS ist wach, aber die Freigabe ist nicht verbunden: im Finder öffnen' : w.state === 'err' ? '⚠ ' + (w.error || '') : '';
    }
    // Hinweise
    const warn = [];
    if (st.to_music) warn.push('<div class="warn">Das Ziel ist dein Musik-Stick: während des Spiegelns ruhen Analyse, Ordner-Liste und Vorhören. Mixxx vorher beenden.' + (st.mixxx ? ' <b>Mixxx läuft gerade.</b>' : '') + '</div>');
    if (planned && st.big) warn.push('<div class="bad">⚠ ' + st.big + ' Dateien sind 4 GB oder größer: das Ziel ist FAT32 und kann sie nicht speichern.</div>');
    if (planned && !st.fits) warn.push('<div class="bad">⚠ Zu wenig Platz am Ziel: es braucht etwa ' + GB(need) + ', frei sind ' + GB(free) + '. Weniger Ordner wählen oder am Ziel Platz schaffen (Papierkorb leeren).</div>');
    if (planned && (st.del_total || 0) >= 20) warn.push('<div class="bad">⚠ Am Ziel kommen ' + st.del_total + ' Dateien weg (in den Papierkorb). Stimmt die Richtung ' + esc(sn) + ' ➜ ' + esc(dn) + '?</div>');
    if (st.trash && st.trash.bytes) warn.push('<div class="dim">Papierkorb am Ziel: ' + esc(st.trash.path) + ' (' + GB(st.trash.bytes) + '). Leeren im Finder, wenn du das alte nicht mehr brauchst.</div>');
    // nicht angehakte Ordner deutlich zeigen (Fehlerbericht 13.11.2026: "ausgeglichen", obwohl Screenshots fehlte; die Liste war zu)
    const off = av.filter(f => !f.sel);
    if (off.length && !$('foldbox').dataset.auto) { $('foldbox').open = true; $('foldbox').dataset.auto = '1'; }   // Kaestchen gleich zeigen
    if (off.length && st.src) warn.push('<div class="warn">' + off.length + ' Ordner der Quelle ' + (off.length === 1 ? 'ist' : 'sind') + ' nicht angehakt und ' + (off.length === 1 ? 'wird' : 'werden') + ' nicht gespiegelt: <b>' +
      off.slice(0, 8).map(f => esc(f.name) + (f.there ? '' : ' (fehlt am Ziel)')).join(', ') + (off.length > 8 ? ' …' : '') + '</b> <button id="offall"' + (busy ? ' disabled' : '') + '>Auch anhaken</button></div>');
    $('warn').innerHTML = warn.join('');
    if ($('offall')) $('offall').onclick = () => op({ op: 'sel', names: av.map(f => f.name) });
    // Dauer
    const sp = Math.round((st.speed || 0) / 1e6) + ' MB/s ' + (st.speed_measured ? '(gemessen beim letzten Lauf auf diesem Weg)' : '(angenommen, der erste Lauf misst es)');
    let eta = '';
    if (st.state === 'run' && same && st.rest_s != null) eta = '<div class="dim">Noch etwa ' + hm(st.rest_s) + ' (fertig gegen ' + clock(st.rest_s) + ').</div>';
    else if (planned && st.eta_s != null) eta = st.too_long
      ? '<div class="bad">⚠ Reicht nicht mehr: Spiegeln dauert etwa ' + hm(st.eta_s) + ', die NAS schaltet in ' + hm(st.left_s) + ' ab. Morgen spiegeln (vorher „NAS wecken“) oder die Abschaltzeit ändern.</div>'
      : '<div>Spiegeln dauert etwa <b>' + hm(st.eta_s) + '</b> (fertig gegen ' + clock(st.eta_s) + '). <span class="dim">Gerechnet mit ' + sp + ' und der Zeit des Probelaufs.</span></div>';
    else if (!busy && !st.pair_err && st.plan_est_s) eta = '<div class="dim">Der Probelauf dauert etwa ' + hm(st.plan_est_s) + ' (wie beim letzten Mal). Danach steht hier, wie lange das Spiegeln dauert.</div>';
    else if (!busy && !st.pair_err) eta = '<div class="dim">Nach dem Probelauf steht hier, wie lange das Spiegeln dauert.</div>';
    $('eta').innerHTML = eta;
    // Knoepfe am festen Platz
    $('bplan').disabled = busy || !!st.pair_err || !!st.plan_blocked || !nsel;
    $('bplan').title = st.plan_blocked ? 'Die NAS schaltet bald ab: heute keinen Probelauf mehr (dauert etwa ' + hm(st.plan_need_s) + ')' : '';
    $('brun').disabled = busy || !planned || !!st.sel_changed || !!st.too_long || !st.fits || !!st.big;
    $('bstop').disabled = !busy;
    $('last').textContent = st.last ? 'Zuletzt gespiegelt: ' + new Date(st.last * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
    $('bar').hidden = !busy;
    if (busy) $('bar').querySelector('i').style.width = (st.n ? 100 * (st.i || 0) / st.n : 0) + '%';
    const m = $('msg');
    if (!st.rsync) m.innerHTML = '<span class="bad">Am Musik-Rechner fehlt rsync 3. Im Terminal einmal: brew install rsync</span>';
    else if (st.state === 'plan') m.textContent = 'Probelauf: ' + (st.cur || '') + ' … (' + ((st.i || 0) + 1) + ' von ' + (st.n || '?') + ')';
    else if (st.state === 'run') m.textContent = 'Spiegle ' + (st.cur || '') + ' … (' + ((st.i || 0) + 1) + ' von ' + (st.n || '?') + ')';
    else if (planned && st.sel_changed) m.innerHTML = '<span class="warn">Die Ordner-Auswahl hat sich geändert: bitte noch einmal den Probelauf.</span>';
    else if (planned) m.textContent = 'Probelauf fertig. Verändert wurde nichts. Passt alles, tippe auf „Spiegeln“.';
    else if (st.state === 'ok' && same) m.innerHTML = '<span class="ok">Fertig: ' + (st.done || []).length + ' Ordner gespiegelt' + ((st.trashed_dirs || []).length ? ', in den Papierkorb: ' + esc(st.trashed_dirs.join(', ')) : '') + '. Ersetztes und Gelöschtes liegt in ' + esc(st.backup || '') + '.</span>';
    else if (st.state === 'stopped' && same) m.textContent = 'Angehalten. Ein neuer Probelauf zeigt, was noch fehlt.';
    else if (st.state === 'err' && same) m.innerHTML = '<span class="bad">' + esc(st.error || 'Fehler') + '</span>';
    else if (st.plan_blocked) m.innerHTML = '<span class="warn">Die NAS schaltet um ' + esc(st.off_at) + ' ab (in ' + hm(st.left_s) + '): heute kein Probelauf mehr, er dauert etwa ' + hm(st.plan_need_s) + '.</span>';
    else m.textContent = st.pair_err ? '' : 'Mit dem Probelauf beginnen.';
    // Ergebnis
    const fs = same ? (st.folders || []) : [];
    if (fs.length && (st.state === 'planned' || st.state === 'run' || st.state === 'ok')) {
      const sum = k => fs.reduce((a, f) => a + (f[k] || 0), 0);
      $('res').innerHTML = '<div class="box"><table><thead><tr><th>Ordner</th><th class="num">neu</th><th class="num">ersetzen</th><th class="num">löschen</th><th class="num">zu kopieren</th></tr></thead><tbody>' +
        fs.map(f => '<tr><td>' + esc(f.name) + (f.exists ? '' : ' <span class="warn">(neu am Ziel)</span>') + (f.err ? '<div class="bad">' + esc(f.err) + '</div>' : '') +
          (f.deleted && f.deleted.length ? '<details class="dl"><summary>' + f.delete + ' Dateien, die am Ziel wegkommen</summary><div>' + f.deleted.map(esc).join('<br>') + (f.delete > f.deleted.length ? '<br>…' : '') + '</div></details>' : '') + '</td>' +
          '<td class="num">' + (f.new || '') + '</td><td class="num">' + (f.replace || '') + '</td><td class="num del">' + (f.delete || '') + '</td><td class="num">' + (f.bytes ? GB(f.bytes) : '') + '</td></tr>').join('') +
        '<tr><td><b>Zusammen</b></td><td class="num"><b>' + sum('new') + '</b></td><td class="num"><b>' + sum('replace') + '</b></td><td class="num del"><b>' + sum('delete') + '</b></td><td class="num"><b>' + GB(sum('bytes')) + '</b></td></tr></tbody></table></div>';
    } else if (!busy) $('res').innerHTML = '';
    const gone = planned ? (st.gone || []) : [];
    const was = new Set([...document.querySelectorAll('#gone input:checked')].map(i => i.value));
    $('gone').innerHTML = gone.length ? '<div class="box"><b>An der Quelle nicht mehr da</b> (aufgelöst), am Ziel aber noch:<br>' + gone.map(g => '<label style="display:block;margin:4px 0"><input type="checkbox" value="' + esc(g) + '"' + (was.has(g) ? ' checked' : '') + '> ' + esc(g) + ' am Ziel auch in den Papierkorb legen</label>').join('') +
      '<div class="dim">Ohne Haken bleibt der Ordner am Ziel liegen.</div></div>' : '';
  }

  async function poll() {
    try { st = await mac('/mirror'); } catch (e) { fail(e); return; }
    draw();
    clearTimeout(timer);
    timer = setTimeout(poll, busyNow() || st.sizing || (st.wake && st.wake.state === 'wait') ? 1500 : 15000);   // Laufwerke und NAS nachfuehren
  }

  // Vorlagen
  $('pairs').addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b || b.disabled) return;
    if (b.dataset.p) return op({ op: 'pair', id: b.dataset.p });
    if (b.id === 'padd') {
      const n = await SM.ask('Name der neuen Vorlage (übernimmt Quelle und Ziel von jetzt):', 'Meine Spiegelung', 'Anlegen');
      if (n) op({ op: 'pair_add', name: n });
    }
    if (b.id === 'pren') {
      const curp = (st.pairs || []).find(p => p.id === st.pair) || {};
      const n = await SM.ask('Neuer Name der Vorlage:', curp.name || '', 'Umbenennen');
      if (n && n.trim() && n.trim() !== curp.name) op({ op: 'pair_rename', id: st.pair, name: n.trim() });
      return;
    }
    if (b.id === 'pdel' && await SM.ask('Vorlage „' + (((st.pairs || []).find(p => p.id === st.pair)) || {}).name + '“ löschen? Die Dateien bleiben, wo sie sind.', undefined, 'Löschen')) op({ op: 'pair_del', id: st.pair });
  });
  // Laufwerk aus der Liste
  $('ssrc').onchange = () => { if ($('ssrc').value) op({ op: 'drive', side: 'src', path: $('ssrc').value }); $('ssrc').blur(); };
  $('sdst').onchange = () => { if ($('sdst').value) op({ op: 'drive', side: 'dst', path: $('sdst').value }); $('sdst').blur(); };
  // Ordner anhaken
  $('folders').addEventListener('change', () => {
    clearTimeout(selTimer);
    selTimer = setTimeout(() => op({ op: 'sel', names: [...document.querySelectorAll('#folders input:checked')].map(i => i.value) }), 400);
  });
  async function eject(side) {
    const d = drv(side === 'src' ? st.src_drive : st.dst_drive);
    if (!d) return;
    try { if (!music) await mac('/mirror'); } catch (e) { fail(e); return; }
    ejecting = true; draw();
    const ok = await SM.ejectStick(music, (t, k) => { $('msg').innerHTML = '<span class="' + (k === 'err' ? 'bad' : k === 'ok' ? 'ok' : '') + '">' + esc(t) + '</span>'; }, d);
    ejecting = false;
    if (ok) { await new Promise(r => setTimeout(r, 1500)); }
    poll();
  }
  $('ejsrc').onclick = () => eject('src');
  $('ejdst').onclick = () => eject('dst');
  $('fall').onclick = () => op({ op: 'sel', names: (st.avail || []).map(f => f.name) });
  $('fnone').onclick = () => op({ op: 'sel', names: [] });

  // anderer Ordner: Laufwerke am Mac, durch die Ordner klicken
  async function showPick(p, fallback) {
    try {
      if (fallback) { try { await mac('/dirs?p=' + encodeURIComponent(p)); } catch (e) { p = fallback; } }
      const d = await mac('/dirs?p=' + encodeURIComponent(p || ''));
      pick = d;
      $('pickwhere').textContent = (pickSide === 'src' ? 'Quelle: ' : 'Ziel: ') + (d.path ? d.path : 'Laufwerke am Musik-Rechner');
      $('pick').innerHTML = d.path ? d.dirs.map((n, i) => '<button class="xdrv" data-i="' + i + '">📁 ' + esc(n) + '</button>').join('') || '<div class="dim">Keine Unterordner.</div>'
        : d.drives.map((v, i) => '<button class="xdrv" data-d="' + i + '">' + (v.kind === 'net' ? '🗄' : v.kind === 'home' ? '🖥' : '💾') + ' ' + esc(v.kind === 'home' ? 'Dieser Musik-Rechner (Benutzerordner)' : v.name) + (v.music ? ' <span class="dim">(dein Musik-Stick)</span>' : '') + '</button>').join('');
      $('ptake').disabled = !d.path;
      $('pup').disabled = !d.path;
      $('pnew').disabled = !d.path;
    } catch (e) { $('pickwhere').textContent = 'Fehler: ' + e.message; }
  }
  $('pick').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b || !pick) return;
    if (b.dataset.i != null) showPick(pick.path + '/' + pick.dirs[+b.dataset.i]);
    else if (b.dataset.d != null) showPick(pick.drives[+b.dataset.d].path);
  });
  const openPick = side => {                          // beim jetzigen Ordner anfangen; gibt es ihn (noch) nicht, beim Laufwerk
    pickSide = side;
    $('pickbox').hidden = false;
    const p = side === 'src' ? st.src : st.dst, dp = side === 'src' ? st.src_drive : st.dst_drive;
    showPick(dp ? p : '', dp);
  };
  $('bsrc').onclick = () => openPick('src');
  $('bdst').onclick = () => openPick('dst');
  $('pup').onclick = () => showPick(pick && pick.parent ? pick.parent : '');
  $('pclose').onclick = () => { $('pickbox').hidden = true; };
  // neuen Ordner anlegen (Wunsch 13.11.2026: ohne Finder), etwa „Backup Firmen PC“ am Ziel; danach gleich darin
  $('pnew').onclick = async () => {
    if (!pick || !pick.path) return;
    const name = await SM.ask('Name des neuen Ordners in ' + pick.path + ':', '', 'Anlegen');
    if (!name || !name.trim()) return;
    try {
      const d = await mac('/export', { op: 'mkdir', parent: pick.path, name: name.trim() });
      showPick(d.path);
    } catch (e) { $('pickwhere').textContent = 'Ordner anlegen: ' + e.message; }
  };
  $('ptake').onclick = async () => {
    try { st = await mac('/mirror', { op: 'folder', side: pickSide, path: pick.path }); $('pickbox').hidden = true; draw(); }
    catch (e) { $('pickwhere').textContent = 'Fehler: ' + e.message; }
  };

  $('bplan').onclick = async () => { try { st = await mac('/mirror', { op: 'plan' }); draw(); poll(); } catch (e) { fail(e); } };
  $('brun').onclick = async () => {
    const fs = (st && st.folders) || [], sum = k => fs.reduce((a, f) => a + (f[k] || 0), 0), NL = String.fromCharCode(10);
    const gone = [...document.querySelectorAll('#gone input:checked')].map(i => i.value);
    const sn = nameOf(st.src, st.src_drive), dn = nameOf(st.dst, st.dst_drive), many = (st.del_total || 0) >= 20;
    const txt = sn + '  ➜  ' + dn + NL + NL + 'Am Ziel ' + st.dst + ':' + NL + sum('new') + ' neu, ' + sum('replace') + ' ersetzen, ' + sum('delete') + ' löschen (' + GB(sum('bytes')) + '), etwa ' + hm(st.eta_s) +
      (gone.length ? NL + 'Ordner in den Papierkorb: ' + gone.join(', ') : '') +
      (many ? NL + NL + '⚠ ACHTUNG: am Ziel kommen ' + st.del_total + ' Dateien weg. Nur weiter, wenn die Richtung stimmt.' : '') +
      NL + NL + 'Ersetztes und Gelöschtes kommt in den Papierkorb des Ziels (' + (st.trash_name || '') + '). Jetzt spiegeln?';
    if (!await SM.ask(txt, undefined, many ? 'Ja, ' + st.del_total + ' Dateien weg' : 'Spiegeln')) return;
    try { st = await mac('/mirror', { op: 'run', gone, confirm_del: many }); draw(); poll(); } catch (e) { fail(e); }
  };
  $('bwake').onclick = async () => { try { st = await mac('/mirror', { op: 'wake' }); draw(); poll(); } catch (e) { $('wake').textContent = '⚠ ' + e.message; } };
  $('bstop').onclick = async () => { try { st = await mac('/mirror', { op: 'stop' }); draw(); } catch (e) { /* */ } poll(); };
  poll();
})();
