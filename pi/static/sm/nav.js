/* Light-Butler: dieselbe Kopfleiste auf jeder Unterseite.
   Links zurueck zur vorigen Seite (wie der Zurueck-Knopf des Browsers), der Titel, rechts das Panel (Haus) und das Menue mit allen Hauptseiten.
   Jede Seite schreibt nur einen Platzhalter, der Text darin ist der Titel, falls die Texte nicht ankommen:
     <div class="s2lnav" data-back="/settings" data-cur="settings" data-title="h_fixtures">Fixtures</div>
   data-back: Ziel des Pfeils, wenn es keine vorige Seite des Panels gibt (direkt geoeffnet, Lesezeichen), data-cur: Menuepunkt dieser Seite, data-title: Schluessel in texts.py fuer den Titel (nicht data-tk, das benutzt das Panel selbst).
   Texte und Sprache kommen von /api/nav (eigene Texte aus der Uebersetzungstabelle gelten mit). */
(function () {
  'use strict';
  const IC = {
    back: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 8H3M7.5 3.5 3 8l4.5 4.5"/></svg>',
    home: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M2 7.5 8 2.5l6 5M3.8 6.2V13.5h3V10h2.4v3.5h3V6.2"/></svg>',
    menu: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2.5 4h11M2.5 8h11M2.5 12h11"/></svg>',
    close: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg>',
    shows: '<svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><path d="M1 3h13v2H1zM1 7h8v2H1zM1 11h11v2H1z"/><path d="M5 1.5h1.4v12H5z" opacity=".55"/></svg>',
    musik: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="7.5" cy="3.5" rx="5.5" ry="2"/><path d="M2 3.5v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-8M2 7.5c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"/></svg>',
    autodj: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7.5" cy="7.5" r="6"/><circle cx="7.5" cy="7.5" r="1.6"/><path d="M7.5 3.2a4.3 4.3 0 0 1 4.3 4.3" opacity=".6"/></svg>',
    raum: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="2.5" width="12" height="10" rx="1"/><path d="M8.5 2.5v4.5h5M5 12.5V9.5"/></svg>',
    stats: '<svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><rect x="1" y="8" width="3" height="6" rx="0.6"/><rect x="6" y="4" width="3" height="10" rx="0.6"/><rect x="11" y="1" width="3" height="13" rx="0.6"/></svg>',
    health: '<svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><path d="M7.5 13.5S1 9.6 1 5.2C1 3 2.7 1.5 4.6 1.5c1.2 0 2.3.6 2.9 1.6.6-1 1.7-1.6 2.9-1.6C12.3 1.5 14 3 14 5.2c0 4.4-6.5 8.3-6.5 8.3z"/></svg>',
    settings: '<svg width="17" height="17" viewBox="0 0 15 15" fill="currentColor" fill-rule="evenodd"><path d="M12.77 6.32 L14.44 6.59 L14.44 8.41 L12.77 8.68 L12.49 9.57 L12.06 10.39 L13.05 11.77 L11.77 13.05 L10.39 12.06 L9.57 12.49 L8.68 12.77 L8.41 14.44 L6.59 14.44 L6.32 12.77 L5.43 12.49 L4.61 12.06 L3.23 13.05 L1.95 11.77 L2.94 10.39 L2.51 9.57 L2.23 8.68 L0.56 8.41 L0.56 6.59 L2.23 6.32 L2.51 5.43 L2.94 4.61 L1.95 3.23 L3.23 1.95 L4.61 2.94 L5.43 2.51 L6.32 2.23 L6.59 0.56 L8.41 0.56 L8.68 2.23 L9.57 2.51 L10.39 2.94 L11.77 1.95 L13.05 3.23 L12.06 4.61 L12.49 5.43Z M7.5 5.2a2.3 2.3 0 1 0 0.001 0Z"/></svg>',   // Grafik statt Zeichen: im Browser am Mac war das Zeichen viel kleiner als am iPad (12.11.2026)
    artists: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7.5" cy="4.8" r="2.8"/><path d="M2 13.5c.6-2.9 2.9-4.4 5.5-4.4s4.9 1.5 5.5 4.4"/></svg>',
    albums: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7.5" cy="7.5" r="6"/><circle cx="7.5" cy="7.5" r="1.6"/></svg>',
    favs: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M7.5 13S1.8 9.4 1.8 5.4A2.9 2.9 0 0 1 7.5 4a2.9 2.9 0 0 1 5.7 1.4C13.2 9.4 7.5 13 7.5 13z"/></svg>',
    help: '<span style="font-size:15px;font-weight:800;line-height:1">?</span>',
    about: '<span style="font-size:15px;font-weight:800;line-height:1;font-family:Georgia,serif">i</span>',
  };
  // Menue: (Kennung, Adresse, Textschluessel); dieselbe Reihenfolge wie im Entwurf, Panel zuerst
  const MENU = [['panel', '/', 'nav_home', 'home'], ['shows', '/shows', 'h_showman'], ['musik', '/musik', 'h_music'], ['artists', '/musik/interpreten', 'h_artists'], ['albums', '/musik/alben', 'h_albums'], ['favs', '/musik/favoriten', 'h_favs'],
                ['autodj', '/musik/autodj', 'h_autodj'], ['raum', '/raum', 'h_room'], ['stats', '/stats', 'stat_title'], ['health', '/health', 'h_health'],
                ['settings', '/settings', 'h_setpage'], ['help', '/help', 'h_help'], ['about', '/about', 'h_about']];
  const DEF = {
    nav_back: ['Zurück', 'Back'], nav_home: ['Panel', 'Panel'], nav_menu: ['Menü', 'Menu'],
    h_showman: ['Showmanager', 'Show manager'], h_music: ['Musik-Datenbank', 'Music library'], h_room: ['Raumplan', 'Room plan'], h_autodj: ['Auto-DJ', 'Auto DJ'], h_artists: ['Interpreten', 'Artists'], h_albums: ['Alben', 'Albums'], h_favs: ['Favoriten', 'Favourites'], h_missing: ['Fehlt mir', 'Missing songs'], h_damaged: ['Beschädigte Dateien', 'Damaged files'],
    stat_title: ['Statistik', 'Statistics'], h_health: ['Zustand', 'Health'], h_setpage: ['Einstellungen', 'Settings'],
    h_help: ['Hilfe', 'Help'], h_about: ['Über Light-Butler', 'About Light-Butler'],
  };
  let lang = 'de', TX = {};
  const t = (k, fb) => { const v = TX[k] || DEF[k]; return v ? (v[lang === 'en' ? 1 : 0] || v[0]) : (fb || k); };
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const CSS = '.s2lnav{position:relative;display:flex;align-items:center;gap:8px;margin:0 0 10px;font-family:inherit}' +
    '.s2l-b{flex:none;width:34px;height:34px;min-height:0;padding:0;border-radius:50%;background:#2a2c3d;color:#9fd0ff;' +
    'border:1px solid #3a3f58;display:flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer;font:inherit}' +
    '.s2l-b:hover{border-color:#5a6080}.s2l-b.on{background:#2a2c3d;border-color:#ff9a3c;color:#ff9a3c}' +
    '.s2l-t{flex:1;min-width:0;font-size:19px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
    '.s2l-m{position:absolute;right:0;top:42px;z-index:9999;min-width:210px;background:#1c1f2c;border:1px solid #3a3f58;' +
    'border-radius:12px;padding:6px;box-shadow:0 10px 30px rgba(0,0,0,.55)}.s2l-m[hidden]{display:none}' +
    '.s2l-m a{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:8px;color:#dde;text-decoration:none;font-size:15px;font-weight:600}' +
    '.s2l-m a:hover{background:#262a3c}.s2l-m a span{width:18px;display:flex;justify-content:center;color:#9fd0ff}' +
    '.s2l-m a.cur{background:#2a2f45;color:#fff}.s2l-m a.cur span{color:#ff9a3c}';

  function href(id, url) { return id === 'help' ? '/help?lang=' + lang : url; }

  function build(el) {
    if (!el.dataset.fb) el.dataset.fb = el.textContent.trim();
    const cur = el.dataset.cur || '', back = el.dataset.back || '/';
    const items = MENU.map(([id, url, k, ic]) => '<a href="' + href(id, url) + '"' + (id === cur ? ' class="cur" aria-current="page"' : '') + '><span>' +
      (IC[ic || id] || '') + '</span>' + esc(t(k)) + '</a>').join('');
    el.innerHTML = '<a class="s2l-b" data-n="back" href="' + esc(back) + '" title="' + esc(t('nav_back')) + '" aria-label="' + esc(t('nav_back')) + '">' + IC.back + '</a>' +
      '<span class="s2l-t">' + esc(el.dataset.title ? t(el.dataset.title, el.dataset.fb) : el.dataset.fb) + '</span>' +
      '<a class="s2l-b" data-n="home" href="/" title="' + esc(t('nav_home')) + '" aria-label="' + esc(t('nav_home')) + '">' + IC.home + '</a>' +
      '<button type="button" class="s2l-b" data-n="menu" title="' + esc(t('nav_menu')) + '" aria-label="' + esc(t('nav_menu')) + '" aria-expanded="false">' + IC.menu + '</button>' +
      '<div class="s2l-m" hidden>' + items + '</div>';
    const btn = el.querySelector('[data-n=menu]'), m = el.querySelector('.s2l-m');
    btn.onclick = e => { e.stopPropagation(); open(m.hidden ? el : null); };
    el.querySelector('[data-n=back]').onclick = e => { if (cameFromPanel()) { e.preventDefault(); history.back(); } };
  }

  // Kam man von einer anderen Seite des Panels? Dann fuehrt der Pfeil dorthin zurueck. Von derselben Seite (Editor -> Editor,
  // etwa nach dem Assistenten) gilt data-back: zurueck zur Showliste statt in die vorige Show (Wunsch von Markus, 06.11.2026).
  function cameFromPanel() {
    try {
      if (history.length < 2 || !document.referrer) return false;
      const r = new URL(document.referrer);
      return r.origin === location.origin && r.pathname !== location.pathname;
    } catch (e) { return false; }
  }

  function open(el) {                             // el = Leiste, deren Menue aufgeht; null = alle zu
    document.querySelectorAll('.s2lnav').forEach(n => {
      const m = n.querySelector('.s2l-m'), b = n.querySelector('[data-n=menu]');
      if (!m) return;
      const on = n === el;
      m.hidden = !on; b.classList.toggle('on', on); b.setAttribute('aria-expanded', on ? 'true' : 'false');
      b.innerHTML = on ? IC.close : IC.menu;
    });
  }

  function all() { document.querySelectorAll('.s2lnav').forEach(build); }

  // Der Auto-DJ spielt den Ton im Browser: im selben Tab hoerte er beim Seitenwechsel auf. Darum ein eigenes Fenster, und laeuft
  // es schon, nur nach vorne holen (nicht neu laden, sonst stoppt die Musik).
  function openAutoDJ() {
    let w = null;
    try { w = window.open('', 'lb_autodj'); } catch (x) { w = null; }
    if (!w) { location.href = '/musik/autodj'; return; }      // Fenster blockiert: wie bisher im selben Tab
    try { if (w.location.pathname !== '/musik/autodj') w.location.href = '/musik/autodj'; } catch (x) { w.location.href = '/musik/autodj'; }
    w.focus();
  }
  window.S2LNav = Object.assign(window.S2LNav || {}, { openAutoDJ });

  function init() {
    if (!document.getElementById('s2lnavcss')) {
      const s = document.createElement('style'); s.id = 's2lnavcss'; s.textContent = CSS; document.head.appendChild(s);
    }
    all();
    document.addEventListener('click', e => { if (!e.target.closest || !e.target.closest('.s2l-m')) open(null); });
    document.addEventListener('click', e => {               // Auto-DJ im eigenen Fenster (Wunsch 08.11.2026): Ton laeuft weiter
      const a = e.target.closest && e.target.closest('a[href="/musik/autodj"]');
      if (!a || e.metaKey || e.ctrlKey || location.pathname === '/musik/autodj') return;
      e.preventDefault(); open(null); openAutoDJ();
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') open(null); });
    window.addEventListener('pageshow', () => open(null));   // zurueck aus dem Zwischenspeicher des Browsers: Menue zu
    fetch('/api/nav', { cache: 'no-store' }).then(r => r.json()).then(D => {
      lang = D.lang === 'en' ? 'en' : 'de'; TX = D.texts || {}; all();
    }).catch(() => {});
  }

  // Das Panel ruft das beim Umschalten der Sprache auf (setLang), damit die Leiste sofort mitgeht
  window.S2LNAV = { set(l, texts) { lang = l === 'en' ? 'en' : 'de'; if (texts) TX = texts; all(); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
