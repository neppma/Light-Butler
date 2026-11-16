// ordner.js - Ordner umbenennen oder verschieben (Wunsch 09.11.2026, Schritt in der Datenpflege). Der Mac benennt um und merkt
// jede Datei fuer Mixxx vor (music_serve POST /cd op rename_dir, cd_assist.rename_dir).
(function () {
  'use strict';
  const $ = id => document.getElementById(id), esc = SM.esc;
  let music = '', dirs = [];
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
  async function loadDirs() {
    try {
      const d = await mac('/cd');
      const all = new Map();                    // auch Ueberordner ohne eigene Lieder ("U-MUSIK/Artists/Xavier Naidoo")
      for (const [p, n] of d.dirs || []) {
        const parts = p.split('/');
        for (let i = 1; i <= parts.length; i++) { const k = parts.slice(0, i).join('/'); all.set(k, (all.get(k) || 0) + n); }
      }
      dirs = [...all.keys()].sort((a, b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1);
      $('odirs').innerHTML = dirs.map(p => '<option value="' + esc(p) + '">' + all.get(p) + ' Lieder</option>').join('');
    } catch (e) { $('omsg').textContent = e.message; }
  }
  async function info() {
    const d = $('odir').value.trim().replace(/^\/+|\/+$/g, '');
    $('oinfo').textContent = '';
    if (!d) return;
    if (!$('onew').value.trim() || $('onew').dataset.auto === '1') { $('onew').value = d; $('onew').dataset.auto = '1'; }
    try {
      const f = await mac('/cd?d=' + encodeURIComponent(d));
      const n = (f.files || []).filter(x => !x.elsewhere).length;
      const sub = dirs.filter(x => x.startsWith(d + '/')).length;
      $('oinfo').textContent = n + ' Lieder direkt in diesem Ordner' + (sub ? ', dazu ' + sub + ' Unterordner (gehen mit)' : '');
    } catch (e) { $('oinfo').textContent = e.message; }
  }
  $('odir').addEventListener('change', info);
  $('onew').addEventListener('input', () => { $('onew').dataset.auto = ''; });
  $('ogo').onclick = async () => {
    const d = $('odir').value.trim().replace(/^\/+|\/+$/g, ''), nw = $('onew').value.trim().replace(/^\/+|\/+$/g, '');
    $('omsg').textContent = ''; $('odone').textContent = '';
    if (!d || !nw) { $('omsg').textContent = 'Bitte Ordner und neuen Pfad eingeben.'; return; }
    if (nw === d) { $('omsg').textContent = 'Der neue Pfad ist gleich wie der alte.'; return; }
    if (!await SM.ask('Ordner umbenennen?\n\n' + d + '\n→ ' + nw + '\n\nDie Musik bleibt gleich, Mixxx übernimmt die neuen Pfade beim nächsten Start der App „Light-Butler Mixxx“.', undefined, 'Umbenennen')) return;
    $('ogo').disabled = true;
    try {
      const r = await mac('/cd', { op: 'rename_dir', dir: d, new: nw });
      $('odone').textContent = 'Umbenannt: ' + r.dir + ' · ' + r.songs + ' Lieder für Mixxx vorgemerkt (beim nächsten Start der App „Light-Butler Mixxx“, bis dahin nicht „Bibliothek neu einlesen“).';
      $('odir').value = r.dir; $('onew').value = r.dir; $('onew').dataset.auto = '1';
      await loadDirs(); info();
    } catch (e) { $('omsg').textContent = e.message; }
    $('ogo').disabled = false;
  };
  const q = new URLSearchParams(location.search).get('d');
  if (q) $('odir').value = q;
  loadDirs().then(() => { if (q) info(); });
})();
