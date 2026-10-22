# KORG nanoKONTROL Studio -> DaVinci Resolve 21 — ATEM ISO Edition v1.2

**macOS / Hammerspoon / USB MIDI — frissítés a működő v1.1-re**

## Telepítés GitHub-ról

```sh
git clone https://github.com/sipeti/davinci-nanokontrolstudio.git
cd davinci-nanokontrolstudio
sh ./install.command
```

Frissítéskor a repó könyvtárában: `git pull --ff-only && sh ./install.command`, majd Hammerspoon → Reload Config. A telepítő mentést készít az előző Lua-fájlról, és megőrzi a MIDI-betanítást.

**A repository kezdeti állapota a korábban tesztelt v1.2 csomag.** Új fejlesztésekhez külön branchet és pull requestet használunk.

## Mi az új?

1. **JOG-trim a MARKER SET nyomva tartásával.** Ha csak forgatod a nagy kereket, a lejátszófej lépked (`←/→`). Ha **nyomva tartod a MARKER SET-et és forgatod a kereket**, a kijelölt editpontot nudgolja 1-1 képkockával (`,`/`.`). Amikor elengeded a MARKER SET-et, visszaáll az eredeti JOG/SHUTTLE. A MARKER SET lenyomásakor a `V` parancs kiválasztja a közeli editpontot. A `MARKER ◀/▶` továbbra is használható 1 képkockás finomításhoz.
2. **SELECT 5 = minden engedélyezett, szerkeszthető sáv kettévágása a lejátszófejnél.** Először `⌘⇧A` (kijelölés megszüntetése), majd `⌘B` (Split Clip). Így egy korábban véletlenül kijelölt klip nem korlátozza a műveletet. **A lezárt és a nem célzott/tiltott sávokat nem oldjuk fel, illetve nem kapcsoljuk be.** Ellenőrizd a Resolve track target/destination kapcsolóit. Elsősorban az **Edit Page**-en használd, a timeline-ra fókuszálva.
3. **SELECT 5 egyszeri, külön betanítása.** Nem kell újrakalibrálni a meglévő 24 gombot és jogot. A program továbbra is a `nanokontrol_studio_resolve21_v1` Hammerspoon-beállításkulcsot használja, így minden korábbi MIDI-kiosztás megmarad.
4. Az NK menüben az Accessibility jogosultság státusza is megjelenik. A program **nem küld ⌘B-t, ha ez hiányzik.**

## Frissítés v1.1-ről: 4 lépés

1. **Hammerspoon Accessibility:** a beküldött képen piros volt: `WARNING! Accessibility is not enabled!`. Nyisd meg a **System Settings → Privacy & Security → Accessibility** részt; a **Hammerspoon** mellett kapcsold be az engedélyt. Ha már be van kapcsolva, de a Hammerspoon továbbra is `WARNING`-ot ír, zárd be teljesen és indítsd újra a Hammerspoont. Ezt az **NK → Hammerspoon Accessibility: OK** sorral is ellenőrizheted.
2. A klónozott repository könyvtárában futtasd:

   ```sh
   sh ./install.command
   ```

   A telepítő menti a korábbi `~/.hammerspoon/nanokontrol_resolve21.lua` állományt (időbélyeges `.backup.*`), majd frissíti. A meglévő `~/.hammerspoon/init.lua` beállításokat és a mentett MIDI-gombokat megtartja; ha kell, egyszer szúrja be a `require("nanokontrol_resolve21")` sort.
3. Hammerspoon menüsorikon → **Reload Config**. Az NK menüben válaszd: **SELECT 5 (Cmd+B) egyszeri betanítása**, majd **egyszer nyomd meg a Korg SELECT 5** gombját. A menü visszajelzi, hogy beállítva. Fontos: **ne az „Újrakalibrálás (26 lépés)” menüpontot** válaszd! Az csak a teljes, eredeti kiosztás újrafelvételéhez kell.
4. Nyiss egy **duplikált ATEM ISO timeline-t**, válts az Edit Page-re, és próbáld ki a lenti mintát.

**KORG KONTROL Editorban nem kell semmit újraírni**, ha a korábbi v1.1-hez már `Jog Wheel Type = Sign Magnitude`, `Acceleration = Const`, `Jog CC = 82`, `MARKER SET Button Behavior = Momentary` beállításod van. A **Momentary** feltétel fontos: lenyomás `127`, felengedés `0`; Toggle üzemmóddal nem működik a nyomva-tartós trim.

## Működés és teszt

| Korg | Funkció | Resolve |
| --- | --- | --- |
| JOG tekerése önmagában | lejátszófej ±1 frame / MIDI-impulzus | `← / →` |
| MARKER SET lenyomása | editpont kijelölése, TRIM aktív, amíg nyomod | `V` |
| MARKER SET nyomva + JOG tekerés | editpont eltolása balra/jobbra | `, / .` |
| MARKER SET felengedése | JOG/SHUTTLE visszaállítása | nincs új parancs |
| MARKER ◀/▶ | editpont ±1 frame | `, / .` |
| SELECT 5 **(új)** | kijelölés törlése, majd vágás a megcélzott sávokon | `⌘⇧A` → `⌘B` |
| TRACK ◀/▶ | előző / következő editpont | `↑ / ↓` |
| SELECT 1/2 | Cut / Edit Page | Workspace natív menü |
| SELECT 3/4 | Trim / Selection mód | `T / A` |
| CYCLE | JOG ↔ SHUTTLE | `K` és üzemmódváltás |
| PLAY, STOP, REW, FF | transzport | `Space, K, J, L` |
| nagy REC | Undo | `⌘Z` |
| MUTE 1–4 | CAM 1–4, megfelelő Sync Bin/multicam nézetben | `1`–`4` |

A korábbi 24 gomb többi kiosztása, a Cut/Edit menüváltás, a 65 ms-os SHUTTLE csoportosítás, a CC82 automatikus migráció és a kamera-funkciók **változatlanok**.

### Kameraváltás időpontjának javítása

1. **SELECT 2** → Edit Page. **TRACK ◀/▶** → a rossz vágás közelébe.
2. Ha kell, **SELECT 3** → Trim mód. **Nyomd le és tartsd nyomva MARKER SET-et**: a `V` kijelöli a legközelebbi szerkesztési pontot, a menüsor `NK TRIM`-re vált.
3. Ellenőrizd, hogy a kijelölt **videoeditpont kétoldalas, középső (Roll)** része aktív. Enélkül a Resolve Ripple Trim-et, vagy akár klipmozgatást is végezhet. A kiválasztott oldal `U`-val módosítható, ha szükséges.
4. **Forgasd a JOG-ot**. Jobbra `.` (előre), balra `,` (vissza), egy MIDI-impulzusra egy billentyűparancs. A trim sebessége így a kerék által ténylegesen küldött impulzusoktól is függ.
5. **Engedd el a MARKER SET-et**: a kijelző `NK JOG` (vagy ha előtte SHUTTLE-ben voltál, `NK SHUTTLE`) lesz. Visszanézés, szükség esetén **REC** → Undo.

### Felesleges rész kivágása a műsorból

1. A **normál JOG-gal** állj a kihagyandó rész elejére.
2. **SELECT 5** → vágás a megcélzott, nem zárolt videosávokon és hangsávokon.
3. JOG-gal keresd meg a kihagyandó rész végét, majd **SELECT 5** újra.
4. Ellenőrizd a két vágáspontot és a hangot. Jelöld ki a középső tartományt az érintett sávokon, majd a Resolve-ban végezz megfelelő törlést / ripple delete-et. A **SELECT 5 önmagában nem töröl és nem ripple-el**, csak szétvág.

**Figyelem:** ATEM ISO-műsoroknál a timeline-on gyakran külön master hang és ISO-kamerahang is van. A zárolás/track target konfiguráció döntheti el, hogy ezek közül mit vágsz. A program nem írja át ezt automatikusan. Mindenkor duplikált timeline-on próbáld ki először.

## Hibaelhárítás

- **MARKER SET nyomva tartása után nincs trim:** KORG KONTROL Editor → az adott gomb `Momentary`, nem `Toggle`; nyomáskor CC=127, elengedéskor CC=0. A jog maradjon Sign Magnitude (CC82). Az NK menüsor jelzésének `NK TRIM`-re kell váltania.
- **SELECT 5 nem vág:** ellenőrizd `NK → SELECT 5 (Cmd+B): beallitva`, `NK → Hammerspoon Accessibility: OK`, és hogy a Resolve van fókuszban. A timeline Edit Page-en legyen aktív. Ellenőrizd az érintett sávok célzását és lakatját.
- **Csak az egyik sávot vágja:** Resolve célzott/engedélyezett sávok beállítása; a `⌘⇧A` megszünteti a klipkijelölést, de nem állít át zárolt vagy kizárt sávokat.
- **Hammerspoon továbbra is piros Accessibility WARNING:** macOS beállításban kapcsold be és indítsd újra a Hammerspoont. A Hammerspoon menüjében közvetlenül is kérhető az engedély.
- **SHUTTLE furcsa:** `CYCLE` → vissza JOG, vagy STOP. A fizikai jog nem rugós, középállású shuttle gyűrű; a lejátszássebességet továbbra is a Resolve JKL vezérlése határozza meg.
- **Másik MIDI-gombot tanítottál SELECT 5 helyett:** válaszd újra az `NK → SELECT 5 (Cmd+B) egyszeri betanítása` menüt; az eredeti 24 kiosztás akkor sem változik.

## Telepített fájlok és visszaállítás

- Lua vezérlő: `~/.hammerspoon/nanokontrol_resolve21.lua`
- Konfigurációbetöltő: `~/.hammerspoon/init.lua` → `require("nanokontrol_resolve21")`
- Meglévő kiosztás: Hammerspoon `hs.settings` → `nanokontrol_studio_resolve21_v1`
- Biztonsági mentés: `~/.hammerspoon/nanokontrol_resolve21.lua.backup.<idobelyeg>`

Ha vissza akarod állítani a v1.1-et, a telepített Lua-fájlt cseréld vissza a mentésből, majd Reload Config. Ez a telepítő **nem módosítja** a KORG hardvert és a Resolve projektjét.

**Ellenőrzés:** Lua-szintaxis és szimulált MIDI-vezérlő tesztek (`JOG`, `SHUTTLE`, nyomva-tartós trim, SELECT 5 egygombos kalibrálás, a 24 régi binding megőrzése, Accessibility védelem) sikeresen lefutottak. Valódi Korgon / Resolve-on a tényleges viselkedést még érdemes ellenőrizni.

## Dokumentáció

- [Korg nanoKONTROL Studio](https://www.korg.com/us/support/download/product/0/552/)
- [Hammerspoon MIDI](https://www.hammerspoon.org/docs/hs.midi.html)
- [Hammerspoon eventtap](https://www.hammerspoon.org/docs/hs.eventtap.html)
- [DaVinci Resolve 21 trimming](https://docs.imaster.org/davinci-resolve-21-manual/part-6-edit/ch.-51-trimming)
- [DaVinci Resolve 21 editing basics](https://docs.imaster.org/davinci-resolve-21-manual/part-6-edit/ch.-43-editing-basics)