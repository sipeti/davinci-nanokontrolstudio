# nanoKONTROL Studio — DaVinci Resolve 21 vezérlő / Scene 1

**Állapot:** aktuális \`fix/clean-assignable-relearn\` (draft PR #2). A 2026-10-23-i Hammerspoon MIDI-napló és a 28 lépéses Lua-betanítási sorrend alapján. A lent felsorolt gombfunkciók **a szoftveres hozzárendelések**; a tényleges elmentett \`hs.settings\` a Korgon végzett legutolsó 28/28 sikeres betanítást követi. Az ismert CC-ket nem kell minden alkalommal újratanítani.

## Alap

| Korg kezelőszerv | MIDI / fizikai Scene 1 | DaVinci Resolve |
| --- | --- | --- |
| JOG CW / CCW | CC82, Sign Magnitude 1–64 / 65–127 | egy frame előre / vissza |
| JOG, CYCLE után | ugyanaz a CC82 | SHUTTLE −4…+4, 1 MIDI impulzus = 1 fokozat |
| MARKER SET + JOG | CC55 nyomva + CC82 | \`V\`, majd \`,\` / \`.\` (kijelölt vágáspont finomítása) |
| FADER 1 (bal szélső **tolópotméter**) | CC2, 0–127 | középállásos SHUTTLE, ±4 fokozat; 60–68 = STOP |
| SCENE | hardveres, körkörös 1→2→3→4→5 | A scene-váltást a hardver intézi; a PLAY/CYCLE LED-et a szoftver fél másodpercenként szinkronizálja |

A MIDI-csatorna a Korg Editorban `1`, a Hammerspoon **bemenetén** `channel=0`. A 2026-10-23-i valós LED-próba alapján a **kimeneten** is `sendCommand(..., channel=0)` működik, de ott ez a Hammerspoon dokumentációjában *minden csatornás küldés*; `channel=1` API-szinten sikerült, de a fizikai LED nem villant fel.

## Az öt scene közös transzportja

A Korg mentésben mind az öt scene **ugyanazokat a fizikai transport CC-ket** tartalmazza, csak a MIDI-csatorna változik:

| Scene | MIDI bemeneti csatorna Hammerspoonban | Fix közös kezelőszervek |
| --- | ---: | --- |
| 1 | 0 | PLAY, STOP, REW, FF, Return to Zero, CYCLE, TRACK ◀/▶ |
| 2 | 1 | ugyanaz |
| 3 | 2 | ugyanaz |
| 4 | 3 | ugyanaz |
| 5 | 4 | ugyanaz |

A MODE (CYCLE) a Hammerspoon teljes kontrollerállapota, **nem jelenetenként külön mód**. A Scene 2–5 JOG-tárcsája a mentésben eltérő, Continuous/CC86 beállítású; ezeket a jelenlegi Lua **nem** kezeli JOG-ként. Az összes MUTE/SOLO/REC/SELECT/KNOB/FADER akció Scene 1-specifikus marad, kivéve a fenti fizikai transzportgombokat.

**Scene-váltás közben PLAY tovább fut**; SCENE lenyomására nem küldünk STOP-ot és nem változtatjuk a Resolve állapotát. A Korg helyi LED-memóriája scene-váltáskor törlődhet; ezért a Hammerspoon fél másodpercenként újraküldi a PLAY (CC80) és CYCLE (CC54) pillanatnyi **lokális** LED-állapotát a hardverpróbán működő output channel=0 (all-channel broadcast) paraméterrel, a deduplikációt szándékosan megkerülve. Ez nem küld Resolve-billentyűparancsokat.

A PLAY/CYCLE visszajelzés csak azokban a scene-ekben lesz fizikailag látható, amelyeket a KORG KONTROL Editorban External LED módra állítottál, és **Write Scene Data** paranccsal ki is írtál a készülékre. A legutóbb elemzett mentésben Scene 1–2 External és Scene 3–5 Internal volt.

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
| PLAY (CC80) | Világít minden mozgó lejátszásnál: PLAY/Space, REW/FF, SHUTTLE/JOG és FADER ±1…±4 |
| STOP (CC63) | Megálláskor **folyamatosan világít**, felengedés után is; következő lejátszáskor kialszik |
| REW (CC58) | Visszafelé mozgásnál **világít** a PLAY mellett, pl. J vagy SHUTTLE −1…−4 |
| FF (CC59) | Előrefelé SHUTTLE/FF-nél **világít** a PLAY mellett, pl. L vagy SHUTTLE +1…+4 |
| CYCLE (CC54) | SHUTTLE mód aktív → világít; JOG mód → kialszik |
| MUTE, SELECT, MARKER, SOLO, REC és egyéb gombok | **Lenyomásra fel**, felengedésre le |
| NK menü → LED visszajelzés KI | mind a **44 ismert Scene 1 gomb LED-je kikapcsolva** |

**Az aktuális Resolve PLAY/PAUSE vagy kameraállapot NINCS API-ból lekérdezve.** A Resolve előtérben történő **fizikai SPACE/J/K/L billentyűket** a Hammerspoon figyeli, módosítók és billentyűismétlés nélkül, és továbbengedi a Resolve felé. A Korg saját szimulált J/K/L/Space eseményeit rövid védőablak kizárja a dupla számolásból. A transzport-led visszajelzés scene-váltás után fél másodpercen belül helyreállítódhat a PLAY/STOP/REW/FF/CYCLE újraküldésétől. A betöltéskor még ismeretlen állapot esetén **egyik transzport LED sem világít**, amíg nem láttunk parancsot. **Egérrel indított lejátszás, eltérő shortcut vagy már futó Resolve playback újratöltéskor továbbra sem detektálható** ebből; ez *megfigyelt parancsok alapján becsült helyi állapot*, nem valós idejű DAW feedback.

**A készüléken kipróbált kimenet: `channel=0` (broadcast).** A Hammerspoon `channel=1` üzenete nem világította a MUTE 1 LED-et, a `channel=0` viszont igen. A PLAY és CYCLE LED-állapot mind az öt scene között közös; a **nem transzport** gombok Resolve-funkciói Scene 1-re korlátozódnak.

## Rövid telepítés / próba

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git switch fix/clean-assignable-relearn
git pull --ff-only
sh ./install.command
~~~

Hammerspoon → Reload Config. A már **sikeresen eltárolt 28/28 kalibráció** megmarad, nincs szükség újbóli betanításra.

A duplikált Resolve-timeline-ban: **PLAY, PLAY, STOP; CYCLE kétszer; MUTE 1 lenyom/felenged; SELECT 1; SOLO 1**. Az NK menüben a *LED (Scene 1 External)* sor MIDI-kimeneti állapotot is mutat. A **LED visszajelzés BE/KI** menüponttal az összes ismert LED lenullázható.
