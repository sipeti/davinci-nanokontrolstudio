-- Standalone hardware-only Scene 2 MUTE 1 / SOLO 1 LED proof.
-- Never touches Resolve, key presses, transport, mixer or controller settings.
-- Usage (Hammerspoon Console):
--   dofile(os.getenv("HOME") .. "/Projects/davinci-nanokontrolstudio/scripts/scene2_mute_solo_led_probe.lua")
--   Press Scene 2 MUTE 1, then SOLO 1; then run nkScene2LedProbe.flash()
--   nkScene2LedProbe.stop() disconnects and turns both learned LEDs off.
-- Scene 2: input callback channel=1; previously tested output channel=1.
if type(_G.nkScene2LedProbe) == "table"
  and type(_G.nkScene2LedProbe.stop) == "function" then
  _G.nkScene2LedProbe.stop()
end

local outputChannel = 1
local name = nil
for _, candidate in ipairs(hs.midi.devices()) do
  local lower = candidate:lower()
  if lower:find("nanokontrol", 1, true)
    and lower:find("studio", 1, true) then
    name = candidate
    break
  end
end
if not name then
  hs.printf("[NK SCENE2 LED] BLOCKED; nanoKONTROL Studio not found")
  return nil
end
local device = hs.midi.new(name)
if not device then
  hs.printf("[NK SCENE2 LED] BLOCKED; MIDI device could not be opened")
  return nil
end

local probe = {device = device, learned = {}, step = 1,
  timers = {}, active = true, flashing = false}
local labels = {"MUTE 1", "SOLO 1"}
local function send(cc, value)
  if not probe.active or type(cc) ~= "number" then return false end
  local ok, result = pcall(function()
    return device:sendCommand("controlChange", {
      channel = outputChannel, controllerNumber = cc,
      controllerValue = value,
    })
  end)
  hs.printf("[NK SCENE2 LED] SEND ch=%d cc=%d value=%d API_OK=%s API_RESULT=%s",
    outputChannel, cc, value, tostring(ok), tostring(result))
  return ok and result ~= false
end
local function clearTimers()
  for _, timer in ipairs(probe.timers) do
    if timer then timer:stop() end
  end
  probe.timers = {}
end
local function later(delay, callback)
  probe.timers[#probe.timers + 1] = hs.timer.doAfter(delay, callback)
end

function probe.stop()
  if not probe.active then return end
  clearTimers()
  probe.flashing = false
  -- Always leave the two *observed* Scene 2 LEDs off.
  send(probe.learned[1], 0)
  send(probe.learned[2], 0)
  device:callback(nil)
  probe.active = false
  if _G.nkScene2LedProbe == probe then _G.nkScene2LedProbe = nil end
  hs.printf("[NK SCENE2 LED] STOPPED; RESOLVE_WRITES=0")
end

function probe.flash()
  if not probe.active or probe.flashing then
    hs.printf("[NK SCENE2 LED] BLOCKED; already stopped or running")
    return false
  end
  local mute, solo = probe.learned[1], probe.learned[2]
  if not mute or not solo then
    hs.printf("[NK SCENE2 LED] BLOCKED; learn MUTE 1, then SOLO 1 first")
    return false
  end
  if mute == solo then
    hs.printf("[NK SCENE2 LED] BLOCKED; MUTE/SOLO must have distinct CCs")
    return false
  end
  probe.flashing = true
  hs.printf("[NK SCENE2 LED] FLASH MUTE 1 then SOLO 1; look at physical LEDs; this does NOT mute or solo audio")
  if not send(mute, 127) then
    probe.flashing = false
    send(mute, 0)
    return false
  end
  later(1.2, function()
    if not probe.active then return end
    send(mute, 0)
    later(0.35, function()
      if not probe.active then return end
      if not send(solo, 127) then
        send(solo, 0)
        probe.flashing = false
        return
      end
      later(1.2, function()
        if not probe.active then return end
        send(solo, 0)
        probe.flashing = false
        hs.printf("[NK SCENE2 LED] COMPLETE; output commands sent; VISUAL_CONFIRMATION_REQUIRED; RESOLVE_WRITES=0")
      end)
    end)
  end)
  return true
end

device:callback(function(_, _, command, _, meta)
  if not probe.active or probe.flashing or command ~= "controlChange"
    or type(meta) ~= "table" or meta.channel ~= 1
    or type(meta.controllerNumber) ~= "number"
    or meta.controllerValue ~= 127 then return end
  local cc = meta.controllerNumber
  if cc < 0 or cc > 127 or probe.learned[1] == cc then return end
  if probe.step > 2 then return end
  probe.learned[probe.step] = cc
  hs.printf("[NK SCENE2 LED] LEARNED %s: incoming_ch=1 cc=%d", labels[probe.step], cc)
  probe.step = probe.step + 1
  if probe.step == 2 then
    hs.printf("[NK SCENE2 LED] Now press Scene 2 SOLO 1 (not transport)")
  elseif probe.step == 3 then
    hs.printf("[NK SCENE2 LED] READY; run nkScene2LedProbe.flash() in Hammerspoon Console")
  end
end)

_G.nkScene2LedProbe = probe
hs.printf("[NK SCENE2 LED] START; select Scene 2, press MUTE 1; RESOLVE_WRITES=0")
return probe
