-- Offline, no real MIDI or filesystem: test timestamped ch0/ch1 raw logging.
local logs, writes, timers = {}, {}, {}
local opened, closed, callbackCount = false, false, 0
local originalOpen = io.open
io.open = function(path, mode)
  assert(mode == "w")
  assert(path:find("/Library/Caches/nk-midi-timestamped-", 1, true))
  assert(path:sub(-4) == ".csv")
  opened = true
  local file = {}
  function file:write(text)
    assert(not closed)
    writes[#writes + 1] = text
    return self
  end
  function file:flush()
    assert(not closed)
    return self
  end
  function file:close()
    closed = true
    return true
  end
  return file
end
local clockNs = 100000000000
local epoch = 1761290000.123
local hardware
hs = {
  printf = function(fmt, ...)
    logs[#logs + 1] = string.format(fmt, ...)
  end,
  timer = {
    absoluteTime = function()
      clockNs = clockNs + 10000000
      return clockNs
    end,
    secondsSinceEpoch = function()
      epoch = epoch + 0.013
      return epoch
    end,
    doAfter = function(seconds, cb)
      assert(seconds == 120)
      local timer = {cb = cb, stopped = false}
      function timer:stop() self.stopped = true end
      timers[#timers + 1] = timer
      return timer
    end,
  },
  midi = {
    devices = function() return {"Other", "nanoKONTROL Studio"} end,
    new = function(name)
      assert(name == "nanoKONTROL Studio")
      local dev = {}
      function dev:callback(cb)
        self.cb = cb
        callbackCount = callbackCount + 1
      end
      hardware = dev
      return dev
    end,
  },
}
local probe = assert(loadfile("scripts/scene2_timestamped_midi_probe.lua"))()
io.open = originalOpen
assert(opened and not closed)
assert(probe.phase == "UNMARKED")
assert(not probe.mark("SCENE0"), "unknown marker must be rejected")
assert(probe.mark("SCENE1"))
hardware.cb(hardware, "nanoKONTROL Studio", "controlChange", "", {
  channel = 0, controllerNumber = 16, controllerValue = 64,
  data = "B0 10 40", timestamp = "MIDI_EVENT_1",
})
assert(probe.mark("SCENE2"))
hardware.cb(hardware, "nanoKONTROL Studio", "controlChange", "", {
  channel = 1, controllerNumber = 16, controllerValue = 65,
  data = "B1 10 41", timestamp = "MIDI_EVENT_2",
})
-- Other CC is logged, not misinterpreted as a knob or dropped.
hardware.cb(hardware, "nanoKONTROL Studio", "controlChange", "", {
  channel = 1, controllerNumber = 21, controllerValue = 127,
  data = "B1 15 7F", timestamp = "MIDI_EVENT_3",
})
hardware.cb(hardware, "nanoKONTROL Studio", "noteOn", "", {
  channel = 1, note = 60, velocity = 127,
})
assert(probe.events == 3)
assert(probe.count["SCENE1 CHANNEL=0 CC=16"] == 1)
assert(probe.count["SCENE2 CHANNEL=1 CC=16"] == 1)
assert(probe.count["SCENE2 CHANNEL=1 CC=21"] == 1)
probe.stop()
assert(closed)
assert(hardware.cb == nil)
assert(callbackCount == 2)
assert(timers[1].stopped)
assert(_G.nkMidiTs == nil)
assert(not probe.mark("SCENE2"), "cannot restart stopped logger")
local csv = table.concat(writes)
assert(csv:find("kind,epoch_ms,elapsed_ms,phase,channel,cc,value,raw_hex,midi_timestamp",1,true))
assert(csv:find("MARK,",1,true))
assert(csv:find(",SCENE1,0,16,64,B0 10 40,MIDI_EVENT_1",1,true))
assert(csv:find(",SCENE2,1,16,65,B1 10 41,MIDI_EVENT_2",1,true))
assert(csv:find(",SCENE2,1,21,127,B1 15 7F,MIDI_EVENT_3",1,true))
local summary = table.concat(logs, "\n")
assert(summary:find("SCENE1 CHANNEL=0 CC=16 COUNT=1",1,true))
assert(summary:find("SCENE2 CHANNEL=1 CC=16 COUNT=1",1,true))
assert(summary:find("RAW=B0 10 40",1,true))
assert(summary:find("RAW=B1 10 41",1,true))
assert(summary:find("WRITES=0",1,true))
print("SCENE2_TIMESTAMPED_MIDI_PROBE_TEST=PASS")
