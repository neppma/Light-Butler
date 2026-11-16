"""Bereich Szenen: das Plus (neue Szene) und "Szenen auf Standard zuruecksetzen" erscheinen erst nach Bearbeiten,
wie beim Bereich Ziele."""
from _common import check, finish

import webpanel

p = webpanel.make_page()
check("if(EDIT){const add=document.createElement('button');add.className='sadd'" in p, "Plus nur im Bearbeiten-Modus")
check("if(EDIT){const rs=document.createElement('div')" in p and "rs.firstChild.onclick=resetScenes" in p,
      "Zuruecksetzen nur im Bearbeiten-Modus")
check(p.count('onclick="resetScenes()"') == 0, "kein fester Zuruecksetzen-Knopf mehr unter den Szenen")
finish("test_szenen_bearbeiten")
