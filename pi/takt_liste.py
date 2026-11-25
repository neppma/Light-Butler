"""
takt_liste.py - Namen und kurze Beschreibungen fuer andere Geraete (GET /api/liste und szene/effekt/bewegung in /api/takt,
Wunsch Bravia-Dashboard 24.11.2026): Szenen, Effekte des Effektbands und Bewegungsarten, je mit Farben, Tempo, Charakter,
damit ein Dashboard jeder Szene ein passendes Muster zuordnen kann. Nur lesen, aufs Licht wirkt das nie.

Szenen sind im Panel frei aenderbar: ihre Beschreibung entsteht aus den Eigenschaften (Farbe, Licht-Mix, Tempo, Bewegung).
Die Effektband-Voreinstellungen liegen im WLED-Geraet; die Beschreibungen hier gehoeren zu den Namen der Sicherung in wled/
(Stand 01.11.2026). Ein unbekannter Name bekommt eine allgemeine Beschreibung.
"""
import unicodedata

from scenes import COLOR_LABELS, MIX_LABELS

MOVE_NAMES = {"home": "Stop", "horizontal": "Rechts-Links", "vertical": "Rauf-Runter", "circle": "Kreis", "random": "Zufall",
              "sweep": "Besen", "fan": "Schwimmer", "duck": "Ente", "calm": "Ruhig", "auto": "Musik"}
MOVE_DESCR = {
    "home": "keine Bewegung, die Koepfe stehen in der Mitte",
    "horizontal": "Koepfe schwenken gleichmaessig nach rechts und links",
    "vertical": "Koepfe und Balken nicken rauf und runter",
    "circle": "Koepfe fahren Kreise",
    "random": "springt im Takt zu zufaelligen Zielen, unruhig",
    "sweep": "breite fegende Bewegung wie ein Besen, schwungvoll",
    "fan": "die Arme gehen auseinander und wieder zusammen wie beim Schwimmen",
    "duck": "die Arme wippen parallel wie eine Ente, gemuetlich",
    "calm": "langsames, ruhiges Gleiten",
    "auto": "Bewegung folgt der Musik (ruhig bis wild)",
}
SPEED_WORDS = {"slow": "langsam", "mid": "mittel", "fast": "schnell"}
COLOR_WORDS = {"auto": "Farbe nach Stimmung", "duo": "zwei Farben im Wechsel", "multi": "bunt", "austria": "rot-weiss-rot"}
MIX_WORDS = {"pulse": "Pulsieren (Atmen)", "switch": "Bloecke wechseln", "backforth": "Lauflicht hin und her",
             "sweep": "Lauflicht im Kreis", "grow": "waechst von der Mitte", "shrink": "waechst und schrumpft",
             "onoff": "an und aus im Takt"}

# Effektband: Name der Voreinstellung (wie im WLED-Geraet) -> Beschreibung
EB_DESCR = {
    "austria": "rot-weiss-rot, mittel, ruhiges Muster in den Landesfarben",
    "scanner": "rot, schnell, ein Lichtpunkt laeuft hin und her",
    "kitt": "rot, schnell, ein Lichtpunkt laeuft hin und her",
    "fairy": "bunt, langsam, funkelnde Lichterkette",
    "fire": "rot, orange, gelb, mittel, flackerndes Feuer",
    "fireworks starburst": "bunt, mittel, Feuerwerk mit Funkenregen",
    "gravimeter": "bunt, folgt dem Ton, Pegelanzeige mit fallendem Punkt",
    "juggle": "bunt, mittel, mehrere Lichtpunkte schwingen durcheinander",
    "lightning": "weiss, unregelmaessig, Blitze wie bei Gewitter",
    "meteor smooth": "bunt, langsam, Meteor mit langem Schweif",
    "midnoise": "bunt, folgt dem Ton, Pegel waechst aus der Mitte, schnell",
    "phased": "bunt, mittel, wellenfoermig wandernde Farben",
    "popcorn": "bunt, mittel, huepfende Lichtpunkte",
    "pride 2015": "Regenbogen, mittel, ruhig fliessende Farben",
    "rain": "bunt, mittel, fallende Tropfen",
    "scan": "bunt, langsam, ein Lichtbalken wandert hin und her",
    "weihnachten": "goldgelb, ruhig, festliches Funkeln",
    "dj light": "bunt, schnell, folgt dem Ton, Lichtbalken aus der Mitte im Takt",
    "gravfreq": "bunt, schnell, folgt dem Ton, Pegel nach Tonhoehe",
    "gravcenter": "bunt, folgt dem Ton, Pegel aus der Mitte heraus",
    "juggles": "bunt, folgt dem Ton, tanzende Lichtpunkte",
    "demo": "wechselnde Effekte nacheinander (Playlist)",
    "noisefire": "rot, orange, folgt dem Ton, Feuer lodert mit der Lautstaerke",
    "noisemeter": "bunt, folgt dem Ton, unruhiger Pegel",
    "puddlepeak": "bunt, folgt dem Ton, Farbflecken auf den Spitzen",
    "ripple peak": "bunt, folgt dem Ton, Wellenringe bei Spitzen",
    "m-club": "wechselnde Club-Effekte nacheinander (Playlist)",
    "rot bpm": "rot, im Takt, pulsiert mit dem Tempo",
    "blink": "bunt, schnell, Blinken",
    "solid blau": "blau, ruhig, dauerhaft an",
    "ripple peak 2": "kaltweiss, folgt dem Ton, schnelle Wellenringe bei Spitzen",
    "solid red": "rot, ruhig, dauerhaft an",
    "strobo": "weiss, sehr schnell, Stroboskop-Blitze",
    "android": "orange, mittel, Balken waechst und schrumpft",
    "solid grun": "gruen, ruhig, dauerhaft an",
    "solid gruen": "gruen, ruhig, dauerhaft an",
    "solid weiss": "weiss, ruhig, dauerhaft an",
    "m-club effekt": "wechselnde Club-Effekte nacheinander (Playlist)",
    "sparkle": "weiss auf dunkel, mittel, einzelne funkelnde Punkte",
    "karussell": "rot, mittel, kreisende Abschnitte",
    "disco": "bunt, mittel, Lichtpunkte wie eine Discokugel",
}


def _key(name):
    """Vergleich unabhaengig von Gross-/Kleinschreibung, Umlauten und Zusaetzen wie "(Playlist)"."""
    n = str(name).replace("ß", "ss").replace("ü", "ue").replace("Ü", "Ue")
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    return n.split("(")[0].strip()


def eb_descr(name):
    k = _key(name)
    return EB_DESCR.get(k) or "Effekt des Effektbands"


def scene_descr(s):
    """Kurzbeschreibung einer Szene aus ihren Eigenschaften (Farben, Tempo, Charakter)."""
    sp = s.special or ""
    if sp == "blackout":
        return "alles aus, dunkel"
    if sp == "auto":
        return "zurueck zur Automatik: Licht folgt der Musik"
    if sp == "laser":
        return "Laser-Show im Takt, Raum dunkel"
    if sp.startswith("aim:"):
        return "die Strahler zeigen fest auf einen Platz (%s), ruhig" % sp[4:]
    colors = dict(COLOR_LABELS)
    mixes = dict(MIX_LABELS)
    parts = [COLOR_WORDS.get(s.color) or colors.get(s.color, s.color).split(" (")[0]]
    if s.mix == "static":
        parts.append("ruhig, dauerhaft an")
    elif s.mix == "strobe":
        parts.append("sehr schnell, Stroboskop-Blitze")
    elif s.mix == "lightning":
        parts.append("unregelmaessig, Blitze wie bei Gewitter")
    elif s.mix == "random":                            # Tempo aus der Blitzrate, nicht aus speed
        parts.append("langsam" if s.rate < 0.5 else "mittel" if s.rate < 1.5 else "sehr schnell")
        parts.append("zufaellig aufleuchtende Lichter")
    else:
        parts.append(SPEED_WORDS.get(s.speed, s.speed))
        parts.append(MIX_WORDS.get(s.mix) or mixes.get(s.mix, s.mix).split(" (")[0])
    if s.move not in ("home", "auto") and s.move:
        parts.append("Bewegung " + MOVE_NAMES.get(s.move, s.move))
    if s.level < 0.8:
        parts.append("gedimmt")
    return ", ".join(p for p in parts if p)


def liste(show):
    """GET /api/liste: alle Szenen, Effekte des Effektbands, Bewegungsarten mit Namen und Beschreibung."""
    eb = [{"nr": i, "name": n, "beschreibung": eb_descr(n)} for i, n in show._eb_names()]
    sz = [{"name": s.name, "beschreibung": scene_descr(s)} for s in show.scene_defs]
    mv = [{"name": MOVE_NAMES[k], "beschreibung": MOVE_DESCR[k]} for k in
          ("horizontal", "fan", "duck", "home", "random", "sweep", "circle", "vertical", "calm", "auto")]
    return {"version": 1, "szenen": sz, "effekte": eb, "bewegungen": mv}
