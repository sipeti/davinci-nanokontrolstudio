# Scene 2 MUTE/SOLO — commanded LED bank chase

The first physical MUTE 1 and SOLO 1 LED proof passed on 2026-10-24.
The user visually confirmed actual hardware illumination; observed input
channel=1 CC21/CC29 and successful output channel=1 on/off messages.

This follow-up is a **standalone temporary Hammerspoon experiment**.
It does NOT query or change Resolve, change any track mute/solo state,
or edit Korg controller settings. A successful LED blink says nothing about
whether the Fairlight mixer track is muted/soloed.

## Run

macOS Terminal (any local Git branch, no install and no branch switch):

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
git show origin/research/scene2-mute-solo-led-proof:scripts/scene2_led_bank_probe.lua > /tmp/nk-scene2-led-bank.lua
~~~

Hammerspoon Console:

~~~lua
dofile("/tmp/nk-scene2-led-bank.lua")
~~~

On the Korg, select **Scene 2** and press the following buttons in exactly
this order: **MUTE 1, MUTE 2, ..., MUTE 8, SOLO 1, SOLO 2, ..., SOLO 8**.

Every press is learned individually from the actual hardware's input
channel 1. The console prints LEARNED 01/16 through 16/16 READY.
The script ignores fader/rotary CCs and duplicates. If the wrong button was
pressed, stop and restart rather than trusting the displayed labels.

When READY, in Hammerspoon Console:

~~~lua
nkScene2BankLedProbe.flashAll()
~~~

Expected: 16 consecutive individual LED flashes, each ON for approximately
0.55 seconds and OFF before the next button is lit. The log includes the
actual output CC values (all on output channel 1) and ends
CHASE COMPLETE; VISUAL_CONFIRMATION_REQUIRED; RESOLVE_WRITES=0.

After looking at all 16 LEDs, clean up:

~~~lua
if nkScene2BankLedProbe then nkScene2BankLedProbe.stop() end
~~~

A 5-minute failsafe also detaches the callback and switches the 16 learned
LEDs off. The working main Lua controller, shared transport and existing
28-step calibration remain unchanged.

## Remaining gates

- Verify the physical CC map for all 16 buttons from Hammerspoon logs.
- Confirm which 16 physical LEDs actually illuminate in the predicted order.
- Do **not** mistake commanded LEDs for Resolve state feedback.
- The separate actual mixer mute and solo API/MCU feedback and no-jump
  control loop require independent research and live tests.
