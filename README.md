# nanoKONTROL Studio → DaVinci Resolve 21 — CLEAN

**Kísérleti, egyszerű változat; a működő v1.2 továbbra is a main ágon marad.**
Nincs HUI/Mackie emuláció, nincs kimenő LED MIDI CC, nincs Resolve API-szinkron. Egyetlen 28 lépéses betanító a teljes Scene 1 kiosztáshoz.

## 0. Biztonsági mentés; gyári visszaállítás NEM kötelező

Mentsd a Korg teljes Scene Set és Global Data konfigurációját a KORG KONTROL Editorban. Ha az Editorban `Assignable` látszik, és a Scene 1 JOG Sign Magnitude/Const/CC82, illetve SLIDER 1 CC2 már be van állítva, **ne végezz felesleges factory resetet**.

**Csak szükség esetén**, a hivatalos nanoKONTROL Studio kézikönyv 17. oldala szerint:
1. Korg hátul → Standby.
2. Tartsd lenyomva: **SCENE + RETURN TO ZERO (`|◀`, a transzport legbaloldalibb gombja) + STOP**. **Nem** a TRACK ◀ gomb!
3. Kapcsold USB állásba, és várd meg a Scene gomb és az öt Scene LED villogásának végét. Ne kapcsold ki villogás alatt.

A reset a Korg hardverkonfigurációját felülírja. Hivatalos kézikönyv: https://cdn.korg.com/us/support/download/files/d66996c95d7d55be1aa119b8fbb88e71.pdf

## 1. Assignable Mode — nem HUI, nem Mackie

1. Korg → Standby.
2. **SCENE + CYCLE** együtt nyomva, majd USB bekapcsolás.
3. KORG KONTROL Editor:
   - Global Controller Mode = **Assignable**
   - **Scene 1 → LED Mode = Internal** (a kézikönyv Scene Parameters része, nem az Editor Global/Power Management nézete)
   - Scene 1, Global MIDI Channel = 1
   - JOG = **Sign Magnitude**, Acceleration = **Const**, CC 82
   - Minden betanítandó gomb: CC / **Momentary**, On 127 / Off 0
   - A bal első **tolópotméter** FADER 1 = CC 2; a bal első **tekerő** nem FADER 1.
4. Communication → Write Scene Data / Write Global Data a Korgra (mindig a megfelelő szerkesztett beállítást írd ki).
5. Teszthez maradj **Scene 1**-en, és ne használd párhuzamosan másik programban a HUI/Mackie control surface-t.

A Global ablakban látható **Use Scene Button as Scrub = Enable** csak DAW Mixer Control Mode-ban vonatkozik a Scrub funkcióra; Assignable-hez opcionálisan `Disable` lehet. **USB Auto LED Off** csökkenti a fényerőt inaktivitáskor; az **USB LED Illumination** díszkivilágítást kapcsol be tétlenség után. A díszkivilágítás elkerülésére azt állítsd `Disable`-re, ha zavar. Ezek **nem** a Scene 1 `LED Mode = Internal/External` beállításai.

A képernyőn látható Scene 1 fizikai kiosztásban: **első tolópotméter = CC2**, **első forgó poti = CC13**.

Korg hivatalos útmutató: https://support.korg.co.uk/en-US/using-the-nanokontrol-studio-with-logic-in-assignable-mode-405741

## 2. GitHub / Hammerspoon telepítés

Ellenőrizd, hogy tiszta-e a helyi repo:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git status --short
git fetch origin
git switch --track origin/fix/clean-assignable-relearn
sh ./install.command
~~~

Ha a helyi branch már létezik, használj: git switch fix/clean-assignable-relearn, git pull --ff-only, majd sh ./install.command.

Utána Hammerspoon → Reload Config. A telepítő menti a régi Lua-fájlt. A korábbi (eltérő verziójú) MIDI-kiosztás nem lesz használva, amíg a tiszta újratanítás végig nem ment.

## 3. TELJES 28 lépéses betanítás

NK menü → **TELJES UJRABETANITAS (28 lepes)**. A menüsor jelzi: NK SETUP 1/28. Az aktuális instrukciót Hammerspoon alert mutatja.

| Lépések | Korg vezérlő |
| --- | --- |
| 1–2 | JOG jobbra, majd balra |
| 3–14 | CYCLE; Return to Zero; REW; FF; STOP; PLAY; nagy REC; TRACK ◀; TRACK ▶; MARKER SET; MARKER ◀; MARKER ▶ |
| 15–18 | MUTE 1–4 (CAM 1–4) |
| 19–22 | MUTE 5–8 (IN / OUT / CLEAR / ESC) |
| 23–27 | SELECT 1–5 (Cut / Edit / Trim / Selection / Cmd+B Split) |
| **28** | **FADER 1, a legbaloldalibb TOLÓPOTMÉTER** teljesen le, majd teljesen fel |

A gomboknál a **lenyomás ÉS a felengedés** fejezi be a lépést. A poti/fader CC-jeleket nem tanulja meg gombként. Az utolsó lépésben **kizárólag CC 1:2** és szinte teljes 0–127 tartomány fogadható el, így nem csúszhat be helyette az első tekerő poti.

A mentett MIDI konfiguráció **csak a 28/28 sikeres lépés után** íródik felül. Megszakításkor semmi nincs félkészen elmentve.

## 4. Használat

- JOG tárcsa = képkockánkénti lépés. MARKER SET nyomva + JOG = szerkesztési pont ±1 frame.
- CYCLE = JOG/SHUTTLE.
- FADER 1 = önálló SHUTTLE ±4 J/K/L sebességfokozat. 60–68 középen STOP. Indulás/STOP után **előbb középre kell húzni**, csak aztán aktív.
- SELECT 1/2 = Cut/Edit; SELECT 5 = Cmd+Shift+A, majd Cmd+B Split az aktív, szerkeszthető sávokon.
- MUTE 1–4 = CAM 1–4, csak a megfelelő Resolve nézetben.
- LED-eket csak a Korg **Internal** módja kezeli; nincs kimenő MIDI LED-parancs.
- Duplikált ATEM ISO timeline-on tesztelj.

## 5. Nincs több millió menüpont

Az NK menüben csak csatlakozás/státusz, egyetlen teljes betanítás, megszakítás és vezérlés BE/KI maradt. Betanítás alatt az utolsó bejövő CC is látható.

### Visszaállítás

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git switch main
sh ./install.command
~~~

Hammerspoon Reload Config. A main v1.2 nem érti az új setupVersion=2 kulcsot; ha azzal folytatod, régi 26 lépéses tanítás vagy a korábbi Lua/Hammerspoon backup visszaállítása szükséges. A Korg saját mentett Scene Set/Global Data fájljaiból bármikor visszatölthető a korábbi hardverkonfiguráció.

**Ez a változat csak Scene 1 / Assignable Mode-hoz készült.** Resolve API, Fairlight MCU/HUI és az öt scene kezelése nem része ennek a diagnosztikai, tiszta verziónak.
