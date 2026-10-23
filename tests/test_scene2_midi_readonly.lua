-- Passive Scene 2 MIDI probe regression; no Resolve or MIDI setters.
local logs, devices = {}, {}
hs = {
  printf = function(fmt, ...)
    logs[#logs + 1] = string.format(fmt, ...)
  end,
  midi = {
    devices = function()
      return {"Other", "nanoKONTROL Studio"}
    end,
    new = function(name)
      assert(name == "nanoKONTROL Studio")
      local dev = { callbackCount = 0 }
      function dev:callback(fn)
        self.callbackCount = self.callbackCount + 1
        self.fn = fn
      end
      devices[#devices + 1] = dev
      return dev
    end,
  },
}
local file = "scripts/scene2_midi_readonly.lua"
local d1 = assert(loadfile(file))()
assert(d1 == _G.nkScene2MidiProbe and type(d1.fn) == "function")
assert(logs[#logs]:find("WRITE=0", 1, true))
d1.fn(d1, "nanoKONTROL Studio", "controlChange", "", {
  channel = 0, controllerNumber = 13, controllerValue = 127,
})
assert(#logs == 1, "Scene 1 must not appear in Scene 2 probe")
d1.fn(d1, "nanoKONTROL Studio", "noteOn", "", {
  channel = 1, note = 13, velocity = 127,
})
assert(#logs == 1, "Notes must not be logged")
d1.fn(d1, "nanoKONTROL Studio", "controlChange", "", {
  channel = 1, controllerNumber = 13, controllerValue = 0, data = "B1 0D 00",
})
assert(#logs == 2 and logs[2]:find("ch=1 cc=13 value=0", 1, true))
d1.fn(d1, "nanoKONTROL Studio", "controlChange", "", {
  channel = 1, controllerNumber = 20, controllerValue = 127, data = "B1 14 7F",
})
assert(#logs == 3 and logs[3]:find("cc=20 value=127", 1, true))
local d2 = assert(loadfile(file))()
assert(d1.fn == nil and d2.fn and d2 ~= d1, "reloading must detach old logger")
d2:callback(nil)
_G.nkScene2MidiProbe = nil
assert(d2.fn == nil)
print("SCENE2_MIDI_READONLY_TEST=PASS")
