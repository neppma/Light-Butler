"""
mixxx_uebertragen.py - Mixxx-Daten von fehlenden Tracks auf ihren Zwilling uebertragen (Wunsch von Markus, 09.11.2026).

Nach dem Aufraeumen (Doppelte geloescht, Dateien verschoben) fuehrt Mixxx viele "fehlende Tracks" (track_locations.fs_deleted=1).
An ihnen haengen noch Plattenkisten, Wiedergabelisten und Hotcues. Bereinigt man sie in Mixxx (Purge), waeren diese weg.
Dieses Skript sucht zu jedem fehlenden Track den Zwilling, der noch da ist:
  1. gleicher Dateiname (verschoben, z. B. U-MUSIK -> OLDIES), sonst
  2. gleicher Interpret und Titel (Gross/klein und Satzzeichen egal) mit hoechstens DUR_TOL_S Sekunden Unterschied
  0. vorher: feste Paare aus zwillinge.tsv (alter Pfad TAB neuer Pfad, von Hand oder von Claude angelegt, z. B. wenn die
     behaltene Datei neu getaggt und umbenannt wurde und sonst nichts mehr passt)
und uebertraegt:
  - Plattenkisten: der Zwilling kommt in dieselben Kisten (nie doppelt),
  - Wiedergabelisten (auch Auto-DJ und Verlauf): der Zwilling tritt an dieselbe Stelle, ausser er steht dort schon,
  - Bewertung, Farbe, Wiedergaben (Zahl, zuletzt) und "hinzugefuegt am" (das fruehere Datum): nur wenn der Zwilling keine
    hat bzw. weniger (zweimal laufen aendert nichts),
  - Hotcues: nur wenn der Zwilling keine hat und beide hoechstens HOTCUE_TOL_S Sekunden auseinander liegen (sonst passen die
    Stellen nicht).
Es loescht nichts; danach kann Markus die fehlenden Tracks in Mixxx bereinigen, ohne etwas zu verlieren. Mehrmals laufen ist
harmlos (was schon uebertragen ist, bleibt). Aufruf (die App macht das beim Start, vor Mixxx, siehe mixxx_umbenennen.sh):

    python3 mixxx_uebertragen.py DATENBANK [--protokoll DATEI.json] [--zwillinge DATEI.tsv] [--nur-zaehlen]
Ausgabe: eine Zeile JSON mit den Zahlen.
"""
import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata

DUR_TOL_S = 3.0
HOTCUE_TOL_S = 0.5
HOTCUE = 1                                               # cues.type 1 = Hotcue


def key(s):
    return re.sub(r"[^0-9a-zà-ɏ]+", "", unicodedata.normalize("NFC", str(s or "")).lower())


def fname(p):
    return unicodedata.normalize("NFC", os.path.basename(str(p or ""))).lower()


def load_pairs(path, pairs=None):
    """zwillinge.tsv (und die Listen der Umbenennungen): je Zeile "alter Pfad<TAB>neuer Pfad" (Pfade wie Mixxx sie kennt).
    Fehlt die Datei: unveraendert."""
    pairs = {} if pairs is None else pairs
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                a, _, b = line.rstrip("\n").partition("\t")
                if a and b:
                    pairs[unicodedata.normalize("NFC", a)] = unicodedata.normalize("NFC", b)
    except OSError:
        pass
    return pairs


def load_dir(d):
    """Alle Paare aus dem Ordner der Umbenennungen: erledigt-*.tsv, offen.tsv, zwillinge.tsv (Fehlerbericht 09.11.2026: Mixxx
    hatte vor dem Start der App neu eingelesen, die umbenannten Dateien standen als neue Tracks da, die alten fehlten; ueber den
    Namen oder Interpret+Titel fand sich nicht jeder Zwilling)."""
    pairs = {}
    try:
        names = sorted(f for f in os.listdir(d) if f.startswith("erledigt-") and f.endswith(".tsv")) + ["offen.tsv", "zwillinge.tsv"]
    except OSError:
        return pairs
    for f in names:
        load_pairs(os.path.join(d, f), pairs)
    return pairs


def find_twins(con, pairs=None):
    """[(fehlende id, Zwilling id, Art, Pfad, Pfad Zwilling, Dauer-Unterschied)] und die Zahl ohne Zwilling."""
    alive_name, alive_at, alive_loc = collections.defaultdict(list), collections.defaultdict(list), {}
    for tid, loc, a, t, dur in con.execute(
            "SELECT t.id, l.location, t.artist, t.title, t.duration FROM library t JOIN track_locations l ON l.id = t.location "
            "WHERE l.fs_deleted = 0 AND t.mixxx_deleted = 0"):
        alive_name[fname(loc)].append((tid, loc, float(dur or 0)))
        alive_loc[unicodedata.normalize("NFC", str(loc or ""))] = (tid, loc, float(dur or 0))
        if key(a) and key(t):
            alive_at[(key(a), key(t))].append((tid, loc, float(dur or 0)))
    out, none = [], 0
    for tid, loc, a, t, dur in con.execute(
            "SELECT t.id, l.location, t.artist, t.title, t.duration FROM library t JOIN track_locations l ON l.id = t.location "
            "WHERE l.fs_deleted = 1 AND t.mixxx_deleted = 0"):
        dur = float(dur or 0)
        fixed, q = None, unicodedata.normalize("NFC", str(loc or ""))
        for _ in range(10):                                  # auch Ketten (a -> b -> c), wenn b selbst nicht mehr da ist
            q = (pairs or {}).get(q)
            if not q:
                break
            if q in alive_loc:
                fixed = alive_loc[q]
                break
        cands = [(fixed, "fest")] if fixed else [(c, "Name") for c in alive_name.get(fname(loc), [])]
        if not cands and key(a) and key(t):
            cands = [(c, "Interpret+Titel") for c in alive_at.get((key(a), key(t)), []) if abs(c[2] - dur) <= DUR_TOL_S]
        if not cands:
            none += 1
            continue
        (cid, cloc, cdur), kind = min(cands, key=lambda x: abs(x[0][2] - dur))
        out.append((tid, cid, kind, loc, cloc, abs(cdur - dur)))
    return out, none


VALUE_COLS = ("rating", "color", "timesplayed", "played", "last_played_at", "datetime_added")


def values_for(con, cols, old, new):
    """Was vom fehlenden Track auf den Zwilling soll: {Spalte: Wert}. Nur Verbesserungen, nie etwas wegnehmen."""
    use = [c for c in VALUE_COLS if c in cols]
    if not use:
        return {}
    o = dict(zip(use, con.execute("SELECT " + ", ".join(use) + " FROM library WHERE id = ?", (old,)).fetchone() or [None] * len(use)))
    w = dict(zip(use, con.execute("SELECT " + ", ".join(use) + " FROM library WHERE id = ?", (new,)).fetchone() or [None] * len(use)))
    out = {}
    if o.get("rating") and not w.get("rating"):
        out["rating"] = o["rating"]
    if o.get("color") is not None and w.get("color") is None and "color" in use:
        out["color"] = o["color"]
    if (o.get("timesplayed") or 0) > (w.get("timesplayed") or 0):
        out["timesplayed"] = o["timesplayed"]
    if o.get("played") and not w.get("played"):
        out["played"] = o["played"]
    if o.get("last_played_at") and str(o["last_played_at"]) > str(w.get("last_played_at") or ""):
        out["last_played_at"] = o["last_played_at"]
    if o.get("datetime_added") and w.get("datetime_added") and str(o["datetime_added"]) < str(w["datetime_added"]):
        out["datetime_added"] = o["datetime_added"]
    return out


def transfer(con, dry=False, pairs=None):
    twins, none = find_twins(con, pairs)
    n = {"fehlend": len(twins) + none, "mit_zwilling": len(twins), "ohne_zwilling": none, "kisten": 0, "listen": 0, "hotcues": 0,
         "hotcues_nicht_passend": 0, "werte": 0}
    cols = {r[1] for r in con.execute("PRAGMA table_info(library)")}
    log = []
    for old, new, kind, oloc, nloc, ddur in twins:
        did = {"alt": oloc, "zwilling": nloc, "art": kind, "kisten": 0, "listen": 0, "hotcues": 0, "werte": 0}
        for (crate,) in con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = ?", (old,)).fetchall():
            if not con.execute("SELECT 1 FROM crate_tracks WHERE crate_id = ? AND track_id = ?", (crate, new)).fetchone():
                did["kisten"] += 1
                if not dry:
                    con.execute("INSERT INTO crate_tracks (crate_id, track_id) VALUES (?, ?)", (crate, new))
        for pid, pl in con.execute("SELECT id, playlist_id FROM PlaylistTracks WHERE track_id = ?", (old,)).fetchall():
            if not con.execute("SELECT 1 FROM PlaylistTracks WHERE playlist_id = ? AND track_id = ?", (pl, new)).fetchone():
                did["listen"] += 1
                if not dry:
                    con.execute("UPDATE PlaylistTracks SET track_id = ? WHERE id = ?", (new, pid))
        hc = con.execute("SELECT count(*) FROM cues WHERE track_id = ? AND type = ?", (old, HOTCUE)).fetchone()[0]
        if hc and not con.execute("SELECT 1 FROM cues WHERE track_id = ? AND type = ?", (new, HOTCUE)).fetchone():
            if ddur <= HOTCUE_TOL_S:
                did["hotcues"] = hc
                if not dry:
                    con.execute("INSERT INTO cues (track_id, type, position, length, hotcue, label, color) "
                                "SELECT ?, type, position, length, hotcue, label, color FROM cues WHERE track_id = ? AND type = ?",
                                (new, old, HOTCUE))
            else:
                n["hotcues_nicht_passend"] += 1
        sets = values_for(con, cols, old, new)
        if sets:
            did["werte"] = 1
            if not dry:
                con.execute("UPDATE library SET " + ", ".join(k + " = ?" for k in sets) + " WHERE id = ?", list(sets.values()) + [new])
        for k in ("kisten", "listen", "hotcues", "werte"):
            n[k] += did.get(k, 0)
        if did["kisten"] or did["listen"] or did["hotcues"] or did.get("werte"):
            log.append(did)
    if not dry:
        con.commit()
    return n, log


LB_COLOR = 0x9B30FF                                      # wie cue_estimate.LB_COLOR (lila: vom Light-Butler)


def _same(have, cues, sr):
    """Stehen in Mixxx genau diese LB-Cues (gleiche Zahl, Namen, lila, Lage auf 0,05 s)? have = [(Position, Name, Farbe)]."""
    if not isinstance(cues, list) or not cues or len(have) != len(cues):
        return False
    try:
        want = sorted((float(t), str(nm)[:40]) for t, nm in cues)
    except (TypeError, ValueError):
        return False
    return all(int(col or 0) == LB_COLOR and str(lab or "") == nm and abs(float(pos) / (sr * 2) - t) <= 0.05
               for (pos, lab, col), (t, nm) in zip(have, want))


def write_cues(con, items, dry=False):
    """Geschaetzte Cues (cue_estimate, Wunsch 11.11.2026) in Lieder ganz ohne Hotcues: items = [{"loc": Pfad in Mixxx,
    "cues": [[s, Name], ...]}]. Position in Samples (Stereo) mit der Abtastrate des Liedes. Lieder mit Hotcues bleiben unberuehrt,
    ausser mit "old": stehen dort genau diese LB-Cues (lila, Name, Lage), werden sie durch die neuen ersetzt (lange Mixe, 14.11.2026)."""
    n = 0
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("cues"), list):
            continue
        row = con.execute("SELECT l.id, l.samplerate FROM library l JOIN track_locations t ON t.id = l.location "
                          "WHERE t.location = ? AND COALESCE(l.mixxx_deleted, 0) = 0", (str(it.get("loc") or ""),)).fetchone()
        if not row or not (row[1] or 0) > 0:
            continue
        tid, sr = row
        cues = [c for c in it["cues"] if isinstance(c, list) and len(c) == 2 and isinstance(c[0], (int, float)) and c[0] >= 0][:8]
        if not cues:
            continue
        have = con.execute("SELECT position, label, color FROM cues WHERE track_id = ? AND type = ? ORDER BY position", (tid, HOTCUE)).fetchall()
        if have:                                             # hat schon Hotcues: nur genau die alten LB-Cues ersetzen (14.11.2026)
            olds = [o for o in (it.get("olds") if isinstance(it.get("olds"), list) else [])[:6]] or [it.get("old")]
            if not any(_same(have, o, sr) for o in olds) or _same(have, cues, sr):
                continue                                     # von Markus gesetzt oder geaendert, oder schon die neuen: nie anfassen
            if not dry:
                con.execute("DELETE FROM cues WHERE track_id = ? AND type = ?", (tid, HOTCUE))
        n += 1
        if not dry:
            for i, (t, name) in enumerate(sorted(cues)):
                con.execute("INSERT INTO cues (track_id, type, position, length, hotcue, label, color) VALUES (?, ?, ?, 0, ?, ?, ?)",
                            (tid, HOTCUE, int(round(float(t) * sr * 2)), i, str(name)[:40], LB_COLOR))
    if not dry:
        con.commit()
    return n


def merge_unicode_twins(con, dry=False):
    """Dieselbe Datei zweimal in Mixxx, nur die Umlaute verschieden gespeichert ("ü" als ein Zeichen (NFC) oder als u + Punkte
    (NFD); Fehlerbericht 11.11.2026: 83 Lieder nach dem Import der Liste "geaenderte Tags" und Neu-Einlesen). Je Gruppe bleibt
    der Eintrag in der Schreibweise, die Mixxx selbst beim Einlesen verwendet: NFC. Fehlerbericht 12.11.2026: die erste Fassung
    behielt die Schreibweise vom Stick (NFD), nach "Bibliothek neu einlesen" standen 84 Lieder bei den fehlenden Tracks. Darum
    nimmt diese Fassung auch ausgeblendete und als fehlend markierte Eintraege mit und dreht so eine fruehere Zusammenlegung um:
    der NFC-Eintrag wird wieder sichtbar (und nicht fehlend), Kisten, Listen, Hotcues und Werte der anderen gehen auf ihn ueber,
    die anderen werden ausgeblendet. Die Datei bleibt, wie sie ist. Nur wenn ihr Ordner lesbar ist (Stick steckt)."""
    rows = con.execute("SELECT l.id, t.location, COALESCE(l.mixxx_deleted, 0), t.id FROM library l "
                       "JOIN track_locations t ON t.id = l.location").fetchall()
    groups = collections.defaultdict(list)
    for tid, loc, hid, lid in rows:
        if loc:
            groups[unicodedata.normalize("NFC", loc)].append((tid, loc, hid, lid))
    cols = {r[1] for r in con.execute("PRAGMA table_info(library)")}
    cache, n = {}, 0
    for nfc, g in groups.items():
        if len(g) < 2:
            continue
        keep_rows = [x for x in g if x[1] == nfc]
        others = [x for x in g if x[1] != nfc and not x[2]]       # sichtbare in anderer Schreibweise
        if len(keep_rows) != 1 or not others:
            continue                                               # schon richtig oder nicht eindeutig: nichts tun
        d = os.path.dirname(nfc)
        if d not in cache:
            try:
                cache[d] = set(unicodedata.normalize("NFC", x) for x in os.listdir(d))
            except OSError:
                cache[d] = None
        if cache[d] is None or os.path.basename(nfc) not in cache[d]:
            continue                                               # Stick weg oder Datei nicht da: lieber nichts tun
        keep, _l, keep_hidden, keep_lid = keep_rows[0]
        for old, _loc, _h, _lid in others:
            n += 1
            if dry:
                continue
            for (crate,) in con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = ?", (old,)).fetchall():
                if not con.execute("SELECT 1 FROM crate_tracks WHERE crate_id = ? AND track_id = ?", (crate, keep)).fetchone():
                    con.execute("INSERT INTO crate_tracks (crate_id, track_id) VALUES (?, ?)", (crate, keep))
            con.execute("DELETE FROM crate_tracks WHERE track_id = ?", (old,))
            for pid, pl in con.execute("SELECT id, playlist_id FROM PlaylistTracks WHERE track_id = ?", (old,)).fetchall():
                if con.execute("SELECT 1 FROM PlaylistTracks WHERE playlist_id = ? AND track_id = ?", (pl, keep)).fetchone():
                    con.execute("DELETE FROM PlaylistTracks WHERE id = ?", (pid,))
                else:
                    con.execute("UPDATE PlaylistTracks SET track_id = ? WHERE id = ?", (keep, pid))
            if not con.execute("SELECT 1 FROM cues WHERE track_id = ? AND type = ?", (keep, HOTCUE)).fetchone():
                con.execute("UPDATE cues SET track_id = ? WHERE track_id = ? AND type = ?", (keep, old, HOTCUE))
            sets = values_for(con, cols, old, keep)
            if sets:
                con.execute("UPDATE library SET " + ", ".join(k + " = ?" for k in sets) + " WHERE id = ?", list(sets.values()) + [keep])
            con.execute("UPDATE library SET mixxx_deleted = 1 WHERE id = ?", (old,))
        if not dry:
            con.execute("UPDATE library SET mixxx_deleted = 0 WHERE id = ?", (keep,))
            con.execute("UPDATE track_locations SET fs_deleted = 0 WHERE id = ?", (keep_lid,))
    if not dry and n:
        con.commit()
    return n


TEMP_PREFIXES = ("/private/tmp/", "/tmp/")         # hier liegt nie echte Musik (Probedateien von Testlaeufen)


def hide_temp_tracks(con, dry=False):
    """Mixxx-Eintraege aus Zwischenordnern (Probedateien, Fehlerbericht 11.11.2026) ausblenden. Die Datei bleibt."""
    q = " OR ".join("t.location LIKE ?" for _ in TEMP_PREFIXES)
    ids = [r[0] for r in con.execute("SELECT l.id FROM library l JOIN track_locations t ON t.id = l.location "
                                     "WHERE COALESCE(l.mixxx_deleted, 0) = 0 AND (" + q + ")", [p + "%" for p in TEMP_PREFIXES])]
    if ids and not dry:
        con.executemany("UPDATE library SET mixxx_deleted = 1 WHERE id = ?", [(i,) for i in ids])
        con.executemany("DELETE FROM PlaylistTracks WHERE track_id = ?", [(i,) for i in ids])
        con.commit()
    return len(ids)


TODO_LIST = "LB zu analysieren"


def todo_playlist(con, dry=False, name=TODO_LIST):
    """Wiedergabeliste mit allen Liedern, die Mixxx noch nicht analysiert hat (kein Eintrag in track_analysis, Datei da),
    nach Interpret und Titel (Wunsch 11.11.2026: Mixxx zeigt das nicht an, "Neue Titel" sind die der letzten Woche).
    Nur geaendert, wenn sich der Inhalt aendert; leer = Liste weg. Rueckgabe 1 = geaendert (oder waere es)."""
    try:
        ids = [r[0] for r in con.execute(
            "SELECT l.id FROM library l JOIN track_locations t ON t.id = l.location WHERE COALESCE(l.mixxx_deleted, 0) = 0 "
            "AND COALESCE(t.fs_deleted, 0) = 0 AND NOT EXISTS (SELECT 1 FROM track_analysis a WHERE a.track_id = l.id) "
            "ORDER BY lower(COALESCE(l.artist, '')), lower(COALESCE(l.title, '')), l.id")]
    except sqlite3.Error:
        return 0                                         # alte Mixxx-Datenbank ohne track_analysis: nichts tun
    row = con.execute("SELECT id FROM Playlists WHERE name = ? AND hidden = 0", (name,)).fetchone()
    cur = [r[0] for r in con.execute("SELECT track_id FROM PlaylistTracks WHERE playlist_id = ? ORDER BY position", (row[0],))] if row else []
    if ids == cur:
        return 0
    if dry:
        return 1
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if row and not ids:                                  # alles analysiert: Liste weg
        con.execute("DELETE FROM PlaylistTracks WHERE playlist_id = ?", (row[0],))
        con.execute("DELETE FROM Playlists WHERE id = ?", (row[0],))
    elif ids:
        if row:
            pid = row[0]
            con.execute("DELETE FROM PlaylistTracks WHERE playlist_id = ?", (pid,))
            con.execute("UPDATE Playlists SET date_modified = ? WHERE id = ?", (now, pid))
        else:
            pos = (con.execute("SELECT MAX(position) FROM Playlists").fetchone()[0] or 0) + 1
            pid = con.execute("INSERT INTO Playlists (name, position, hidden, date_created, date_modified, locked) VALUES (?, ?, 0, ?, ?, 0)",
                              (name, pos, now, now)).lastrowid
        con.executemany("INSERT INTO PlaylistTracks (playlist_id, track_id, position, pl_datetime_added) VALUES (?, ?, ?, ?)",
                        [(pid, tid, i + 1, now) for i, tid in enumerate(ids)])
    con.commit()
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mixxx-Daten von fehlenden Tracks auf ihren Zwilling uebertragen")
    ap.add_argument("db")
    ap.add_argument("--protokoll", default="")
    ap.add_argument("--zwillinge", default="", help="feste Paare: alter Pfad TAB neuer Pfad")
    ap.add_argument("--ordner", default="", help="Ordner der Umbenennungen: alle Paare daraus (erledigt-*.tsv, offen.tsv, zwillinge.tsv)")
    ap.add_argument("--nur-zaehlen", action="store_true")
    ap.add_argument("--cues", default="", help="geschaetzte Cues fuer Lieder ohne Hotcues (cue_estimate, mixxx_neu.json)")
    ap.add_argument("--liste-nicht-analysiert", action="store_true", help=f"Wiedergabeliste '{TODO_LIST}' anlegen und nachfuehren")
    a = ap.parse_args(argv)
    con = sqlite3.connect(a.db, timeout=5)
    try:
        pairs = load_dir(a.ordner) if a.ordner else {}
        if a.zwillinge:
            load_pairs(a.zwillinge, pairs)
        n, log = transfer(con, dry=a.nur_zaehlen, pairs=pairs)
        n["umlaut_doppelt"] = merge_unicode_twins(con, dry=a.nur_zaehlen)   # vor Cues und Liste: die zaehlen dann richtig
        n["probe"] = hide_temp_tracks(con, dry=a.nur_zaehlen)
        n["cues"] = 0
        if a.cues and os.path.isfile(a.cues):
            try:
                with open(a.cues, encoding="utf-8") as f:
                    n["cues"] = write_cues(con, json.load(f), dry=a.nur_zaehlen)
            except (OSError, ValueError) as e:
                n["cues_fehler"] = str(e)[:120]
        n["liste"] = todo_playlist(con, dry=a.nur_zaehlen) if a.liste_nicht_analysiert else 0
    finally:
        con.close()
    if a.protokoll and not a.nur_zaehlen and log:
        with open(a.protokoll, "w", encoding="utf-8") as f:
            json.dump({"t": round(time.time()), "zahlen": n, "eintraege": log}, f, ensure_ascii=False, indent=1)
    n["geaendert"] = n["kisten"] + n["listen"] + n["hotcues"] + n["werte"] + n["cues"] + n["liste"] + n["umlaut_doppelt"] + n["probe"]
    print(json.dumps(n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
