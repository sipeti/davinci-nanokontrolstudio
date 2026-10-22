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
1. A **SCENE 1** legyen kiválasztva. A Hammerspoon NK menüben kattints **FADER 1 SHUTTLE betanitasa (2 MIDI ertek)**. Mozgasd csak az első fadert legalább 5 egységgel. Ha másik kezelőt érintettél, szakítsd meg és kezdd újra.
2. Nyisd meg a Resolve-ot, azon belül egy duplikált timeline-t. Húzd a FADER 1-et középre, ahol az NK menüben a MIDI-érték **60–68**. Ekkor **READY** lesz; az előző, szélső faderállás önmagában nem indíthat lejátszást.
3. Középről felfelé tolva **+1…+4** sebességfokozat, lefelé **−1…−4**. Középen **STOP**, a fizikai STOP mindig elsőbbséget élvez.
4. A nagy tárcsa továbbra is JOG, de **aktív faderes lejátszás közben** a JOG-ot a program biztonsági okból figyelmen kívül hagyja. A rendes JOG-hoz előbb húzd középre a fadert. A CYCLE-os régi JOG/SHUTTLE mód megmarad.
5. STOP, CYCLE vagy másik transport parancs után a fader újra csak középre visszahúzás után indulhat. Az NK menü és menüsor visszajelzi a legutóbbi beállított fokozatot.

**Fontos:** a Korg fadere nem rugós; a közép-STOP csak akkor következik be, amikor ténylegesen középre húzod. A Resolve sebessége a J/K/L billentyűzetparancsain múlik, nem közvetlen idővonal-sebesség API-n.

## 3. LED próba (csak ezután)
1. KORG KONTROL Editor **Global → LED Mode = External**, majd küldd fel az új **Global Data** beállítást a Korgra (a Communication menüben).
2. NK menüben **LED kimenet teszt (MUTE 1, 700ms)**. Elvárt: MUTE 1 LED kb. 0,7 másodpercig világít, majd kialszik.
3. NK menüben **LED feedback BE/KI**. Ezután nyomd meg a Korgon a **MUTE 1–4**, **SELECT 1/2**, **PLAY / STOP / REW / FF** és **CYCLE** gombokat.
4. MUTE: a legutóbb kiválasztott CAM 1–4 LED-je világít. SELECT 1/2: a legutóbb **sikeresen kért** Cut/Edit váltás LED-je. PLAY/STOP/REW/FF: a legutóbbi Korg-transportkérés LED-je. CYCLE: SHUTTLE módban világít, JOG-ban kialszik.
5. **MARKER SET** nyomva tartva LED ON, elengedve OFF. A nagy REC (Undo) és SELECT 5 (⌘B) rövid ACK-villanást ad, amennyiben a gombnak van megfelelő vezérelhető LED-je.
6. A Korg **External** módban scene-váltáskor minden LED-et lekapcsolhat. Scene 1-be visszatérés után válaszd az NK menüben a **LED allapot frissitese (Scene 1)** pontot.

A LED-ek **nem olvassák ki a Resolve tényleges állapotát**. Ha a Resolve-ban egérrel váltasz kamerát, oldalakat, playt vagy trim módot, az NK LED-je a legutóbbi Korg-parancsot mutatja, nem feltétlenül az aktuális valóságot.

## 4. Visszaállítás

A teszt befejezése után, ha a stabil v1.2-t szeretnéd:
```sh
git switch main
sh ./install.command
```
Majd Hammerspoon → Reload Config. A KORG KONTROL Editorban állítsd vissza a mentett **Global Data** beállításokat, különösen **LED Mode = Internal**, ha nem szeretnéd a szoftveres LED-vezérlést. A kiegészítő fader-binding a Hammerspoon beállításokban maradhat; a v1.2 egyszerűen nem használja.

## Hibakeresés
- Nincs LED: ellenőrizd External mód, jelenlegi Scene 1, megfelelő CC/note-kiosztás, a Korg `On Value=127 / Off Value=0` alapértékei, valamint USB-MIDI kimenet.
- FADER 1 nem indul: nézd meg az NK menüben a betanított `cc:1:...` értéket, húzd egyszer középre, és figyeld a READY jelzést. Ha nincs 60–68 közötti MIDI-érték, fizikailag keresd meg a középállást és mozgasd lassan.
- Másik scene-ben is ugyanaz történik: a jelenlegi verzió nem tudja az 5 scene-t önállóan azonosítani, ezért **jelenleg csak Scene 1-en tesztelj**.
- FADER 1 után JOG nem léptet: aktív faderes shuttle mellett szándékosan tiltott; középen újra működik.
- Ha bizonytalan vagy: STOP, NK → vezérlés szüneteltetése, majd helyreállítás.
