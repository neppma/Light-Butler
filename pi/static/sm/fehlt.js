// Merkliste "Fehlt mir" (Wunsch von Markus, 14.11.2026): gemerkte Lieder und Suchen, die in der Sammlung fehlen.
// Was inzwischen da ist, zeigt der Pi nicht mehr (showman/missing.py). Spotify-Suche im eigenen Fenster, ✕ nimmt heraus.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = SM.esc;
  let items = [], hidden = 0;
  const dateTxt = s => s ? new Date(s * 1000).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '';
  const qOf = x => x.q || [x.t, x.a].filter(Boolean).join(' ');
  function draw() {
    const f = $('q').value.trim().toLowerCase();
    const view = items.filter(x => !f || [x.a, x.t, x.al, x.q].join(' ').toLowerCase().includes(f));
    $('sum').textContent = view.length + (view.length === 1 ? ' Lied' : ' Lieder') + (hidden ? ' · ' + hidden + ' inzwischen in deiner Sammlung (ausgeblendet)' : '');
    $('list').className = view.length ? '' : 'empty';
    $('list').innerHTML = view.map(x => '<div class="it"><div><div class="t">' + (x.q ? 'Suche: „' + esc(x.q) + '“' : esc(x.t)) + '</div><div class="s">' +
      esc([x.a, x.al ? 'Album ' + x.al : '', 'gemerkt ' + dateTxt(x.at)].filter(Boolean).join(' · ')) + '</div></div>' +
      SM.spotifyLink(qOf(x), '', 'Auf Spotify anhören: ' + qOf(x)) +
      '<button class="del" data-k="' + esc(x.k) + '" title="Von der Liste nehmen" aria-label="Von der Liste nehmen">✕</button></div>').join('') ||
      (items.length ? 'Nichts passt zur Suche.' : 'Noch nichts gemerkt' + (hidden ? ' (alles Gemerkte ist inzwischen in deiner Sammlung)' : '') + '.');
  }
  async function load() {
    try { const d = await (await fetch('/api/sm/missing')).json(); items = d.items || []; hidden = d.hidden || 0; }
    catch (e) { $('list').textContent = 'Konnte die Liste nicht laden: ' + e.message; return; }
    draw();
  }
  $('list').addEventListener('click', async e => {
    const b = e.target.closest('button.del'); if (!b) return;
    try { const d = await SM.cmd('missing_del', { k: b.dataset.k }); items = d.items || []; hidden = d.hidden || 0; draw(); }
    catch (err) { SM.toast(err.message, 5000); }
  });
  $('q').addEventListener('input', draw);
  load();
})();
