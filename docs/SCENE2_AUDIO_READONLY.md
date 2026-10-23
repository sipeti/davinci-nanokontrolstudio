# Scene 2 audio — read-only Resolve 21.1 probe

**Research only. No audio writes.** The shipping `main` controller is unchanged.

The intended mapping is:

| Korg strip | Rotary knob | Linear slider/fader |
| --- | --- | --- |
| 1…8 | Audio clip **under the playhead on that strip's audio track A1…A8**: Inspector `AudioVolume` | The corresponding Fairlight **mixer track/channel volume** |

Both inputs are absolute and non-motorized, so **neither may write anything until the actual Resolve value is read and soft takeover/pickup succeeds**. Scene switching, project/timeline changes, clip changes, external GUI edits and reconnects must invalidate pickup. No readback means **no write**.

## Why the investigation is split

Resolve Studio **21.1** introduced `TimelineItem.GetProperties()` with `AudioVolume` and `AudioVolumeEnabled` and `SetProperties({...})`. Its supported clip-level `AudioVolume` range is **−100…+30 dB**. This may cover the **rotary knobs** after proof on the user's actual 21.1 build.

The documented Timeline scripting API includes `GetTrackCount("audio")` and `GetItemListInTrack("audio", trackIndex)`, but no documented mixer **track-volume getter/setter pair** was identified. `GetIsTrackEnabled/SetTrackEnable` is **not** a substitute for the Fairlight track-volume control or verified track MUTE feedback. The **sliders remain disabled** until a reliable read/write path is found, possibly through an independently tested HUI/MCU mixer feedback bridge.

References: [21.1 TimelineItem API](https://wheheohu.github.io/bmd_doc/ResolveAPI/21.1.0/resolve_api/TimelineItem), [21.1 audio property keys](https://wheheohu.github.io/bmd_doc/ResolveAPI/21.1.0/resolve_settings/TimelineItemPropertie%20s), [21.1 API method catalog](https://github.com/dmmdea/davinci-resolve-cli/blob/main/docs/api-catalog-21.1.md).

## One-off, read-only check on the Mac

1. Switch to the **research branch**, without installing its Lua file:
   ```sh
   cd ~/Projects/davinci-nanokontrolstudio
   git fetch origin
   git switch --track origin/research/scene2-audio-readonly-probe
   ```
2. Open a **copy/disposable test project** in Resolve Studio 21.1. Have one or more audio clips under the **timeline playhead**, ideally on tracks A1, A2 and A3.
3. In Resolve, open **Workspace → Console**, choose the **Python** tab and execute:
   ```python
   import os
   exec(open(os.path.expanduser("~/Projects/davinci-nanokontrolstudio/scripts/scene2_audio_readonly_probe.py"), encoding="utf-8").read())
   ```
4. Look for `SCENE2_AUDIO_READONLY_PROBE=COMPLETE; WRITES=0`. Each track shows one of:
   - `playhead_clip=unique AudioVolume_dB=<value> enabled=<bool> item_id=available`: a supported gain readback and persistent clip identifier exist for exactly one clip under the playhead (the actual ID is never printed).
   - `NO UNIQUE TARGET`: the track is empty at the playhead, multiple clips overlap, or playhead-frame conversion could not be verified.
   - `AudioVolume readback incomplete`: Resolve did not return an authoritative gain value.
5. The `MIXER_METHOD_NAMES` line lists **available method names**, not evidence of a safe mixer setter. The tool does **not** move faders or send any MIDI.

This probe intentionally refuses non-integer FPS, drop-frame timecodes and incompatible timecode/frame origins; it does not guess a clip's identity. If it prints `PLAYHEAD_FRAME=UNVERIFIED`, the next research step is determining a safe position conversion before any clip control can be enabled.

The script prints only track indices, numeric volumes and method names — **not project names, clip filenames, audio data or paths**. It makes no calls that start with `Set`, and contains no keyboard/mouse simulation or network requests.

## First live Resolve test — PASS for readback, no writes

The user ran this exact script in **Resolve's Py3 Console on macOS**. The probe completed with `WRITES=0` and reported:

- **50 fps** and a verified non-drop-frame playhead position (no unsafe frame-rate conversion).
- **A1, A4, A5, A6 and A7:** exactly one audio clip matched at the playhead, and `AudioVolume_dB`, `AudioVolumeEnabled=True` and `item_id=available` were all returned. Actual gain values and internal IDs are intentionally *not* recorded in the public repository.
- **A2 and A3:** no clip matched at the current playhead; the script correctly returned `NO UNIQUE TARGET` rather than selecting a neighboring clip.
- **A8:** no output because there were fewer than eight audio tracks in the active timeline.
- `MIXER_METHOD_NAMES=none` for the probed Timeline object. **This is not proof that no control-surface or other mixer interface exists**; it is only evidence that this particular object did not expose matching getter/setter names.

**Verified:** frame/timecode handling, single-clip selection, per-clip `AudioVolume` readback and availability of a per-item identifier, without a write.

**Not yet verified:** that those reported dB values match the Inspector on a representative clip; that `SetProperties` writes/reads back/undoes correctly; that clip identity remains stable across timeline changes, overlapping audio, linked media or gain automation; and that the Fairlight **track fader** has a separate authoritative read/write interface.

**Inspector/manual-edit check — PASS on the user's Resolve 21.1:** on the audio track A4, the Inspector showed +10.0 dB and the read-only Py3 probe showed `AudioVolume_dB=10.0`. After the user manually adjusted the Inspector to +9.0 dB, the subsequent probe reported `AudioVolume_dB=9.0` on A4, `AudioVolumeEnabled=True`, and `item_id=available`; the command ended with `WRITES=0`. This establishes matching dB readback and that a manual UI change becomes visible to the API. The script did not print item IDs, so cross-run identifier equality is **not** independently verified by this evidence.

**Next isolated step:** on a disposable project only, test a tightly bounded `TimelineItem.SetProperties({"AudioVolume": value})` round-trip with a *fresh* identity+gain read immediately before writing; verify the resulting Inspector value, re-read via `GetProperties()`, then restore the original dB and verify again. Keep all production Scene 2 MIDI knob/fader writes **disabled**. Do not run a setter on live material before an explicitly reviewed test.

## Before activating any Scene 2 gain controls

- Confirm `AudioVolume` readback against the Inspector in Resolve Studio **21.1.0.17**, including linked AV clips and clips with keyframes.
- On disposable media only: test a bounded `SetProperties({"AudioVolume": db})`, check return **and readback**, then undo; distinguish static Inspector volume from automated clip envelopes.
- Define a reversible, non-jumping MIDI CC-to-dB curve and independent **WAIT_FOR_PICKUP → ENGAGED → STALE** state machine per physical strip/target.
- Invalidate on scene/timeline/project/clip changes, external volume edits, loss of connection and ambiguous overlap.
- Prove current Fairlight **mixer track volume** from an authoritative feedback path before enabling faders.
- Preserve Scene 1 JOG/SHUTTLE, the 28/28 MIDI calibration and global transport.

Implementation scope is tracked in [issue #3](https://github.com/sipeti/davinci-nanokontrolstudio/issues/3).
