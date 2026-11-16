#!/usr/bin/env python3
"""
lumi_program.py - erzeugt das Lumi-Programm LightButler.littlefoot aus der aktuellen Belegung (Download auf der Seite /lumi).

Das Programm laeuft auf dem Lumi selbst: jede Taste leuchtet in der Farbe ihrer Belegung, auch nach den Oktav-Pfeilen.
Jeder Pfeil springt zwei Oktaven, also immer eine ganze Seite von 24 Tasten.
Laden: Datei im ROLI Dashboard auf den Lumi ziehen. Zurueck: im Dashboard auf Werkseinstellungen zuruecksetzen.
Die Noten bleiben wie im Standardprogramm (48 + Oktave * 12 + Taste).
"""
from lumi_view import color_of

FIRST, COUNT = 24, 96              # Noten 24 bis 119: alle Stellungen, die vorkommen koennen
FREE = 0xFF181818                  # freie Taste: fast dunkel
TEMPLATE = """/*
<metadata description="Light-Butler: Tastenfarben nach Belegung (erzeugt vom Light-Butler)" target="LUMI Keys" tags="MIDI;Controller;">
</metadata>
*/

const int configItemId_octave = 4;
const int numKeys = 24;
const int firstNote = %(first)d;
const int numNotes = %(count)d;

int channel[numKeys];
int pressed[numKeys];
int colours[numNotes];
int currentOctave;

void initialise()
{
    setLocalConfigActiveState (0, true, true);
    setLocalConfigActiveState (1, true, true);
    setLocalConfigActiveState (2, true, true);
    setLocalConfigActiveState (configItemId_octave, true, true);
    setLocalConfigItemRange (configItemId_octave, -4, 5);
    setLocalConfig (11, 0);
    currentOctave = getLocalConfig (configItemId_octave);

    for (int i = 0; i < numNotes; ++i)
        colours[i] = %(free)s;

%(fill)s
}

int getNote (int index)
{
    return 48 + currentOctave * 12 + index;
}

void repaint()
{
    currentOctave = getLocalConfig (configItemId_octave);
    clearDisplay();

    for (int key = 0; key < numKeys; ++key)
    {
        int i = getNote (key) - firstNote;
        int colour = %(free)s;

        if (i >= 0 && i < numNotes)
            colour = colours[i];

        if (pressed[key] != 0)
            colour = 0xffffffff;

        fillPixel (colour, key, 0);
    }

    fillPixel (currentOctave - 2 >= -4 ? 0xffffffff : 0, 0, 1);
    fillPixel (currentOctave + 2 <= 5 ? 0xffffffff : 0, 1, 1);
}

void handleButtonDown (int index)
{
    if (index == 1 && currentOctave - 2 >= -4)
        setLocalConfig (configItemId_octave, currentOctave - 2);

    if (index == 2 && currentOctave + 2 <= 5)
        setLocalConfig (configItemId_octave, currentOctave + 2);
}

void keyStrike (int index, int z, int vz)
{
    pressed[index] = 1;
    int note = getNote (index);
    int chan = assignChannel (note);
    channel[index] = chan;
    sendNoteOn (chan, note, vz);
}

void keyPress (int index, int z, int vz)
{
    sendAftertouch (channel[index], getNote (index), z);
}

void keyLift (int index, int z, int vz)
{
    pressed[index] = 0;
    int note = getNote (index);
    int chan = channel[index];
    sendNoteOff (chan, note, vz);
    deassignChannel (note, chan);
}
"""


def argb(css):
    return "0xff" + css[1:].lower()


def program(keys):
    fill = []
    for note, act in sorted(((int(n), a) for n, a in keys.items())):
        css = color_of(act)
        if css and FIRST <= note < FIRST + COUNT:
            fill.append(f"    colours[{note - FIRST}] = {argb(css)};")
    return TEMPLATE % {"first": FIRST, "count": COUNT, "free": hex(FREE), "fill": "\n".join(fill)}

