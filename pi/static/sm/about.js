// Seite "Über Light-Butler" (/about, 15.11.2026): Stand, Lizenz (GPLv3), Sicherheit, fremde Bestandteile. Sprache wie das Panel.
(function () {
  'use strict';
  let EN = false, TX = {};
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const t = k => { const v = TX[k]; return v ? (EN ? v[1] || v[0] : v[0]) : ''; };

  function paint() {
    document.documentElement.lang = EN ? 'en' : 'de';
    document.querySelectorAll('[data-en]').forEach(el => {
      if (el.dataset.de === undefined) el.dataset.de = el.textContent;
      el.textContent = EN ? el.dataset.en : el.dataset.de;
    });
    const s = document.getElementById('safety');
    if (s && TX.sf_intro) {
      s.innerHTML = '<p style="margin:0 0 6px">' + esc(t('sf_intro')) + '</p><ul>' +
        ['sf_strobe', 'sf_laser', 'sf_fog', 'sf_out', 'sf_rig'].map(k => '<li>' + esc(t(k)) + '</li>').join('') + '</ul>';
    }
  }

  function init() {
    paint();
    fetch('/api/about', { cache: 'no-store' }).then(r => r.json()).then(d => {
      EN = d.lang === 'en'; TX = d.texts || {};
      document.getElementById('stand').textContent = d.stand || '–';
      paint();
    }).catch(() => {});
    const det = document.querySelector('details');
    det.addEventListener('toggle', () => {
      const box = document.getElementById('lic');
      if (!det.open || box.dataset.ok) return;
      fetch('/LICENSE').then(r => r.text()).then(x => { box.textContent = x; box.dataset.ok = '1'; }).catch(() => {});
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
