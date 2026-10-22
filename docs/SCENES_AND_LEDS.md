# nanoKONTROL Studio — scene-ek, potméterek, faderek és LED-feedback

Állapot: **terv + külön bekapcsolható LED-kimenet próba**. A v1.2 `main` meglévő kezelőszerveit nem módosítja.

## Tervezési döntések

1. **JOG ↔ SHUTTLE marad a CYCLE-on a napi munkában.** A hardveres SCENE gomb az öt bankon ciklikusan végiglépked; Scene 2 → Scene 1 négy lenyomás lenne. A SCENE inkább munkafolyamat-profil, nem egy gyakori kétállású kapcsoló.
2. **A SCENE váltását nem szabad számlálóval találgatni.** Az assignable módú SCENE-váltás belső Korg-művelet, nincs dokumentált, külön megbízható scene-váltás CC a Hammerspoon felé. Az aktív scene-t a hozzá tartozó, egyedivé tett bejövő CC / MIDI-csatorna alapján ismerjük fel. Ha nem különböztethető meg, a szoftver maradjon kompatibilis az eredeti v1.2-vel, és ne változtasson funkciót.
3. **Global LED Mode = External csak teljesen implementált LED-echo után.** Ebben az üzemmódban az eszköz csak bejövő CC/note üzenetre világít; SCENE-váltáskor az összes gomb LED-je kialszik. Kezdetben egy explicit, 700 ms-os próbával ellenőrizzük az oda-vissza MIDI kapcsolatot.
4. **A Resolve-állapot és a kontroller saját állapota külön dolog.** Hammerspoonból csak a saját gombparancsaink következményét ismerjük. Az aktív Resolve-kamera, sávonkénti mute/solo, tényleges play állapot vagy mixing gain valódi visszajelzéséhez a Resolve támogatott vezérlési protokollja / MCU-HUI / ellenőrizhető UI-állapot kell. Nem jelzünk ki olyan „igazságot”, amit nem ismerünk.
5. **Nem motoros fader + nem végtelenített potméter:** soha ne legyen fókuszváltáskor váratlan értékugrás. Az abszolút értékeket dead-zone, küszöb vagy pickup logika kezeli; betöltéskor és scene-váltáskor nem indul önként parancs.

## Javasolt bankkiosztás (v2 terv)

| Bank | Munkafolyamat | Nagy tárcsa | S/M/R/SELECT szerepe |
| --- | --- | --- | --- |
| Scene 1 | **ATEM Edit / áttekintés** | JOG, CYCLE-re SHUTTLE; MARKER SET nyomva trim | **A meglévő v1.2 kiosztás változatlan marad**; további SOLO/REC gombok később |
| Scene 2 | **ISO-kamerák / Sync Bin** | JOG; CYCLE-re SHUTTLE | MUTE 1–8 potenciális kamera 1–8 kiválasztás, SOLO 1–8 review-jelölés, REC/SELECT makrók; csak az adott Sync Bin nézetben érvényes |
| Scene 3 | **Finom Trim** | JOG roll trim az előzetesen kijelölt vágásponton; külön trim-lépésköz | SOLO váltja a vágáspont típusát, REC undo/redo; a destruktív műveletek külön védelemmel |
| Scene 4 | **Fairlight / Audio** | transport/scrub | 8 fader = 8 sávszint, 8 poti = pan, MUTE/SOLO/REC a hangkeverő módja **csak későbbi MCU/HUI-kompatibilis integrációval**, nem egyszerű billentyűzet-emulációval |
| Scene 5 | **Review / utility** | navigáció | jelölések és gyakori műsor-utómunka-makrók, egyelőre nincs hozzárendelés |

**MVP-kiosztás Scene 1-re, amivel érdemes kezdeni:**

| Kezelő | Funkció | Megjegyzés |
| --- | --- | --- |
| Poti 1 | timeline zoom lépések | Relatív CC-változásból billentyűparancs; nem jelent valódi abszolút Resolve zoom-állapotot |
| Poti 2 | JOG lépésköz 1 / 5 / 25 frame | A fizikai poti állásából számolt programoldali lépésköz |
| Poti 3 | JOG TRIM lépésköz 1 / 5 frame | A képkockapontos finomítás marad alapértelmezett |
| Poti 4 | SHUTTLE gyorsítás 1–4 fokozat | Kizárólag a vezérlő saját gyorsítási paramétere |
| Fader 1 | önálló ±1–4 fokozatú SHUTTLE | 0–127 tartomány, 60–68 körül STOP; nem rugós visszatérés, biztonságos STOP gomb mindig működik |
| Fader 2 | coarse timeline zoom | Csak akkor, ha a poti-zoom kevés; ne legyen duplikált kezelő véletlenül |
| Fader 3–8 | tartalék / későbbi Fairlight | Ne mímeljünk nem létező vagy bizonytalan Resolve-paramétert |

**Kiegészítő gombok:**

- **SOLO 1–3:** timeline marker hozzáadása, előző/következő marker, amint Resolve 21-shortcut ellenőrizve.
- **SOLO 4–5:** timeline „Fit” és Snapping (ha az aktív oldalon megbízható).
- **REC 1–4:** rossz kameraváltás megjelölése / review-állapotok (meghatározandó, lehet marker-alapú).
- **REC 5–8:** szabadon hagyjuk, amíg nincs valódi napi igény.
- **SELECT 1–5 és MUTE 1–8:** a működő v1.2 kiosztásukat Scene 1-en érintetlenül hagyjuk.

## LED-visszajelzés — három kategória

| Kategória | Példa | Mit állítunk a LED-del? |
| --- | --- | --- |
| Pillanatnyi ACK | REC/marker/split/makró | Esemény fogadva; rövid felvillanás |
| Lokális kiválasztás | CAM 1–4; Cut vs Edit; CYCLE | „Utoljára ezt kérted a Korg-ról”; **nem** bizonyítja a Resolve tényleges állapotát |
| Valódi DAW állapot | hangcsatorna Solo/Mute, hangerő, actual playback | **Későbbi integráció**, előbb MCU/HUI vagy más megbízható state source |

A LED-visszajelzést scene-váltáskor újra kell küldeni, **miután** az aktív scene egy beérkezett esemény alapján biztosan azonosítható. A hardveres öt SCENE LED-et maga a Korg kezeli; azokat nem szükséges szoftveresen utánozni.

## V1.2 kompatibilitás és kockázatok

- A jelenlegi 26 lépéses MIDI-learn, a `nanokontrol_studio_resolve21_v1` beállításkulcs és a meglévő bindingok változatlanok maradnak.
- Az új potik/faderek/32 gomb betanítása **külön, megszakítható kiegészítő** folyamat lesz, nem 50+ lépéses kötelező első indítás.
- Scene 2–5 fizikai Korg-konfiguráció nélkül nem aktiválunk más gombkiosztást.
- A hardver visszaírása előtt mentsük a Korg saját *Scene Set* (`.nktrl_st_set`) és *Global Data* (`.nktrl_st_glob`) fájlját. Ezt nem teszi meg a Hammerspoon telepítő.
- A Scene 2–5 MIDI-csatornák / CC-k tényleges hozzárendelését a felhasználó által mentett Korg scene set alapján kell validálni. Nem találgatjuk a bináris/proprietary formátumot, és nem írjuk felül az eszközt távolról.

## Opt-in LED próba (ebben a draft PR-ben)

A Hammerspoon NK menüben új: **LED kimenet teszt (MUTE 1, 700ms)**.

1. A *KORG KONTROL Editor* segítségével **mentsd** a teljes jelenlegi scene-setet és global konfigurációt, majd a **Global → LED Mode** legyen ideiglenesen **External**, és a Global képernyő megfelelő írási műveletével küldd a Korgra.
2. A draft branch kódját helyben telepítve, a Resolve szerkesztése nélkül, használd az **NK → LED kimenet teszt (MUTE 1, 700ms)** menüpontot.
3. Elvárt: a betanított MUTE 1 LED kb. 700 ms-ig világít, utána kialszik. Ez csak MIDI-kimeneti proof-of-concept; nem Resolve-állapot-visszajelzés.
4. A teszt után **állítsd vissza az Internal LED Mode-ot**, ha a teljes LED-feedback még nincs bevezetve, különben a többi gomb nem világít a megszokott módon.
5. Ha nem villan fel: ellenőrizzük a MIDI outputot, az egyes scene-ek MIDI csatornáját, a Korg LED Mode-ot és az output sendCommand visszatérési értékét. **Ne induljon semmilyen Resolve szerkesztési parancs** pusztán a LED-teszttől.

## Későbbi implementáció — szándékosan kis lépések

1. **LED proof** hardveres visszajelzése; 1 gomb, nincs automatikus state.
2. **Minden már betanított gomb pillanatnyi echo-ja**, utána a helyi, egyértelmű lokális állapotok (mód/kameraválasztási kérés) LED-je.
3. **Poti 1 / Fader 1**, soft-takeover/dead-zone, Resolve nélküli MIDI tesztekkel + egy duplikált timeline-on.
4. **Scene 2 felismerése** garantáltan eltérő MIDI-üzenetből. Scene 1 v1.2 fallback teszt.
5. **MCU/HUI Fairlight** külön mérföldkő. Nem keverjük össze az ATEM Edit gyorsbillentyűzet-emulációjával.
