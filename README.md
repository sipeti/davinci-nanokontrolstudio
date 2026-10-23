# nanoKONTROL Studio → DaVinci Resolve 21 — CLEAN

**Kísérleti, egyszerű változat; a működő v1.2 továbbra is a main ágon marad.**
Nincs HUI/Mackie emuláció és nincs Resolve API-szinkron. **Scene 1 External LED módhoz Hammerspoon MIDI-visszajelzés** és **PLAY/PLAY toggle** működés van; a teljes kiosztást egy 28 lépéses betanító állítja be.

**Teljes gomb/CC/poti/fader térkép: [docs/CONTROL_MAP.md](docs/CONTROL_MAP.md).**

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
   - **Scene 1 → LED Mode = External** (Scene 1 → Common, nem az Editor Global/Power Management nézete); utána **Write Scene Data**
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

**JOG kalibráció:** Sign Magnitude esetén CC82 / 1–64 = jobbra, CC82 / 65–127 = balra. Ha a 2/28-as lépés nem lép tovább, az NK menüben nézd az **utolsó MIDI** sort. Ha `cc:0:86` vagy `cc:0:82=1..64` érkezik balra tekerésre, akkor a fizikai eszköz konfigurációját kell ellenőrizni. A `KORG KONTROL Editor` megjelenített beállítása önmagában nem azonos a készülékben tárolt állapottal: **Communication → Write Scene Data**, megerősítés, majd új próba. A frissített betanító már **nem engedi tovább a CC86-ot az 1/28 lépésnél**, és egyszeri figyelmeztetést mutat a nem megfelelő MIDI-kódra.

A gomboknál a **lenyomás ÉS a felengedés** fejezi be a lépést. A poti/fader CC-jeleket nem tanulja meg gombként. Az utolsó lépésben **kizárólag a JOG-gal azonos MIDI-csatornájú CC2-t** (Hammerspoonban általában `cc:0:2`) és szinte teljes 0–127 tartományt fogadható el, így nem csúszhat be helyette az első tekerő poti.

A mentett MIDI konfiguráció **csak a 28/28 sikeres lépés után** íródik felül. Megszakításkor semmi nincs félkészen elmentve.

## 4. Használat

- JOG tárcsa = képkockánkénti lépés. MARKER SET nyomva + JOG = szerkesztési pont ±1 frame.
- CYCLE = JOG/SHUTTLE. **Wheel SHUTTLE: egy CC82 impulzus = egy fokozat**; a program a 45 ms-on belüli gyors tekerést összevonja, így nem indít minden impulzusra új STOP/J/L sorozatot. ±4 fokozat; a STOP bármikor megállítja. A JOG 1 impulzus = 1 frame változatlan.
- FADER 1 = önálló SHUTTLE ±4 J/K/L sebességfokozat. 60–68 középen STOP. Indulás/STOP után **előbb középre kell húzni**, csak aztán aktív.
- SELECT 1/2 = Cut/Edit; SELECT 5 = Cmd+Shift+A, majd Cmd+B Split az aktív, szerkeszthető sávokon.
- MUTE 1–4 = CAM 1–4, csak a megfelelő Resolve nézetben.
- PLAY = `Space`: **első megnyomás lejátszás, második megnyomás pause/stop**. Nem küld előtte `K`-t.
- **External LED-ek:** PLAY világít, ha a Hammerspoon utoljára Play-t kért; CYCLE világít SHUTTLE módban; minden más gomb nyomva világít és felengedve kialszik. A Hammerspoon nem olvassa a Resolve tényleges playback/Sync Bin kameraállapotát, ezért ez **lokális kérést jelző**, nem hiteles Resolve-állapot.
- **LED menü:** `LED visszajelzes BE/KI`; KI állásban az összes ismert Scene 1 LED-et kikapcsolja. A LED-kimenet fizikai MIDI Channel 1 (`hs.midi.sendCommand(channel=1)`); a Hammerspoon bemeneti csatornaértéke `0`.
- Duplikált ATEM ISO timeline-on tesztelj.


**Érzékenységfrissítés a sikeres 28/28 betanítás után:** nem kell újrakalibrálni a Korgot vagy a Hammerspoon MIDI-kiosztást. Elég a branchen `git pull --ff-only && sh ./install.command`, majd Hammerspoon → Reload Config. A korábbi `setupVersion=2` mentés megmarad.

## 5. Nincs több millió menüpont

Az NK menüben csatlakozás/státusz, teljes betanítás, megszakítás, vezérlés BE/KI és **egyetlen LED BE/KI kapcsoló** van. Betanítás alatt az utolsó bejövő CC is látható. A LED-kapcsoló KI állásban nullázza a 44 ismert Scene 1 gomb LED-jét.

**Teljes MIDI-napló:** Hammerspoon menüsor ikon → **Console** (vagy Hammerspoon Console megnyitása). A 28 lépéses betanítás alatt **minden MIDI-esemény** automatikusan megjelenik például így:

~~~text
[NK MIDI] step=2/28 type=controlChange channel=0 controller=cc:0:86 value=61 delta=-4 raw=B0 56 3D
~~~

A `channel=0` Hammerspoonban az **1-es fizikai MIDI-csatorna**, a `controller=cc:0:86` a Continuous JOG. A `delta` csak az adott vezérlő **előző** értékéhez képesti különbség (pozitív = növekedett, negatív = csökkent). A Sign Magnitude JOG a `cc:0:82` vezérlőn küld 1–64 / 65–127 értékeket. A naplózás kizárólag a betanító alatt aktív: normál vágás közben nincs MIDI-spam. A Hammerspoon Console egy valódi ablak, nem kell hozzá külön menüpontot készíteni.

### Ha External módban egyetlen LED sem világít

1. Ellenőrizd a KORG KONTROL Editorban: **Scene 1 → LED Mode = External**; utána **Communication → Write Scene Data**. A Korg Editor bezárható. A Scene 1 aktív legyen.
2. GitHub frissítés + telepítés + Hammerspoon Reload Config után nyisd meg a **Hammerspoon → Console** ablakot.
3. Illeszd be **egyetlen parancsként** (nem kell újratanítás, új menü vagy Resolve):

~~~lua
require("nanokontrol_resolve21").ledProbe()
~~~

4. Figyeld a **MUTE 1 LED-et**: előbb 1,5 másodpercig az **1-es MIDI-csatornán** próbál világítani, majd rövid szünet után 1,5 másodpercig **0 = összes csatorna** küldéssel. A kód automatikusan elküldi a kikapcsoló üzeneteket is.
5. Küldd el a Console \`[NK LED PROBE]\` sorait, és írd meg, hogy **első / második / egyik sem** próbán felvillant-e a LED.

**Értelmezés:** ha az első felvillan, a fizikai MIDI output jó a helyes 1-es csatornán, és a rendes MIDI callback/LED mappingot kell vizsgálni. Ha csak a második, csatornaeltérést vagy a Korg csatornabeállítását kell felülvizsgálni. Ha a sendCommand \`pcall=false\` vagy \`result=false\`, a Hammerspoon kimeneti eszközének elérhetőségét vizsgáljuk. Ha \`result=true\`, de egyik LED sem világít, az **csak API-szintű elfogadás**, nem a LED hardverének visszaigazolása: a Korg Scene 1 valódi External/Write állapotát és a MIDI-output útvonalat kell ellenőrizni.

A teszt nem küld Resolve billentyűket, nem nyúl a kalibrációhoz, és nem ír a Korg konfigurációjába.

### Visszaállítás

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git switch main
sh ./install.command
~~~

Hammerspoon Reload Config. A main v1.2 nem érti az új setupVersion=2 kulcsot; ha azzal folytatod, régi 26 lépéses tanítás vagy a korábbi Lua/Hammerspoon backup visszaállítása szükséges. A Korg saját mentett Scene Set/Global Data fájljaiból bármikor visszatölthető a korábbi hardverkonfiguráció.

**Ez a változat csak Scene 1 / Assignable Mode-hoz készült.** Resolve API, Fairlight MCU/HUI és az öt scene kezelése nem része ennek a diagnosztikai, tiszta verziónak.
