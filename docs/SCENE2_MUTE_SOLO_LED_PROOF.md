# Scene 2 MUTE/SOLO physical LED proof (no Resolve changes)

This is a standalone opt-in Hammerspoon hardware test for exactly two buttons:
**Scene 2 MUTE 1** and **Scene 2 SOLO 1**. No track mute, solo, mixer
volume, clip gain, transport or production Lua controller is changed. It learns
the actual two incoming CCs from physical button presses; no CC numbers are
guessed. Unlike track-mute status LEDs, this is a **commanded LED flash only**,
not authoritative Resolve state feedback.

**Do not reload Hammerspoon settings or run install.command.**

In macOS Terminal (from any local branch):

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
git show origin/research/scene2-mute-solo-led-proof:scripts/scene2_mute_solo_led_probe.lua > /tmp/nk-scene2-led.lua
~~~

In **Hammerspoon Console**, with the Korg in Scene 2:

~~~lua
dofile("/tmp/nk-scene2-led.lua")
~~~

1. Press **MUTE 1** on the hardware. Console should say
   LEARNED MUTE 1: incoming_ch=1 cc=...
2. Press **SOLO 1**. Console should say
   LEARNED SOLO 1: incoming_ch=1 cc=..., followed by READY.
3. Without pressing buttons during the flash, run:

~~~lua
nkScene2LedProbe.flash()
~~~

The script sends on **output channel=1**, the route already proven for the
Scene 2 shared transport LEDs, with the *learned* CC numbers. First the MUTE 1
LED should illuminate for ~1.2 seconds and turn off, then SOLO 1 for ~1.2
seconds and off. Each send is logged with API_OK and API_RESULT. An
API-success log alone **does not prove** the physical LED illuminated;
visually confirm which buttons lit, or report if neither did.

Cleanup:

~~~lua
if nkScene2LedProbe then nkScene2LedProbe.stop() end
~~~

This sends OFF only to the two learned LEDs and detaches the standalone MIDI
callback. The current main controller and its LED heartbeat are left intact.

If the logger fails to learn the buttons, check whether the Scene 2 hardware
buttons use MIDI CC press=127 on channel 1; do not guess the missing CCs.
If the LEDs do not light, first confirm the Korg scene is configured for
**External LED mode**, then retry; do not broadcast to channel 0 blindly.

**Next work after physical proof:** learn all 8 MUTE and 8 SOLO CCs, use
authoritative Resolve mixer-state readback, then bind LED states. Actual
track mute/solo actions are NOT tested by this probe.
