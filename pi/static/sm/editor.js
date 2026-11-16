// editor.js - Show-Editor: linke Leiste, Transport, Eigenschaften, Import, Speichern. Zeichnen und Ziehen stehen in timeline.js.
(function () {
  'use strict';
  const SM = window.SM, $ = id => document.getElementById(id), esc = SM.esc;
  const NAME = new URLSearchParams(location.search).get('show');
  if (!NAME) { location.replace('/shows'); return; }

  let meta = null, doc = null, tl = null, link = null;
  const hist = new SM.History();
  let clipboard = null, dirty = false, tab = 'fix', selFix = null, selScene = null, selGroup = null;
  let st = {}, stT = 0, liveTimer = null, liveDirty = false, editing = false;
  const audio = $('audio');
  let hasAudio = false;
  let wantLight = true;                      // Play im Editor geht ans Licht, der Knopf schaltet es ab (nur anhören)
  const lightShown = () => (st.loaded ? !!st.light : wantLight);

  // ---- Hilfen ----------------------------------------------------------------------------------------
  const fixOf = n => meta.fixtures.find(f => f.name === n);
  const allGroups = () => [...doc.groups, ...meta.groups];
  const groupOf = id => allGroups().find(g => g.id === id);
  const targetLabel = tg => {
    if (tg.master) return 'Master';
    if (tg.panel) return 'Panel-Szenen';
    if (tg.group) { const g = groupOf(tg.group); return '▣ ' + (g ? g.name : tg.group); }
    const f = fixOf(tg.fixture);
    return f ? (f.nr ? f.nr + ' ' : '') + f.label : tg.fixture + ' (fehlt)';
  };
  const attrsFor = tg => {
    if (!tg.group) { const f = fixOf(tg.fixture); return f ? f.attrs : []; }
    const g = groupOf(tg.group), seen = new Map();
    for (const n of (g ? g.fixtures : [])) { const f = fixOf(n); for (const a of (f ? f.attrs : [])) if (!seen.has(a.attr)) seen.set(a.attr, a); }
    return [...seen.values()];
  };
  const attrLabel = tr => { if (SM.isMaster(tr)) return 'Helligkeit aller Geräte'; if (tr.target.panel) return 'Szene aus dem Hauptpanel'; const a = attrsFor(tr.target).find(x => x.attr === tr.attr); return a ? a.label : tr.attr; };
  const patternOf = k => meta.patterns.find(p => p.key === k);
  const patternLabel = k => { const p = patternOf(k); return p ? p.label : k; };
  const beat = () => 60 / (doc.bpm || 120);
  const attrOf = tr => attrsFor(tr.target).find(x => x.attr === tr.attr);
  const stepped = tr => { const a = attrOf(tr); return !!(a && a.stepped); };
  const stepLabel = (tr, v) => {
    const a = attrOf(tr), o = a && a.options ? a.options.find(x => x.v === Math.round(v)) : null;
    return o ? o.label : String(Math.round(v));
  };
  const newStepValue = (tr, t) => {           // neue Stufe: wie an dieser Stelle, sonst die erste aus der Liste
    const cur = SM.keyValueAt(tr, t);
    if (cur !== null) return cur;
    const a = attrOf(tr);
    return a && a.options && a.options.length ? a.options[0].v : 0;
  };

  // Vor dem Wechsel zu einer anderen Show alle Fenster zu: sonst holt "Zurueck" die Seite mit offenem Fenster wieder
  const closeModals = () => document.querySelectorAll('.modal').forEach(m => m.remove());
  // Holt der Browser die Seite aus seinem Zwischenspeicher (Zurueck), steht sonst der alte Stand da: neu laden
  window.addEventListener('pageshow', e => { if (e.persisted) { closeModals(); if (!dirty) location.reload(); } });
  function modal(html, wire) {
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = '<div class="box">' + html + '</div>';
    document.body.appendChild(m);
    const close = () => m.remove();
    wire(m, close);
    return close;
  }
  const ask = (title, val, label) => new Promise(res => modal(
    '<h2>' + esc(title) + '</h2><div class="row"><input id="askv" style="flex:1" value="' + esc(val === undefined ? '' : val) + '"></div><div class="row"><button id="askok" class="on">' + (label || 'OK') + '</button><button id="askno">Abbrechen</button></div>',
    (m, close) => {
      const i = m.querySelector('#askv');
      i.focus(); i.select();
      const ok = () => { close(); res(i.value); };
      m.querySelector('#askok').onclick = ok;
      m.querySelector('#askno').onclick = () => { close(); res(null); };
      i.onkeydown = e => { if (e.key === 'Enter') ok(); if (e.key === 'Escape') { close(); res(null); } };
    }));
  const confirmBox = (title, label) => new Promise(res => modal(
    '<h2>' + esc(title) + '</h2><div class="row"><button id="askok" class="on">' + esc(label || 'Ja') + '</button><button id="askno">Abbrechen</button></div>',
    (m, close) => { m.querySelector('#askok').onclick = () => { close(); res(true); }; m.querySelector('#askno').onclick = () => { close(); res(false); }; }));

  // ---- Aenderungen -----------------------------------------------------------------------------------
  function begin() { hist.push(doc); }
  function setDirty(on) { dirty = on; $('dirty').textContent = on ? ' •' : ''; }
  function commit() {
    setDirty(true);
    tl.setDoc(doc);
    renderBot();
    if (tab === 'scene' || tab === 'grp') renderList();
    pushLive();
  }
  function pushLive() {                      // die Engine bekommt jede Aenderung, das Licht folgt beim Bearbeiten
    liveDirty = true;
    clearTimeout(liveTimer);
    liveTimer = setTimeout(flushLive, 180);
  }
  async function flushLive() {
    clearTimeout(liveTimer);
    if (!liveDirty) return;
    liveDirty = false;
    try { await SM.cmd('live', { name: NAME, doc }); } catch (e) { SM.toast(e.message); }
  }
  function swapDoc(d) { d.marks = doc.marks; if (!d.marks) delete d.marks; d.lyrics = doc.lyrics; if (!d.lyrics) delete d.lyrics; doc = d; afterSwap(); }   // die Cues kommen aus dem Lied, Undo laesst sie stehen
  function undo() { const d = hist.undo(doc); if (d) swapDoc(d); }
  function redo() { const d = hist.redo(doc); if (d) swapDoc(d); }
  function afterSwap() { $('grid').value = doc.grid; $('bpmv').textContent = fmtBpm(); commit(); }
  const fmtBpm = () => (Math.round(doc.bpm * 100) / 100).toString();

  // Abschnitte und Cues: das Lied muss nur einmal in einem Deck liegen, der Pi behaelt sie in der Showdatei
  let marksWarn = false;
  // Fehlen der Show Abschnitte und Cue-Punkte, holt der Editor sie einmal vom Mac (Analyse der Bruecke, auch wenn das Lied nie
  // in einem Deck lag). Laeuft der Mac nicht, kommen sie wie bisher, sobald das Lied in Mixxx liegt (Wunsch von Markus 06.11.2026).
  let macTried = false;
  async function pollMarks() {
    let r;
    try { r = await SM.cmd('marks', { name: NAME }); } catch (e) { return; }
    const m0 = r.marks || {};
    if (!macTried && (doc.mixxx || {}).title && !(m0.se || []).length && !(m0.cu || []).length) {
      macTried = true;
      try { const x = await SM.cmd('marks_from_mac', { name: NAME }); if (x.found) r = await SM.cmd('marks', { name: NAME }); } catch (e) { /* Mac aus */ }
    }
    if (r.warn && !marksWarn) SM.toast('Abschnitte und Cues stammen aus einer anderen Datei als die MP3 dieser Show, sie können versetzt liegen.', 8000);
    const changed = JSON.stringify(r.marks || null) !== JSON.stringify(doc.marks || null) || r.warn !== marksWarn;
    marksWarn = r.warn;
    if (!changed) return;
    if (r.marks) doc.marks = r.marks; else delete doc.marks;
    tl.need = true;
    if (!$('bot').contains(document.activeElement)) renderBot();
  }

  async function save() {
    try {
      const used = new Set(doc.tracks.flatMap(t => t.clips.map(c => c.label)));
      const r = await SM.cmd('save', { name: NAME, doc, patterns: meta.library.filter(p => used.has(p.name)) });
      doc = Object.assign(r.doc, { ui: doc.ui });
      setDirty(false);
      tl.setDoc(doc);
      SM.toast('Gespeichert' + (r.warnings && r.warnings.length ? ' (' + r.warnings.join(', ') + ')' : ''));
    } catch (e) { SM.toast('Speichern ging nicht: ' + e.message, 6000); }
  }

  // ---- Transport -------------------------------------------------------------------------------------
  const localPlaying = () => hasAudio && !audio.paused && !audio.ended;
  function position() {
    if (hasAudio && (localPlaying() || !st.playing)) return audio.currentTime;
    if (st.playing) return st.pos + (performance.now() - stT) / 1000;
    return st.pos || 0;
  }
  const takeOver = async () => {           // Play hier: diese Show laeuft, auch wenn gerade eine andere geladen war
    clearTimeout(liveTimer); liveDirty = false;
    await SM.cmd('live', { name: NAME, doc, force: true });
  };
  let ownPlay = false, laserWarned = false;
  async function togglePlay() {
    if (localPlaying() || (!hasAudio && st.playing)) { await pause(); return; }
    try {
      tl.userView = false;                   // Play: die Linie wird wieder verfolgt
      await takeOver();
      if (hasAudio) await audio.play();
      updateStatus(await SM.cmd('play', { pos: position(), light: lightShown(), client: link.client }));
      ownPlay = true;
    } catch (e) { SM.toast(e.message, 5000); }
  }
  async function pause() {
    if (hasAudio) audio.pause();
    updateStatus(await SM.cmd('pause', { pos: position() }));
  }
  async function stop() {
    if (hasAudio) { audio.pause(); audio.currentTime = 0; }
    updateStatus(await SM.cmd('stop'));
    tl.pos = 0;
  }
  let seekT = 0, seekPend = null;
  function seek(t) {
    t = SM.clamp(t, 0, doc.duration);
    if (hasAudio) audio.currentTime = t;
    tl.pos = t;
    if (!st.pos && !st.loaded) { st.pos = t; }
    st.pos = t; stT = performance.now();
    if (!st.loaded) return;
    seekPend = t;
    const now = performance.now();
    if (now - seekT > 90) { seekT = now; SM.cmd('seek', { pos: t }).catch(() => {}); seekPend = null; }
    else setTimeout(() => { if (seekPend !== null) { SM.cmd('seek', { pos: seekPend }).catch(() => {}); seekPend = null; seekT = performance.now(); } }, 100);
  }
  async function setLight(on) {
    wantLight = on;
    if (!on && !st.loaded) { updateStatus(st); return; }
    if (on && !st.loaded) await takeOver(); else await flushLive();
    if (on && !st.loaded) {                    // Vorschau: Licht folgt auch im Stillstand der Abspielposition
      await SM.cmd('play', { pos: position(), light: true, client: link.client });
      if (!localPlaying()) updateStatus(await SM.cmd('pause', { pos: position() }));
    } else if (!on && st.loaded && !st.playing) updateStatus(await SM.cmd('stop'));
    else updateStatus(await SM.cmd('light', { on }));
  }
  function updateStatus(s) {
    if (!s || s.t === 'pong') return;
    const wasStrobeWarn = st.uses_strobe && !st.strobe;
    st = s; stT = performance.now();
    if (ownPlay && !st.loaded) {             // von außen beendet (Knopf SHOW im Panel) oder zu Ende: Musik auch hier aus
      ownPlay = false;
      if (localPlaying()) audio.pause();
    }
    const pl = localPlaying() || st.playing;
    $('bplay').textContent = pl ? '⏸' : '▶';
    $('bplay').classList.toggle('on', pl);
    const b = $('blight');
    b.textContent = lightShown() ? 'Licht an' : 'Licht aus';
    b.classList.toggle('on', lightShown());
    $('blk').classList.toggle('on', !!st.blackout);
    const y = $('syncst');
    if (st.playing && st.src === 'mixxx') y.innerHTML = '<b>● Mixxx</b> ' + esc(st.name);
    else if (st.playing && st.src === 'browser') y.innerHTML = '<b>● Synchron</b> ' + Math.round(Math.abs(st.err_ms)) + ' ms';
    else if (st.playing) y.innerHTML = '<b class="free">● Eigene Uhr</b>';
    else y.textContent = st.loaded ? 'Pause' : '';
    if (st.loaded && st.uses_laser && !st.laser_allowed && !laserWarned) { laserWarned = true; SM.toast('Laser-Clips wirken nicht: „Laser in Shows erlauben“ ist aus.', 5000); }
    if (st.uses_strobe && !st.strobe && !wasStrobeWarn && st.loaded) SM.toast('Strobe nicht erlaubt: höchstens 2 Blitze pro Sekunde. Erlaubnis im Panel.', 5000);
    if (st.vals) drawVals();
  }
  // Linie und Zeit im Bild: geglättet und um den Anzeige-Versatz vorgezogen, nur beim Abspielen. Stillstand und Licht bleiben exakt.
  // Loop, nur im Editor: läuft auch weiter, wenn der Tab im Hintergrund ist (dort ruht das Bild, nicht der Ton)
  let loopPrev = null;
  function checkLoop() {
    if (!doc || !tl) return;
    const playing = localPlaying() || !!st.playing;
    if (!playing || st.src === 'mixxx') { loopPrev = null; return; }   // aus Mixxx gibt das Deck die Zeit vor
    const pos = position(), to = SM.loopJump(loopPrev, pos, tl.loop);
    if (to !== null) { seek(to); loopPrev = to; return; }
    loopPrev = pos;
  }
  function saveLoop() {
    const on = !!(tl.loop && tl.loop.on);
    $('bloop').classList.toggle('on', on);
    $('bloopx').style.display = tl.loop ? '' : 'none';
    try { localStorage.setItem('smloop:' + NAME, JSON.stringify(tl.loop)); } catch (e) { /* privates Fenster */ }
  }
  function toggleLoop() {
    const off = tl.loop && !tl.loop.on;
    if (tl.loop && (tl.loop.on || tl.visible(tl.loop.t0, tl.loop.t1))) tl.loop.on = !tl.loop.on;
    else {                                   // kein Bereich oder er liegt außerhalb der Ansicht: hier neu, aus der Auswahl oder vier Takte
      const sel = SM.loopFromSelection(doc, tl.sel);
      const from = tl.visible(tl.pos, tl.pos + 0.001) ? tl.pos : tl.t(tl.hw);
      const t0 = SM.snap(from, doc, doc.grid), len = 60 / doc.bpm * doc.beats_per_bar * 4;
      tl.loop = sel ? { ...sel, on: true } : { t0, t1: Math.min(doc.duration, t0 + len), on: true };
      SM.toast(off ? 'Loop hierher gesetzt.' : 'Loop gesetzt. Im Lineal oben kannst du ihn ziehen und seine Ränder verschieben.', 4000);
      loopArrive();
    }
    tl.need = true;
    saveLoop();
  }
  function clearLoop() {
    tl.loop = null;
    tl.need = true;
    saveLoop();
  }
  // Neuer Bereich beim Abspielen: gleich dorthin, sonst liefe die Musik außerhalb einfach weiter
  function loopArrive() {
    tl.userView = false;
    if ((localPlaying() || st.playing) && tl.loop && (position() < tl.loop.t0 || position() >= tl.loop.t1)) { seek(tl.loop.t0); loopPrev = tl.loop.t0; }
  }
  const smooth = new SM.SmoothClock();
  let displayLead = SM.displayLead();
  function frame() {
    if (!doc) return;
    checkLoop();
    const playing = localPlaying() || !!st.playing;
    const p = smooth.update(position(), performance.now(), playing) + (playing ? displayLead / 1000 : 0);
    tl.pos = position();                     // exakt: daran setzen K, Einfügen und Ablegen ihre Zeit
    tl.linePos = playing ? p : tl.pos;       // nur die Linie im Bild
    $('time').textContent = SM.fmtTime(tl.linePos);
    if (playing) tl.follow(p);
  }

  // ---- Bearbeiten-Knoepfe ------------------------------------------------------------------------------
  function deleteSel() {
    if (!tl.sel.size) return;
    begin();
    SM.deleteEvents(doc, tl.sel);
    tl.sel.clear();
    commit();
  }
  function copySel() { clipboard = SM.copyEvents(doc, tl.sel); if (clipboard) SM.toast(clipboard.items.length + ' kopiert', 1200); }
  function cutSel() { copySel(); deleteSel(); }
  function paste() {
    if (!clipboard) return;
    begin();
    const ids = SM.pasteEvents(doc, clipboard, SM.snap(tl.pos, doc, doc.grid));
    tl.sel = new Set(ids);
    commit();
  }
  function addKeyHere() {
    const tr = doc.tracks.find(t => t.id === tl.selTrack);
    if (!tr) { SM.toast('Zuerst links in der Timeline eine Spur antippen'); return; }
    if (SM.clipsOnly(tr.attr)) { SM.toast('Auf dieser Spur gibt es nur Clips: unter Muster auf die Spur ziehen'); return; }
    const kind = SM.kindOf(tr.attr);
    begin();
    const jump = stepped(tr);
    const k = SM.addKey(doc, tr, SM.snap(tl.pos, doc, doc.grid), jump ? newStepValue(tr, tl.pos) : (SM.keyValueAt(tr, tl.pos) || SM.defaultValue(kind)), jump ? 'constant' : 'linear');
    tl.sel = new Set([k.id]);
    commit();
  }

  // ---- Linke Leiste ------------------------------------------------------------------------------------
  const TABS = [['fix', 'Geräte'], ['grp', 'Gruppen'], ['pat', 'Muster'], ['scene', 'Szenen']];
  function renderTabs() {
    $('tabs').innerHTML = TABS.map(([k, t]) => '<button data-t="' + k + '" class="' + (tab === k ? 'on' : '') + '">' + t + '</button>').join('');
    $('tabs').querySelectorAll('button').forEach(b => { b.onclick = () => { tab = b.dataset.t; renderTabs(); renderList(); }; });
  }
  function draggable(el, payload, label) {
    let start = null, ghost = null;
    el.addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target.closest('button,a,input')) return;
      start = [e.clientX, e.clientY];
      if (e.pointerType === 'mouse') { try { el.setPointerCapture(e.pointerId); } catch (x) { /* schon weg */ } }   // auch schnelles Wegziehen kommt an
    });
    el.addEventListener('pointermove', e => {
      if (!start) return;
      if (!ghost && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 8) {
        ghost = document.createElement('div');
        ghost.id = 'ghost'; ghost.textContent = label;
        document.body.appendChild(ghost);
        try { el.setPointerCapture(e.pointerId); } catch (x) { /* Finger schon weg */ }
        if (innerWidth <= 820) $('left').classList.remove('open');
      }
      if (ghost) { ghost.style.left = e.clientX + 'px'; ghost.style.top = e.clientY + 'px'; }
    });
    const end = e => {
      if (ghost) {
        ghost.remove(); ghost = null;
        if (e.type === 'pointerup') dropPayload(payload, e.clientX, e.clientY);
      }
      start = null;
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }
  function renderList() {
    const L = $('list');
    L.innerHTML = '';
    const add = html => { const d = document.createElement('div'); d.innerHTML = html; const el = d.firstElementChild; L.appendChild(el); return el; };
    if (tab === 'fix') {
      for (const f of meta.fixtures) {
        const el = add('<div class="item' + (!f.attrs.length ? ' locked' : '') + (selFix === f.name ? ' sel' : '') + '"><span class="nm">' + (f.nr ? f.nr + ' · ' : '') + esc(f.label) + '<br><small>DMX ' + f.address + ' · ' + f.channels + ' K' + (f.attrs.length ? '' : ' · gesperrt') + '</small></span></div>');
        el.onclick = () => { selFix = f.name; selScene = selGroup = null; tl.sel.clear(); link.setWatch(f.name); renderList(); renderBot(); };
        if (f.attrs.length) draggable(el, { kind: 'target', target: { fixture: f.name } }, f.label);
      }
      add('<div class="row"><a href="/fixtures"><button>Geräte bearbeiten</button></a><button id="bprof">Profil laden</button><input type="file" id="fprof" accept=".json" hidden></div>');
      $('bprof').onclick = () => $('fprof').click();
      $('fprof').onchange = e => importProfile(e.target.files[0]);
    } else if (tab === 'grp') {
      for (const g of allGroups()) {
        const el = add('<div class="item' + (selGroup === g.id ? ' sel' : '') + '"><span class="nm">▣ ' + esc(g.name) + '<br><small>' + g.fixtures.length + ' Geräte' + (g.builtin ? ' · aus dem Aufbau' : '') + '</small></span></div>');
        el.onclick = () => { selGroup = g.id; selFix = selScene = null; tl.sel.clear(); renderList(); renderBot(); };
        draggable(el, { kind: 'target', target: { group: g.id } }, g.name);
      }
      add('<div class="row"><button id="bgnew">+ Gruppe</button></div>');
      $('bgnew').onclick = async () => {
        const n = await ask('Neue Gruppe', '');
        if (!n) return;
        begin();
        const g = { id: SM.uid('g'), name: n, fixtures: [] };
        doc.groups.push(g);
        selGroup = g.id; selFix = selScene = null;
        commit(); renderList();
      };
    } else if (tab === 'pat') {
      const cats = [];
      for (const p of meta.patterns) if (!cats.includes(p.cat)) cats.push(p.cat);
      for (const c of cats) {
        add('<h3>' + esc(c) + '</h3>');
        for (const p of meta.patterns.filter(x => x.cat === c)) {
          const el = add('<div class="item"><span class="nm">' + esc(p.label) + '</span></div>');
          draggable(el, { kind: 'pattern', pattern: p.key, label: '' }, p.label);
        }
      }
      if (meta.library.length) add('<h3>Eigene Muster</h3>');
      for (const p of meta.library) {
        const el = add('<div class="item"><span class="nm">★ ' + esc(p.name) + '<br><small>' + esc(patternLabel(p.pattern)) + '</small></span><button class="danger" title="Löschen">×</button></div>');
        draggable(el, { kind: 'pattern', pattern: p.pattern, p: p.p, label: p.name, d: p.d }, p.name);
        el.querySelector('button').onclick = async () => {
          meta.library = meta.library.filter(x => x !== p);
          await SM.cmd('library_save', { patterns: meta.library });
          renderList();
        };
      }
      add('<p class="dim" style="margin:8px 2px">Laser auf Eyes, Derby oder KTV ziehen, Nebelschub auf den Hazer. Beides wirkt nur mit dem Hakerl in den Einstellungen.</p>');
      add('<p class="dim" style="margin:8px 2px">Auf eine Spur ziehen. Ein Clip lässt sich unten einstellen und als eigenes Muster speichern.</p>');
    } else {
      for (const s of doc.scenes) {
        const el = add('<div class="item' + (selScene === s.id ? ' sel' : '') + '"><span class="nm">' + esc(s.name) + '<br><small>' + Object.keys(s.values).length + ' Geräte</small></span></div>');
        el.onclick = () => { selScene = s.id; selFix = selGroup = null; tl.sel.clear(); renderList(); renderBot(); };
        draggable(el, { kind: 'scene', scene: s.id }, s.name);
      }
      add('<div class="row"><button id="bsnew">+ Szene</button><button id="bscap" title="Speichert, was an der Abspielposition programmiert ist">+ Aus Position</button></div>');
      add('<p class="dim" style="margin:8px 2px">Szenen in die Zeile „Szenen“ der Timeline ziehen.</p>');
      const mk = async (values, title) => {
        const n = await ask(title, 'Szene ' + (doc.scenes.length + 1));
        if (!n) return;
        begin();
        const s = { id: SM.uid('s'), name: n, values };
        doc.scenes.push(s);
        selScene = s.id; selFix = selGroup = null;
        commit(); renderList();
      };
      $('bsnew').onclick = () => mk({}, 'Neue Szene');
      $('bscap').onclick = async () => {
        await flushLive();
        const r = await SM.cmd('capture', { t: tl.pos });
        mk(r.values, 'Szene aus der Position ' + SM.fmtTime(tl.pos));
      };
    }
  }
  async function importProfile(file) {
    if (!file) return;
    try {
      const r = await SM.cmd('profile_import', { profile: JSON.parse(await file.text()) });
      SM.toast('Profil „' + r.type + '“ gespeichert. Gerät damit unter „Geräte bearbeiten“ anlegen.', 6000);
    } catch (e) { SM.toast(e.message, 6000); }
  }
  function dropPayload(pl, cx, cy) {
    const info = tl.dropInfo(cx, cy);
    if (!info) return;
    if (pl.kind === 'target') {
      begin();
      const attrs = attrsFor(pl.target).filter(a => ['dimmer', 'color', 'move'].includes(a.attr));
      for (const a of (attrs.length ? attrs : attrsFor(pl.target).slice(0, 1))) SM.ensureTrack(doc, pl.target, a.attr);
      commit();
    } else if (pl.kind === 'scene') {
      begin();
      const c = SM.addSceneClip(doc, info.t, beat() * doc.beats_per_bar * 4, pl.scene);
      tl.sel = new Set([c.id]);
      commit();
    } else if (pl.kind === 'pattern') {
      const p = patternOf(pl.pattern);
      if (p.out === 'panel') { addPanelScene(info.t); return; }
      if (info.row && info.row.panel) { SM.toast('Die Zeile nimmt nur Szenen aus dem Panel'); return; }
      if (info.row && info.row.master) { SM.toast('Die Master-Zeile nimmt nur Keyframes, Muster gehören auf eine Gerätespur'); return; }
      let target = info.row ? info.row.target || (info.row.track && info.row.track.target) : null;
      if (!target && selFix) target = { fixture: selFix };
      if (!target) { SM.toast('Muster auf eine Spur ziehen'); return; }
      const attrs = attrsFor(target);
      let attr = null;
      if (info.row && info.row.track && SM.kindOf(info.row.track.attr) === p.out && !stepped(info.row.track)) attr = info.row.track.attr;
      else if (p.out === 'laser' || p.out === 'fog' || p.out === 'nano_fx') attr = attrs.some(a => a.attr === p.out) ? p.out : null;
      else if (p.out === 'color') attr = attrs.some(a => a.attr === 'color') ? 'color' : null;
      else if (p.out === 'move') attr = attrs.some(a => a.attr === 'move') ? 'move' : null;
      else attr = attrs.some(a => a.attr === 'dimmer') ? 'dimmer' : null;
      if (!attr) { SM.toast('Dieses Gerät hat keine passende Spur für „' + p.label + '“'); return; }
      begin();
      const tr = SM.ensureTrack(doc, target, attr);
      const c = SM.addClip(tr, info.t, pl.d || (p.out === 'fog' ? 3 : beat() * doc.beats_per_bar * 2), pl.pattern, pl.p || p.defaults, pl.label);
      tl.selTrack = tr.id;
      tl.sel = new Set([c.id]);
      commit();
    }
  }

  // ---- Unten: Eigenschaften ------------------------------------------------------------------------------
  function changed(fn) {           // beim Ziehen eines Reglers nur ein Undo-Schritt
    return e => {
      if (!editing) { begin(); editing = true; }
      fn(e);
      setDirty(true);
      tl.need = true;
      pushLive();
      if (e.type === 'change') { editing = false; tl.setDoc(doc); }
    };
  }
  const F = {
    num(label, val, lo, hi, step, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><div class="rg"><input type="range" min="' + lo + '" max="' + hi + '" step="' + step + '" value="' + val + '"><input type="number" min="' + lo + '" max="' + hi + '" step="' + step + '" value="' + (+val) + '"></div>';
      const [r, n] = w.querySelectorAll('input');
      const h = changed(e => { const v = SM.clamp(+e.target.value || 0, lo, hi); on(v); (e.target === r ? n : r).value = v; });
      r.oninput = h; r.onchange = h; n.oninput = h; n.onchange = h;
      return w;
    },
    time(label, val, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><div class="rg"><input type="text" inputmode="decimal" value="' + SM.fmtTime(val) + '"><button type="button" class="stp" title="Einen Rasterschritt weniger (Pfeil runter)">▼</button><button type="button" class="stp" title="Einen Rasterschritt mehr (Pfeil rauf)">▲</button></div>';
      const i = w.querySelector('input');
      const [dn, up] = w.querySelectorAll('button');
      i.onchange = () => {
        const v = SM.parseTime(i.value);
        if (v === null) { SM.toast('Zeit bitte als 1:23.500 oder in Sekunden'); i.value = SM.fmtTime(val); return; }
        begin(); on(v); SM.resort(doc); commit();
      };
      const step = (dir, refocus) => {           // beim Halten eines Felds bleibt der Stand, jeder Schritt ein Undo
        const cur = SM.parseTime(i.value);
        begin(); on(Math.max(0, (cur === null ? val : cur) + dir * SM.timeStep(doc))); SM.resort(doc); commit();
        if (refocus) { const n = [...$('bot').querySelectorAll('label')].find(l => l.firstChild.textContent === label); if (n) n.querySelector('input').focus(); }
      };
      dn.onclick = e => { e.preventDefault(); step(-1); };
      up.onclick = e => { e.preventDefault(); step(1); };
      i.onkeydown = e => {
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); step(e.key === 'ArrowUp' ? 1 : -1, true); }
      };
      return w;
    },
    select(label, val, options, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><select>' + options.map(([k, t]) => '<option value="' + esc(k) + '"' + (k === val ? ' selected' : '') + '>' + esc(t) + '</option>').join('') + '</select>';
      w.querySelector('select').onchange = e => { begin(); on(e.target.value); commit(); };
      return w;
    },
    color(label, val, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><input type="color" value="' + val + '">';
      const i = w.querySelector('input');
      const h = changed(e => on(e.target.value));
      i.oninput = h; i.onchange = h;
      return w;
    },
    check(label, val, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><input type="checkbox"' + (val ? ' checked' : '') + ' style="width:auto;align-self:flex-start;min-height:22px">';
      w.querySelector('input').onchange = e => { begin(); on(e.target.checked ? 1 : 0); commit(); };
      return w;
    },
    text(label, val, on) {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><input type="text" value="' + esc(val || '') + '">';
      w.querySelector('input').onchange = e => { begin(); on(e.target.value); commit(); };
      return w;
    },
  };
  function head(html) { const d = document.createElement('div'); d.className = 'bothead'; d.innerHTML = html; return d; }
  function form() { const d = document.createElement('div'); d.className = 'form'; return d; }
  function button(text, fn, cl) { const b = document.createElement('button'); b.textContent = text; b.onclick = fn; if (cl) b.className = cl; return b; }

  function valueFields(f, kind, v, tr, set) {
    if (kind === 'color') {
      f.appendChild(F.color('Farbe', SM.colorToHex(v), h => set(SM.hexToColor(h, v[3], v[4]))));
      f.appendChild(F.num('Weiß', v[3] || 0, 0, 255, 1, x => { v[3] = x; set(v); }));
      f.appendChild(F.num('UV', v[4] || 0, 0, 255, 1, x => { v[4] = x; set(v); }));
    } else if (kind === 'move') {
      f.appendChild(F.num('Links/Rechts', v[0], 0, 1, 0.01, x => { v[0] = x; set(v); }));
      f.appendChild(F.num('Oben/Unten', v[1], 0, 1, 0.01, x => { v[1] = x; set(v); }));
    } else {
      const a = tr ? attrsFor(tr.target).find(x => x.attr === tr.attr) : null;
      if (a && a.options) {
        const cur = Math.round(v), known = a.options.some(o => o.v === cur);
        const opts = a.options.map(o => [String(o.v), o.label]);
        if (!known) opts.unshift([String(cur), 'Wert ' + cur]);
        f.appendChild(F.select(a.label, String(cur), opts, x => set(+x)));
      }
      f.appendChild(F.num(a && a.options ? 'Nummer' : 'Wert', v, a ? a.lo : 0, a ? a.hi : 255, 1, set));
    }
  }
  function renderBot() {
    const B = $('bot');
    B.innerHTML = '';
    if (!doc) return;
    if (tl.sel.size > 1) {
      B.appendChild(head('<b>' + tl.sel.size + ' Ereignisse gewählt</b>'));
      const f = form();
      const items = [...tl.sel].map(id => SM.find(doc, id)).filter(Boolean);
      const first = Math.min(...items.map(x => x.ev.t));
      f.appendChild(F.time('Erstes Ereignis bei', first, v => SM.moveEvents(doc, tl.sel, v - first)));
      B.appendChild(f);
      return;
    }
    if (tl.sel.size === 1) {
      const x = SM.find(doc, [...tl.sel][0]);
      if (x) { (x.type === 'key' ? botKey : x.type === 'clip' ? botClip : botSceneClip)(B, x); return; }
    }
    if (selScene) { botScene(B); return; }
    if (selGroup) { botGroup(B); return; }
    if (selFix) { botFixture(B); return; }
    botShow(B);
  }
  function botKey(B, x) {
    const k = x.ev, tr = x.track, kind = SM.kindOf(tr.attr);
    B.appendChild(head('<b>◆ Keyframe</b><span class="dim">' + esc(targetLabel(tr.target)) + ' · ' + esc(attrLabel(tr)) + '</span>'));
    const f = form();
    f.appendChild(F.time('Zeit', k.t, v => { k.t = Math.max(0, v); }));
    valueFields(f, kind, k.v, tr, v => { k.v = v; });
    if (!stepped(tr)) f.appendChild(F.select('Bis zum nächsten', k.e, SM.EASES, v => { k.e = v; }));
    B.appendChild(f);
  }
  function botClip(B, x) {
    const c = x.ev, tr = x.track, p = patternOf(c.pattern), kind = SM.kindOf(tr.attr);
    const h = head('<b>' + esc(p.label) + '</b><span class="dim">' + esc(targetLabel(tr.target)) + ' · ' + esc(attrLabel(tr)) + '</span>');
    h.appendChild(button('Als eigenes Muster', async () => {
      const n = await ask('Name des Musters', c.label || p.label);
      if (!n) return;
      meta.library = meta.library.filter(e => e.name !== n);
      meta.library.push({ name: n, pattern: c.pattern, p: SM.clone(c.p), d: c.d });
      await SM.cmd('library_save', { patterns: meta.library });
      SM.toast('Gespeichert: ' + n);
      if (tab === 'pat') renderList();
    }));
    B.appendChild(h);
    if (kind === 'laser' && !st.laser_allowed) B.appendChild(head('<span class="warn">Wirkt nicht: Einstellungen allgemein → Ausgabe → „Laser in Shows erlauben“ ist aus.</span>'));
    if (kind === 'fog' && !st.fog_allowed) B.appendChild(head('<span class="warn">Wirkt nicht: Einstellungen allgemein → Ausgabe → „Nebel in Shows erlauben“ ist aus.</span>'));
    if (kind === 'laser') B.appendChild(head('<span class="warn">Nie auf Personen oder in Augenhöhe richten. Bei Pause und Springen ist der Laser aus.</span>'));
    if (kind === 'fog') B.appendChild(head('<span class="dim">Höchstens 10 s, danach Mindestpause wie beim SMOKE-Knopf. Ist die Maschine aus oder kalt, entfällt der Schub. Vorsicht Rauchmelder.</span>'));
    const f = form();
    f.appendChild(F.time('Startzeit', c.t, v => { c.t = Math.max(0, v); }));
    f.appendChild(F.time('Dauer', c.d, v => { c.d = Math.max(0.025, kind === 'fog' ? Math.min(10, v) : v); }));
    f.appendChild(F.select('Muster', c.pattern, meta.patterns.filter(q => q.out === kind).map(q => [q.key, q.label]), v => { c.pattern = v; c.p = SM.clone(patternOf(v).defaults); }));
    const widgets = {};
    for (const k of p.params) {
      const d = meta.params[k], val = (c.p && c.p[k] !== undefined) ? c.p[k] : p.defaults[k];
      if (k + '_to' in p.defaults) {             // Von und Bis: solange beide gleich sind, geht Bis mit, es entsteht kein Verlauf
        const prevTo = c.p[k + '_to'] === undefined ? val : c.p[k + '_to'];
        if (c.p[k + '_to'] === undefined) c.p[k + '_to'] = prevTo;
        const w = F.num(d.label, val, d.lo, d.hi, d.step, v => {
          const linked = c.p[k + '_to'] === c.p[k] || c.p[k] === undefined;
          c.p[k] = v;
          if (linked) {
            c.p[k + '_to'] = v;
            if (widgets[k + '_to']) widgets[k + '_to'].querySelectorAll('input').forEach(x => { x.value = v; });
          }
        });
        f.appendChild(w);
        continue;
      }
      if (k.endsWith('_to')) {
        const w = F.num(d.label, val, d.lo, d.hi, d.step, v => { c.p[k] = v; });
        widgets[k] = w;
        f.appendChild(w);
        continue;
      }
      if (d.unit === 'color') f.appendChild(F.color(d.label, val, v => { c.p[k] = v; }));
      else if (d.unit === 'select') f.appendChild(F.select(d.label, val, d.options, v => { c.p[k] = v; }));
      else if (d.unit === 'bool') f.appendChild(F.check(d.label, val, v => { c.p[k] = v; }));
      else {
        const hi = (k === 'fade_in' || k === 'fade_out') ? Math.max(c.d, 1) : Math.min(d.hi, k === 'repeat' ? 64 : d.hi);
        f.appendChild(F.num(d.label + (d.unit ? ' (' + d.unit + ')' : ''), val, d.lo, hi, d.step, v => { c.p[k] = v; }));
      }
    }
    B.appendChild(f);
  }
  function botSceneClip(B, x) {
    const c = x.ev;
    B.appendChild(head('<b>Szene in der Timeline</b>'));
    const f = form();
    f.appendChild(F.time('Startzeit', c.t, v => { c.t = Math.max(0, v); }));
    f.appendChild(F.time('Dauer', c.d, v => { c.d = Math.max(0.025, v); }));
    f.appendChild(F.select('Szene', c.scene, doc.scenes.map(s => [s.id, s.name]), v => { c.scene = v; }));
    f.appendChild(F.num('Fade In (s)', c.fade_in, 0, Math.max(1, c.d), 0.05, v => { c.fade_in = v; }));
    f.appendChild(F.num('Fade Out (s)', c.fade_out, 0, Math.max(1, c.d), 0.05, v => { c.fade_out = v; }));
    B.appendChild(f);
  }
  function botScene(B) {
    const s = doc.scenes.find(z => z.id === selScene);
    if (!s) { selScene = null; botShow(B); return; }
    const h = head('<b>Szene</b>');
    h.appendChild(button('Löschen', () => {
      begin();
      doc.scene_clips = doc.scene_clips.filter(c => c.scene !== s.id);
      doc.scenes = doc.scenes.filter(z => z !== s);
      selScene = null;
      commit(); renderList();
    }, 'danger'));
    B.appendChild(h);
    const f = form();
    f.appendChild(F.text('Name', s.name, v => { s.name = v; }));
    const free = meta.fixtures.filter(x => x.attrs.length && !s.values[x.name]);
    if (free.length) f.appendChild(F.select('Gerät hinzufügen', '', [['', 'wählen ...']].concat(free.map(x => [x.name, x.label])), v => {
      if (!v) return;
      s.values[v] = {};
      for (const a of fixOf(v).attrs) if (a.attr === 'dimmer' || a.attr === 'color') s.values[v][a.attr] = SM.defaultValue(SM.kindOf(a.attr));
    }));
    B.appendChild(f);
    for (const name of Object.keys(s.values)) {
      const fx = fixOf(name);
      if (!fx) continue;
      const hh = head('<b style="font-size:12px">' + esc(fx.label) + '</b>');
      hh.appendChild(button('×', () => { begin(); delete s.values[name]; commit(); }, 'danger'));
      B.appendChild(hh);
      const g = form(), vals = s.values[name];
      for (const a of Object.keys(vals)) {
        const lb = (fx.attrs.find(q => q.attr === a) || { label: a }).label;
        const kind = SM.kindOf(a);
        if (kind === 'scalar') g.appendChild(F.num(lb, vals[a], 0, 255, 1, v => { vals[a] = v; }));
        else valueFields(g, kind, vals[a], null, v => { vals[a] = v; });
      }
      B.appendChild(g);
    }
  }
  function botGroup(B) {
    const g = groupOf(selGroup);
    if (!g) { selGroup = null; botShow(B); return; }
    const h = head('<b>▣ Gruppe</b>' + (g.builtin ? '<span class="dim">aus dem Aufbau, nicht änderbar</span>' : ''));
    if (!g.builtin) h.appendChild(button('Löschen', () => {
      begin();
      doc.tracks = doc.tracks.filter(t => t.target.group !== g.id);
      doc.groups = doc.groups.filter(x => x !== g);
      selGroup = null;
      commit(); renderList();
    }, 'danger'));
    B.appendChild(h);
    if (g.builtin) { B.appendChild(Object.assign(document.createElement('div'), { className: 'dim', textContent: g.fixtures.map(n => (fixOf(n) || { label: n }).label).join(', ') })); return; }
    const f = form();
    f.appendChild(F.text('Name', g.name, v => { g.name = v; }));
    for (const fx of meta.fixtures.filter(x => x.attrs.length)) {
      f.appendChild(F.check(fx.label, g.fixtures.includes(fx.name), v => {
        g.fixtures = g.fixtures.filter(n => n !== fx.name);
        if (v) g.fixtures.push(fx.name);
      }));
    }
    B.appendChild(f);
  }
  function botFixture(B) {
    const fx = fixOf(selFix);
    if (!fx) { selFix = null; botShow(B); return; }
    B.appendChild(head('<b>' + esc(fx.label) + '</b><span class="dim">' + esc(fx.maker ? fx.maker + ' · ' : '') + esc(fx.type) + ' · DMX ' + fx.address + '–' + (fx.address + fx.channels - 1) + (fx.target ? ' · ' + esc(fx.target) : '') + '</span><a href="/api/sm/profile?type=' + encodeURIComponent(fx.type) + '" download="' + esc(fx.type) + '.json"><button>Profil sichern</button></a>'));
    if (fx.type === 'laser_ktv' || fx.type === 'laser_ktv34') B.appendChild(head('<a href="/help">Anleitung: Handbuch, Kapitel Geräte-Anleitungen</a>'));
    if (fx.attrs.length) {
      const h = head('<span class="dim">Spur anlegen:</span>');
      for (const a of fx.attrs) {
        const has = SM.findTrack(doc, { fixture: fx.name }, a.attr);
        const b = button(a.label, () => { begin(); SM.ensureTrack(doc, { fixture: fx.name }, a.attr); commit(); });
        b.disabled = !!has;
        h.appendChild(b);
      }
      B.appendChild(h);
    } else B.appendChild(head('<span class="warn">Gesperrt: Dieses Gerät lässt sich nicht programmieren.</span>'));
    const g = document.createElement('div');
    g.className = 'dmxgrid'; g.id = 'dmxg';
    g.innerHTML = fx.map.map(m => '<div class="dmxrow' + (m.locked ? ' lock' : '') + '" title="' + esc(fx.desc[m.param] || '') + '"><i>' + (fx.address + m.ch - 1) + '</i><span>' + esc(m.param) + (m.locked ? ' 🔒' : '') + '</span><b data-p="' + esc(m.param) + '">–</b></div>').join('');
    B.appendChild(g);
    const v = document.createElement('div');
    v.id = 'attrvals'; v.className = 'dim'; v.style.marginTop = '6px';
    B.appendChild(v);
  }
  function drawVals() {
    const v = $('attrvals');
    if (v && st.vals) v.textContent = Object.entries(st.vals).map(([k, x]) => k + ': ' + (Array.isArray(x) ? x.map(y => Math.round(y * 100) / 100).join('/') : typeof x === 'string' ? x : Math.round(x))).join(' · ') || 'nichts programmiert an dieser Stelle';
    const g = $('dmxg');
    if (g) g.querySelectorAll('b[data-p]').forEach(b => { b.textContent = st.dmx && st.dmx[b.dataset.p] !== undefined ? st.dmx[b.dataset.p] : '–'; });
  }
  function botShow(B) {
    B.appendChild(head('<b>Show „' + esc(doc.name) + '“</b>'));
    const f = form();
    const num = (label, val, lo, hi, step, fn) => {
      const w = document.createElement('label');
      w.innerHTML = '<span>' + esc(label) + '</span><input type="number" min="' + lo + '" max="' + hi + '" step="' + step + '" value="' + val + '">';
      w.querySelector('input').onchange = e => { begin(); fn(SM.clamp(+e.target.value || lo, lo, hi)); $('bpmv').textContent = fmtBpm(); commit(); };
      return w;
    };
    f.appendChild(num('Tempo (BPM)', fmtBpm(), 20, 400, 0.01, v => { doc.bpm = v; }));
    f.appendChild(num('Erster Schlag bei (s)', doc.beat_offset, 0, 600, 0.001, v => { doc.beat_offset = v; }));
    f.appendChild(num('Schläge je Takt', doc.beats_per_bar, 1, 16, 1, v => { doc.beats_per_bar = v; }));
    f.appendChild(F.time('Länge', doc.duration, v => { doc.duration = Math.max(1, v); }));
    const lead = document.createElement('label');
    lead.innerHTML = '<span>Linie vorziehen (ms, nur Anzeige in diesem Browser)</span><input type="number" min="-500" max="500" step="10" value="' + displayLead + '">';
    lead.querySelector('input').onchange = e => { displayLead = SM.clamp(+e.target.value || 0, -500, 500); SM.setDisplayLead(displayLead); };
    f.appendChild(lead);
    const lv = document.createElement('label');
    lv.innerHTML = '<span>Licht-Versatz (ms, wirkt sofort auf das echte Licht, plus = früher)</span><input type="number" min="-1000" max="1000" step="10" value="' + (st.light_ms || 0) + '">';
    lv.querySelector('input').onchange = e => SM.cmd('light_ms', { ms: SM.clamp(+e.target.value || 0, -1000, 1000) }).then(updateStatus).catch(x => SM.toast(x.message));
    f.appendChild(lv);
    B.appendChild(f);
    B.appendChild(mixxxBox());
    if (!doc.tracks.some(t => !SM.isPinned(t))) B.appendChild(Object.assign(document.createElement('p'), { className: 'dim', textContent: 'So geht es los: MP3 wählen, Gerät links in die Timeline ziehen, Muster auf eine Spur ziehen. Doppelt tippen setzt einen Keyframe. Play geht ans echte Licht, mit „Licht aus“ hörst du nur.' }));
  }

  // Szene aus dem Hauptpanel in die eigene Zeile: laeuft dort genau wie im Panel
  function addPanelScene(t) {
    const opts = (meta.params.panel_scene || {}).options || [];
    if (!opts.length || !opts[0][0]) { SM.toast('Im Hauptpanel gibt es noch keine passende Szene'); return; }
    begin();
    const tr = SM.panelTrack(doc), c = SM.addClip(tr, t, beat() * doc.beats_per_bar * 4, 'panel_scene', { panel_scene: opts[0][0] }, '');
    tl.selTrack = tr.id;
    tl.sel = new Set([c.id]);
    commit();
  }

  // ---- Show-Assistent: Vorschlag als neue Kopie der Show --------------------------------------------------------
  async function openAssistant() {
    if (dirty) {
      if (!await confirmBox('Der Assistent arbeitet mit der gespeicherten Show. Jetzt speichern?', 'Speichern')) return;
      await save();
      if (dirty) return;
    }
    const info = await SM.cmd('assist_info', { name: NAME });
    const src = { mixxx: info.sections + ' Abschnitte und ' + info.cues + ' Cues aus der Mixxx-Analyse.',
      wave: 'Aufbau aus der Wellenform geschätzt. Genauer wird es, wenn das Lied einmal in einem Mixxx-Deck liegt.',
      raster: 'Noch keine Analyse und keine Wellenform: Der Aufbau folgt nur dem Takt. Besser zuerst die MP3 laden.' }[info.source];
    const box = (id, label, on, hint) => '<label class="row" style="gap:6px"><input type="checkbox" id="' + id + '"' + (on ? ' checked' : '') + ' style="min-height:0"><span>' + label + (hint ? ' <span class="dim">(' + hint + ')</span>' : '') + '</span></label>';
    const emptyShow = !dirty && !(doc.scene_clips || []).length && !(doc.tracks || []).some(t => (t.clips || []).length || (t.keys || []).length);
    modal('<h2>Show-Assistent</h2><p><b>' + (emptyShow ? 'Die Show ist noch leer: Der Vorschlag kommt direkt in diese Show.' : 'Der Vorschlag kommt als neue Kopie, diese Show bleibt unverändert.') + '</b></p><p class="dim">' + esc(info.title || NAME) + (info.genre ? ' · ' + esc(info.genre) : '') + '<br>' + esc(src) + (info.stems ? ' Dazu die Pegelkurven von Stimme, Bass, Kick, Snare/Hi-Hat und Sonstigem.' : '') + (info.room ? ' Mit Raumplan: Lichtwellen durch den Raum.' : '') + (info.hits ? ' ' + info.hits + ' starke Peaks in der Wellenform.' : '') + (info.lyrics_lines ? ' ' + info.lyrics_lines + ' Liedzeilen mit Zeiten.' : info.lyrics_text ? ' Liedtext ohne Zeiten.' : '') + '</p><p class="dim" id="aspent" style="margin-top:0"></p>' +
      '<div class="row"><label style="flex:1">Stil <select id="asty" style="width:100%"><option value="">' + (info.genre ? 'kein fester Stil' : 'kein Genre bekannt') + '</option>' +
      Object.entries(info.styles).map(([k, t]) => '<option value="' + k + '"' + (k === info.style ? ' selected' : '') + '>' + esc(t) + '</option>').join('') + '</select></label></div>' +
      '<div class="row"><label style="flex:1">Ruhig bis wild' + (info.lvl ? ' <span class="dim">(vorgestellt nach Energiestufe ' + info.lvl + ')</span>' : '') + ' <input id="awild" type="range" min="0" max="1" step="0.05" value="' + SM.wildFor(info.lvl) + '" style="width:100%"></label></div>' +
      box('alaser', 'Laser', true, info.laser_allowed ? '' : 'leuchtet erst mit „Laser in Shows erlauben“') +
      box('afog', 'Nebel', true, info.fog_allowed ? '' : 'wirkt erst mit „Nebel in Shows erlauben“') +
      box('astrobe', 'Schnelle Blitze', true, info.strobe ? '' : 'ohne Strobe-Erlaubnis höchstens 2 pro Sekunde') +
      box('amove', 'Bewegung', true, '') +
      (info.nano_effects ? box('anfx', 'Nanoleaf-Effekte', true, 'ab und zu einer deiner ' + info.nano_effects + ' Effekte') : '') +
      box('aamb', 'Ambiente an', false, 'Barlicht, Theke, Couchtisch ruhig dazu') +
      '<hr style="border:0;border-top:1px solid #2c2f42;margin:8px 0">' + ('<div class="row"><label style="flex:1">Wer entwirft? <select id="amode" style="width:100%"><option value="">Offline, nach festen Regeln</option><option value="claude">Claude verfeinert die Regeln (Internet)</option><option value="design">Claude entwirft die ganze Show (Internet, dauert Minuten)</option></select></label></div>') +
      '<div id="aclbox" style="display:none"><div class="row" id="akeyinfo" style="justify-content:flex-end;gap:8px;align-items:center;margin-bottom:4px"><button id="akeydel" style="font-size:11px;min-height:0;padding:2px 8px">Schlüssel löschen</button></div><p class="dim">An Anthropic gehen Titel, Genre, Tempo, Aufbau, Lautstärke, dein Aufbau ohne Adressen, dein Wunsch und der Liedtext, keine Musik. Verfeinern kostet geschätzt einige Cent, die ganze Show geschätzt 50 Cent bis 1,50 Euro. Scheitert es, entsteht der Vorschlag offline.</p>' +
      '<div class="row"><textarea id="awish" rows="2" style="flex:1" placeholder="Wunsch, zum Beispiel: mehr Blau, im zweiten Refrain alles auf einmal"></textarea></div>' +
      '<div class="row" id="alyrow"><textarea id="alyrics" rows="3" style="flex:1" maxlength="20000" placeholder="Eigener Liedtext (freiwillig, sonst der aus der Show)"></textarea></div>' +
      '<div class="row" id="akeyrow"><input id="akey" type="password" autocomplete="off" style="flex:1" placeholder="API-Schlüssel von platform.claude.com"><button id="akeysave">Hinterlegen</button></div></div>' +
      '<div id="ares" class="dim" style="margin:6px 0"></div><div class="row"><button id="ago" class="on">Vorschlag erstellen</button><button id="ano">Schließen</button></div>', (m, close) => {
      const q = s => m.querySelector(s);
      const keyView = has => { q('#akeyrow').style.display = has ? 'none' : ''; q('#akeydel').style.display = has ? '' : 'none'; };
      const money = x => x.toFixed(2).replace('.', ',') + ' $';
      const spentText = s => { q('#aspent').textContent = 'Claude bisher: ' + (s && s.calls ? 'geschätzt ' + money(s.usd) + ' in ' + s.calls + (s.calls === 1 ? ' Aufruf' : ' Aufrufen') : 'noch kein Aufruf gezählt') + '. Das Guthaben steht auf platform.claude.com.'; };
      spentText(info.spent);
      keyView(info.has_key);
      q('#ano').onclick = close;
      q('#amode').onchange = e => { q('#aclbox').style.display = e.target.value ? '' : 'none'; q('#alyrow').style.display = e.target.value === 'design' ? '' : 'none'; };
      const setKey = async key => {
        try { keyView((await SM.cmd('claude_key', { key })).has_key); q('#akey').value = ''; } catch (e) { q('#ares').textContent = e.message; }
      };
      q('#akeysave').onclick = () => setKey(q('#akey').value);
      q('#akeydel').onclick = async () => { if (await confirmBox('API-Schlüssel wirklich löschen? Du musst ihn danach neu eingeben.', 'Löschen')) setKey(''); };
      q('#ago').onclick = async () => {
        q('#ago').disabled = true;
        const mode = q('#amode').value, claude = mode === 'claude', design = mode === 'design';
        q('#ares').textContent = design ? 'Claude entwirft die Show, das dauert einige Minuten. Das Fenster kann offen bleiben ...' : claude ? 'Claude denkt nach, das dauert bis zu zwei Minuten ...' : 'Wird erstellt ...';
        let r;
        try {
          r = await SM.cmd('assist', { design, lyrics: q('#alyrics').value, name: NAME, style: q('#asty').value, wild: +q('#awild').value, laser: q('#alaser').checked, fog: q('#afog').checked, strobe: q('#astrobe').checked, move: q('#amove').checked, ambient: q('#aamb').checked, nano_fx: !q('#anfx') || q('#anfx').checked, claude, wish: q('#awish').value, keep_copy: !emptyShow });
          while (r.job) {                                 // lange Arbeit im Hintergrund: eine abgerissene Verbindung schadet nicht
            await new Promise(res => setTimeout(res, 3000));
            let j;
            try { j = await SM.cmd('assist_job'); } catch (e) { continue; }
            if (j.state === 'running') { q('#ares').textContent = 'Claude entwirft die Show ... ' + (j.chars ? Math.round(j.chars / 1000) + ' tausend Zeichen' : 'denkt nach'); continue; }
            if (j.state !== 'done') throw new Error(j.error || 'Vorschlag ging nicht');
            r = j.result;
          }
        } catch (e) { q('#ares').textContent = e.message; q('#ago').disabled = false; return; }
        q('#ares').textContent = '„' + r.show + '“ ist fertig' + (r.design ? ', von Claude entworfen' : r.claude ? ', mit Claude verfeinert' : ', offline erstellt') + '. ' + (r.note || '') + (r.cost_usd ? ' Dieser Aufruf kostete geschätzt ' + money(r.cost_usd) + '.' : '') + (r.replaced ? ' Er steht direkt in dieser Show, weil sie noch leer war.' : ' Diese Show bleibt unverändert, ein neuer Klick macht einen weiteren Vorschlag.');
        spentText(r.spent);
        const go = q('#ago');
        go.disabled = false; go.textContent = r.replaced ? 'Vorschlag ansehen' : 'Vorschlag öffnen';
        go.onclick = () => { closeModals(); if (r.replaced) { dirty = false; location.reload(); } else location.href = '/shows/edit?show=' + encodeURIComponent(r.show); };
      };
    });
  }

  // ---- Zuordnung zu einem Lied aus Mixxx -------------------------------------------------------------------
  function mixxxBox() {
    const m = doc.mixxx || {};
    const h = head('<b style="font-size:12px">Mixxx</b><span class="dim">' + (m.title ? esc(m.title) + ' (' + SM.fmtTime(m.dur).replace(/\.\d+$/, '') + ')' : doc.audio ? 'Erkennung über die MP3 dieser Show' : 'noch keine MP3 und kein Lied gewählt') + '</span>');
    h.appendChild(button('Lied wählen', pickMixxx));
    if (m.title) h.appendChild(button('Trennen', () => { begin(); doc.mixxx = Object.assign({}, m, { title: '', dur: 0 }); commit(); }));
    const on = document.createElement('label');
    on.style.cssText = 'display:flex;gap:5px;align-items:center';
    on.innerHTML = '<input type="checkbox"' + (m.on === false ? '' : ' checked') + ' style="min-height:0"><span>startet aus Mixxx</span>';
    on.querySelector('input').onchange = e => { begin(); doc.mixxx = Object.assign({ title: '', dur: 0 }, m, { on: e.target.checked }); commit(); };
    h.appendChild(on);
    const mk = doc.marks, info = document.createElement('span');
    info.className = 'dim';
    info.textContent = mk ? mk.se.length + ' Abschnitte, ' + mk.cu.length + ' Cues in der Timeline' + (marksWarn ? ' (andere Datei als die MP3)' : '') : 'Abschnitte und Cues: Lied einmal in ein Mixxx-Deck laden';
    h.appendChild(info);
    const ly = doc.lyrics, lyb = document.createElement('span');
    lyb.className = 'dim';
    const lyn = ly ? ly.lines.filter(x => x[1]).length : 0;
    lyb.textContent = ly ? (lyn ? lyn + ' Liedzeilen mit Zeiten' : 'Liedtext ohne Zeiten (Länge passt nicht)') + ' von LRCLIB: ' + ly.title : '';
    h.appendChild(button(ly ? 'Liedtext neu holen' : 'Liedtext holen', fetchLyrics));
    if (ly) h.appendChild(button('Liedtext weg', async () => { try { await SM.cmd('lyrics_clear', { name: NAME }); delete doc.lyrics; tl.need = true; renderBot(); } catch (e) { SM.toast(e.message); } }));
    if (ly) h.appendChild(lyb);
    return h;
  }
  async function fetchLyrics() {
    if (dirty) {                                  // der Pi liest Laenge und Titel aus der gespeicherten Show
      if (!await confirmBox('Der Light-Butler liest Titel und Länge aus der gespeicherten Show. Jetzt speichern?', 'Speichern')) return;
      await save();
      if (dirty) return;
    }
    SM.toast('Suche bei LRCLIB ...');
    try {
      const r = await SM.cmd('lyrics_fetch', { name: NAME });
      doc.lyrics = r.lyrics; tl.need = true; renderBot();
      SM.toast(r.lyrics.lines.length ? r.lyrics.lines.filter(x => x[1]).length + ' Liedzeilen mit Zeiten' : 'Nur Text, ohne Zeiten: Die Länge passt zu keinem Eintrag (zum Beispiel ein Remix)', 6000);
    } catch (e) {
      const t = await ask('Nichts gefunden. Anders suchen? (Interpret - Titel)', (doc.marks || {}).title || '', 'Suchen');
      if (!t) return;
      try { const r = await SM.cmd('lyrics_fetch', { name: NAME, title: t }); doc.lyrics = r.lyrics; tl.need = true; renderBot(); } catch (x) { SM.toast(x.message, 6000); }
    }
  }
  async function pickMixxx() {
    const row = t => '<div class="show" data-t="' + esc(t.title) + '" data-d="' + t.dur + '"><span class="nm" style="font-size:13px">' + esc(t.title) + '<small>' + SM.fmtTime(t.dur).replace(/\.\d+$/, '') + '</small></span></div>';
    modal('<h2>Lied aus Mixxx</h2><div class="row"><input id="mxq" style="flex:1" placeholder="Titel oder Interpret suchen"></div><div id="mxr" class="dim">Lädt ...</div><div class="row"><button id="askno">Schließen</button></div>', (m, close) => {
      m.querySelector('#askno').onclick = close;
      const show = async () => {
        let d;
        try { d = await SM.get('/api/sm/mixxx?q=' + encodeURIComponent(m.querySelector('#mxq').value)); } catch (e) { m.querySelector('#mxr').textContent = e.message; return; }
        const R = m.querySelector('#mxr');
        R.innerHTML = (d.decks.length ? '<h3>Gerade in den Decks</h3>' + d.decks.map(row).join('') : '') +
          '<h3>Bibliothek (' + d.total + ')</h3>' + (d.tracks.length ? d.tracks.map(row).join('') : '<p>' + (d.total ? 'Nichts gefunden.' : (d.connected ? 'Die Bibliothek kommt gerade nach und nach an. Bitte gleich noch einmal öffnen, oder das Lied in ein Deck laden.' : 'Mixxx ist nicht verbunden.')) + '</p>');
        R.querySelectorAll('.show').forEach(e => { e.onclick = () => {
          begin();
          doc.mixxx = { on: (doc.mixxx || {}).on !== false, title: e.dataset.t, dur: +e.dataset.d };
          close(); commit();
        }; });
      };
      let tm;
      m.querySelector('#mxq').oninput = () => { clearTimeout(tm); tm = setTimeout(show, 200); };
      show();
    });
  }

  // ---- MP3 importieren -------------------------------------------------------------------------------
  async function importMp3(file, uploaded) {
    // uploaded: die MP3 liegt schon am Pi (Musik-Datenbank hat sie vom Mac geschickt), nur Wellenform und Tempo rechnen.
    // Rueckgabe: true, wenn alles geklappt hat (Quick macht dann mit dem Assistenten weiter)
    if (!file) return false;
    let done = false;
    try {
      if (!uploaded) {
        SM.toast('MP3 wird hochgeladen ...', 60000);
        const r = await fetch('/api/sm/audio?name=' + encodeURIComponent(NAME), { method: 'POST', body: file });
        const j = await r.json();
        if (!r.ok || j.error) throw new Error(j.error || r.statusText);
      }
      begin();
      doc.audio = 'audio.mp3';
      loadAudio();
      SM.toast('Wellenform wird berechnet ...', 60000);
      const C = window.AudioContext || window.webkitAudioContext;
      const ac = new C();
      const buf = await ac.decodeAudioData(await file.arrayBuffer());
      if (ac.close) ac.close();
      const a = SM.analyzeBuffer(buf);
      doc.duration = a.duration;
      tl.peaks = a.peaks;
      tl.setStems(null);                      // andere MP3: die Kurven gehoeren zur alten
      await SM.cmd('peaks', { name: NAME, data: a.peaks });
      const t = (await SM.cmd('analyze', { env: a.env, rate: a.envRate })).tempo;
      if (t.bpm > 0) { doc.bpm = t.bpm; doc.beat_offset = t.offset; $('bpmv').textContent = fmtBpm(); }
      tl.fit();
      commit();
      await save();
      done = true;
      SM.toast(t.bpm > 0 ? 'Fertig: etwa ' + t.bpm + ' BPM erkannt, unten bei den Eigenschaften der Show änderbar.' : 'Fertig. Das Tempo bitte unten bei den Eigenschaften der Show eintragen.', 7000);
    } catch (e) { SM.toast('MP3: ' + e.message, 8000); commit(); }
    return done;
  }
  // Quick aus der Musik-Datenbank: der Assistent fuellt die neue Show gleich, mit den Standardwerten seines Fensters
  // (Stil nach Genre, Regler in der Mitte, Hakerl wie vorbelegt, offline nach festen Regeln, ohne Claude). Vorher der
  // Abschnitte, Cue-Punkte und Drops vom Mac (Analyse der Bruecke, auch ohne Deck) und der Liedtext: aus dem Speicher am Pi
  // (Vorab-Lauf), nur wenn nie gesucht von LRCLIB.
  async function quickAssist() {
    SM.toast('Quick: Liedtext und Show werden erstellt ...', 60000);
    try {
      try { await SM.cmd('marks_from_mac', { name: NAME }); } catch (e) { /* ohne Abschnitte und Cues: aus der Wellenform */ }
      try { await SM.cmd('lyrics_quick', { name: NAME }); } catch (e) { /* ohne Liedtext geht es auch */ }
      const info = await SM.cmd('assist_info', { name: NAME });
      const r = await SM.cmd('assist', { name: NAME, style: info.style || '', wild: SM.wildFor(info.lvl), laser: true, fog: true, strobe: true, move: true,
        ambient: false, nano_fx: true, claude: false, design: false, keep_copy: false });
      dirty = false;
      if (r.replaced) location.reload();
      else location.href = '/shows/edit?show=' + encodeURIComponent(r.show);
    } catch (e) { SM.toast('Quick: ' + e.message + ' Den Assistenten kannst du von Hand starten.', 9000); }
  }
  function loadAudio() {
    audio.src = '/api/sm/audio?name=' + encodeURIComponent(NAME) + '&v=' + Date.now();
    hasAudio = true;
    audio.load();
  }

  // Pegelkurven der getrennten Spuren, falls Mac oder Windows-PC sie zu dieser MP3 gerechnet haben (nur Anzeige)
  let stemsCreated = null;                       // Stand der geladenen Kurven: neu laden, wenn am Pi neuere liegen
  async function loadStems() {
    try {
      const d = await SM.get('/api/sm/stems?name=' + encodeURIComponent(NAME));
      tl.setStems(d);
      stemsCreated = d && d.curves ? (d.created || '') : null;
    } catch (e) { /* ohne Kurven */ }
  }
  // Alle 15 s fragen: rechnet gerade jemand? Sind (neue) Kurven da, kommen sie von selbst, ohne Neuladen der Seite.
  async function pollStems() {
    const el = $('stemst');
    if (!el) return;
    let s;
    try { s = await SM.get('/api/sm/stems_state?name=' + encodeURIComponent(NAME)); } catch (e) { return; }
    if (s.current && (stemsCreated == null || (s.created || '') !== stemsCreated)) {
      const first = stemsCreated == null;
      await loadStems();
      if (first && tl.stems) SM.toast('Die Spur-Kurven sind da und werden unter der Wellenform gezeigt.', 5000);
    }
    if (!s.current && stemsCreated != null) { tl.setStems(null); stemsCreated = null; }   // andere MP3: alte Kurven passen nicht mehr
    let t = '', tip = '';
    if (!s.audio) { t = ''; }
    else if (s.busy) { t = 'Kurven: ' + s.busy + ' rechnet …'; tip = 'Die Spur-Kurven zu dieser MP3 werden gerade gerechnet. Sie erscheinen von selbst, sobald sie fertig sind.'; }
    else if (!s.current && (s.max_min == null ? 6 : s.max_min) > 0 && s.audio_s > (s.max_min == null ? 6 : s.max_min) * 60) { t = 'Kurven: MP3 zu lang'; tip = 'Spur-Kurven gibt es nur für MP3s bis ' + (s.max_min == null ? 6 : s.max_min) + ' Minuten (Einstellungen → Ausgabe: Pegelkurven bis Liedlänge).'; }
    else if (!s.current) { t = 'Kurven: noch keine'; tip = 'Der Wächter am Mac oder Windows-PC rechnet sie, sobald er läuft. Sie erscheinen dann von selbst.'; }
    el.textContent = t; el.title = tip; el.classList.toggle('busy', !!s.busy);
  }

  // ---- Laden -----------------------------------------------------------------------------------------
  async function loadDialog() {
    const d = await SM.get('/api/sm/shows');
    modal('<h2>Show laden</h2>' + d.shows.map(s => '<div class="show" data-n="' + esc(s.name) + '"><span class="nm">' + esc(s.name) + '<small>' + SM.fmtTime(s.duration) + ' · ' + s.tracks + ' Spuren' + (s.has_audio ? '' : ' · ohne Musik') + '</small></span></div>').join('') + '<div class="row"><a href="/shows"><button>Zur Übersicht</button></a><button id="askno">Schließen</button></div>', (m, close) => {
      m.querySelector('#askno').onclick = close;
      m.querySelectorAll('.show').forEach(e => { e.onclick = async () => {
        if (dirty && !await confirmBox('Ungespeicherte Änderungen verwerfen?', 'Verwerfen')) return;
        dirty = false;
        closeModals();
        location.href = '/shows/edit?show=' + encodeURIComponent(e.dataset.n);
      }; });
    });
  }

  // ---- Start ------------------------------------------------------------------------------------------
  function wire() {
    $('bstart').onclick = () => { tl.userView = false; seek(0); };
    $('bplay').onclick = togglePlay;
    $('bstop').onclick = stop;
    $('time').onclick = async () => {
      const v = await ask('Zeit (Minuten:Sekunden oder Sekunden)', SM.fmtTime(tl.pos), 'Springen');
      if (v === null) return;
      const t = SM.parseTime(v);
      if (t === null) SM.toast('Zeit nicht verstanden'); else { tl.userView = false; seek(t); tl.follow(t); }
    };
    $('bzi').onclick = () => tl.zoom(1.5);
    $('bzo').onclick = () => tl.zoom(1 / 1.5);
    $('bzf').onclick = () => tl.fit();
    const g = $('grid');
    g.innerHTML = SM.GRIDS.map(([k, t]) => '<option value="' + k + '">Raster: ' + t + '</option>').join('');
    g.onchange = () => { begin(); doc.grid = g.value; setDirty(true); tl.need = true; };
    $('bmarks').classList.toggle('on', tl.showMarks);
    $('bmarks').onclick = () => {
      tl.showMarks = !tl.showMarks; tl.need = true;
      $('bmarks').classList.toggle('on', tl.showMarks);
      try { localStorage.setItem('smmarks', tl.showMarks ? '1' : '0'); } catch (e) { /* privates Fenster */ }
      if (tl.showMarks && !doc.marks) SM.toast('Noch keine Abschnitte und Cues: Lied einmal in ein Mixxx-Deck laden.', 5000);
    };
    $('bundo').onclick = undo; $('bredo').onclick = redo;
    $('bmulti').onclick = () => { tl.multi = !tl.multi; $('bmulti').classList.toggle('on', tl.multi); };
    $('bkey').onclick = addKeyHere;
    $('bloop').onclick = toggleLoop;
    $('bloopx').onclick = clearLoop;
    setInterval(checkLoop, 40);
    $('bcut').onclick = cutSel; $('bcopy').onclick = copySel; $('bpaste').onclick = paste; $('bdel').onclick = deleteSel;
    $('bsave').onclick = save; $('bload').onclick = loadDialog;
    $('bmp3').onclick = () => $('fmp3').click();
    $('bassist').onclick = () => openAssistant().catch(e => SM.toast(e.message, 6000));
    $('fmp3').onchange = e => { importMp3(e.target.files[0]); e.target.value = ''; };
    const volIcon = () => { $('volic').textContent = audio.volume === 0 ? '🔇' : audio.volume < 0.5 ? '🔉' : '🔊'; };
    $('vol').oninput = e => { audio.volume = +e.target.value; volIcon(); try { localStorage.setItem('smvol', e.target.value); } catch (x) { /* privates Fenster */ } };
    try { const v = localStorage.getItem('smvol'); if (v !== null) { audio.volume = +v; $('vol').value = v; } } catch (x) { /* privates Fenster */ }
    volIcon();
    $('blight').onclick = () => setLight(!lightShown()).catch(e => SM.toast(e.message));
    $('blk').onclick = () => SM.cmd('blackout', { on: !st.blackout }).then(updateStatus).catch(e => SM.toast(e.message));
    $('bbot').onclick = () => { $('bot').classList.toggle('closed'); };
    $('bleft').onclick = () => $('left').classList.toggle('open');
    audio.onplay = audio.onpause = () => updateStatus(st);
    audio.onended = () => { SM.cmd('stop').then(updateStatus).catch(() => {}); };
    document.addEventListener('keydown', e => {
      if (e.target.closest && e.target.closest('input,select,textarea')) return;
      const k = e.key.toLowerCase(), c = e.ctrlKey || e.metaKey;
      if (c && k === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
      else if (c && k === 'y') { e.preventDefault(); redo(); }
      else if (c && k === 's') { e.preventDefault(); save(); }
      else if (c && k === 'c') copySel();
      else if (c && k === 'x') cutSel();
      else if (c && k === 'v') paste();
      else if (c && k === 'a') { e.preventDefault(); doc.tracks.forEach(t => { t.keys.forEach(x => tl.sel.add(x.id)); t.clips.forEach(x => tl.sel.add(x.id)); }); doc.scene_clips.forEach(x => tl.sel.add(x.id)); tl.need = true; renderBot(); }
      else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
      else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteSel(); }
      else if (e.key === 'Home') seek(0);
      else if (k === 'k') addKeyHere();
      else if (k === 'l') { if (e.shiftKey) clearLoop(); else toggleLoop(); }
      else if (e.key === '+') tl.zoom(1.25);
      else if (e.key === '-') tl.zoom(0.8);
      else if (e.key === 'Escape') { tl.select(null); selFix = selScene = selGroup = null; renderList(); renderBot(); }
    });
    window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
    setInterval(() => { if (dirty) SM.cmd('autosave', { name: NAME, doc }).catch(() => {}); }, 60000);
  }
  async function main() {
    try {
      meta = await SM.get('/api/sm/meta');
      const d = await SM.get('/api/sm/show?name=' + encodeURIComponent(NAME));
      doc = d.doc;
      if (d.autosave && await confirmBox('Es gibt einen neueren automatisch gesicherten Stand. Wiederherstellen?', 'Wiederherstellen')) { doc = d.autosave.doc; setDirty(true); }
    } catch (e) {
      document.body.innerHTML = '<div style="padding:20px"><p>Show nicht ladbar: ' + esc(e.message) + '</p><a href="/shows">Zur Übersicht</a></div>';
      return;
    }
    $('title').textContent = doc.name;
    const cv = $('cover');                           // Cover des Liedes (aus der MP3 oder vom Mac), fehlt es: unsichtbar
    if (cv) { cv.hidden = true; cv.onload = () => { cv.hidden = false; }; cv.onerror = () => { cv.hidden = true; }; cv.src = '/api/sm/cover?show=' + encodeURIComponent(doc.name); }
    document.title = 'Showmanager - ' + doc.name;
    $('bpmv').textContent = fmtBpm();
    tl = new SM.Timeline($('mid'), {
      targetLabel, attrLabel, patternLabel, begin, commit, stepped, stepLabel, newStepValue,
      onSelect: () => { if (tl.sel.size) { selFix = selScene = selGroup = null; } renderBot(); },
      onSeek: seek,
      onFrame: frame,
      onLoop: saveLoop,
      onLoopNew: loopArrive,
      onStems: on => { try { localStorage.setItem('smstems', on ? '1' : '0'); } catch (e) { /* privates Fenster */ } },
      onFold: keys => { try { localStorage.setItem('smfold:' + NAME, JSON.stringify(keys)); } catch (e) { /* privates Fenster */ } },
      onLive: () => { setDirty(true); pushLive(); renderBotLight(); },
      onDeleteTrack: async tr => {
        if ((tr.keys.length || tr.clips.length) && !await confirmBox('Spur „' + attrLabel(tr) + '“ mit allen Ereignissen löschen?', 'Löschen')) return;
        begin(); doc.tracks = doc.tracks.filter(t => t !== tr); commit();
      },
      onAddPanelScene: addPanelScene,
      onDeleteTarget: async tg => {
        const key = SM.targetKey(tg);
        if (!await confirmBox('Alle Spuren von „' + targetLabel(tg) + '“ löschen?', 'Löschen')) return;
        begin(); doc.tracks = doc.tracks.filter(t => SM.targetKey(t.target) !== key); commit();
      },
    });
    try { tl.collapsed = new Set(JSON.parse(localStorage.getItem('smfold:' + NAME) || '[]')); } catch (e) { /* privates Fenster */ }
    try { tl.loop = JSON.parse(localStorage.getItem('smloop:' + NAME) || 'null'); } catch (e) { /* privates Fenster */ }
    try { tl.showMarks = localStorage.getItem('smmarks') !== '0'; } catch (e) { tl.showMarks = true; }
    try { tl.showStems = localStorage.getItem('smstems') !== '0'; } catch (e) { tl.showStems = true; }
    tl.setDoc(doc);
    pollMarks(); setInterval(pollMarks, 5000);
    setInterval(pollStems, 15000); setTimeout(pollStems, 1500);
    wire();
    $('bloop').classList.toggle('on', !!(tl.loop && tl.loop.on));
    $('bloopx').style.display = tl.loop ? '' : 'none';
    $('grid').value = doc.grid;
    renderTabs(); renderList(); renderBot();
    if (doc.audio) {
      loadAudio();
      try { tl.peaks = await SM.get('/api/sm/peaks?name=' + encodeURIComponent(NAME)); tl.need = true; } catch (e) { /* ohne Wellenform */ }
      loadStems();
      audio.onerror = () => { hasAudio = false; SM.toast('Musik nicht ladbar'); };
    }
    link = new SM.Link(() => (hasAudio && st.owner === link.client && st.loaded) ? { pos: audio.currentTime, playing: !audio.paused && !audio.ended } : null, updateStatus);
    updateStatus(await SM.get('/api/sm/status'));
    await SM.cmd('live', { name: NAME, doc }).catch(e => SM.toast(e.message));
    tl.fit();
    const qs = new URLSearchParams(location.search);
    if (!doc.audio && qs.get('import')) {   // aus der Musik-Datenbank: MP3 liegt schon am Pi
      const quick = qs.get('quick') === '1';
      history.replaceState(null, '', '/shows/edit?show=' + encodeURIComponent(NAME));
      try {
        const r = await fetch('/api/sm/audio?name=' + encodeURIComponent(NAME));
        if (r.ok && await importMp3(await r.blob(), true) && quick) await quickAssist();
      } catch (e) { SM.toast('MP3: ' + e.message, 8000); }
    }
  }
  // Beim Ziehen die Zahlen unten mitfuehren, ohne das Formular neu aufzubauen (sonst verliert es den Fokus).
  let botT = 0;
  function renderBotLight() { const n = performance.now(); if (n - botT > 120) { botT = n; renderBot(); } }
  main();
})();
