# v1.3 draft — FADER 1 shuttle + LED-visszajelzés: hardverpróba

**Állapot:** PR #1, kísérleti változat. A `main` továbbra is a működő v1.2. A Scene 1-re készült, nincs hardveres scene-állapot-szinkron vagy Fairlight mixer.

## 0. Biztonsági mentés
- KORG KONTROL Editor: olvasd be és mentsd le a jelenlegi **Scene Set** (`.nktrl_st_set`) és **Global Data** (`.nktrl_st_glob`) beállításokat.
- Resolve: duplikált ATEM ISO timeline-on tesztelj.
- Hammerspoon telepítő a korábbi `~/.hammerspoon/nanokontrol_resolve21.lua` fájlról időbélyeges backupot készít. A mentett `nanokontrol_studio_resolve21_v1` MIDI-gombhozzárendeléseket megtartja.

## 1. Telepítés GitHub-ról
A repository munkakönyvtárában, **tiszta worktree** mellett:
```sh
git fetch origin
git switch --track origin/design/scenes-led-feedback-probe
sh ./install.command
```
Ha már létezik a helyi `design/scenes-led-feedback-probe` branch, arra válts és `git pull --ff-only`. **Nem** kell teljes, 26 lépéses újrakalibrálás. Hammerspoon → Reload Config.

## 2. FADER 1 teszt (LED Mode maradhat Internal)
1. A **SCENE 1** legyen kiválasztva. A Hammerspoon NK menüben kattints **FADER 1 SHUTTLE betanitasa (2 MIDI ertek)**. A menüsorban **NK LEARN F1** jelenik meg. Húzd végig az első fadert, és nézd az **Utolso MIDI** és **MIDI bejovo** sorokat a menüben: az első két *különböző*, ugyanahhoz a CC-hez tartozó értékre megtörténik a kalibráció. A korábbi 5 egységes küszöböt kivettük. Ha nem jelenik meg CC, nem érkezik MIDI a betanítóhoz; ne kezdd újra a teljes gombkiosztást. Ha másik kezelőt mozdítottál meg, szakítsd meg és kezdd újra.
2. Nyisd meg a Resolve-ot, azon belül egy duplikált timeline-t. Húzd a FADER 1-et középre, ahol az NK menüben a MIDI-érték **60–68**. Ekkor **READY** lesz; az előző, szélső faderállás önmagában nem indíthat lejátszást.
3. Középről felfelé tolva **+1…+4** sebességfokozat, lefelé **−1…−4**. Középen **STOP**, a fizikai STOP mindig elsőbbséget élvez.
4. A nagy tárcsa továbbra is JOG, de **aktív faderes lejátszás közben** a JOG-ot a program biztonsági okból figyelmen kívül hagyja. A rendes JOG-hoz előbb húzd középre a fadert. A CYCLE-os régi JOG/SHUTTLE mód megmarad.
5. STOP, CYCLE vagy másik transport parancs után a fader újra csak középre visszahúzás után indulhat. Az NK menü és menüsor visszajelzi a legutóbbi beállított fokozatot.

**Fontos:** a Korg fadere nem rugós; a közép-STOP csak akkor következik be, amikor ténylegesen középre húzod. A Resolve sebessége a J/K/L billentyűzetparancsain múlik, nem közvetlen idővonal-sebesség API-n.

## 3. LED próba (csak ezután)
1. KORG KONTROL Editor **Global → LED Mode = External**, majd küldd fel az új **Global Data** beállítást a Korgra (a Communication menüben).
2. NK menüben **LED kimenet teszt (MUTE 1, 700ms)**. Elvárt: MUTE 1 LED kb. 0,7 másodpercig világít, majd kialszik.
3. NK menüben **LED feedback BE/KI**. Ezután nyomd meg a Korgon a **MUTE 1–4**, **SELECT 1/2**, **PLAY / STOP / REW / FF** és **CYCLE** gombokat.
4. **Nem hagyunk beragadt "last requested" LED-eket.** MUTE 1–4 / PLAY / STOP / REW / FF a fizikai lenyomás alatt világít, elengedésre kialszik. SELECT 1/2 alapból ugyanígy működik. Csak a **Resolve API-ból ellenőrzött Cut/Edit oldal** maradhat világítva, ha bekapcsolod az API-szinkront (lásd 4. fejezet). A CYCLE nyomására sem marad tartósan bekapcsolva az LED; az aktuális JOG/SHUTTLE mód az NK menüsorban látható.
5. **MARKER SET** nyomva tartva LED ON, elengedve OFF. A nagy REC (Undo) és SELECT 5 (⌘B) rövid ACK-villanást ad, amennyiben a gombnak van megfelelő vezérelhető LED-je.
6. A Korg **External** módban scene-váltáskor minden LED-et lekapcsolhat. Scene 1-be visszatérés után válaszd az NK menüben a **LED allapot frissitese (Scene 1)** pontot.

A LED-ek **nem állítanak ellenőrizetlen Resolve-állapotot**. A kameraválasztás és transport csak fizikai gomb-ACK (momentary). A Cut/Edit page LED opcionálisan a Resolve API-val ellenőrzött tény lehet. Ez a bridge nem tudja leolvasni a Play/Stop állapotot vagy a Sync Bin aktuális kameráját.

### 3a. Beragadt LED-ek azonnali törlése
NK → **MINDEN LED KIKAPCSOLASA (reset)**. Ez akkor is elérhető, ha a szoftveres LED-feedback korábban kikapcsolt, de a Korgon megmaradt a LED állapota. Global LED Mode: External szükséges. A Hammerspoon újratöltése az ismert LED-eket ugyancsak kioltja.

## 4. Resolve 21.1 API — valódi Cut/Edit visszajelzés, csak olvasás

1. DaVinci Resolve **Studio** → Preferences → System → General → **External scripting using = Local**. Soha nem kell Network módot választani.
2. A v1.3 kísérleti frissítés telepíti a `~/.hammerspoon/resolve_status.py` segédet. A Resolve 21.1 beépített `ResolvePython` interpreterével kommunikál; nem telepít Python-csomagot. Ha régebbi Resolve-verziód vagy eltérő alkalmazásútvonalad van, az NK menü megmutatja a hiba okát.
3. NK → **Resolve allapot lekerese MOST (csak olvasas)**. Nyisd meg újra az NK menüt: a **Resolve API sync** sorban `page=cut/edit/color/... TC=...` kell látszódjon; csak sikeres válasz után engedjük meg a tartós SELECT 1/2 page LED-et.
4. Ha az egyszeri próba működik: NK → **Resolve API status sync 3mp BE/KI**. Aktív Resolve-ablaknál, 3 másodpercenként frissíti az oldalt és timecode-ot; csak olvas, nem módosít projektet, sávot vagy playheadet. A poll alapértelmezés szerint **KI** van.
5. Ha a lekérdezés `not_connected`: ellenőrizd a Studio/Local beállítást, a Resolve futását és a projekt betöltését. Ha `ResolvePython hianyzik`, a telepített Resolve 21.1+ interpreter helye eltér a dokumentált macOS útvonaltól; nem indul alternatív, bizonytalan parancs automatikusan.


## 5. Visszaállítás

A teszt befejezése után, ha a stabil v1.2-t szeretnéd:
```sh
git switch main
sh ./install.command
```
Majd Hammerspoon → Reload Config. A KORG KONTROL Editorban állítsd vissza a mentett **Global Data** beállításokat, különösen **LED Mode = Internal**, ha nem szeretnéd a szoftveres LED-vezérlést. A kiegészítő fader-binding a Hammerspoon beállításokban maradhat; a v1.2 egyszerűen nem használja.

## 6. Hibakeresés
- Nincs LED: ellenőrizd External mód, jelenlegi Scene 1, megfelelő CC/note-kiosztás, a Korg `On Value=127 / Off Value=0` alapértékei, valamint USB-MIDI kimenet.
- **FADER 1 menüpont után semmi:** elvárt az `NK LEARN F1` státusz, majd az `Utolso MIDI` sor változása fader mozgatásakor. Ha a bemenő MIDI számláló sem nő, ellenőrizd a Korg Scene 1 / Assignable Mode-ot és Hammerspoon MIDI inputot. A mentett Scene Set alapján a fader jelénél először `cc:1:2` értéket keresünk, de a tényleges beérkező MIDI jel dönt.
- **LED gombnyomás után ég:** ellenőrizd, hogy már az új kód fut-e, használd `NK → MINDEN LED KIKAPCSOLASA`, és hogy a Korg gombjai `Momentary`, nem `Toggle` módban vannak.
- FADER 1 nem indul: nézd meg az NK menüben a betanított `cc:1:...` értéket, húzd egyszer középre, és figyeld a READY jelzést. Ha nincs 60–68 közötti MIDI-érték, fizikailag keresd meg a középállást és mozgasd lassan.
- Másik scene-ben is ugyanaz történik: a jelenlegi verzió nem tudja az 5 scene-t önállóan azonosítani, ezért **jelenleg csak Scene 1-en tesztelj**.
- FADER 1 után JOG nem léptet: aktív faderes shuttle mellett szándékosan tiltott; középen újra működik.
- Ha bizonytalan vagy: STOP, NK → vezérlés szüneteltetése, majd helyreállítás.
