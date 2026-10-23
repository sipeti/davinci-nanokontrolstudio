-- Scene 2 physical MIDI identification: strictly read-only.
-- Run in Hammerspoon Console:
-- dofile(os.getenv("HOME") .. "/Projects/davinci-nanokontrolstudio/scripts/scene2_midi_readonly.lua")
-- To stop only this logger (without stopping the active controller):
-- if nkScene2MidiProbe then nkScene2MidiProbe:callback(nil); nkScene2MidiProbe=nil end
-- Creates its own hs.midi object. Does not modify nanokontrol_resolve21.lua,
-- send MIDI, press keys, connect to Resolve or change any audio.
local previous = rawget(_G, "nkScene2MidiProbe")
if previous then
  previous:callback(nil)
  _G.nkScene2MidiProbe = nil
end

local deviceName
for _, name in ipairs(hs.midi.devices()) do
  local candidate = name:lower()
  if candidate:find("nanokontrol", 1, true)
    and candidate:find("studio", 1, true) then
    deviceName = name
    break
  end
end

if not deviceName then
  hs.printf("[NK SCENE2 PROBE] BLOCKED: nanoKONTROL Studio not found")
  return nil
end

local device = hs.midi.new(deviceName)
if not device then
  hs.printf("[NK SCENE2 PROBE] BLOCKED: cannot open MIDI input")
  return nil
end

device:callback(function(_, _, command, _, meta)
  if command ~= "controlChange" or type(meta) ~= "table"
    or meta.channel ~= 1 then return end -- Scene 2 incoming channel (zero-based)
  if type(meta.controllerNumber) ~= "number"
    or type(meta.controllerValue) ~= "number" then return end
  hs.printf("[NK SCENE2 MIDI] ch=1 cc=%d value=%d raw=%s",
    meta.controllerNumber, meta.controllerValue, tostring(meta.data or "-"))
end)

_G.nkScene2MidiProbe = device -- retain independently from controller
hs.printf("[NK SCENE2 PROBE] STARTED; WRITE=0; turn Scene 2 knobs 1-8 left/right")
return device
