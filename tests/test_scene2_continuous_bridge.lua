-- Hardware-free, no Resolve edits, no second MIDI callback.
-- Exercises the optional bridge that is called by the EXISTING controller.
local originalOpen = io.open
local now = 1800000000
local logs, lines = {}, {}
local openCount, closeCount = 0, 0
local heartbeat
local ready = true
io.open = function(path, mode)
  assert(path:find("/Library/Caches/nk-scene2-controller-events.csv", 1, true))
  assert(mode == "w")
  openCount = openCount + 1
  local file = {closed = false}
  function file:write(line)
    assert(not self.closed)
    lines[#lines + 1] = line
    return self
  end
  function file:flush()
    assert(not self.closed)
    return self
  end
  function file:close()
    assert(not self.closed)
    self.closed = true
    closeCount = closeCount + 1
    return true
  end
  return file
end
local hs = {
  timer = {
    secondsSinceEpoch = function() return now end,
    doEvery = function(interval, cb)
      assert(interval == 0.5)
      heartbeat = {cb = cb, stopped = false}
      function heartbeat:stop() self.stopped = true end
      return heartbeat
    end,
  },
  printf = function(fmt, ...)
    logs[#logs + 1] = string.format(fmt, ...)
  end,
}
local factory = assert(loadfile("scene2_clip_gain_bridge.lua"))()
local bridge = factory(hs, function() return ready end)
assert(bridge.active == false, "must be opt-in")
assert(openCount == 0, "no files opened on module load")
assert(bridge:start() == true)
assert(bridge.active and openCount == 1)
local function midi(ch, cc, val)
  now = now + .02
  bridge:publish("controlChange", {
    channel=ch, controllerNumber=cc, controllerValue=val})
end
midi(1,16,97)
midi(1,16,97) -- duplicate must not fill the log
midi(1,16,98)
midi(1,17,46)
midi(1,21,127) -- MUTE candidate: published only as M, never clip gain
midi(1,8,50)  -- Factory slider 6, MCU strip 6
midi(1,9,51)  -- Factory slider 7, MCU strip 7
midi(1,12,52) -- Factory slider 8, MCU strip 8 (locked by Python)
midi(1,7,53)  -- No physical fader uses CC7
midi(1,10,54) -- No physical fader uses CC10
midi(1,11,55) -- No physical fader uses CC11
midi(0,16,65) -- Scene 1: one RESET, no gain
midi(0,16,66) -- do not spam repeated resets
midi(1,16,98) -- scene switch cleared last value
ready = false
heartbeat.cb() -- controls disabled/not frontmost -> H=0
midi(1,16,99) -- suppressed while Resolve not frontmost
ready = true
heartbeat.cb() -- H=1 before fresh scene2 events
midi(1,16,98) -- first knob event after focus return logged again
bridge:stop()
assert(not bridge.active)
assert(heartbeat.stopped)
assert(closeCount == 1 and openCount == 1)
assert(bridge.events == 9, "5 rotary changes + 4 mixer candidates, got "
  .. tostring(bridge.events))
assert(bridge:start(), "explicit restart should be possible")
assert(openCount == 2)
bridge:stop()
assert(closeCount == 2)
local out = table.concat(lines)
assert(out:find("kind,channel,cc,value; H=heartbeat", 1, true))
assert(out:find(",H,0,0,1",1,true))
assert(out:find(",H,0,0,0",1,true))
assert(out:find(",C,1,16,97",1,true))
assert(out:find(",C,1,16,98",1,true))
assert(out:find(",C,1,17,46",1,true))
assert(out:find(",R,0,16,65",1,true))
assert(not out:find(",C,1,21,127",1,true))
assert(out:find(",M,1,21,127",1,true))
assert(out:find(",M,1,8,50",1,true))
assert(out:find(",M,1,9,51",1,true))
assert(out:find(",M,1,12,52",1,true))
assert(not out:find(",M,1,7,53",1,true))
assert(not out:find(",M,1,10,54",1,true))
assert(not out:find(",M,1,11,55",1,true))
local resetCount=0
for _ in out:gmatch(",R,0,16,") do resetCount=resetCount+1 end
assert(resetCount == 1)
assert(type(hs.midi) == "nil", "bridge must NOT acquire a second MIDI input")
print("SCENE2_CONTINUOUS_INPUT_BRIDGE_TEST=PASS")
