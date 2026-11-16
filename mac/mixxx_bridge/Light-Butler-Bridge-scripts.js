/*
 * Light-Butler Bridge fuer Mixxx 2.5
 *
 * Liest alle 100 ms den Zustand der Decks und sendet ihn als MIDI-SysEx (ASCII-JSON) an den virtuellen
 * MIDI-Port "IAC Driver Bus 1". Das Programm mixxx_bridge.py auf dem Mac liest ihn dort und leitet ihn an den
 * Raspberry Pi weiter. Dieses Mapping steuert nichts in Mixxx, es liest nur.
 *
 * Felder je Deck (kurz, damit die Nachricht klein bleibt):
 *   d  Deck-Nummer          pl Play (0/1)             tl Titel geladen (0/1)
 *   du Laenge in Sekunden   fb BPM der Datei          bp BPM aktuell (mit Pitch und Sync)
 *   rr Abspielgeschwindigkeit (1.0 = normal)          pp Position 0..1
 *   bd Beat-Abstand 0..1 (Lage innerhalb des Beats)   sy Sync an (0/1)
 *   vo Kanalfader 0..1      or Crossfader-Seite (0 links, 1 Mitte, 2 rechts)   vu Pegel 0..1
 *   k  Tonart jetzt (Mixxx-Nr. 1..24)  fk Tonart der Datei  cf Crossfader -1..1
 *   q  laufende Nummer
 */
var S2L = {};
S2L.INTERVAL = 100;      // ms zwischen zwei Messungen
S2L.seq = 0;
S2L.timer = 0;

S2L.missing = {};      // Steuerwerte, die Mixxx nicht kennt (werden nur einmal gemeldet)
S2L.sent = 0;
S2L.errors = 0;

S2L.num = function (group, key) {
    var v;
    try {
        v = engine.getValue(group, key);
    } catch (e) {
        var id = group + " " + key;
        if (!S2L.missing[id]) {
            S2L.missing[id] = true;
            print("[Light-Butler] Steuerwert nicht lesbar: " + id + " (" + e + ")");
        }
        return 0;
    }
    return (typeof v === "number" && isFinite(v)) ? v : 0;
};

S2L.round = function (v, digits) {
    var f = Math.pow(10, digits);
    return Math.round(v * f) / f;
};

// Text als MIDI-SysEx senden: F0 7D 53 <ASCII> F7 (7D = Kennung fuer nicht-kommerzielle Nutzung)
S2L.sendText = function (text) {
    var msg = [0xF0, 0x7D, 0x53];
    for (var i = 0; i < text.length; i++) {
        var c = text.charCodeAt(i);
        msg.push(c < 128 ? c : 63);
    }
    msg.push(0xF7);
    midi.sendSysexMsg(msg, msg.length);
    S2L.sent++;
};

S2L.init = function (id, debugging) {
    S2L.debugging = debugging;
    S2L.timer = engine.beginTimer(S2L.INTERVAL, S2L.tick);
    print("[Light-Butler] Bridge gestartet (Version 3, Timer " + S2L.timer + ")");
};

S2L.shutdown = function () {
    if (S2L.timer) {
        engine.stopTimer(S2L.timer);
        S2L.timer = 0;
    }
    print("[Light-Butler] Bridge beendet");
};

S2L.tick = function () {
    try {
        S2L.tickInner();
    } catch (e) {
        S2L.errors++;
        if (S2L.errors <= 5) {
            print("[Light-Butler] FEHLER im Messzyklus: " + e);
        }
    }
    // etwa alle 5 Sekunden ein Lebenszeichen im Terminal
    if ((S2L.seq % 50) === 0) {
        print("[Light-Butler] aktiv, gesendet: " + S2L.sent + ", Fehler: " + S2L.errors);
    }
};

S2L.tickInner = function () {
    S2L.seq = (S2L.seq + 1) % 100000;
    var decks = S2L.num("[App]", "num_decks");
    if (decks < 1) { decks = 2; }
    var cf = S2L.round(S2L.num("[Master]", "crossfader"), 3);
    for (var d = 1; d <= decks; d++) {
        var g = "[Channel" + d + "]";
        var loaded = S2L.num(g, "track_loaded");
        // leere Decks nur etwa jede Sekunde melden
        if (!loaded && (S2L.seq % 10) !== 0) { continue; }
        var o = {
            d: d, q: S2L.seq, pl: S2L.num(g, "play"), tl: loaded,
            du: S2L.round(S2L.num(g, "duration"), 3),
            fb: S2L.round(S2L.num(g, "file_bpm"), 3),
            bp: S2L.round(S2L.num(g, "bpm"), 2),
            rr: S2L.round(S2L.num(g, "rate_ratio"), 4),
            pp: S2L.round(S2L.num(g, "playposition"), 5),
            bd: S2L.round(S2L.num(g, "beat_distance"), 4),
            sy: S2L.num(g, "sync_enabled"),
            vo: S2L.round(S2L.num(g, "volume"), 3),
            or: S2L.num(g, "orientation"),
            vu: S2L.round(S2L.num(g, "VuMeter"), 3),
            k: S2L.num(g, "key"), fk: S2L.num(g, "file_key"),
            cf: cf
        };
        S2L.sendText(JSON.stringify(o));
    }
};
