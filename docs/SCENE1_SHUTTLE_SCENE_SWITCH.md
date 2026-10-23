# Scene 1 shuttle fader safe rearm after observed Scene 2+ activity

**Research PR only; no installation and no changes to the shipping main.**

The nanoKONTROL Studio has two different movement interfaces:

- Relative JOG wheel: CC82 Sign Magnitude; common JOG/SHUTTLE navigation
  shared across Scenes 1–5. No absolute-position pickup applies.
- Absolute Scene 1 slider 1: CC2; its neutral range is 60–68 (MIDI value).
  The existing code refuses transport control until that slider is first
  centered. Once armed, its position controls ±4 JKL shuttle levels.

The Korg does not necessarily emit a MIDI event when switching Scenes.
If an **actual Scene 2–5 control event** is observed after the Scene 1
shuttle fader was armed, this fix:

1. Disarms the Scene 1 absolute fader; does NOT stop actual playback or
   change the common JOG/SHUTTLE transport gear.
2. Clears a potentially stale held Scene 1 MARKER/trim state.
3. Lets Scene 2 and subsequent Scene 1 relative JOG wheel events work
   immediately, without faderActive blocking the wheel.
4. Requires physical fader 1 to return to its neutral region before it
   can affect playback again, preventing accidental takeover from an
   old high/low fader position.

This cannot detect a purely silent Scene 1 -> Scene 2 -> Scene 1 switch
when **no input event is received from Scene 2 at all**; do not claim
fully authoritative hardware scene position detection. After adjusting
Scene 2 rotary gains, an incoming CC is naturally observed, so the
intended workflow is covered.

Regression tests simulate an active Scene 1 fader, Scene 2 CC13, then a
return to Scene 1 JOG and an absolute fader parked at 127. They also
test rearming at CC64 and a stale held MARKER button.

All changes are confined to a small Scene-switch invalidation guard
and Lua hardware-free regression tests. No new setup, CC mapping,
Korg Editor writing, Resolve script or automatic audio-gain setter.
