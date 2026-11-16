// play.js - Playback-Seite: Show waehlen, Play, Pause, Stop. Braucht den Editor nicht.
(function () {
  'use strict';
  const SM = window.SM, $ = id => document.getElementById(id), esc = SM.esc;
  const audio = $('audio'), cv = $('wave');
  let shows = [], cur = null, peaks = null, st = {}, stT = 0, link = null, soundHere = true, light = true, ownPlay = false;

  const hasSound = () => soundHere && cur && cur.has_audio;
  const localPlaying = () => hasSound() && !audio.paused && !audio.ended;
  function position() {
    if (hasSound() && (localPlaying() || !st.playing)) return audio.currentTime;
    if (st.src === 'mixxx') return st.pos + (performance.now() - stT) / 1000;
    if (st.playing && st.name === (cur && cur.name)) return st.pos + (performance.now() - stT) / 1000;
    return st.name === (cur && cur.name) ? (st.pos || 0) : 0;
  }
  const duration = () => (cur ? cur.duration : 0) || 1;

  let lyricLines = [];                       // Liedzeilen der gewaehlten Show: nur Anzeige
  function showLyric(pos) {
    let line = '';
    for (let i = 0; i < lyricLines.length && lyricLines[i][0] <= pos; i++) line = pos < SM.lyricEnd(lyricLines, i) ? lyricLines[i][1] : '';
    const el = $('plyric');
    if (el.textContent !== line) el.textContent = line;
  }
  function select(s, keepAudio) {
    cur = s;
    $('plname').textContent = s ? s.name : 'Keine Show gewählt';
    const cv = $('plcover');                         // Cover der gewaehlten Show (aus ihrer MP3 oder vom Mac)
    if (cv) { cv.hidden = true; cv.onload = () => { cv.hidden = false; }; cv.onerror = () => { cv.hidden = true; }; if (s) cv.src = '/api/sm/cover?show=' + encodeURIComponent(s.name); else cv.removeAttribute('src'); }
    peaks = null;
    lyricLines = [];
    $('plyric').textContent = '';
    if (s) SM.get('/api/sm/show?name=' + encodeURIComponent(s.name)).then(r => { if (cur === s) lyricLines = ((r.doc || {}).lyrics || {}).lines || []; }).catch(() => {});
    if (s && s.has_audio && !keepAudio) {
      audio.src = '/api/sm/audio?name=' + encodeURIComponent(s.name);
      audio.load();
      SM.get('/api/sm/peaks?name=' + encodeURIComponent(s.name)).then(p => { peaks = p; drawWave(); }).catch(() => {});
    } else if (!keepAudio) audio.removeAttribute('src');
    renderList();
    drawWave();
  }
  async function refresh() {
    const d = await SM.get('/api/sm/shows');
    shows = d.shows;
    updateStatus(d.status);
    if (cur) { const n = shows.find(x => x.name === cur.name); cur = n || null; if (!n) select(null); }
    if (!cur && st.name) { const n = shows.find(x => x.name === st.name); if (n) select(n); }   // laufende Show wiederfinden
    if (!cur && shows.length === 1) select(shows[0]);
    renderList();
  }
  // Spur-Kurven: was gerade gerechnet wird (Shows und Vorab-Lauf der Bibliothek), alle 10 s
  let stemBusy = new Set(), stemSig = '';
  function stemNote(s) {
    if (stemBusy.has(s.name)) return ' · <span style="color:#ffb86b">Kurven werden gerechnet</span>';
    return s.stems ? ' · Kurven ✓' : '';
  }
  async function pollStemAct() {
    let a;
    try { a = await SM.cmd('stems_activity'); } catch (e) { return; }
    const w = a.work || [], b = a.bulk || {};
    const busy = new Set(w.filter(x => x.kind === 'show').map(x => x.title));
    const ended = [...stemBusy].some(n => !busy.has(n));
    const parts = w.map(x => x.who + ' rechnet „' + x.title + '“' + (x.kind === 'vorab' ? ' (Bibliothek vorab)' : ' (Show)'));
    let t = parts.length ? 'Spur-Kurven: ' + parts.join(' · ') : 'Spur-Kurven: gerade wird nichts gerechnet.';
    if (b.on) t += ' Vorab-Lauf: ' + (b.done || 0) + ' von ' + (b.total || 0) + ' Liedern' + (b.eta_h != null ? ', noch etwa ' + Math.max(1, Math.ceil(b.eta_h)) + ' h' : '')
      + (!b.music ? ', wartet auf den Musik-Rechner (Mixxx-Brücke)' : !(b.workers || []).length ? ', kein Rechner meldet sich' : '') + '.';
    $('stemact').textContent = t;
    const sig = [...busy].sort().join('|');
    if (sig !== stemSig) { stemBusy = busy; stemSig = sig; if (ended) refresh().catch(() => {}); else renderList(); }
  }
  pollStemAct(); setInterval(pollStemAct, 10000);

  // ---- Papierkorb: geloeschte Shows zuruecklegen oder endgueltig loeschen (Wunsch von Markus 06.11.2026) ----------
  function renderTrash(items) {
    $('trashsum').textContent = 'Papierkorb' + (items.length ? ' (' + items.length + ')' : ' (leer)');
    $('tempty').style.display = items.length ? '' : 'none';
    const L = $('tlist');
    L.innerHTML = items.length ? '' : '<p class="dim">Keine gelöschten Shows.</p>';
    for (const t of items) {
      const d = document.createElement('div');
      d.className = 'show';
      d.innerHTML = '<img class="cvimg" loading="lazy" alt="" src="/api/sm/cover?show=' + encodeURIComponent(s.name) + '" onerror="this.remove()"><span class="nm">' + esc(t.name) + '<small>gelöscht ' + esc(t.deleted) + ' · ' + t.tracks + ' Spuren' + (t.has_audio ? '' : ' · ohne Musik') + '</small></span>' +
        '<button data-t="back">Zurücklegen</button><button data-t="del" class="danger">Endgültig löschen</button>';
      d.querySelector('[data-t=back]').onclick = async () => {
        try { const r = await SM.cmd('trash_restore', { entry: t.entry }); renderTrash(r.items); await refresh(); SM.toast('„' + r.name + '“ ist wieder in der Liste.'); }
        catch (e) { SM.toast(e.message, 6000); }
      };
      d.querySelector('[data-t=del]').onclick = async () => {
        if (!await SM.ask('„' + t.name + '“ endgültig löschen?\nDas lässt sich nicht rückgängig machen.', undefined, 'Endgültig löschen')) return;
        try { renderTrash((await SM.cmd('trash_delete', { entry: t.entry })).items); } catch (e) { SM.toast(e.message, 6000); }
      };
      L.appendChild(d);
    }
  }
  async function loadTrash() { try { renderTrash((await SM.cmd('trash_list')).items); } catch (e) { /* aelterer Pi */ } }
  $('tempty').onclick = async () => {
    if (!await SM.ask('Den ganzen Papierkorb endgültig leeren?\nDas lässt sich nicht rückgängig machen.', undefined, 'Papierkorb leeren')) return;
    try { renderTrash((await SM.cmd('trash_delete', { all: true })).items); } catch (e) { SM.toast(e.message, 6000); }
  };
  $('trash').addEventListener('toggle', () => { if ($('trash').open) loadTrash(); });
  loadTrash();

  function renderList() {
    const L = $('plist');
    L.innerHTML = shows.length ? '' : '<p class="dim">Noch keine Show. Mit „+ Neue Show“ anlegen.</p>';
    for (const s of shows) {
      const d = document.createElement('div');
      d.className = 'show' + (cur && cur.name === s.name ? ' sel' : '');
      d.innerHTML = '<span class="nm">' + esc(s.name) + '<small>' + SM.fmtTime(s.duration).replace(/\.\d+$/, '') + ' · ' + Math.round(s.bpm) + ' BPM · ' + s.tracks + ' Spuren' + (s.has_audio ? '' : ' · ohne Musik') + stemNote(s) + '</small></span>' +
        '<a href="/shows/edit?show=' + encodeURIComponent(s.name) + '"><button>Bearbeiten</button></a><button data-a="copy" class="ib" title="Kopieren" aria-label="Kopieren"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg></button><button data-a="ren" class="ib" title="Umbenennen" aria-label="Umbenennen"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></svg></button><button data-a="del" class="danger ib" title="In den Papierkorb" aria-label="In den Papierkorb"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/></svg></button>';
      d.onclick = e => { if (!e.target.closest('button,a') && !(st.loaded && st.playing)) select(s); };
      d.querySelectorAll('button[data-a]').forEach(b => { b.onclick = () => action(b.dataset.a, s).catch(err => SM.toast(err.message, 5000)); });
      L.appendChild(d);
    }
  }
  async function action(a, s) {
    if (a === 'copy') {
      const n = await SM.ask('Name der Kopie', s.name + ' Kopie', 'Kopieren');
      if (n) { await SM.cmd('copy', { name: s.name, new: n }); await refresh(); }
    } else if (a === 'ren') {
      const n = await SM.ask('Neuer Name', s.name, 'Umbenennen');
      if (n && n !== s.name) { await SM.cmd('rename', { name: s.name, new: n }); if (cur && cur.name === s.name) cur = { name: n }; await refresh(); }
    } else if (a === 'del') {
      if (await SM.ask('„' + s.name + '“ in den Papierkorb legen?', undefined, 'In den Papierkorb')) { await SM.cmd('delete', { name: s.name }); SM.toast('„' + s.name + '“ liegt im Papierkorb (unten auf dieser Seite).'); loadTrash(); if (cur && cur.name === s.name) select(null); await refresh(); }
    }
  }
  async function play() {
    if (!cur) { SM.toast('Zuerst eine Show wählen'); return; }
    try {
      if (hasSound()) await audio.play();
      updateStatus(await SM.cmd('play', { name: cur.name, reload: !st.loaded, pos: position(), light, client: hasSound() ? link.client : null }));
      ownPlay = true;
    } catch (e) { SM.toast(e.message, 5000); }
  }
  async function pause() {
    if (hasSound()) audio.pause();
    updateStatus(await SM.cmd('pause', { pos: position() }));
  }
  async function stop() {
    if (hasSound()) { audio.pause(); audio.currentTime = 0; }
    updateStatus(await SM.cmd('stop'));
  }
  async function seek(t) {
    t = SM.clamp(t, 0, duration());
    if (hasSound()) audio.currentTime = t;
    if (st.loaded) updateStatus(await SM.cmd('seek', { pos: t }));
  }
  function updateStatus(s) {
    if (!s) return;
    st = s; stT = performance.now();
    if (ownPlay && !st.loaded) {             // von außen beendet (Knopf SHOW im Panel) oder zu Ende: Musik auch hier aus
      ownPlay = false;
      if (localPlaying()) audio.pause();
    }
    if (st.src === 'mixxx' && st.playing && (!cur || cur.name !== st.name)) { const n = shows.find(x => x.name === st.name); if (n) select(n); }
    const pl = localPlaying() || st.playing;
    $('pplay').classList.toggle('on', !!pl);
    $('blk').classList.toggle('on', !!st.blackout);
    if (st.loaded) { light = !!st.light; }
    const b = $('plight');
    b.classList.toggle('on', light);
    b.textContent = light ? 'Licht an' : 'Licht aus';
    const y = $('syncst');
    if (st.playing && st.src === 'mixxx') y.innerHTML = '<b>● Mixxx</b>';
    else if (st.playing && st.src === 'browser') y.innerHTML = '<b>● Synchron</b> ' + Math.round(Math.abs(st.err_ms)) + ' ms';
    else if (st.playing) y.innerHTML = '<b class="free">● Eigene Uhr</b>';
    else y.textContent = st.loaded ? 'Pause' : '';
    let w = '';
    if (st.uses_strobe && !st.strobe) w = 'Strobe nicht erlaubt: höchstens 2 Blitze pro Sekunde. Erlaubnis im Panel.';
    if (st.loaded && st.playing && !hasSound() && !st.owner) w = (w ? w + ' ' : '') + 'Nur Licht: Die Show läuft nach der Uhr des Light-Butlers.';
    if (st.ended && localPlaying()) audio.pause();
    $('pwarn').textContent = w;
  }
  const smooth = new SM.SmoothClock(), displayLeadMs = SM.displayLead();
  function displayPos() {                    // geglättet und vorgezogen, nur im Bild und nur beim Abspielen
    const playing = localPlaying() || !!st.playing;
    return playing ? smooth.update(position(), performance.now(), true) + displayLeadMs / 1000 : smooth.update(position(), performance.now(), false);
  }
  function drawWave() {
    const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(r.width * dpr)) { cv.width = r.width * dpr; cv.height = r.height * dpr; }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, r.width, r.height);
    const dur = duration(), p = peaks, mid = r.height / 2, pos = displayPos();
    if (p && p.min && p.min.length) {
      const sc = r.height / 2 / 127;
      for (let x = 0; x < r.width; x++) {
        const i = Math.floor(x / r.width * dur * p.rate), j = Math.min(p.min.length, Math.max(i + 1, Math.ceil((x + 1) / r.width * dur * p.rate)));
        let mn = 127, mx = -127;
        const stride = Math.max(1, Math.floor((j - i) / 24));
        for (let k = i; k < j; k += stride) { if (p.min[k] < mn) mn = p.min[k]; if (p.max[k] > mx) mx = p.max[k]; }
        g.fillStyle = x / r.width * dur < pos ? '#e8710a' : '#3f7fd0';
        if (mx >= mn) g.fillRect(x, mid - mx * sc, 1, Math.max(1, (mx - mn) * sc));
      }
    } else {
      g.fillStyle = '#2c2f42'; g.fillRect(0, mid - 1, r.width, 2);
      g.fillStyle = '#e8710a'; g.fillRect(0, mid - 1, pos / dur * r.width, 2);
    }
    g.fillStyle = '#ff3b30'; g.fillRect(pos / dur * r.width - 1, 0, 2, r.height);
  }
  let lastDraw = 0;
  function frame(now) {
    $('pltime').textContent = SM.fmtTime(displayPos());
    showLyric(displayPos());
    if (now - lastDraw > 66) { lastDraw = now; drawWave(); }
    requestAnimationFrame(frame);
  }
  function wire() {
    $('pplay').onclick = play;
    $('ppause').onclick = () => pause().catch(e => SM.toast(e.message));
    $('pstop').onclick = () => stop().catch(e => SM.toast(e.message));
    $('pstart').onclick = () => seek(0).catch(e => SM.toast(e.message));
    $('pnew').onclick = async () => {
      const n = await SM.ask('Name der neuen Show', '', 'Anlegen');
      if (!n) return;
      try { await SM.cmd('create', { name: n }); location.href = '/shows/edit?show=' + encodeURIComponent(n.trim()); } catch (e) { SM.toast(e.message, 6000); }
    };
    $('blk').onclick = () => SM.cmd('blackout', { on: !st.blackout }).then(updateStatus).catch(e => SM.toast(e.message));
    $('plight').onclick = () => {
      light = !light;
      if (st.loaded) SM.cmd('light', { on: light }).then(updateStatus).catch(e => SM.toast(e.message)); else updateStatus(st);
    };
    $('psound').onclick = () => {
      if (localPlaying()) { SM.toast('Erst Pause drücken'); return; }
      soundHere = !soundHere;
      $('psound').classList.toggle('on', soundHere);
      $('psound').textContent = soundHere ? 'Ton hier' : 'Ton woanders';
    };
    $('vol').oninput = e => { audio.volume = +e.target.value; try { localStorage.setItem('smvol', e.target.value); } catch (x) { /* privates Fenster */ } };
    try { const v = localStorage.getItem('smvol'); if (v !== null) { audio.volume = +v; $('vol').value = v; } } catch (x) { /* privates Fenster */ }
    const wavePick = e => { const r = cv.getBoundingClientRect(); seek((e.clientX - r.left) / r.width * duration()).catch(() => {}); };
    cv.addEventListener('pointerdown', e => { cv.setPointerCapture(e.pointerId); wavePick(e); });
    audio.onended = () => { SM.cmd('stop').then(updateStatus).catch(() => {}); };
  }
  wire();
  link = new SM.Link(() => (hasSound() && st.loaded && st.owner === link.client) ? { pos: audio.currentTime, playing: !audio.paused && !audio.ended } : null, updateStatus);
  refresh().catch(e => SM.toast(e.message, 6000));
  // Zurueck aus dem Zwischenspeicher des Browsers oder wieder sichtbar: Liste neu, sonst fehlen neue Shows (z. B. vom Assistenten)
  window.addEventListener('pageshow', e => { if (e.persisted) refresh().catch(() => {}); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh().catch(() => {}); });
  requestAnimationFrame(frame);
})();
