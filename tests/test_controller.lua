-- Deterministic simulation. No physical Korg, no Resolve or macOS APIs.
local keys, sent, timers = {}, {}, {}
local midiCallback, menuCallback, now = nil, nil, 1000
local saved = {
  wheel = "cc:1:82",
  faderShuttle = "cc:1:2",
  buttons = {
    cycle = "cc:1:54", stop = "cc:1:59", play = "cc:1:60",
    rew = "cc:1:58", ff = "cc:1:61", undo = "cc:1:63",
    cutPage = "cc:1:21", editPage = "cc:1:22",
    cam1 = "cc:1:29", cam2 = "cc:1:30",
    editSelect = "cc:1:80", splitAll = "cc:1:25",
  }
}
local menus = {}
local app = {
  title = function() return "DaVinci Resolve" end,
  bundleID = function() return "com.blackmagic-design.DaVinciResolve" end,
  selectMenuItem = function() return true end,
}
hs = {
  settings = {get = function() return saved end, set = function(_, v) saved = v end},
  alert = {show = function() end},
  printf = function() end,
  eventtap = {keyStroke = function(_, ch) table.insert(keys, ch) end},
  application = {frontmostApplication = function() return app end},
  timer = {
    secondsSinceEpoch = function() return now end,
    doAfter = function(delay, fn)
      local timer = {delay = delay, fn = fn, stopped = false}
      function timer:stop() self.stopped = true end
      table.insert(timers, timer)
      return timer
    end,
  },
  menubar = {
    new = function()
      local m = {}
      function m:setTitle(text) self.title = text end
      function m:setMenu(fn) menuCallback = fn end
      return m
    end,
  },
  midi = {
    devices = function() return {"nanoKONTROL Studio"} end,
    virtualSources = function() return {} end,
    deviceCallback = function() end,
    new = function()
      return {
        callback = function(_, fn) midiCallback = fn end,
        sendCommand = function(_, typ, meta)
          table.insert(sent, {typ = typ, meta = meta})
          return true
        end,
      }
    end,
  },
  accessibilityState = function() return true end,
}
local loaded = assert(loadfile("nanokontrol_resolve21.lua"))()
assert(type(loaded) == "table" and midiCallback and menuCallback, "module failed to initialize")
local function cc(n,v)
  midiCallback(nil, "nanoKONTROL Studio", "controlChange", nil,
    {channel = 1, controllerNumber = n, controllerValue = v})
end
local function flushTimers()
  local n = 0
  while #timers > 0 do
    n = n + 1
    assert(n < 30, "recursive timers")
    local batch = timers
    timers = {}
    for _, t in ipairs(batch) do if not t.stopped then t.fn() end end
    now = now + 1
  end
end
local function countKeys(k)
  local n = 0
  for _, x in ipairs(keys) do if x == k then n = n + 1 end end
  return n
end
local function menuAction(fragment)
  for _, row in ipairs(menuCallback()) do
    if row.title and row.title:find(fragment, 1, true) and row.fn then
      return row.fn()
    end
  end
  error("Missing menu item: " .. fragment)
end
-- Boot should NOT run transport commands even if the fader starts far from center.
cc(2, 127)
flushTimers()
assert(#keys == 0, "unexpected command before fader centered")
cc(2, 64)
assert(#keys == 0, "centering must only arm")
cc(2, 127)
flushTimers()
assert(countKeys("k") == 1 and countKeys("l") == 4,
  "FADER 1 full forward must send K, then L x4")
local prior = #keys
-- While fader shuttle is active, the large wheel is not allowed to nudge frames.
cc(82, 1)
assert(#keys == prior, "JOG must be gated during active fader shuttle")
cc(2, 64)
assert(countKeys("k") == 2, "FADER 1 center must STOP")
-- Reaching center after STOP is required to re-arm.
cc(59, 127)
prior = #keys
cc(2, 127)
flushTimers()
assert(#keys == prior, "STOP must disarm until return to center")
cc(2, 64)
cc(2, 0)
flushTimers()
assert(countKeys("j") == 4, "reverse full-scale should send J x4")
-- LED mode opt-in. Active camera/button state is local only.
menuAction("LED feedback BE/KI")
local emitted = #sent
assert(emitted > 0, "LED refresh did not transmit commands")
cc(29, 127)
assert(countKeys("1") == 1, "camera 1 mapping")
local camOn = false
for _, output in ipairs(sent) do
  if output.typ == "controlChange" and output.meta.controllerNumber == 29
    and output.meta.controllerValue == 127 then camOn = true end
end
assert(camOn, "MUTE 1 LED did not light")
cc(21, 127)
local cutOn = false
for _, output in ipairs(sent) do
  if output.typ == "controlChange" and output.meta.controllerNumber == 21
    and output.meta.controllerValue == 127 then cutOn = true end
end
assert(cutOn, "SELECT 1 LED did not light")
menuAction("LED feedback BE/KI")
assert(#sent > emitted, "LED disable should send OFF")
print("MIDI_SIMULATION=PASS")
