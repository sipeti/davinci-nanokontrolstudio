# Timestamped MIDI comparison: Korg Scene 1 vs Scene 2

Purpose: prove with a *fresh, marked, isolated hardware capture* whether
the same physical rotary 4 sends a CC16 event on Hammerspoon input channel
0 in Scene 1 and channel 1 in Scene 2, without confusing separate earlier
tests or confusing MIDI input numbering with the sendCommand output API.

The previous 3365-event log was mixed (2748 channel 0, 617 channel 1)
but had no timestamps or per-scene markers. The newer isolated 925-event
log contained **only channel 1 CC16**, supporting the Scene 2 mapping.
Neither log alone proves simultaneous dual-channel messages.

The Hammerspoon MIDI input callback exposes channel 0..15, a timestamp,
and actual raw hex MIDI bytes; hs.timer.secondsSinceEpoch() is fractional
wall-clock seconds, while hs.timer.absoluteTime() is monotonic nanoseconds.
This probe stores both Unix epoch milliseconds and monotonic elapsed
milliseconds. Beware that MIDI sendCommand OUTPUT channel 0 is separately
documented as all-channel mode; this probe NEVER sends MIDI.

## Start one isolated, read-only capture

macOS Terminal, on any local branch:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
git show origin/research/scene2-eight-rotary-clip-gain:scripts/scene2_timestamped_midi_probe.lua > /tmp/nk-scene2-timestamped.lua
~~~

Hammerspoon Console:

~~~lua
if nkScene2LiveStop then nkScene2LiveStop() end
dofile("/tmp/nk-scene2-timestamped.lua")
~~~

Then:

1. Physically set Korg **Scene 1**. In Hammerspoon Console:
   nkMidiTs.mark("SCENE1")
2. Turn **rotary 4 only** slowly a few times. Do not turn other knobs.
3. Physically set Korg **Scene 2**. In Hammerspoon Console:
   nkMidiTs.mark("SCENE2")
4. Turn **rotary 4 only** a few times.
5. In Hammerspoon Console: nkMidiTs.stop()

The script prints a compact per-phase/channel/CC histogram and the first
raw MIDI bytes (for example, B0 10 xx and B1 10 xx) with elapsed
millisecond timestamps. These are examples, not assumed results.

Full CSV path is printed as FILE=... under ~/Library/Caches. A unique
filename is used for each recording. CSV columns are:

kind,epoch_ms,elapsed_ms,phase,channel,cc,value,raw_hex,midi_timestamp

MARK records are phase separators; CC records preserve Hammerspoon
raw meta.data and meta.timestamp. The program records **input only**,
never sets volume, sends MIDI, issues shortcuts or alters the main Lua.
It automatically stops after 120 seconds or 12000 CC events. Stop playback
first and do this on a disposable timeline if the existing main scene 1
bindings might have editing side-effects.

## Interpretation

- SCENE1 / channel 0 / CC16 / raw B0 ... and SCENE2 / channel 1 / CC16 /
  raw B1 ... strongly confirms correctly distinct input scenes.
- SCENE2 / both channels for the same physical motion would warrant
  inspecting the Korg editor, other virtual MIDI sources, duplicate
  callbacks or routing — do not silently remap both channels to A4 gain.
- Repeated events on one scene alone are expected during a fast absolute
  potentiometer sweep; that does not imply erroneous indexing.
- A timestamped log with explicit scene markers is more informative
  than counts merged across multiple days or sessions.

**Next gate:** after interpreting these exact data, rerun PR #13's fixed
eight-rotary monitor with its default WRITE-FREE mode and only then
consider test-copy writes. Neither timestamp probe nor read-only monitor
authorizes production gain writes.
