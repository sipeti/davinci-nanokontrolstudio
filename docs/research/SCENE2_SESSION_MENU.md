# Scene 2 - optional one-click TEST operation (Draft PR #15)

**Operator-approved for menu installation, not yet deployed on the user's Mac.**
Only a named, backed-up test project may be written.
The existing Hammerspoon Scene 1 bindings, Korg mode and 28/28
calibration are unchanged. No automatic startup or production approval.

The operator accepted combined Scene1/Scene2 switching and low-latency
rotaries on 25 October 2026: 189 verified writes (A4/A5/A6/A7),
1373 mixer fader sends, 6 MUTE/SOLO key presses, host-sourced LED
feedback and clean Ctrl+C release. This does not verify clips on A1-A3/A8
or actual illumination of every physical Korg LED.

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
old queued writes. Every ten verified writes, `SCENE2_FAST_TIMING`
reports the Python handler duration and first Resolve snapshot duration
in milliseconds; it does not include the Korg/MIDI transit time. This
distinguishes Python polling lag from the remaining Resolve API cost.
The MCU mixer path, Scene1, host LEDs and gain curve are unchanged.

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

The menu helper starts the **accepted --low-latency mode** and expects:
`~/Library/Application Support/NK Scene2/scripts/`,
`~/Library/Application Support/NK Scene2/venv/bin/python3` (mido +
python-rtmidi), and `/opt/homebrew/bin/python3` (Resolve API).
The durable venv must be created by the operator before enabling START.
Stage after review:

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


## Operator-approved Mac installation (25 October 2026)

Stage into a temporary folder. Stop any existing terminal combined session
with Ctrl+C first. This installer refuses unknown local Hammerspoon main
code, mismatched optional bridge, active workers, missing dependencies or
failing Python unit tests. It DOES NOT start a worker, merge the Draft PR,
or change any `hs.settings` calibration.

```sh
cd ~/Projects/davinci-nanokontrolstudio
git fetch origin feature/scene2-mcu-fairlight-bridge
mkdir -p /tmp/nk-scene2-install
git archive FETCH_HEAD nanokontrol_resolve21.lua scene2_clip_gain_bridge.lua \
  scene2_session_menu.lua scripts tests | tar -x -C /tmp/nk-scene2-install
bash /tmp/nk-scene2-install/scripts/install_scene2_menu.sh
```

The installer creates a persistent MCU venv under
`~/Library/Application Support/NK Scene2/venv/`, preserving versions
from the tested `/tmp/nk-mcu-venv` when available; otherwise it installs
`mido` and `python-rtmidi`. Installed scripts go to the adjacent
`scripts/` directory. It creates timestamped backups under `backups/`
and prints the exact backup path. The Hammerspoon `init.lua`, hardware
Assignable scenes, stored 28/28 calibration, and Scene1 actions are never
overwritten. After a successful install, use Hammerspoon's **Reload Config**,
then NK JOG > **Scene 2 TEST: START**, confirm and return to Resolve.

To undo the menu install, stop the menu session, copy the backed-up
`nanokontrol_resolve21.lua` and `scene2_clip_gain_bridge.lua` into
`~/.hammerspoon/`, and remove the menu helper only if the backup folder
contains `session_menu_was_absent`. Reload Hammerspoon. Never delete the
backup folder until the rollback has been verified.

The menu is still intentionally **test-project-only**: it authorizes
`hajoagyu_261022 testing`. The project-name and no-automation guard
remain. Production projects require a separate, explicit approval of the
project-specific write policy; do not silently remove that restriction.
