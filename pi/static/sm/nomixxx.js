// Betrieb ohne Mixxx (Wunsch von Markus, 14.11.2026, Einstellung "Mixxx verwenden" aus). Der Pi setzt dann auf jeder Seite die
// Klasse nomixxx und laedt diese Datei. Sie sorgt dafuer, dass das Wort Mixxx nirgends mehr zu lesen ist:
//  1. Elemente mit der Klasse mx (nur mit Mixxx sinnvoll) blendet nomixxx.css aus.
//  2. Feste Wendungen werden ersetzt (PHRASES), etwa "Helfer oder die Mixxx-App" -> "Helfer".
//  3. Klammern und Nebensaetze mit Mixxx fallen weg, danach jeder Satz, der Mixxx noch nennt (Hinweise erklaeren dort, was in Mixxx zu tun ist).
//  4. Bleibt von einer Zeile, einem Knopf oder einer Einstellung kein Text uebrig, verschwindet sie ganz.
// Gilt fuer Text, title und placeholder, auch fuer alles, was die Seiten spaeter einfuegen (MutationObserver). Nur Anzeige:
// an Mixxx, an Dateien und am Licht aendert das nichts.
(() => {
  'use strict';
  const root = document.documentElement;
  if (!root.classList.contains('nomixxx')) return;
  const PHRASES = [
    [/\s*\(?(Light-Butler )?Helfer bzw\. Mixxx-App\)?/g, ' (Light-Butler Helfer)'],
    [/(der |dem )?Helfer oder (die |der )?Mixxx-(App|Brücke)/g, '$1Helfer'],
    [/(die |der )?Mixxx-(App|Brücke) oder (der |dem )?Helfer/g, '$3Helfer'],
    [/von der Mixxx-Brücke/g, 'vom Helfer'], [/die Mixxx-Brücke/g, 'der Helfer'], [/der Mixxx-Brücke/g, 'dem Helfer'],
    [/Mixxx-Brücke/g, 'Helfer'],
    [/ und damit Mixxx am (Mac|Musik-Rechner)/g, ''], [/ \(und Mixxx am (Mac|Musik-Rechner)\)/g, ''],
    [/Mixxx-Vorhersage/g, 'Lied-Vorhersage'],
    [/Tempo und Beat von Mixxx/g, 'Tempo und Beat aus der Liedanalyse'],
    [/Tonart von Mixxx/g, 'Tonart aus der Liedanalyse'],
    [/Mixxx-Bibliothek/g, 'Bibliothek'],
    [/Sterne \(Mixxx\)/g, 'Sterne'],
    [/aus Mixxx/g, 'aus der Bibliothek'],
  ];
  const SENT = /[^.!?]*(?:[.!?]+(?=\s|$)|$)\s*/g;
  const fix = s => {
    if (!s || s.indexOf('Mixxx') < 0) return s;
    for (const [re, to] of PHRASES) s = s.replace(re, to);
    if (s.indexOf('Mixxx') < 0) return s;
    s = s.replace(/\s*\([^()]*Mixxx[^()]*\)/g, '').replace(/\s*„[^„“]*Mixxx[^„“]*“/g, '');
    if (s.indexOf('Mixxx') < 0) return s;
    s = s.replace(/[,;]\s*[^,;.!?()]*Mixxx[^,;.!?()]*/g, '');   // Nebensatz mit Mixxx ("…, Mixxx behaelt Hotcues"): nur er faellt weg
    if (s.indexOf('Mixxx') < 0) return s;
    const lead = /^\s*/.exec(s)[0];
    const out = (s.match(SENT) || []).filter(x => x.indexOf('Mixxx') < 0).join('').trim();
    return out ? lead + out : '';
  };
  const HIDE = 'option,button,label,li,tr,.srow,.row,.it,.song,.step,.fl,a.btn,th,.hint,.note,p,small';
  function hideEmpty(el) {
    const h = el && el.closest && el.closest(HIDE);
    if (h && !/[A-Za-zÄÖÜäöü0-9]/.test(h.textContent || '')) h.style.display = 'none';
  }
  function doNode(n) {
    if (n.nodeType === 3) {
      const v = n.nodeValue;
      if (v && v.indexOf('Mixxx') >= 0) {
        const w = fix(v);
        if (w !== v) { n.nodeValue = w; if (!w) hideEmpty(n.parentElement); }
      }
      return;
    }
    if (n.nodeType !== 1 || n.tagName === 'SCRIPT' || n.tagName === 'STYLE') return;
    for (const a of ['title', 'placeholder', 'aria-label']) {
      const v = n.getAttribute(a);
      if (v && v.indexOf('Mixxx') >= 0) { const w = fix(v); if (w) n.setAttribute(a, w); else n.removeAttribute(a); }
    }
    if (n.tagName === 'INPUT' && n.type !== 'text' && n.value && n.value.indexOf('Mixxx') >= 0) n.value = fix(n.value);
    for (let c = n.firstChild; c; c = c.nextSibling) doNode(c);
  }
  let busy = false;
  const mo = new MutationObserver(list => {
    if (busy) return;
    busy = true;
    try {
      for (const m of list) {
        if (m.type === 'characterData') doNode(m.target);
        else if (m.type === 'attributes') doNode(m.target);
        else m.addedNodes.forEach(doNode);
      }
    } finally { busy = false; }
  });
  const go = () => {
    if (document.title.indexOf('Mixxx') >= 0) document.title = fix(document.title) || 'Light-Butler';
    doNode(document.body);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['title', 'placeholder', 'aria-label'] });
  };
  if (document.body) go(); else document.addEventListener('DOMContentLoaded', go);
  window.S2L_MXFIX = fix;                                  // fuer Tests und fuer Seiten, die Texte selbst setzen (alert, confirm)
})();
