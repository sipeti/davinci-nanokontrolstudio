# Scene 2 combined physical bench (Draft PR #15)

**Status:** combined launcher has offline tests only. Not production, no startup service and no edits to Scene 1 or live Hammerspoon files.

The existing single Hammerspoon MIDI callback writes one shared
`~/Library/Caches/nk-scene2-controller-events.csv`. Two separate Python
workers read that file concurrently: the Fairlight MCU worker handles
physical mixer faders / MUTE / SOLO and actual Resolve feedback; the Resolve
API worker handles CC13..20 per-clip gain. Two consumers are **not** two
Korg hardware listeners. Keeping them as separate processes prevents an
expensive Resolve API clip-gain write from blocking mixer MIDI throughput.

## Stage the whole Draft branch

```sh
cd ~/Projects/davinci-nanokontrolstudio
git fetch origin feature/scene2-mcu-fairlight-bridge
mkdir -p /tmp/nk-scene2-combined
git archive FETCH_HEAD scripts | tar -x -C /tmp/nk-scene2-combined
```

The launcher requires the existing `/tmp/nk-mcu-venv/bin/python3` (mido,
python-rtmidi), `/opt/homebrew/bin/python3` (Resolve Python API),
and the two IAC ports already configured.

First turn ON **NK JOG > Scene 2 clip gain MIDI bridge: BE**. Ensure Resolve
is running but **reopen the backed-up disposable test project only after
starting the combined runner** so MCU sees its initial 8 host fader values.
Keep Scene 2 selected; go to the Edit/Fairlight page with stopped playback.
The clip gain worker requires valid audio clips under the playhead, with
no gain keyframes / Fairlight automation.

For the named backed-up disposable project only:

```sh
/opt/homebrew/bin/python3 /tmp/nk-scene2-combined/scripts/scene2_combined_bench.py \
  --seconds 90 --write-test-copy \
  --expected-project "hajoagyu_261022 testing" \
  --confirmed-backup --confirmed-no-automation --max-clip-writes 12
```

Without `--write-test-copy`, both workers are read-only. The launcher
starts no daemon and changes no macOS or Korg settings. Ctrl+C gracefully
stops both workers. A clip worker reaching its write cap exits normally;
the mixer can finish its bounded run. If either worker fails, the launcher
stops the other. The MCU's existing global 1200-message output cap and
180-second maximum still apply; this bench is **not** an infinite-running
production controller. Strip 8 remains locked (potential Bus 1).

**Physical acceptance sought:** turn an A4/A5 clip gain rotary while moving
one already-accepted mixer fader, and verify those affect different Resolve
objects. Test MUTE/SOLO and confirm LEDs match Resolve feedback on the
actual Korg hardware; note that the earlier clips tests physically proved
A4, but A5 and host LED return remain to be signed off.
