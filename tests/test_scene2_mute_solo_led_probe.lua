-- Standalone LED-probe behavior. No Resolve calls, shortcuts or config changes.
local logs, sent, timers, instances = {}, {}, {}, {}
hs = {
  printf = function(fmt, ...)
    logs[#logs+1] = string.format(fmt, ...)
  end,
  midi = {
    devices = function() return {"Other", "nanoKONTROL Studio"} end,
    new = function(name)
      assert(name == "nanoKONTROL Studio")
      local dev = {}
      function dev:callback(cb) self.cb = cb end
      function dev:sendCommand(kind, meta)
        assert(kind == "controlChange")
        assert(meta.channel == 1, "output must target Scene 2, not all channels")
        sent[#sent+1] = {cc=meta.controllerNumber, value=meta.controllerValue}
        return true
      end
      instances[#instances+1] = dev
      return dev
    end,
  },
  timer = {
    doAfter = function(_, cb)
      local timer = {callback = cb, canceled = false}
      function timer:stop() self.canceled = true end
      timers[#timers+1] = timer
      return timer
    end
  }
}
local function fireNext()
  for _, timer in ipairs(timers) do
    if timer.callback and not timer.canceled then
      local cb = timer.callback
      timer.callback = nil
      cb()
      return
    end
  end
  error("no timer to fire")
end
local probe = assert(loadfile("scripts/scene2_mute_solo_led_probe.lua"))()
local dev = probe.device
assert(probe.flash() == false, "must not flash before learning")
assert(#sent == 0, "no output until explicit flash")
dev.cb(dev, "nanoKONTROL Studio", "controlChange", "", {
  channel=0, controllerNumber=40, controllerValue=127
})
assert(probe.learned[1] == nil)
dev.cb(dev, "nanoKONTROL Studio", "controlChange", "", {
  channel=1, controllerNumber=40, controllerValue=0
})
assert(probe.learned[1] == nil)
dev.cb(dev, "nanoKONTROL Studio", "controlChange", "", {
  channel=1, controllerNumber=40, controllerValue=127
})
assert(probe.learned[1] == 40)
dev.cb(dev, "nanoKONTROL Studio", "controlChange", "", {
  channel=1, controllerNumber=40, controllerValue=127
})
assert(probe.learned[2] == nil)
dev.cb(dev, "nanoKONTROL Studio", "controlChange", "", {
  channel=1, controllerNumber=48, controllerValue=127
})
assert(probe.learned[2] == 48)
assert(#sent == 0)
assert(probe.flash() == true)
assert(probe.flash() == false, "must not overlap")
assert(sent[1].cc == 40 and sent[1].value == 127)
fireNext()
assert(sent[2].cc == 40 and sent[2].value == 0)
fireNext()
assert(sent[3].cc == 48 and sent[3].value == 127)
fireNext()
assert(sent[4].cc == 48 and sent[4].value == 0)
probe.stop()
assert(dev.cb == nil)
assert(sent[5].cc == 40 and sent[5].value == 0)
assert(sent[6].cc == 48 and sent[6].value == 0)
assert(_G.nkScene2LedProbe == nil)
for _, line in ipairs(logs) do
  assert(not line:find("AUDIO_GAIN_WRITE"))
end
print("SCENE2_MUTE_SOLO_LED_PROBE_TEST=PASS")
