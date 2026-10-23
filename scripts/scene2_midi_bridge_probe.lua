-- Optional, passive Scene 2 live pickup test: MIDI input -> local event log.
-- Does not send MIDI, press keys, call Resolve or change controller settings.
-- Start in Hammerspoon Console: dofile("/tmp/nk-scene2-live/scripts/scene2_midi_bridge_probe.lua")
-- Stop: if nkScene2LiveStop then nkScene2LiveStop() end
if type(_G.nkScene2LiveStop) == "function" then _G.nkScene2LiveStop() end

local home = os.getenv("HOME")
if not home then
  hs.printf("[NK LIVE] BLOCKED: HOME unavailable; AUDIO_WRITES=0")
  return nil
end
local path = home .. "/Library/Caches/nk-scene2-live-midi.csv"
local deviceName
for _, name in ipairs(hs.midi.devices()) do
  local lower = name:lower()
  if lower:find("nanokontrol", 1, true)
    and lower:find("studio", 1, true) then
    deviceName = name
    break
  end
end
if not deviceName then
  hs.printf("[NK LIVE] BLOCKED: nanoKONTROL Studio unavailable; AUDIO_WRITES=0")
  return nil
end
local device = hs.midi.new(deviceName)
if not device then
  hs.printf("[NK LIVE] BLOCKED: MIDI input unavailable; AUDIO_WRITES=0")
  return nil
end
local file = io.open(path, "w")
if not file then
  hs.printf("[NK LIVE] BLOCKED: cannot create passive event log; AUDIO_WRITES=0")
  return nil
end
file:write("# passive Scene 2 MIDI input; channel,cc,value\n")
file:close()

local running = true
local events = 0
local timer = nil
local failed = false
_G.nkScene2LiveStop = function()
  if not running then return end
  running = false
  device:callback(nil)
  if timer then timer:stop(); timer = nil end
  _G.nkScene2LiveProbe = nil
  _G.nkScene2LiveStop = nil
  hs.printf("[NK LIVE] STOP; EVENTS=%d; AUDIO_WRITES=0", events)
end

device:callback(function(_, _, command, _, meta)
  if not running or command ~= "controlChange" or type(meta) ~= "table" then return end
  local ch, cc, value = meta.channel, meta.controllerNumber, meta.controllerValue
  if type(ch) ~= "number" or type(cc) ~= "number"
    or type(value) ~= "number" then return end
  if value < 0 or value > 127 or cc < 0 or cc > 127 then return end
  -- Capture only Scene 2 rotary CCs and a different-scene signal for reset.
  if ch == 1 and (cc < 13 or cc > 20) then return end
  local out = io.open(path, "a")
  if not out then
    if not failed then hs.printf("[NK LIVE] LOG FAILED; AUDIO_WRITES=0") end
    failed = true
    return
  end
  out:write(string.format("%d,%d,%d\n", ch, cc, value))
  out:close()
  events = events + 1
end)

_G.nkScene2LiveProbe = device
timer = hs.timer.doAfter(120, function()
  if type(_G.nkScene2LiveStop) == "function" then _G.nkScene2LiveStop() end
end)
hs.printf("[NK LIVE] START; turn Scene 2 rotary 4 (CC16); AUDIO_WRITES=0")
return device
