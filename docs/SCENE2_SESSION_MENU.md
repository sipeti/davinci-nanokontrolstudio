# Scene 2 - optional one-click TEST operation (Draft PR #15)

**Not deployed.** Only a named, backed-up test project may be written.
The existing Hammerspoon Scene 1 bindings, Korg mode and 28/28
calibration are unchanged. No automatic startup or production approval.

Hardware A4 and A5 clip-gain AudioVolume writes passed. Mixer faders
and MCU host LED packets passed, but physical LED illumination and all
eight channels in the combined mode still need the operator's check.

## Clip gain scale

The new gain curve uses all 128 physical rotary positions:

- Fully left (CC0): **-100 dB**.
- Physical centre (CC64): **0 dB**.
- Fully right (CC127): **+30 dB**.
- Fine control near centre: CC63=-0.5 dB, CC65=+0.273 dB.
- This changes pickup positions from the previous experimental curve:
  a new physical pickup is required on first use.

## Low-latency rotary test (opt-in)

The default worker retains its conservative 200ms poll and 120ms
pre-setter stability pause. The optional `--low-latency` mode uses 20ms
polling, skips that extra pause and reuses the first full snapshot per CC.
Its setter STILL takes a fresh snapshot of the exact project, playhead,
target clip and gain BEFORE writing, and another after for readback.
Already-engaged rotaries send only the latest CC in each batch to avoid
old queued writes. The MCU mixer path, Scene1, host LEDs and gain curve
are unchanged.

The low-latency optimization has NOT been physically accepted: continue
to use only a backed-up disposable test copy with no clip automation.
Stopped playback is required. Because the 120ms playback-motion gate is
bypassed, never use this mode while playback/scrubbing is active.

```sh
/opt/homebrew/bin/python3 /tmp/nk-scene2-combined/scripts/scene2_combined_bench.py \
  --run-until-stopped --low-latency --write-test-copy \
  --expected-project "hajoagyu_261022 testing" \
  --confirmed-backup --confirmed-no-automation --max-clip-writes 0
```

## Continuous session

Normal bench: `--seconds 90`, 1200 MCU messages and 12 clip writes
unless explicitly overridden. New `--run-until-stopped` instead runs
both workers until stopped; mixer packet cap and clip write cap are
disabled ONLY in this explicit mode. Read-only remains the default.
Writes still require a named backed-up test project and confirmation
of absent gain automation/keyframes. The MCU strip 8 Bus1 remains locked.

```sh
/opt/homebrew/bin/python3 "/tmp/nk-scene2-combined/scripts/scene2_combined_bench.py" \
  --run-until-stopped --write-test-copy \
  --expected-project "hajoagyu_261022 testing" \
  --confirmed-backup --confirmed-no-automation --max-clip-writes 0
```

Ctrl+C stops both workers; MCU NOTE/TOUCH releases are sent during
shutdown. Existing Hammerspoon bridge must be ON. Do not let a second
copy of the clip worker or session run concurrently.

## Optional NK JOG Start/Stop menu (staged, not live installed)

`scene2_session_menu.lua` is optional. It starts ONLY on menu click,
shows a confirmation prompt naming the test project, writes diagnostics to
`~/Library/Logs/nk-scene2-session.log`, and uses `hs.task` streaming
output, so a long-running task cannot fill OS pipes. A second click
sends SIGINT to the parent supervisor, which stops both children.

The menu helper expects the scripts at
`~/Library/Application Support/NK Scene2/scripts/` and
`/opt/homebrew/bin/python3`. Stage after review:

```sh
cd ~/Projects/davinci-nanokontrolstudio
git fetch origin feature/scene2-mcu-fairlight-bridge
mkdir -p "$HOME/Library/Application Support/NK Scene2"
git archive FETCH_HEAD scripts | tar -x -C "$HOME/Library/Application Support/NK Scene2"
```

Installing the new **optional** menu helper and updated controller
requires explicit user approval after review/backups. Never rewrite
`~/.hammerspoon/init.lua` or run the 28-step calibration. The one-click
start is for the exact named test copy only: do NOT use it on a production
project. On a change of project, stop the session first. To seed mixer
faders, make Resolve emit a new MCU bank/project snapshot after startup.
