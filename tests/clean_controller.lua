-- Hardware-free regression test for the one-shot 28-step MIDI wizard.
local menus, queue, keys, outputs, repeatingTimers = {}, {}, {}, {}, {}
local saved, midiCallback, keyboardCallback, keyboardTap = nil, nil, nil, nil
local nowSeconds = 1000
local SPACE_KEYCODE = 49
local TRANSPORT_KEYCODES = {space=SPACE_KEYCODE,j=38,k=40,l=37}
local alerts, midiLogs, urlEvents = {}, {}, {}
local reloadCount = 0
-- Simulated device with a scene-local LED memory and one working output
-- route per scene. Unlike the Korg, the mock can inspect both states.
local activeHardwareScene = 1
local sceneExternal = {[1]=true,[2]=true,[3]=false,[4]=false,[5]=false}
local sceneLEDs = {[1]={},[2]={},[3]={},[4]={},[5]={}}
local function selectHardwareScene(scene)
  activeHardwareScene = scene
  sceneLEDs[scene] = {} -- Korg manual: changing a scene clears all LEDs
end
local app = {
  title=function() return "DaVinci Resolve" end,
  bundleID=function() return "com.blackmagic-design.DaVinciResolve" end,
  selectMenuItem=function() return true end,
}
local frontmost = app
local function keyEvent(keycode, flags, autorepeat)
  return {
    getKeyCode=function() return keycode end,
    getFlags=function() return flags or {} end,
    getProperty=function() return autorepeat or 0 end,
  }
end
hs = {
  keycodes={map=TRANSPORT_KEYCODES},
  settings = {
    get=function() return {wheel="cc:1:86", buttons={stop="cc:1:59"}} end,
    set=function(_,value) saved=value end,
  },
  alert={show=function(msg) alerts[#alerts+1]=msg end},
  printf=function(fmt,...) midiLogs[#midiLogs+1]=string.format(fmt, ...) end,
  reload=function() reloadCount=reloadCount+1 end,
  urlevent={bind=function(name,callback) urlEvents[name]=callback end},
  application={frontmostApplication=function() return frontmost end},
  eventtap={
    event={types={keyDown=10},properties={keyboardEventAutorepeat=99}},
    new=function(types,fn)
      assert(#types==1 and types[1]==10,"only watch keyboard keyDown")
      keyboardCallback=fn
      keyboardTap={active=false}
      function keyboardTap:start() self.active=true;return self end
      return keyboardTap
    end,
    keyStroke=function(mods,k)
      keys[#keys+1]={key=k,mods=mods}
      -- Worst case: Hammerspoon observes synthetic J/K/L/Space synchronously.
      -- The watcher must not count any of those as physical key presses.
      if keyboardCallback and TRANSPORT_KEYCODES[k] and #mods==0 then
        keyboardCallback(keyEvent(TRANSPORT_KEYCODES[k]))
      end
    end,
  },
  timer={secondsSinceEpoch=function() return nowSeconds end,
  doEvery=function(interval,fn)
    local t={interval=interval,fn=fn,stopped=false}
    function t:stop() self.stopped=true end
    repeatingTimers[#repeatingTimers+1]=t
    return t
  end,doAfter=function(delay,fn)
    local t={delay=delay,fn=fn,stopped=false}
    function t:stop() self.stopped=true end
    queue[#queue+1]=t
    return t
  end},
  menubar={new=function()
    local obj={}
    function obj:setTitle(v) menus.title=v end
    function obj:setMenu(cb) menus.items=cb end
    return obj
  end},
  midi={
    devices=function() return {"nanoKONTROL Studio"} end,
    deviceCallback=function() end,
    new=function()
      local dev={}
      function dev:callback(cb) midiCallback=cb end
      function dev:sendCommand(cmd,meta)
        outputs[#outputs+1]={cmd=cmd,cc=meta.controllerNumber,
          value=meta.controllerValue,channel=meta.channel}
        -- Scene 1 out=0 and Scene 2 out=1 were tested on hardware.
        -- Other scenes' output routes are candidate channels 2..4.
        local modeledScene = meta.channel >= 0 and meta.channel <= 4
          and meta.channel + 1 or nil
        if modeledScene == activeHardwareScene
          and sceneExternal[modeledScene] then
          sceneLEDs[modeledScene][meta.controllerNumber]=meta.controllerValue
        end
        return true
      end
      return dev
    end,
  },
}
local controller=assert(loadfile("nanokontrol_resolve21.lua"))()
assert(controller.ledHeartbeat==repeatingTimers[1],
  "LED heartbeat timer must be kept reachable after module load (GC safe)")
assert(controller.keyboardTap==keyboardTap and keyboardTap.active,
  "Keyboard event tap must be started and retained against GC")
local function cc(id,v,ch)
  assert(midiCallback)
  ch=ch or 0
  midiCallback(nil,"nanoKONTROL Studio","controlChange",nil,
    {channel=ch,controllerNumber=id,controllerValue=v,
    data=string.format('%02X %02X %02X',0xb0+ch,id,v)})
end
local function tickLED()
  assert(#repeatingTimers==1,"exactly one bounded LED heartbeat timer expected")
  assert(repeatingTimers[1].interval==0.5,"LED refresh should take 0.5 sec")
  assert(not repeatingTimers[1].stopped)
  repeatingTimers[1].fn()
end
local function runPending()
  local runs=0
  while #queue>0 do
    runs=runs+1; assert(runs<40,"runaway timers")
    local batch=queue;queue={}
    for _,t in ipairs(batch) do if not t.stopped then t.fn() end end
  end
end
local function keyCount(k)
  local n=0
  for _,entry in ipairs(keys) do if entry.key==k then n=n+1 end end
  return n
end
local function latestLED(cc)
  for i=#outputs,1,-1 do
    if outputs[i].cc==cc then return outputs[i].value end
  end
  return nil
end
local function allLEDBlanked(startIndex,endIndex)
  for i=startIndex or 1,endIndex or #outputs do
    if outputs[i].value~=0 or outputs[i].channel~=0
       or outputs[i].cmd~="controlChange" then return false end
  end
  return true
end
local function checkTransportLEDs(play,stop,rew,ff,label)
  for _,x in ipairs({
      {80,play,"PLAY"},{63,stop,"STOP"},{58,rew,"REW"},{59,ff,"FF"}
    }) do
    local want = x[2] and 127 or 0
    assert(latestLED(x[1])==want,
      (label or "transport").." "..x[3].." expected "..want
      .." got "..tostring(latestLED(x[1])))
  end
end
local function findMenuAction(items, label)
  for _,x in ipairs(items) do
    if x.title and x.title:find(label,1,true) and x.fn then
      return x.fn
    end
    if type(x.menu) == "table" then
      local nested = findMenuAction(x.menu, label)
      if nested then return nested end
    end
  end
  return nil
end
local function menuAction(label)
  local fn = findMenuAction(menus.items(), label)
  assert(fn, "menu item not found: "..label)
  return fn()
end
assert(menus.title=="NK JOG")
local daily = menus.items()
assert(#daily==4, "Daily menu: device, bank, restart, service")
assert(daily[1].disabled==true and
  daily[1].title:find("Korg:",1,true), "Device status is read-only")
assert(daily[2].title:find("Fairlight:",1,true) and daily[2].disabled,
  "Fairlight bank status must be read-only")
assert(daily[3].title=="Restart Controller" and
  type(daily[3].fn)=="function", "One-click restart must be present")
assert(daily[4].title=="Service & Diagnostics" and
  type(daily[4].menu)=="table", "Service is one compact submenu")
assert(type(daily[4].menu[#daily[4].menu].menu)=="table",
  "Calibration remains under service diagnostics")
assert(findMenuAction(daily,"Recalibrate all 28 controls"),
  "Calibration must remain reachable")
assert(findMenuAction(daily,"LED feedback:"),
  "LED diagnostics must remain reachable")
assert(type(daily[4].menu[2].fn)=="function",
  "Bank paging action must remain reachable for service")
assert(type(daily[4].menu[1].fn)=="function",
  "Service-only pause/resume action remains available")
assert(type(urlEvents["nk-controller-pause-for-update"])=="function"
  and type(urlEvents["nk-controller-restart"])=="function",
  "Local update workflow must register both callbacks")
-- Old v1.2 settings deliberately not reused as a valid v1.3 configuration.
local exists=false
for _,item in ipairs(menus.items()) do
  if item.title:find("Calibration required",1,true) then exists=true end
end
assert(exists,"must require clean recalibration")
menuAction("Recalibrate all 28 controls")
assert(menus.title=="NK SETUP 1/28")
-- Regression: a CC86 Continuous jog's clockwise values could previously
-- masquerade as CC82 Sign Magnitude and leave setup stuck on step 2/28.
cc(86,24)
cc(86,36)
cc(86,30)
assert(menus.title=="NK SETUP 1/28","Continuous CC86 must NOT pass step 1")
assert(alerts[#alerts]:find("CC86",1,true),"wrong MIDI mode must be diagnosed")
local sawUp, sawDown, sawRaw = false,false,false
for _,line in ipairs(midiLogs) do
  if line:find("controller=cc:0:86",1,true) and line:find("delta=+12",1,true) then sawUp=true end
  if line:find("controller=cc:0:86",1,true) and line:find("delta=-6",1,true) then sawDown=true end
  if line:find("raw=B0 56",1,true) then sawRaw=true end
end
assert(sawUp and sawDown and sawRaw,"MIDI Console logging should include channel=0, delta and raw bytes")
cc(82,1)
assert(menus.title=="NK SETUP 2/28")
cc(82,24)
assert(menus.title=="NK SETUP 2/28","clockwise magnitude must not pass CCW")
assert(alerts[#alerts]:find("JOG COUNTERCLOCKWISE",1,true),"wrong CCW magnitude must be diagnosed")
cc(82,65)
assert(menus.title=="NK SETUP 3/28")
-- 25 real button CCs in learn order, captured by the Korg MIDI logger.
local buttonIDs = {54,62,58,59,63,80,81,60,61,55,56,57,
  21,22,23,24,25,26,27,28,46,47,48,49,50}
for i=1,25 do
  local ccId=buttonIDs[i]
  assert(menus.title=="NK SETUP "..(i+2).."/28")
  cc(ccId,127)
  assert(menus.title=="NK SETUP "..(i+2).."/28","advanced before release")
  cc(ccId,0)
end
assert(menus.title=="NK SETUP 28/28")
-- Turning knob 1 (CC13) cannot accidentally become the first FADER.
cc(13,0);cc(13,127)
assert(menus.title=="NK SETUP 28/28")
-- An incomplete FADER movement is not enough.
cc(2,20);cc(2,95)
assert(menus.title=="NK SETUP 28/28")
cc(2,0);cc(2,127)
assert(menus.title=="NK JOG")
assert(saved and saved.setupVersion==2 and saved.faderShuttle=="cc:0:2")
assert(saved.wheel=="cc:0:82")
assert(saved.buttons.splitAll=="cc:0:50")
-- At successful 28/28 the External-mode controller receives a fresh OFF
-- on each known LED. Hardware test verified output channel 0 (ALL),
-- whereas output channel 1 returned true without lighting the Korg.
assert(#outputs==69,
  "44 Scene1 resets, 20 other-scene resets, then five STOP status LEDs")
assert(allLEDBlanked(1,44),"Scene1 initial LED OFF on output channel=0")
for outputChannel=1,4 do
  for i=45+(outputChannel-1)*5,49+(outputChannel-1)*5 do
    assert(outputs[i].channel==outputChannel and outputs[i].value==0,
      "shared LEDs must reset on Scenes 2-5 independently")
  end
end
for outputChannel=0,4 do
  local e=outputs[65+outputChannel]
  assert(e.cc==63 and e.channel==outputChannel and e.value==127,
    "STOP must latch in each Scene after learning")
end
checkTransportLEDs(false,true,false,false,"after 28/28 setup")
assert(outputs[1].channel==0,
  "normal LED feedback MUST use hardware-verified output=0, not the failed channel=1")
-- The physical fader can't start transport until it has been centered.
keys={}
cc(2,127)
runPending()
assert(#keys==0,"unarmed slider started playback")
cc(2,64)
assert(#keys==0,"centering should only arm")
cc(2,127)
runPending()
assert(keyCount("k")==1 and keyCount("l")==4,"4 forward JKL gears")
checkTransportLEDs(true,false,false,true,"FADER forward +4")
local n=#keys
cc(82,1)
assert(#keys==n,"wheel should not trim during live fader shuttle")
cc(2,64)
assert(keyCount("k")==2,"center STOP must send K")
checkTransportLEDs(false,true,false,false,"FADER centered")
-- STOP button disarms fader, must center again.
cc(63,127) -- physical STOP (CC63)
n=#keys
cc(2,127);runPending()
assert(#keys==n,"STOP must disarm fader")
cc(2,64);cc(2,0);runPending()
assert(keyCount("j")==4,"4 reverse JKL gears")
checkTransportLEDs(true,false,true,false,"FADER reverse -4")
-- A held marker changes wheel to edit-point nudge; release cancels.
cc(2,64);cc(80,127) -- physical PLAY
cc(55,127) -- physical MARKER SET 
cc(82,1)
assert(keyCount(".")==1,"held MARKER SET should trim")
cc(55,0)
cc(82,1)
assert(keyCount("right")>=1,"release restores plain JOG")
-- Wheel SHUTTLE response must be immediate (one tick) and burst-coalesced.
cc(54,127) -- physical CYCLE (CC54)
assert(menus.title=="NK SHUTTLE","CYCLE should switch to wheel SHUTTLE")
keys={}
cc(82,1)
assert(#keys==0,"one wheel event should queue a short batch, not K spam")
runPending()
assert(keyCount("k")==1 and keyCount("l")==1,
  "one jog tick must trigger one forward shuttle gear")
assert(menus.title=="NK SHUTTLE +1")
checkTransportLEDs(true,false,false,false,"SHUTTLE +1: normal 1x PLAY, no FF")
cc(82,65)
runPending()
assert(keyCount("k")==2,"one reverse tick at +1 must STOP shuttle")
assert(menus.title=="NK SHUTTLE")
checkTransportLEDs(false,true,false,false,"SHUTTLE back to zero")
keys={}
for _=1,4 do cc(82,1) end
assert(#keys==0,"fast MIDI burst should not restart Resolve 4 times")
runPending()
assert(keyCount("k")==1 and keyCount("l")==4,
  "four forward ticks must make one K then Lx4 (not four separate restarts)")
assert(menus.title=="NK SHUTTLE +4")
checkTransportLEDs(true,false,false,true,"SHUTTLE +4")
keys={}
cc(82,65)
runPending()
assert(keyCount("k")==1 and keyCount("l")==3,
  "one reverse tick at +4 should reduce to +3")
assert(menus.title=="NK SHUTTLE +3")
checkTransportLEDs(true,false,false,true,"SHUTTLE +3")
keys={}
cc(82,65) -- queue a wheel update
cc(63,127) -- physical STOP must cancel queued wheel changes
runPending()
assert(keyCount("k")==1 and keyCount("l")==0,
  "STOP must cancel a pending wheel batch")
assert(menus.title=="NK SHUTTLE")
checkTransportLEDs(false,true,false,false,"SHUTTLE STOP")

-- Absolute signed shuttle gears (0 is STOP): one physical pulse moves
-- one gear. +1 means normal 1x L, +2 is L twice and FF illuminates.
-- Crossing zero must stop before reverse. No overshoot when changing sign.
keys={}
cc(82,1);runPending()
assert(menus.title=="NK SHUTTLE +1"
  and keyCount("k")==1 and keyCount("l")==1,
  "0 -> +1 should generate one K + one L")
checkTransportLEDs(true,false,false,false,"wheel 0 -> +1")
cc(82,1);runPending()
assert(menus.title=="NK SHUTTLE +2"
  and keyCount("k")==2 and keyCount("l")==3,
  "+1 -> +2 should issue K and two L (2x)")
checkTransportLEDs(true,false,false,true,"wheel +1 -> +2: FF ON")
cc(82,65);runPending()
assert(menus.title=="NK SHUTTLE +1" and keyCount("l")==4,
  "+2 -> +1 should return to one L (1x)")
checkTransportLEDs(true,false,false,false,"wheel +2 -> +1: FF OFF")
cc(82,65);runPending()
assert(menus.title=="NK SHUTTLE" and keyCount("k")==4,
  "+1 -> 0 should stop, not reverse")
checkTransportLEDs(false,true,false,false,"wheel +1 -> 0 STOP")
cc(82,65);runPending()
assert(menus.title=="NK SHUTTLE -1" and keyCount("j")==1,
  "0 -> -1 must start normal reverse (J once)")
checkTransportLEDs(true,false,true,false,"wheel 0 -> -1: PLAY + REW")
cc(82,1);runPending()
assert(menus.title=="NK SHUTTLE" and keyCount("k")==6,
  "-1 -> 0 must STOP, not play forward")
checkTransportLEDs(false,true,false,false,"wheel -1 -> 0 STOP")

-- User-requested mixed controls: STOP -> FF must jump to +2 (2x).
-- From there, PLAY OR one wheel tick left must return to +1 (not STOP).
-- REW from STOP is -1, wheel right returns to zero.
keys={}
cc(59,127);cc(59,0);runPending()
assert(menus.title=="NK SHUTTLE +2",
  "Korg FF from STOP must set shared shuttle gear +2")
assert(keyCount("k")==1 and keyCount("l")==2,
  "Korg FF must send K then two L commands (2x)")
checkTransportLEDs(true,false,false,true,"STOP -> FF +2")
cc(82,65);runPending()
assert(menus.title=="NK SHUTTLE +1"
  and keyCount("k")==2 and keyCount("l")==3,
  "FF +2 followed by one wheel-left must downshift to +1, not -1")
checkTransportLEDs(true,false,false,false,"FF +2 -> wheel-left +1")
cc(63,127);cc(63,0)
checkTransportLEDs(false,true,false,false,"STOP after mixed FF/SHUTTLE")
keys={}
cc(59,127);cc(59,0);runPending()
assert(keyCount("k")==1 and keyCount("l")==2,
  "second STOP -> FF again must emit two L")
keys={}
cc(80,127);cc(80,0);runPending()
assert(menus.title=="NK SHUTTLE +1",
  "FF +2 -> PLAY must downgrade to +1 speed")
assert(keyCount("k")==1 and keyCount("l")==1
  and keyCount("space")==0,
  "PLAY from +2 must send K+L, not Space pause")
checkTransportLEDs(true,false,false,false,"FF +2 -> PLAY +1")
keys={}
cc(80,127);cc(80,0)
assert(keyCount("space")==1 and keyCount("k")==0,
  "PLAY again at +1 must retain PLAY -> PLAY pause toggle")
checkTransportLEDs(false,true,false,false,"PLAY +1 -> PLAY = pause")
keys={}
cc(58,127);cc(58,0);runPending()
assert(menus.title=="NK SHUTTLE -1"
  and keyCount("k")==1 and keyCount("j")==1,
  "REW from STOP must move reverse at -1")
checkTransportLEDs(true,false,true,false,"STOP -> REW -1")
cc(82,1);runPending()
assert(menus.title=="NK SHUTTLE" and keyCount("k")==2,
  "REW -1 then wheel-right must return to zero STOP")
checkTransportLEDs(false,true,false,false,"REW -1 -> wheel-right STOP")
-- PLAY from reverse playback returns to forward +1, not pause.
cc(58,127);cc(58,0);runPending()
keys={}
cc(80,127);cc(80,0);runPending()
assert(menus.title=="NK SHUTTLE +1"
  and keyCount("k")==1 and keyCount("l")==1
  and keyCount("space")==0,
  "REW -1 -> PLAY must switch to forward 1x")
checkTransportLEDs(true,false,false,false,"REW -1 -> PLAY +1")
cc(63,127);cc(63,0)

-- Reproduce: a single SHUTTLE tick starts playback, then keyboard Space
-- must pause it, without any manual STOP to resynchronize the PLAY LED.
keys={}
cc(82,1)
runPending()
assert(menus.title=="NK SHUTTLE +1","One wheel tick must start +1")
checkTransportLEDs(true,false,false,false,"single wheel tick starts PLAY, not FF")
local keysBeforeSpace=#keys
nowSeconds=1000.5 -- safely outside earlier synthetic Space guard
assert(keyboardCallback(keyEvent(SPACE_KEYCODE))==false,
  "Physical Space must reach Resolve during SHUTTLE")
assert(menus.title=="NK SHUTTLE","Space should keep mode but clear speed")
checkTransportLEDs(false,true,false,false,"physical Space stops shuttle")
assert(#keys==keysBeforeSpace,
  "Keyboard watcher must not synthesize K or another Space")
cc(82,1)
runPending()
assert(latestLED(80)==127,"Second SHUTTLE start must relight PLAY")
cc(80,127);cc(80,0)
assert(latestLED(80)==0,
  "Korg PLAY must pause an active SHUTTLE without separate STOP")
cc(54,127) -- physical CYCLE returns to JOG
assert(menus.title=="NK JOG")
keys={}
cc(82,1)
assert(keyCount("right")==1, "normal JOG must remain 1 frame per tick")

-- The Korg user can use the physical Resolve Space without resync STOP:
-- the eventtap observes the key but MUST not swallow it or emit extra keys.
cc(63,127);cc(63,0) -- known STOP state
keys={}
nowSeconds=1001
assert(keyboardCallback(keyEvent(SPACE_KEYCODE))==false,
  "physical Space must pass through to Resolve")
assert(#keys==0 and latestLED(80)==127,
  "keyboard Space must light PLAY without synthetic Resolve commands")
nowSeconds=1002
keyboardCallback(keyEvent(SPACE_KEYCODE))
assert(#keys==0 and latestLED(80)==0,
  "second physical Space must clear PLAY LED")
-- Modifiers, key autorepeat, other applications, uninteresting keys ignored.
keyboardCallback(keyEvent(SPACE_KEYCODE,{cmd=true}))
keyboardCallback(keyEvent(SPACE_KEYCODE,nil,1))
assert(latestLED(80)==0,"modified/repeated Space must not change PLAY LED")
frontmost={title=function() return "Hammerspoon" end,
  bundleID=function() return "org.hammerspoon.Hammerspoon" end}
keyboardCallback(keyEvent(SPACE_KEYCODE))
assert(latestLED(80)==0,"Space in another app must not affect Resolve state")
frontmost=app
keyboardCallback(keyEvent(0)) -- 'A' key, not Space
assert(latestLED(80)==0,"unrelated keys must not affect transport")
-- Korg PLAY posts its own Space. The event tap can receive that synthetic
-- event: the 150ms guard MUST stop a double toggle of transportIntent.
keys={}
nowSeconds=1003
cc(80,127);cc(80,0)
assert(keyCount("space")==1,"Korg PLAY must send exactly one Space")
checkTransportLEDs(true,false,false,false,"Korg PLAY")
nowSeconds=1003.2
keyboardCallback(keyEvent(SPACE_KEYCODE))
assert(keyCount("space")==1 and latestLED(80)==0,
  "physical Space after Korg PLAY must pause and clear LED without STOP")
nowSeconds=1004
keyboardCallback(keyEvent(SPACE_KEYCODE))
assert(latestLED(80)==127,
  "physical Space must resume and relight LED without STOP")
cc(63,127);cc(63,0) -- reset for the remainder of existing tests

-- Four keyboard transport commands change persistent LEDs without
-- generating another Resolve keystroke, and never swallow the original.
cc(63,127);cc(63,0)
keys={}
nowSeconds=1010
assert(keyboardCallback(keyEvent(TRANSPORT_KEYCODES.j))==false)
assert(#keys==0,"physical J must pass through unmodified")
checkTransportLEDs(true,false,true,false,"physical keyboard J")
nowSeconds=1011
assert(keyboardCallback(keyEvent(TRANSPORT_KEYCODES.l))==false)
checkTransportLEDs(true,false,false,false,"physical keyboard L once 1x")
nowSeconds=1011.5
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.l))
checkTransportLEDs(true,false,false,true,"physical keyboard L twice 2x")
nowSeconds=1012
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.k))
checkTransportLEDs(false,true,false,false,"physical keyboard K")
nowSeconds=1013
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.space))
checkTransportLEDs(true,false,false,false,"physical keyboard Space")
nowSeconds=1014
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.space))
checkTransportLEDs(false,true,false,false,"physical keyboard Space again")
assert(#keys==0,"physical JKL/Space watcher must never inject key events")
-- Modifiers and auto-repeat must never switch transport LED state.
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.j,{cmd=true}))
keyboardCallback(keyEvent(TRANSPORT_KEYCODES.l,nil,1))
checkTransportLEDs(false,true,false,false,"ignore modifiers and repeats")
-- Korg-generated synthetic JKL gets observed by our mock event tap, but
-- must be counted exactly once, including when we use JKL for SHUTTLE.
keys={}
cc(58,127);cc(58,0);runPending()
assert(keyCount("j")==1 and keyCount("k")==1,
  "Korg REW must issue K then J exactly once")
checkTransportLEDs(true,false,true,false,"Korg REW no double count")
cc(59,127);cc(59,0);runPending()
assert(keyCount("l")==2 and keyCount("k")==2,
  "Korg FF must issue K then two L, not one L")
checkTransportLEDs(true,false,false,true,"Korg FF +2 no double count")
cc(63,127);cc(63,0)
checkTransportLEDs(false,true,false,false,"Korg STOP no double count")

-- Complete one-shot relearn must preserve old saved config if interrupted.
local original=saved
menuAction("Recalibrate all 28 controls")
cc(82,1)
menuAction("Cancel calibration")
assert(saved==original,"aborted wizard must not overwrite settings")
-- Unbound SOLO CC is still a momentary LED, without triggering a shortcut.
local keyN=#keys
cc(29,127)
assert(latestLED(29)==127 and #keys==keyN,"unbound button LED press feedback")
cc(29,0)
assert(latestLED(29)==0,"unbound button LED release feedback")

-- Active PLAY light reflects local Space requests, not an unverified Resolve API.
keys={}
cc(80,127);cc(80,0)
assert(keyCount("space")==1 and keyCount("k")==0,
  "PLAY must send Space without a preceding K")
assert(latestLED(80)==127,"first PLAY must latch the local request LED")
cc(80,127);cc(80,0)
assert(keyCount("space")==2 and keyCount("k")==0,
  "second PLAY must pause with Space and no K")
checkTransportLEDs(false,true,false,false,"second Korg PLAY stops")

-- STOP stays illuminated after release until playback starts again.
cc(80,127);cc(80,0)
cc(63,127)
checkTransportLEDs(false,true,false,false,"STOP pressed")
cc(63,0)
checkTransportLEDs(false,true,false,false,"STOP released: latched")

-- CYCLE LED stays ON in SHUTTLE and goes OFF returning to JOG.
cc(54,127);cc(54,0)
assert(latestLED(54)==127,"CYCLE should show SHUTTLE")
cc(54,127);cc(54,0)
assert(latestLED(54)==0,"CYCLE should clear in JOG")

-- MUTE/CAM LED uses the received physical CC, not an inferred camera state.
cc(21,127)
assert(latestLED(21)==127,"MUTE 1 pressed LED")
cc(21,0)
assert(latestLED(21)==0,"MUTE 1 released LED")

-- The one LED menu toggle must turn *all* 44 LEDs off, and suspend feedback.
local after=#outputs
menuAction("LED feedback:")
assert(#outputs==after+64 and allLEDBlanked(after+1,after+44),
  "LED OFF clears Scene1's 44 buttons plus 4x5 shared LEDs")
for outputChannel=1,4 do
  for i=after+45+(outputChannel-1)*5,after+49+(outputChannel-1)*5 do
    assert(outputs[i].value==0 and outputs[i].channel==outputChannel,
      "LED OFF must clear shared transport LEDs for each of Scenes2-5")
  end
end
after=#outputs
cc(21,127);cc(21,0)
assert(#outputs==after,"LED disabled must send no ACK")
menuAction("LED feedback:")
assert(#outputs>=after+64 and latestLED(80)==0,
  "LED enable should refresh all five scene routes after a clean reset")

-- Hardware-only SCENE switching clears LEDs and emits NO MIDI input.
-- Scene 2 must still recover without pressing transport, using the second
-- output route while leaving the known-working Scene 1 route untouched.
keys={}
cc(80,127,0);cc(80,0,0)
assert(keyCount("space")==1,"Scene1 PLAY should start local playback")
assert(sceneLEDs[1][80]==127,"Scene1 PLAY should be physically lit")
selectHardwareScene(2)
assert(sceneLEDs[2][80]==nil,
  "Simulated scene switch must erase Scene2's local transport LEDs")
local outBeforeHeartbeat=#outputs
tickLED()
assert(#outputs==outBeforeHeartbeat+25,
  "LED heartbeat must re-send five shared CCs on all five routes")
local order={80,63,58,59,54}
for i,ccid in ipairs(order) do
  for outputChannel=0,4 do
    local e=outputs[outBeforeHeartbeat+(i-1)*5+outputChannel+1]
    assert(e.cc==ccid and e.channel==outputChannel,
      "shared transport wrong Scene output "..outputChannel.."/"..ccid)
  end
end
assert(sceneLEDs[2][80]==127 and sceneLEDs[2][63]==0
    and sceneLEDs[2][58]==0 and sceneLEDs[2][59]==0,
  "Scene2 PLAY must relight even without a MIDI scene change event")
assert(keyCount("space")==1 and keyCount("k")==0,
  "LED resync MUST NOT send any Resolve transport shortcut")
-- External is required per scene: a software command cannot change the
-- Korg's scene firmware setting or light an Internal-mode status LED.
sceneExternal[2]=false
selectHardwareScene(2)
tickLED()
assert(sceneLEDs[2][80]==nil,
  "Scene2 Internal LED Mode cannot be fixed by the Hammerspoon output")
sceneExternal[2]=true
tickLED()
assert(sceneLEDs[2][80]==127,"Restored Scene2 External should light again")
selectHardwareScene(1)
tickLED()
assert(sceneLEDs[1][80]==127,
  "Returning Scene1 must also restore transport feedback without MIDI")

-- Extend silent scene changes to Scenes 3-5. Their factory/old saved
-- Internal LED modes must first be switched to External on the device.
for scene=3,5 do
  selectHardwareScene(scene)
  tickLED()
  assert(sceneLEDs[scene][80]==nil,
    "without External mode, Scene3-5 cannot show software status")
  sceneExternal[scene]=true -- simulates Write Scene Data by the human
  tickLED()
  assert(sceneLEDs[scene][80]==127,
    "Scene"..scene.." External should restore PLAY status on heartbeat")
end
selectHardwareScene(1)
tickLED()
assert(sceneLEDs[1][80]==127,
  "Returning to Scene1 must not disturb its verified LED route")

-- The same PLAY/STOP/FF/REW strip works on Scenes 2 through 5, where
-- only the MIDI INPUT channel changes (same physical CCs).
cc(80,127,1);cc(80,0,1)
assert(keyCount("space")==2 and latestLED(80)==0,
  "Scene2 PLAY should pause the running Resolve with same physical CC")
cc(80,127,4);cc(80,0,4)
assert(keyCount("space")==3 and latestLED(80)==127,
  "Scene5 PLAY should restart with unchanged transport binding")
cc(63,127,1);cc(63,0,1)
assert(keyCount("k")==1 and latestLED(80)==0,
  "Scene2 STOP should stop Resolve and clear shared PLAY LED")
keys={}
cc(58,127,2);cc(58,0,2);runPending()
assert(keyCount("j")==1,"Scene3 REW must keep fixed J shortcut")
checkTransportLEDs(true,false,true,false,"Scene3 REW")
cc(59,127,3);cc(59,0,3);runPending()
assert(keyCount("l")==2,"Scene4 FF must send two L to reach +2")
checkTransportLEDs(true,false,false,true,"Scene4 FF button sends two L = 2x")
cc(62,127,4);cc(62,0,4)
assert(keyCount("left")==1,"Scene5 Return to Zero should keep Cmd+Left")
cc(60,127,2);cc(60,0,2)
assert(keyCount("up")==1,"Scene3 TRACK PREV should navigate")
cc(61,127,3);cc(61,0,3)
assert(keyCount("down")==1,"Scene4 TRACK NEXT should navigate")
keys={}
cc(54,127,1);cc(54,0,1)
assert(latestLED(54)==127,"Scene2 CYCLE turns on shared SHUTTLE LED")
tickLED()
assert(latestLED(54)==127,"Silent switch back to Scene1 must relight CYCLE")
cc(54,127,0);cc(54,0,0)
assert(latestLED(54)==0,"Scene1 CYCLE goes back to JOG")
-- The only supported Scene 2-5 wheel format is CC82 Sign Magnitude.
-- All five scenes must produce the same JOG frame steps as Scene 1.
cc(63,127,0);cc(63,0,0)
keys={}
for ch=0,4 do
  selectHardwareScene(ch+1)
  cc(82,1,ch)
  cc(82,65,ch)
end
assert(keyCount("right")==5 and keyCount("left")==5,
  "JOG must step one frame CW/CCW on each of the five input channels")
assert(keyCount("k")==0 and keyCount("l")==0 and keyCount("j")==0,
  "JOG must never accidentally trigger JKL playback")
-- Bug: JOG one frame while PLAY runs used to mark transport UNKNOWN,
-- blanking PLAY / STOP / REW / FF LEDs despite no transport command.
-- Jog arrow keys must leave the last known transport status intact in
-- every scene. Physical Space or K still changes the status normally.
keys={}
checkTransportLEDs(false,true,false,false,"STOP before jog regression")
cc(80,127,0);cc(80,0,0)
assert(keyCount("space")==1,"start one normal PLAY")
checkTransportLEDs(true,false,false,false,"PLAY before JOG")
for ch=0,4 do
  local beforeRight=keyCount("right")
  local beforeLeft=keyCount("left")
  cc(82,1,ch);cc(82,65,ch)
  assert(keyCount("right")==beforeRight+1
    and keyCount("left")==beforeLeft+1,
    "Scene"..(ch+1).." JOG must still step both directions")
  checkTransportLEDs(true,false,false,false,
    "PLAY LED must remain lit after Scene"..(ch+1).." JOG")
end
assert(keyCount("space")==1 and keyCount("k")==0,
  "JOG must not emit Space/K while normal PLAY is running")
tickLED()
checkTransportLEDs(true,false,false,false,
  "status must also survive forced LED refresh after JOG")
cc(80,127,0);cc(80,0,0)
assert(keyCount("space")==2,
  "PLAY after JOG should still pause on second press, not restart")
checkTransportLEDs(false,true,false,false,
  "PLAY pause following Scene1-5 JOG should light STOP")
-- JOG while already stopped must also preserve the stopped indicator.
cc(82,1,4);cc(82,65,0)
checkTransportLEDs(false,true,false,false,"STOP persists through JOG")

-- The old Korg Scene2-5 wheel was CC86 Continuous. Do NOT interpret its
-- absolute values as Sign Magnitude turns (which could jump speed).
keys={}
local logBefore=#midiLogs
cc(86,1,1);cc(86,60,1);cc(86,127,1)
cc(86,1,4)
assert(#keys==0,"CC86 Continuous must be ignored, not treated as JOG")
local warningCount=0
for i=logBefore+1,#midiLogs do
  if midiLogs[i]:find("wheel CC86 ignored",1,true) then
    warningCount=warningCount+1
  end
end
assert(warningCount==2,
  "warn exactly once per stale Continuous scene (Scenes2 and5)")
cc(82,1,5);cc(82,65,5)
assert(#keys==0,"input channel outside the five scenes must be ignored")

-- MARKER SET+JOG is scene-local: switching scenes must release a held
-- trim rather than leak a stale Scene 1 modifier onto Scene 2.
keys={}
cc(55,127,0)
cc(82,1,0)
cc(82,1,1)
cc(55,0,0)
assert(keyCount("v")==1 and keyCount(".")==1
  and keyCount("right")==1,
  "Scene1 held-marker trims; Scene2 wheel must not inherit stale trim")

-- REC/Undo CC81 and MARKER left/right CC56/57 now work in all five scenes.
-- These four controls must not overlap Scene 2 Fairlight MCU MUTE/SOLO.
for ch=0,4 do
  keys={}
  cc(81,127,ch);cc(81,0,ch)
  cc(56,127,ch);cc(56,0,ch)
  cc(57,127,ch);cc(57,0,ch)
  assert(keyCount("z")==1 and keyCount(",")==1 and keyCount(".")==1,
    "Scene"..(ch+1).." REC+MARKER arrows must send Undo/trim")
  local undoCmd=false
  for _,entry in ipairs(keys) do
    if entry.key=="z" and #entry.mods==1 and entry.mods[1]=="cmd" then
      undoCmd=true
    end
  end
  assert(undoCmd,"Scene"..(ch+1).." Undo must be Cmd+Z")
end

-- A fresh MARKER SET on ANY scene selects V, then JOG trims only while
-- held in that scene. Release returns JOG to normal frame navigation.
for ch=0,4 do
  keys={}
  cc(55,127,ch)
  cc(82,1,ch)
  cc(82,65,ch)
  cc(55,0,ch)
  cc(82,1,ch)
  assert(keyCount("v")==1 and keyCount(".")==1
    and keyCount(",")==1 and keyCount("right")==1,
    "Scene"..(ch+1).." MARKER SET hold/release/JOG regression")
  assert(keyCount("left")==0,"marker trim should not navigate while held")
end

-- CYCLE is shared; SHUTTLE speed is global and follows scene switching.
cc(54,127,3);cc(54,0,3)
assert(menus.title=="NK SHUTTLE","Scene4 CYCLE must enter shared SHUTTLE")
keys={}
cc(82,1,0);runPending()
assert(menus.title=="NK SHUTTLE +1"
  and keyCount("k")==1 and keyCount("l")==1,
  "Scene1 wheel starts shared +1 gear")
checkTransportLEDs(true,false,false,false,"all-scenes shuttle +1")
cc(82,1,1);runPending()
assert(menus.title=="NK SHUTTLE +2"
  and keyCount("k")==2 and keyCount("l")==3,
  "Scene2 wheel must CONTINUE from +1 to +2")
checkTransportLEDs(true,false,false,true,"Scene2 +2 FF")
cc(82,65,2);runPending()
assert(menus.title=="NK SHUTTLE +1",
  "Scene3 wheel left must decelerate from +2 to +1")
checkTransportLEDs(true,false,false,false,"Scene3 returns to normal")
cc(82,65,3);runPending()
assert(menus.title=="NK SHUTTLE",
  "Scene4 wheel left from +1 must STOP at zero")
checkTransportLEDs(false,true,false,false,"Scene4 zero")
cc(82,65,4);runPending()
assert(menus.title=="NK SHUTTLE -1",
  "Scene5 wheel left from zero starts reverse -1")
checkTransportLEDs(true,false,true,false,"Scene5 reverse -1")
cc(82,1,1);runPending()
assert(menus.title=="NK SHUTTLE",
  "Scene2 wheel right from -1 must STOP")
checkTransportLEDs(false,true,false,false,"Scene2 reverse to zero")
-- Quick turning across scene changes is still one batched JKL restart.
keys={}
cc(82,1,0);cc(82,1,4);runPending()
assert(menus.title=="NK SHUTTLE +2"
  and keyCount("k")==1 and keyCount("l")==2,
  "two ticks across Scenes1/5 should batch into one +2 request")
-- The old Scene1-only fader binding does not leak into any other scene.
keys={}
cc(2,127,1);cc(2,0,1)
assert(#keys==0,"Scene2 slider CC2 must stay unassigned")
-- FF is shared with all scenes, and the Scene5 wheel can downshift +2->+1.
cc(63,127,0);cc(63,0,0)
keys={}
cc(59,127,2);cc(59,0,2);runPending()
assert(menus.title=="NK SHUTTLE +2","Scene3 FF should set +2")
cc(82,65,4);runPending()
assert(menus.title=="NK SHUTTLE +1",
  "Scene5 wheel left after Scene3 FF must downshift to +1")
checkTransportLEDs(true,false,false,false,"Scene5 after Scene3 FF")
-- Switching modes must keep the current editing/navigation logic.
cc(54,127,4);cc(54,0,4)
assert(menus.title=="NK JOG",
  "Scene5 CYCLE must restore shared JOG and stop transport")
keys={}
cc(82,1,1)
assert(keyCount("right")==1,
  "Scene2 wheel must immediately revert to frame JOG after CYCLE")

-- Scene2 MUTE retains Fairlight ownership; shared REC/MARKER controls
-- MUST NOT accidentally route the Scene1 camera shortcuts.
keys={}
cc(21,127,1);cc(21,0,1)
assert(#keys==0 and latestLED(21)==0,
  "Scene2 MUTE LED feedback is safe but its Resolve action is unmapped")
cc(46,127,1);cc(46,0,1)
assert(#keys==0,"Scene2 SELECT remains unmapped")
local beforeInvalid=#outputs
cc(80,127,5);cc(80,0,5)
assert(#keys==0 and #outputs==beforeInvalid,
  "Unknown MIDI channel outside the five scenes must be ignored")
-- The heartbeat must do nothing while LEDs are disabled or calibrating.
menuAction("LED feedback:")
local afterDisable=#outputs
tickLED()
assert(#outputs==afterDisable,"heartbeat MUST respect LED OFF")
menuAction("LED feedback:")
menuAction("Recalibrate all 28 controls")
local duringLearn=#outputs
tickLED()
assert(#outputs==duringLearn,"heartbeat MUST skip 28-step learning")
menuAction("Cancel calibration")


-- Restart reloads the Lua controller; it does not alter calibration.
local beforeReload=reloadCount
menuAction("Restart Controller")
assert(reloadCount==beforeReload+1, "manual restart uses hs.reload")
urlEvents["nk-controller-restart"]()
assert(reloadCount==beforeReload+2, "updater restarts the same runtime")
-- The physical 2026-10-23 test: only LED_PROBE channel=0 illuminated.
-- Output 0 (Scene 1) carries all learned momentary LEDs. Out 1..4 must
-- never receive a Scene1-only MUTE/SELECT/REC CC, just five shared statuses.
local sharedCCs={[80]=true,[63]=true,[58]=true,[59]=true,[54]=true}
local outputRoutes={}
for _,e in ipairs(outputs) do
  assert(e.channel>=0 and e.channel<=4,
    "unsupported MIDI output channel "..tostring(e.channel))
  outputRoutes[e.channel]=true
  if e.channel~=0 then
    assert(sharedCCs[e.cc],
      "never send Scene1-only editing LED to another scene's output")
  end
end
for channel=0,4 do assert(outputRoutes[channel],
  "missing shared LED output for scene "..(channel+1)) end

-- Direct LED probe must use the SAME hs.midi device, never fire shortcuts,
-- and compare physical channel 1 vs channel 0 (all-channel broadcast).
local probeStart=#outputs
local beforeProbeKeys=#keys
assert(controller.ledProbe()==true,"LED probe must be available from Console")
assert(outputs[probeStart+1].channel==1 and outputs[probeStart+1].cc==21
  and outputs[probeStart+1].value==127,"Stage 1 MUTE1 LED ON / channel 1")
runPending()
assert(outputs[probeStart+2].channel==1 and outputs[probeStart+2].cc==21
  and outputs[probeStart+2].value==0,"Stage 1 MUTE1 LED OFF")
assert(outputs[probeStart+3].channel==0 and outputs[probeStart+3].cc==21
  and outputs[probeStart+3].value==127,"Stage 2 all-channel ON")
assert(outputs[probeStart+4].channel==0 and outputs[probeStart+4].cc==21
  and outputs[probeStart+4].value==0,"Stage 2 all-channel OFF")
assert(#keys==beforeProbeKeys,"LED probe must not edit Resolve")

-- From Draft #12: observed Scene2 input must invalidate the Scene1
-- absolute shuttle fader pickup, not let a parked fader control transport.
cc(63,127,0)
keys={}
cc(2,64,0)
cc(2,127,0)
runPending()
assert(keyCount("k")==1 and keyCount("l")==4,
  "Scene1 fader should still control shuttle when centered first")
selectHardwareScene(2)
keys={}
cc(13,88,1) -- Scene2 rotary 1 reveals scene change
assert(#keys==0,"Scene2 rotary must never issue transport shortcuts")
cc(82,1,1)
assert(keyCount("right")==1,
  "Scene2 JOG must work despite Scene1 fader previously being active")
selectHardwareScene(1)
keys={}
cc(82,65,0)
assert(keyCount("left")==1,
  "returning to Scene1 must not keep stale faderActive lock")
keys={}
cc(2,127,0); runPending()
assert(#keys==0,"non-neutral parked fader must not steal shuttle")
cc(2,64,0)
assert(#keys==0,"centering only rearms, must not issue transport shortcut")
cc(2,0,0); runPending()
assert(keyCount("k")==1 and keyCount("j")==4,
  "rearmed Scene1 fader must recover reverse shuttle")
cc(63,127,0)
cc(55,127,0)
keys={}
cc(14,91,1)
cc(82,1,0)
assert(keyCount("right")==1 and keyCount(".")==0,
  "held Scene1 trim must not survive observed Scene2 CC")
print("SCENE1_FADER_REARM_AFTER_SCENE_SWITCH=PASS")
print("SCENE1_TRIM_STALE_STATE_RESET=PASS")

print("LED_CONSOLE_TWO_CHANNEL_PROBE=PASS")
print("RAW_MIDI_CONSOLE_ZERO_BASED=PASS")
print("JOG_CC82_DIRECTION_DIAGNOSTIC=PASS")
print("CLEAN_WIZARD_28=PASS")
print("FADER_1_STRICT_CC2=PASS")
print("SHUTTLE_ONE_TICK_AND_BURST=PASS")
print("JOG_SHUTTLE_STOP=PASS")
print("EXTERNAL_LED_CHANNEL0_PLAY_TOGGLE=PASS")
print("GLOBAL_TRANSPORT_SCENES_1_TO_5=PASS")
print("JOG_SIGN_MAGNITUDE_SCENES_1_TO_5=PASS")
print("JOG_DURING_PLAY_PRESERVES_TRANSPORT_LEDS=PASS")
print("SHUTTLE_SHARED_GEARS_ACROSS_SCENES=PASS")
print("CONTINUOUS_CC86_REJECTED=PASS")
print("EXTERNAL_LED_SCENES_1_TO_5=PASS")
print("SILENT_SCENE_SWITCH_LED_RESTORE=PASS")
print("PHYSICAL_RESOLVE_SPACE_LED_SYNC=PASS")
print("SHUTTLE_ONE_TICK_PLAY_LED_AND_SPACE=PASS")
print("FADER_REW_FF_LED_SYNC=PASS")
print("TRANSPORT_4_PERSISTENT_LEDS=PASS")
print("PHYSICAL_JKL_AND_SYNTHETIC_GUARD=PASS")
print("SHUTTLE_SIGNED_GEAR_ZERO_AND_FF_THRESHOLD=PASS")
print("FF_2X_PLAY_DOWNSHIFT_WHEEL_COHERENCE=PASS")
