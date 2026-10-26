# Installation, MIDI routing and updates

## Prerequisites

- macOS; [Hammerspoon](https://www.hammerspoon.org/) with Accessibility
  permission and *Launch at Login* enabled if you want the controller after login.
- DaVinci Resolve **Studio 21**, including its scripting modules.
- Homebrew Python 3.10+ and Korg nanoKONTROL Studio in **USB Assignable Mode**.
- KORG KONTROL Editor for the initial JOG/LED Scene Set configuration.
  Keep the physical Korg out of HUI mode.

The one-time Scene 1 **28-step calibration** is stored in Hammerspoon
settings. Subsequent installations do not reset it.

## Physical Korg mapping

| Scene 2 controls | Hardware CCs |
|---|---|
| Sliders 1–8 | **2, 3, 4, 5, 6, 8, 9, 12** (factory mapping) |
| Rotary knobs 1–8 | 13–20 |
| MUTE 1–8 | 21–28 |
| SOLO 1–8 | 29, 30, 31, 33, 34, 35, 36, 37 |
| SELECT 7 / SELECT 8 | 52 / 53, MCU bank left/right |
| JOG | CC82, Sign Magnitude / Const |
| LEDs | External mode |

In the tested 16-audio-track project, the two banks address A1–A8 and
A9–A16. A smaller or differently arranged Resolve project may present
Bus 1 in an MCU strip. Keep bank A1–A8 selected before changing projects
or restarting. **Do not renumber the factory slider CC values.**

## IAC and Resolve configuration

Open **Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver** and
enable the driver. Create two separate buses:

| Bus | Purpose |
|---|---|
| **NK FL To Resolve** | Python MCU commands → Resolve MIDI input |
| **NK FL From Resolve** | Resolve MCU feedback → Python MCU input |

In **Resolve Preferences → System → Control Panels**, select an
MCU-compatible MIDI Audio Console. Set input **NK FL To Resolve** and
output **NK FL From Resolve**, then save. Do not use the physical Korg
port in Resolve: Hammerspoon already owns it. On some Macs the bus names
include the prefix `IAC Driver`; the software expects those exact
prefixed names.

## First installation

From a clean repository checkout:

```sh
sh ./install.command --dry-run
sh ./install.command
sh ./doctor.command
```

Install creates a backed-up Hammerspoon configuration, sets up an
isolated Python venv under `~/Library/Application Support/NK Scene2`,
and copies the Lua/Python runtime. It adds one
`require("nanokontrol_resolve21")` line to Hammerspoon's `init.lua`
only if absent. No global Python packages or separate macOS daemon.

Reload Hammerspoon configuration once. When Resolve is frontmost and the
Korg is connected, Scene 2 starts without extra approval. While Resolve
is closed, the two Python workers stop; only the lightweight Hammerspoon
MIDI/event/LED hooks remain.

## Updating an installed controller

Once the release candidate with the local update URL hooks is installed:

```sh
git fetch origin main
TMP=$(mktemp -d /tmp/nk-release.XXXXXX)
git archive FETCH_HEAD | tar -x -C "$TMP"
cd "$TMP"
sh ./update.command
```

The updater operates on **this source snapshot**; it never performs its
own Git pull. It asks the running Hammerspoon controller to pause, waits
for acknowledgement and for the two Python workers to exit, then calls
the regular **backup-first installer**. It checks copied file contents
before requesting a full Hammerspoon Lua reload. After reload, Scene 2
automatically starts again when Resolve is ready. If Hammerspoon is not
running, it installs now and loads on next launch.

**First migration from the older v1.5 install:** the old running Lua
controller cannot receive the new update URL. Return to A1–A8, choose
the existing **Scene 2 Pause** entry, verify the workers stopped, then
run `sh ./install.command --force` from the new snapshot, and use
**Hammerspoon → Reload Config**. The new `update.command` is then
available for later updates.

**Bank 2 is active?** SELECT 7 first, and confirm A1–A8 in NK JOG.
Restart/update cannot safely infer the Resolve MCU bank after an
uncontrolled reload, so the updater refuses to stop in bank 2.
This is a real track-identity limitation, not a per-project permission prompt.

`sh ./update.command --dry-run` checks the installation source without
performing a stop, copy or restart (subject to the install preflight).

## Restore, checks and troubleshooting

```sh
sh ./doctor.command
sh ./uninstall.command
```

The doctor reads Python/module/IAC state and sends no MIDI.
The uninstaller checks hashes and restores the **immediately preceding**
Lua files, `init.lua` and runtime scripts, retaining backups, the venv
and calibration. Pause active workers before uninstalling.

If a Fairlight slider waits for pickup, confirm Resolve still has the
correct MCU Control Panels assignment. Move the corresponding on-screen
Fairlight fader to elicit host feedback, then cross its value with the
physical slider. A Korg button press alone does not establish an
authoritative LED state: LED feedback comes from Resolve.

Clip gain is intended for a stopped playhead, without unsupported gain
automation or keyframes. The low-latency API cannot reliably detect all
playback/automation conditions. Logs:
`~/Library/Logs/nk-scene2-session.log`.
