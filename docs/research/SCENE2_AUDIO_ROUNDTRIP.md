# Scene 2 — guarded clip AudioVolume round-trip

This is a **one-time experiment**, not MIDI control. The shipping Lua controller is unchanged. Use **only a backed-up, disposable Resolve test project** with a simple audio clip **without volume automation/keyframes**; stop playback first.

## Procedure

In Terminal:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio
git fetch origin
git switch --track origin/research/scene2-audio-roundtrip-test
~~~

**Do not run install.command.** In the copied test project, position the timeline playhead over exactly one A4 audio clip and open Inspector → Audio → Volume.

In Resolve **Workspace → Console → Py3**, run:

~~~python
import os
exec(open(os.path.expanduser("~/Projects/davinci-nanokontrolstudio/scripts/scene2_audio_roundtrip_probe.py"), encoding="utf-8").read())
scene2_preview(4)
~~~

This is **strictly read-only**. It displays the actual project/timeline names, original clip dB and candidate +/-0.5 dB, with a one-time token and a complete confirmation command. Confirm that the active project is a **backup/test copy**, that playback is stopped, and that the printed original dB matches the Inspector.

Only after those checks, paste the exact **scene2_roundtrip(...)** command that the preview printed into the *same Py3 session*. It requires the current project name, the ephemeral token and the exact test-project consent phrase. This is a single-use authorization.

The script writes +0.5 dB (or -0.5 dB if near the upper limit), reads back via GetProperties, immediately attempts to restore the original dB, and verifies it again.

A successful test displays:

~~~text
TEST_WRITE_READBACK=PASS
RESTORE_VERIFIED=True
SCENE2_ROUNDTRIP=PASS
~~~

**After the test**, manually check the Inspector: it should still show the exact original dB.

If it prints **FAIL**, **BLOCKED** or **RESTORE_VERIFIED=False**, do **not** repeat blindly. Manually verify and restore the original dB shown in the log; the rollback may not have completed. Share the console output without private project names.

## Safety contract

- Loading and previewing cannot write anything. Preview creates one ephemeral token, which is consumed on its first authorization attempt.
- Before writing, the script re-reads project UUID, timeline UUID, clip UUID, playhead, frame rate, target track, clip bounds, gain-enabled flag and the original dB. Any mismatch fails closed.
- Overlapping clips, no clip, disabled gain, missing API methods/IDs, invalid or drop-frame timecode, and fractional timeline FPS fail closed.
- Only a single TimelineItem AudioVolume is written. No clip selection, playhead movement, channel mixer fader, mute, keyboard shortcut or MIDI command.
- On any attempted write the script tries restoration even after errors, and checks the restored value. It cannot guarantee recovery after a crash or lost Resolve connection; **the test-project backup is essential**.
- **Only the earlier GetProperties readback was verified on the real Resolve installation.** The write/restore still awaits the user's live test.

API references: [Resolve 21.1 TimelineItem](https://wheheohu.github.io/bmd_doc/ResolveAPI/21.1.0/resolve_api/TimelineItem) and [AudioVolume property](https://wheheohu.github.io/bmd_doc/ResolveAPI/21.1.0/resolve_settings/TimelineItemPropertie%20s).

After this round-trip is confirmed, [issue #3](https://github.com/sipeti/davinci-nanokontrolstudio/issues/3) will track soft takeover and clip-aware pickup. Track mixer faders remain disabled until a separate authoritative feedback path is found.
