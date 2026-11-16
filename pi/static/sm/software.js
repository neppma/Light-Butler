// Systemschema und Downloads (Seite /software, Wunsch von Markus 15.11.2026): Symbole laden das Paket, Kaesten erklaeren.
// Pakete, die es am Pi noch nicht gibt, sind blass (Stand aus /api/sm/pakete). Texte Deutsch/Englisch wie das Panel.
(function () {
  'use strict';
  let EN = false, AV = {};
  const L = (de, en) => (EN && en) ? en : de;
  const D = '/download/';
  const PI_HINT = ['Neuer Raspberry Pi (Pi OS 64 Bit): ZIP auf den Pi kopieren, entpacken, bash install_pi.sh. Ohne persönliche Daten; das Ersatzgerät enthält zusätzlich deine Geräte mit ihren Adressen. Startet mit allen Ausgaben aus.',
    'New Raspberry Pi (Pi OS 64-bit): copy the ZIP to the Pi, unpack it, bash install_pi.sh. Without personal data; the spare unit also contains your devices with their addresses. Starts with all outputs off.'];
  const MAC = [D + 'light-butler-mac.zip', 'Mac: Mixxx-Brücke und Helfer', 'Mac: Mixxx bridge and helper'];
  const MAC_HINT = ['Ein Paket für beides: entpacken, LIESMICH.txt lesen, install_mac.sh starten. Für den Ton BlackHole installieren, für Mixxx den IAC-Treiber einschalten (steht im LIESMICH).',
    'One package for both: unpack, read LIESMICH.txt, run install_mac.sh. Install BlackHole for the audio and switch on the IAC driver for Mixxx (see LIESMICH).'];
  const WINMUSIK = [D + 'light-butler-windows-musik.zip', 'Windows: Helfer und Mixxx-Brücke', 'Windows: helper and Mixxx bridge', 'winmusik'];
  const WINMUSIK_SOON = ['Das eigene Windows-Paket nur für den Musik-Rechner kommt bald. Bis dahin sind Helfer und Mixxx-Brücke im ganzen Windows-Paket (beim Light-Butler) enthalten.',
    'The separate Windows package for the music computer only is coming soon. Until then the helper and the Mixxx bridge are part of the complete Windows package (at the Light-Butler).'];

  // k -> [Titel de, Titel en, Text de, Text en, Downloads [[Pfad, de, en, Verfuegbarkeit?]], blass-Text?]
  const E = {
    'lb-pi': ['Light-Butler auf dem Raspberry Pi', 'Light-Butler on the Raspberry Pi', PI_HINT[0], PI_HINT[1],
      [[D + 'light-butler-pi.zip', 'Pi: frische Installation', 'Pi: fresh installation'],
       [D + 'light-butler-pi-ersatz.zip', 'Pi: Ersatzgerät mit meinen Geräten', 'Pi: spare unit with my devices']]],
    'lb-win': ['Light-Butler auf einem Windows-PC', 'Light-Butler on a Windows PC',
      'Entpacken, LIESMICH.txt lesen. Die EXE braucht kein Python; das ganze Paket richtet Python und alle Pakete selbst ein. Helfer und Mixxx-Brücke sind in beiden dabei.',
      'Unpack, read LIESMICH.txt. The EXE needs no Python; the complete package sets up Python and all packages itself. Helper and Mixxx bridge are included in both.',
      [[D + 'light-butler-windows-exe.zip', 'Windows: Light-Butler.exe ohne Python', 'Windows: Light-Butler.exe without Python', 'exe'],
       [D + 'light-butler-windows-voll.zip', 'Windows: ganzer Light-Butler mit Python', 'Windows: complete Light-Butler with Python']]],
    'lb-mac': ['Light-Butler auf einem Mac', 'Light-Butler on a Mac',
      'Entpacken, im Terminal bash install_lightbutler_mac.sh ausführen (LIESMICH.txt). Startet beim Anmelden von selbst. Helfer und Mixxx-Brücke kommen aus dem Mac-Paket beim Musik-Rechner; laufen sie auf demselben Mac, als Light-Butler localhost angeben.',
      'Unpack, run bash install_lightbutler_mac.sh in Terminal (LIESMICH.txt). Starts by itself at login. Helper and Mixxx bridge come from the Mac package at the music computer; if they run on the same Mac, enter localhost as the Light-Butler.',
      [[D + 'light-butler-mac-voll.zip', 'Mac: ganzer Light-Butler', 'Mac: complete Light-Butler', 'macvoll']],
      ['Kommt später: das Paket für den Light-Butler am Mac ist am Light-Butler noch nicht eingespielt.', 'Coming later: the package for the Light-Butler on a Mac is not installed on the Light-Butler yet.']],
    'helfer-mac': ['Helfer am Mac', 'Helper on the Mac', MAC_HINT[0], MAC_HINT[1], [MAC]],
    'bruecke-mac': ['Mixxx-Brücke am Mac', 'Mixxx bridge on the Mac', MAC_HINT[0], MAC_HINT[1], [MAC]],
    'helfer-win': ['Helfer unter Windows', 'Helper on Windows',
      'Für den Ton braucht Windows VB-Cable, Stereomix oder ein Kabel am Line-In. Die Pegelkurven haben einen eigenen Kasten.',
      'For the audio, Windows needs VB-Cable, Stereo Mix or a cable at the line-in. The level curves have their own box (Pegelkurven).',
      [WINMUSIK], WINMUSIK_SOON],
    'bruecke-win': ['Mixxx-Brücke unter Windows', 'Mixxx bridge on Windows',
      'Braucht Mixxx 2.5 und loopMIDI mit einem Anschluss namens Light-Butler. Gestartet wird über die Verknüpfung „Light-Butler Mixxx“, sie öffnet Mixxx und die Brücke zusammen.',
      'Needs Mixxx 2.5 and loopMIDI with a port named Light-Butler. Start it with the shortcut "Light-Butler Mixxx", which opens Mixxx and the bridge together.',
      [WINMUSIK], WINMUSIK_SOON],
    'stems-mac': ['Pegelkurven am Mac', 'Level curves on the Mac',
      'Im Mac-Paket enthalten: install_mac.sh fragt, ob die Pegelkurven eingerichtet werden sollen (~/s2l-stems, rund 550 MB). Rechnet mit der CPU, etwa 1,5-mal so lang wie das Lied.',
      'Included in the Mac package: install_mac.sh asks whether to set up the level curves (~/s2l-stems, about 550 MB). Runs on the CPU, about 1.5 times the length of the song.', [MAC]],
    'stems-win': ['Pegelkurven auf einem Windows-PC', 'Level curves on a Windows PC',
      'Entpacken, install_stems.ps1 wie in LIESMICH.txt ausführen. Mit einer NVIDIA-Grafikkarte (CUDA) viel schneller als am Mac; startet beim Anmelden und rechnet auf Wunsch die ganze Bibliothek vorab.',
      'Unpack, run install_stems.ps1 as described in LIESMICH.txt. With an NVIDIA graphics card (CUDA) much faster than on the Mac; starts at login and on request computes the whole library in advance.',
      [[D + 'light-butler-windows.zip', 'Windows: Pegelkurven', 'Windows: level curves']]],
    'stems': ['Pegelkurven', 'Level curves', 'Trennt jedes Lied mit Demucs in Schlagzeug, Bass, Gesang und Rest und schickt nur die Lautstärkekurven an den Light-Butler. Der Show-Assistent erkennt daraus ruhige Stellen, Aufbau und Drops. Ein Mac und ein Windows-PC können sich die Arbeit teilen. Symbol antippen zum Laden.',
      'Splits every song with Demucs into drums, bass, vocals and the rest and sends only the loudness curves to the Light-Butler. The show assistant finds quiet parts, build-ups and drops in them. A Mac and a Windows PC can share the work. Tap a symbol to download.'],
    'lb': ['Light-Butler', 'Light-Butler', 'Das Herz der Anlage: hört die Musik, steuert das Licht und liefert das Web-Panel. Läuft auf einem Raspberry Pi, einem Windows-PC oder einem Mac. Symbol antippen zum Laden.',
      'The heart of the system: listens to the music, controls the light and serves the web panel. Runs on a Raspberry Pi, a Windows PC or a Mac. Tap a symbol to download.'],
    'helfer': ['Helfer', 'Helper', 'Läuft am Musik-Rechner im Hintergrund: Musik-Datenbank, Vorhören, Messen von Tonart, Tempo und Energie, Datenpflege. Er schickt den Ton und leitet MIDI-Geräte weiter, die am Musik-Rechner hängen.',
      'Runs in the background on the music computer: music database, preview, measuring key, tempo and energy, data care. It sends the audio and forwards MIDI devices plugged into the music computer.'],
    'bruecke': ['Mixxx-Brücke', 'Mixxx bridge', 'Liest mit, was Mixxx spielt (Lied, Tempo, Beat, Tonart, Hotcues) und kündigt Drops an. Läuft auf demselben Rechner wie Mixxx.',
      'Follows what Mixxx is playing (song, tempo, beat, key, hot cues) and announces drops. Runs on the same computer as Mixxx.'],
    'ton': ['Ton-Abgriff', 'Audio tap', 'Damit der Helfer den Ton des Musik-Rechners per UDP an den Light-Butler schicken kann: am Mac BlackHole, unter Windows VB-Cable oder Stereomix. Ohne Abgriff hört der Light-Butler über Line-In am Mischpult.',
      'So that the helper can send the music computer\'s audio to the Light-Butler via UDP: BlackHole on the Mac, VB-Cable or Stereo Mix on Windows. Without it the Light-Butler listens via line-in at the mixer.'],
    'mixxx': ['Mixxx', 'Mixxx', 'Die freie DJ-Software (mixxx.org), ab Version 2.5. Ihre Daten gehen über IAC (Mac) oder loopMIDI (Windows) an die Mixxx-Brücke.',
      'The free DJ software (mixxx.org), version 2.5 or later. Its data reaches the Mixxx bridge via IAC (Mac) or loopMIDI (Windows).'],
    'musik': ['Musiksammlung', 'Music collection', 'Die MP3s liegen auf einem USB-Stick am Musik-Rechner oder auf einer NAS im Heimnetz. Mixxx und der Helfer lesen sie, der Helfer schreibt auf Wunsch Tags, Cover und Energie hinein. Den Musikordner und ausgeschlossene Ordner wählst du unter Einstellungen → Verbindungen, Stick und NAS gleichst du in der Datenpflege mit „Spiegeln“ ab.',
      'The MP3s live on a USB stick at the music computer or on a NAS in the home network. Mixxx and the helper read them; on request the helper writes tags, covers and energy into them. Choose the music folder and excluded folders under Settings → Connections, keep stick and NAS in step with “Mirror” in data care.'],
    'artnet': ['Art-Net-Gateway', 'Art-Net gateway', 'Ein Gerät im Netzwerk (zum Beispiel ein zweiter Raspberry Pi mit OLA oder ein fertiges Gateway), das Art-Net in DMX für die Lampen umsetzt.',
      'A device on the network (for example a second Raspberry Pi running OLA or a ready-made gateway) that turns Art-Net into DMX for the lights.'],
    'usb': ['DMX über USB', 'DMX via USB', 'Ein FTDI-Adapter (Open DMX USB) direkt am Light-Butler, ohne zweiten Rechner.',
      'An FTDI adapter (Open DMX USB) plugged straight into the Light-Butler, without a second computer.'],
    'wled': ['WLED', 'WLED', 'LED-Streifen mit WLED, der Light-Butler steuert sie über das Netzwerk (Art-Net).', 'LED strips running WLED, controlled by the Light-Butler over the network (Art-Net).'],
    'nano': ['Nanoleaf', 'Nanoleaf', 'Nanoleaf Light Panels, gesteuert über das Netzwerk.', 'Nanoleaf Light Panels, controlled over the network.'],
    'hm': ['HomeMatic', 'HomeMatic', 'Die Haussteuerung schaltet die Raumbeleuchtung und den Nebelschub (nur per Knopf, höchstens 10 s).',
      'The home automation switches the room lighting and the fog burst (button only, at most 10 s).'],
    'pult': ['Mischpult', 'Mixer', 'Der Ton vom Mischpult kommt über Line-In (USB-Soundkarte) zum Light-Butler. Das geht immer, auch ohne Musik-Rechner.',
      'The audio from the mixer reaches the Light-Butler via line-in (USB sound card). This always works, even without a music computer.'],
    'browser': ['Browser', 'Browser', 'Das Web-Panel auf Handy, Tablet oder PC im Heimnetz, Adresse http://NAME:8080/. Keine Installation nötig.',
      'The web panel on a phone, tablet or PC in the home network, address http://NAME:8080/. Nothing to install.'],
    'midi': ['MIDI-Geräte', 'MIDI devices', 'AKAI APC mini mk2 und ROLI Lumi Keys. Per USB direkt am Light-Butler oder am Musik-Rechner; dort leitet der Helfer sie weiter.',
      'AKAI APC mini mk2 and ROLI LUMI Keys. Via USB straight into the Light-Butler or into the music computer, where the helper forwards them.']
  };

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ok = d => !d[3] || AV[d[3]];

  function show(k) {
    const e = E[k];
    if (!e) return;
    document.querySelectorAll('#schema .sel').forEach(x => x.classList.remove('sel'));
    const g = document.querySelector('#schema [data-k="' + k + '"]');
    if (g) g.classList.add('sel');
    const dls = (e[4] || []).filter(ok);
    let h = '<h2>' + esc(L(e[0], e[1])) + '</h2>';
    if (e[2]) h += '<p>' + esc(L(e[2], e[3])) + '</p>';
    if (dls.length) h += '<div class="dl">' + dls.map(d => '<a class="btn" href="' + d[0] + '" download><span>' + esc(L(d[1], d[2])) + '</span><span>⬇</span></a>').join('') + '</div>';
    if (e[5] && (e[4] || []).some(d => !ok(d))) h += '<p class="soon">' + esc(L(e[5][0], e[5][1])) + '</p>';
    document.getElementById('det').innerHTML = h;
  }

  function paint() {
    document.documentElement.lang = EN ? 'en' : 'de';
    document.querySelectorAll('[data-en]').forEach(el => {
      if (el.dataset.de === undefined) el.dataset.de = el.textContent;
      el.textContent = EN ? el.dataset.en : el.dataset.de;
    });
    [['helfer-win', 'winmusik'], ['bruecke-win', 'winmusik'], ['lb-mac', 'macvoll']].forEach(([k, a]) => {
      const g = document.querySelector('#schema [data-k="' + k + '"]');
      if (g) g.classList.toggle('off', !AV[a]);
    });
    const s = document.querySelector('#schema .sel');
    if (s) show(s.dataset.k);
  }

  function init() {
    document.querySelectorAll('#schema [data-k]').forEach(g => {
      g.addEventListener('click', () => show(g.dataset.k));
      g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); show(g.dataset.k); } });
    });
    paint();
    fetch('/api/nav', { cache: 'no-store' }).then(r => r.json()).then(d => { EN = d.lang === 'en'; paint(); }).catch(() => {});
    fetch('/api/sm/pakete', { cache: 'no-store' }).then(r => r.json()).then(d => { AV = d || {}; paint(); }).catch(() => {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
