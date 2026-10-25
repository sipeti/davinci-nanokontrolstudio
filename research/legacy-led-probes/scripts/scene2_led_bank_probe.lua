-- Scene 2 MUTE/SOLO LED chase: physical LEARN + commanded LED output only.
-- No Resolve, shortcuts, mixer writes, production config, or MIDI-mode changes.
-- In Hammerspoon Console:
-- dofile("/tmp/nk-scene2-led-bank.lua")
-- Press MUTE 1..8, then SOLO 1..8 in physical order, then:
-- nkScene2BankLedProbe.flashAll()
-- nkScene2BankLedProbe.stop() -- cleanup
if type(_G.nkScene2BankLedProbe) == "table"
  and type(_G.nkScene2BankLedProbe.stop) == "function" then
  _G.nkScene2BankLedProbe.stop()
end

local names = {}
for i=1,8 do names[#names+1] = "MUTE "..i end
for i=1,8 do names[#names+1] = "SOLO "..i end

local deviceName
for _, name in ipairs(hs.midi.devices()) do
  local candidate = name:lower()
  if candidate:find("nanokontrol",1,true)
    and candidate:find("studio",1,true) then deviceName=name; break end
end
if not deviceName then
  hs.printf("[NK LED BANK] BLOCKED: nanoKONTROL Studio unavailable; RESOLVE_WRITES=0")
  return nil
end
local device = hs.midi.new(deviceName)
if not device then
  hs.printf("[NK LED BANK] BLOCKED: MIDI connection unavailable; RESOLVE_WRITES=0")
  return nil
end
local probe = {device=device, names=names, learned={}, seen={},
  count=0, timers={}, active=true, flashing=false}

local function send(cc, value)
  if not probe.active or type(cc)~="number" then return false end
  local ok, accepted = pcall(function()
    return device:sendCommand("controlChange", {
      channel=1, controllerNumber=cc, controllerValue=value
    })
  end)
  hs.printf("[NK LED BANK] SEND ch=1 cc=%d value=%d api_ok=%s api_result=%s",
    cc,value,tostring(ok),tostring(accepted))
  return ok and accepted==true
end

local function delay(seconds, callback)
  local timer = hs.timer.doAfter(seconds, callback)
  probe.timers[#probe.timers+1] = timer
end

function probe.stop()
  if not probe.active then return end
  for _, timer in ipairs(probe.timers) do timer:stop() end
  probe.timers = {}
  probe.flashing = false
  for _, cc in ipairs(probe.learned) do send(cc,0) end
  device:callback(nil)
  probe.active = false
  if _G.nkScene2BankLedProbe == probe then
    _G.nkScene2BankLedProbe = nil
  end
  hs.printf("[NK LED BANK] STOPPED; RESOLVE_WRITES=0")
end

function probe.show()
  hs.printf("[NK LED BANK] LEARNED=%d/16; RESOLVE_WRITES=0",probe.count)
  for i=1,probe.count do
    hs.printf("[NK LED BANK] %s CC%d", names[i], probe.learned[i])
  end
end

function probe.flashAll()
  if not probe.active or probe.flashing or probe.count~=16 then
    hs.printf("[NK LED BANK] BLOCKED: need 16 unique learned buttons first")
    return false
  end
  probe.flashing = true
  hs.printf("[NK LED BANK] CHASE START; 16 commanded LEDs; RESOLVE_WRITES=0")
  local function pulse(index)
    if not probe.active then return end
    if index>16 then
      probe.flashing=false
      hs.printf("[NK LED BANK] CHASE COMPLETE; VISUAL_CONFIRMATION_REQUIRED; RESOLVE_WRITES=0")
      return
    end
    local cc = probe.learned[index]
    hs.printf("[NK LED BANK] ON: %s CC%d",names[index],cc)
    if not send(cc,127) then
      hs.printf("[NK LED BANK] SEND FAILED; STOPPING")
      probe.stop()
      return
    end
    delay(0.55,function()
      if not probe.active then return end
      if not send(cc,0) then
        hs.printf("[NK LED BANK] OFF FAILED; STOPPING")
        probe.stop()
        return
      end
      delay(0.15,function() pulse(index+1) end)
    end)
  end
  pulse(1)
  return true
end

device:callback(function(_,_,command,_,meta)
  if not probe.active or probe.flashing or probe.count==16
    or command~="controlChange" or type(meta)~="table"
    or meta.channel~=1 or meta.controllerValue~=127
    or type(meta.controllerNumber)~="number" then return end
  local cc=meta.controllerNumber
  -- Ignore rotary/fader CCs (1..20) and already registered buttons.
  if cc<21 or cc>127 or probe.seen[cc] then return end
  local index=probe.count+1
  probe.learned[index]=cc
  probe.seen[cc]=true
  probe.count=index
  hs.printf("[NK LED BANK] LEARNED %02d/16 %s: ch=1 cc=%d",
    index,names[index],cc)
  if index==16 then
    if probe.learned[1]~=21 or probe.learned[9]~=29 then
      hs.printf("[NK LED BANK] WARNING: MUTE1/SOLO1 differ from CC21/CC29 previously proved; verify physical order")
    end
    hs.printf("[NK LED BANK] READY: nkScene2BankLedProbe.flashAll()")
  else
    hs.printf("[NK LED BANK] NEXT: press Scene 2 %s",names[index+1])
  end
end)

_G.nkScene2BankLedProbe=probe
delay(300, function()
  if probe.active then
    hs.printf("[NK LED BANK] 5-minute timeout; cleaning up")
    probe.stop()
  end
end)
hs.printf("[NK LED BANK] START: Scene 2; press MUTE 1 through 8, then SOLO 1 through 8; RESOLVE_WRITES=0")
return probe
