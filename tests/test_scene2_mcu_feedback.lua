-- Offline Scene2 mixer LED tests: only host MCU feedback lights LEDs.
local now = 1800000000
local eventLines = {}
local feedback = ""
local calls = {}
local timers = {}
local ioOld = io.open
io.open = function(path, mode)
  if path:find("nk-scene2-controller-events.csv", 1, true) then
    assert(mode == "w")
    local out = {}
    function out:write(line) eventLines[#eventLines+1] = line; return self end
    function out:flush() return self end
    function out:close() return true end
    return out
  end
  assert(path:find("nk-fairlight-mcu-feedback.csv", 1, true))
  assert(mode == "r")
  local fd = {cursor=1}
  function fd:seek(origin,offset)
    if origin == "end" then self.cursor=#feedback+1; return #feedback end
    if origin == "set" then self.cursor=(offset or 0)+1; return offset or 0 end
    error("unsupported seek")
  end
  function fd:read()
    local p = feedback:find("\n", self.cursor, true)
    if not p then return nil end
    local text = feedback:sub(self.cursor,p-1)
    self.cursor=p+1
    return text
  end
  function fd:lines()
    return function() return self:read("*l") end
  end
  function fd:close() return true end
  return fd
end

local host = {
  timer={
    secondsSinceEpoch=function() return now end,
    doEvery=function(seconds,fn)
      assert(seconds==0.5)
      local timer={stopped=false,fn=fn}
      function timer:stop() self.stopped=true end
      timers[#timers+1]=timer
      return timer
    end,
  },
  printf=function() end,
}
local factory = assert(loadfile("scene2_clip_gain_bridge.lua"))()
local resolveReady = true
local bridge = factory(host, function() return resolveReady end)
bridge:setLedSender(function(cc,on)
  calls[#calls+1] = {cc=cc,on=on}
  return true
end)
local function latest(cc)
  for i=#calls,1,-1 do
    if calls[i].cc == cc then return calls[i].on end
  end
  return nil
end
local function t()
  return math.floor(now*1000+0.5)
end
feedback = ("%d,H,0,1\n%d,L,21,127\n%d,L,29,127\n"):format(t(),t(),t())
assert(bridge:start())
assert(latest(21)==true and latest(29)==true,
  "Only fresh host MCU feedback should illuminate mixer LEDs")
local count=#calls
bridge:publish("controlChange",
  {channel=1,controllerNumber=21,controllerValue=127})
assert(#calls==count, "physical button press MUST NOT change LED state")
local out=table.concat(eventLines)
assert(out:find(",M,1,21,127",1,true),
  "physical MUTE must be forwarded to the MCU candidate stream")
bridge:publish("controlChange",
  {channel=1,controllerNumber=2,controllerValue=64})
bridge:publish("controlChange",
  {channel=1,controllerNumber=33,controllerValue=127})
bridge:publish("controlChange",
  {channel=1,controllerNumber=32,controllerValue=127})
out=table.concat(eventLines)
assert(out:find(",M,1,2,64",1,true))
assert(out:find(",M,1,33,127",1,true))
assert(not out:find(",M,1,32,127",1,true),
  "reserved CC32 is not SOLO4")
feedback = ("%d,H,0,1\n%d,L,21,0\n%d,L,29,127\n"):format(t(),t(),t())
now=now+.5
timers[1].fn()
assert(latest(21)==false and latest(29)==true,
  "changed Fairlight LED feedback must override previous authoritative state")
-- A silent Korg Scene switch blanks physical LEDs. With host feedback
-- unchanged, Scene2 must periodically reassert only known host states.
feedback = ("%d,H,0,1\n%d,L,21,0\n%d,L,29,127\n"):format(t(),t(),t())
local reassertBefore = #calls
now=now+.5
timers[1].fn()
assert(#calls > reassertBefore,
  "active Scene2 must periodically reassert known host mixer LEDs")
local afterReassert = #calls
bridge:publish("controlChange",
  {channel=0,controllerNumber=21,controllerValue=127})
assert(#calls > afterReassert and latest(29)==false,
  "leaving Scene2 must blank the last host-authoritative mixer LEDs")
local afterSwitch = #calls
now=now+.5
timers[1].fn()
assert(#calls == afterSwitch,
  "other scenes must not receive periodic Scene2 reassertions")
bridge:publish("controlChange",
  {channel=1,controllerNumber=21,controllerValue=127})
now=now+.5
timers[1].fn()
assert(#calls > afterSwitch and latest(29)==true,
  "return to Scene2 must restore latest host state without inventing button presses")

resolveReady = false
feedback = ("%d,H,0,0\n"):format(t())
now=now+.5
timers[1].fn()
assert(latest(29)==false,
  "focus loss must send LED OFF BEFORE physical Scene2 ownership is cleared")
assert(bridge.lastScene == nil,
  "focus loss must rearm Scene2 without leaving stale physical scene ownership")
resolveReady = true
feedback = ("%d,H,0,1\n%d,L,37,127\n"):format(t(),t())
now=now+.5
timers[1].fn()
assert(latest(37)==true, "eighth solo uses skipped CC32 pattern")
now=now+3
timers[1].fn()
assert(latest(37)==false, "stale/absent host feedback cannot latch LEDs forever")
bridge:stop()
assert(timers[1].stopped)
io.open=ioOld
print("SCENE2_MCU_AUTHORITATIVE_LED_TEST=PASS")
