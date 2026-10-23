# nanoKONTROL Studio — DaVinci Resolve 21 vezérlő / Scene 1

**Állapot:** aktuális \`fix/clean-assignable-relearn\` (draft PR #2). A 2026-10-23-i Hammerspoon MIDI-napló és a 28 lépéses Lua-betanítási sorrend alapján. A lent felsorolt gombfunkciók **a szoftveres hozzárendelések**; a tényleges elmentett \`hs.settings\` a Korgon végzett legutolsó 28/28 sikeres betanítást követi. Az ismert CC-ket nem kell minden alkalommal újratanítani.

## Alap

| Korg kezelőszerv | MIDI / fizikai Scene 1 | DaVinci Resolve |
| --- | --- | --- |
| JOG CW / CCW | CC82, Sign Magnitude 1–64 / 65–127 | egy frame előre / vissza |
| JOG, CYCLE után | ugyanaz a CC82 | SHUTTLE −4…+4, 1 MIDI impulzus = 1 fokozat |
| MARKER SET + JOG | CC55 nyomva + CC82 | \`V\`, majd \`,\` / \`.\` (kijelölt vágáspont finomítása) |
| FADER 1 (bal szélső **tolópotméter**) | CC2, 0–127 | középállásos SHUTTLE, ±4 fokozat; 60–68 = STOP |
| SCENE | hardveres, körkörös 1→2→3→4→5 | **nincs szoftveresen hozzárendelve**; teszthez Scene 1 |

A MIDI csatorna a Korg Editorban \`1\`, Hammerspoon bemenetén \`channel=0\`. A LED-kimenetnél viszont a Hammerspoon \`sendCommand(..., channel=1)\` paramétert használja a fizikai 1-es csatornához.

## Transzport és navigáció

| Fizikai gomb | CC | Művelet / Resolve-parancs |
| --- | ---: | --- |
| CYCLE | 54 | JOG ⇄ SHUTTLE mód |
| RETURN TO ZERO | 62 | \`⌘←\` |
| REW | 58 | \`J\` |
| FF | 59 | \`L\` |
| STOP | 63 | \`K\` |
| PLAY | 80 | \`Space\` — **megnyomásra PLAY, második megnyomásra STOP/PAUSE** (nincs előtte K) |
| nagy REC | 81 | \`⌘Z\` (Undo) |
| TRACK ◀ | 60 | \`↑\` (előző vágáspont) |
| TRACK ▶ | 61 | \`↓\` (következő vágáspont) |
| MARKER SET | 55 | \`V\`, nyomva tartva JOG TRIM |
| MARKER ◀ | 56 | \`,\` (−1 frame trim) |
| MARKER ▶ | 57 | \`.\` (+1 frame trim) |

**Fontos:** ezek a CC-k a felvett 28 lépéses Hammerspoon MIDI-napló alapján szerepelnek, nem feltétlenül intuitívak a Korg Editor grafikus elrendezésében. A betanító továbbra is megtartja a tényleges gombhoz eltárolt CC-ket.

## Nyolc csatorna — gombsorok

| Csatorna | MUTE (CC21–28) | SOLO (CC) | REC (CC38–45) | SELECT (CC46–53) |
| --- | --- | --- | --- | --- |
| 1 | CAM 1 \`1\` | 29 — szabad | 38 — szabad | Cut Page (46) |
| 2 | CAM 2 \`2\` | 30 — szabad | 39 — szabad | Edit Page (47) |
| 3 | CAM 3 \`3\` | 31 — szabad | 40 — szabad | Trim \`T\` (48) |
| 4 | CAM 4 \`4\` | 33 — szabad | 41 — szabad | Selection \`A\` (49) |
| 5 | In \`I\` | 34 — szabad | 42 — szabad | Deselect + \`⌘B\` (50) |
| 6 | Out \`O\` | 35 — szabad | 43 — szabad | szabad (51) |
| 7 | Clear In/Out \`⌥X\` | 36 — szabad | 44 — szabad | szabad (52) |
| 8 | Escape \`Esc\` | 37 — szabad | 45 — szabad | szabad (53) |

**CAM1–4** a Resolve megfelelő Cut/Sync Bin nézetében értelmezett kiválasztás; nem jelent automatikus *Source Overwrite*-ot. **SELECT 5** a kijelölést megszünteti, majd \`⌘B\`-t küld; a Resolve-ban engedélyezett, nem zárolt sávokra vonatkozik.

Az eddig kiosztatlan SOLO/REC/SELECT gombok nem hajtanak végre Resolve-műveletet, de **External LED** módban röviden világítanak lenyomva.

## Tekerők és tolópotméterek

| Csatorna | Forgó poti (CC) | Tolópotméter (CC) |
| --- | --- | --- |
| 1 | 13 — **szabad** | **2 — SHUTTLE** |
| 2 | 14 — szabad | 3 — szabad |
| 3 | 15 — szabad | 4 — szabad |
| 4 | 16 — szabad | 5 — szabad |
| 5 | 17 — szabad | 6 — szabad |
| 6 | 18 — szabad | 8 — szabad |
| 7 | 19 — szabad | 9 — szabad |
| 8 | 20 — szabad | 12 — szabad |

A \`szabad\` kezelőszerv MIDI-t küld, de a jelenlegi Lua nem rendelt hozzá Resolve-parancsot.

## External LED mód — Scene 1

A KORG KONTROL Editor **Scene 1 → Common → LED Mode = External** beállítást a Korgra is ki kell írni (*Communication → Write Scene Data*).

| LED | Visszajelzés |
| --- | --- |
| PLAY | az **utoljára Hammerspoonon keresztül kért** Play aktív → világít; újabb PLAY/STOP → kialszik |
| CYCLE | SHUTTLE aktív → világít; JOG aktív → kialszik |
| STOP, REW, FF, MUTE, SELECT, MARKER, SOLO, REC | **lenyomásra fel**, felengedésre le |
| NK menü → LED visszajelzés KI | mind a **44 ismert Scene 1 gomb LED-je kikapcsolva** |

**Az aktuális Resolve PLAY/PAUSE vagy kameraállapot NINCS API-ból lekérdezve.** Ha egérrel vagy a Resolve saját billentyűzetével módosítod, a PLAY LED nem feltétlenül a tényleges állapotot mutatja; ez *lokális parancs-visszajelzés*, nem valós idejű DAW feedback.

A LED-ek működéséhez a Hammerspoon a fizikailag 1-es MIDI-csatornát használja **kimeneten** (\`channel=1\`), nem a bejövő \`channel=0\` értéket. Más scene-ek szoftveres LED-vezérlése jelenleg nem része a kódnak.

## Rövid telepítés / próba

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git switch fix/clean-assignable-relearn
git pull --ff-only
sh ./install.command
~~~

Hammerspoon → Reload Config. A már **sikeresen eltárolt 28/28 kalibráció** megmarad, nincs szükség újbóli betanításra.

A duplikált Resolve-timeline-ban: **PLAY, PLAY, STOP; CYCLE kétszer; MUTE 1 lenyom/felenged; SELECT 1; SOLO 1**. Az NK menüben a *LED (Scene 1 External)* sor MIDI-kimeneti állapotot is mutat. A **LED visszajelzés BE/KI** menüponttal az összes ismert LED lenullázható.
