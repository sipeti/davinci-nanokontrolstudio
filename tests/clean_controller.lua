-- Hardware-free regression test for the one-shot 28-step MIDI wizard.
local menus, queue, keys, outputs, repeatingTimers = {}, {}, {}, {}, {}
local saved, midiCallback, keyboardCallback, keyboardTap = nil, nil, nil, nil
local nowSeconds = 1000
local SPACE_KEYCODE = 49
local TRANSPORT_KEYCODES = {space=SPACE_KEYCODE,j=38,k=40,l=37}
local alerts, midiLogs = {}, {}
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
local function menuAction(label)
  for _,x in ipairs(menus.items()) do
    if x.title and x.title:find(label,1,true) and x.fn then return x.fn() end
  end
  error("menu item not found: "..label)
end
assert(menus.title=="NK JOG")
-- Old v1.2 settings deliberately not reused as a valid v1.3 configuration.
local exists=false
for _,item in ipairs(menus.items()) do
  if item.title:find("TELJES BETANITAS SZUKSEGES",1,true) then exists=true end
end
assert(exists,"must require clean recalibration")
menuAction("TELJES UJRABETANITAS")
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
assert(alerts[#alerts]:find("JOG BALRA",1,true),"wrong CCW magnitude must be diagnosed")
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
assert(#outputs==45,"44 reset commands plus persistent STOP LED after setup")
assert(allLEDBlanked(1,44),"initial LED OFF commands need output channel=0")
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
checkTransportLEDs(true,false,false,true,"SHUTTLE +1")
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

-- Reproduce: a single SHUTTLE tick starts playback, then keyboard Space
-- must pause it, without any manual STOP to resynchronize the PLAY LED.
keys={}
cc(82,1)
runPending()
assert(menus.title=="NK SHUTTLE +1" and latestLED(80)==127,
  "One wheel tick must indicate moving transport")
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
checkTransportLEDs(true,false,false,true,"physical keyboard L")
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
cc(58,127);cc(58,0)
assert(keyCount("j")==1,"Korg REW must inject J once")
checkTransportLEDs(true,false,true,false,"Korg REW no double count")
cc(59,127);cc(59,0)
assert(keyCount("l")==1,"Korg FF must inject L once")
checkTransportLEDs(true,false,false,true,"Korg FF no double count")
cc(63,127);cc(63,0)
checkTransportLEDs(false,true,false,false,"Korg STOP no double count")

-- Complete one-shot relearn must preserve old saved config if interrupted.
local original=saved
menuAction("TELJES UJRABETANITAS")
cc(82,1)
menuAction("MEGSZAKITASA")
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
menuAction("LED visszajelzes BE/KI")
assert(#outputs==after+44 and allLEDBlanked(after+1),
  "LED OFF must reset all known buttons on output channel 0")
after=#outputs
cc(21,127);cc(21,0)
assert(#outputs==after,"LED disabled must send no ACK")
menuAction("LED visszajelzes BE/KI")
assert(#outputs>=after+44 and latestLED(80)==0,
  "LED enable should refresh after a clean reset")

-- Scene selection is a hardware-only operation: NO MIDI event is guaranteed.
-- A periodic, state-only CC resend must restore PLAY/CYCLE after returning
-- to Scene 1 (or when entering Scene 2 External). No new key commands.
keys={}
cc(80,127,0);cc(80,0,0)
assert(keyCount("space")==1,"Scene1 PLAY should start local playback")
assert(latestLED(80)==127)
local outBeforeHeartbeat=#outputs
tickLED() -- simulate pressing SCENE away/back without incoming MIDI
assert(#outputs==outBeforeHeartbeat+5,
  "LED scene restore must resend 4 transport LEDs plus CYCLE")
local order={80,63,58,59,54}
for i,ccid in ipairs(order) do
  assert(outputs[outBeforeHeartbeat+i].cc==ccid
    and outputs[outBeforeHeartbeat+i].channel==0,
    "scene restore wrong CC/channel "..ccid)
end
assert(outputs[outBeforeHeartbeat+1].value==127,
  "PLAY must relight after silent scene switch")
assert(outputs[outBeforeHeartbeat+2].value==0
   and outputs[outBeforeHeartbeat+3].value==0
   and outputs[outBeforeHeartbeat+4].value==0,
  "STOP/REW/FF must stay off in normal play")
assert(keyCount("space")==1 and keyCount("k")==0,
  "LED sync MUST NOT change Resolve playback")

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
cc(58,127,2);cc(58,0,2)
assert(keyCount("j")==1,"Scene3 REW must keep fixed J shortcut")
checkTransportLEDs(true,false,true,false,"Scene3 REW")
cc(59,127,3);cc(59,0,3)
assert(keyCount("l")==1,"Scene4 FF must keep fixed L shortcut")
checkTransportLEDs(true,false,false,true,"Scene4 FF")
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
-- Only transport is global: Scene2 MUTE acknowledges LED but MUST NOT
-- invoke Scene1 CAM1 shortcut or any other editing side effect.
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
menuAction("LED visszajelzes BE/KI")
local afterDisable=#outputs
tickLED()
assert(#outputs==afterDisable,"heartbeat MUST respect LED OFF")
menuAction("LED visszajelzes BE/KI")
menuAction("TELJES UJRABETANITAS")
local duringLearn=#outputs
tickLED()
assert(#outputs==duringLearn,"heartbeat MUST skip 28-step learning")
menuAction("MEGSZAKITASA")


-- The physical 2026-10-23 test: only LED_PROBE channel=0 illuminated.
-- Normal PLAY/CYCLE/MUTE feedback must therefore all use channel=0.
for _,e in ipairs(outputs) do
  assert(e.channel==0,"normal Scene1 feedback sent to a non-working channel")
end

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

print("LED_CONSOLE_TWO_CHANNEL_PROBE=PASS")
print("RAW_MIDI_CONSOLE_ZERO_BASED=PASS")
print("JOG_CC82_DIRECTION_DIAGNOSTIC=PASS")
print("CLEAN_WIZARD_28=PASS")
print("FADER_1_STRICT_CC2=PASS")
print("SHUTTLE_ONE_TICK_AND_BURST=PASS")
print("JOG_SHUTTLE_STOP=PASS")
print("EXTERNAL_LED_CHANNEL0_PLAY_TOGGLE=PASS")
print("GLOBAL_TRANSPORT_SCENES_1_TO_5=PASS")
print("SILENT_SCENE_SWITCH_LED_RESTORE=PASS")
print("PHYSICAL_RESOLVE_SPACE_LED_SYNC=PASS")
print("SHUTTLE_ONE_TICK_PLAY_LED_AND_SPACE=PASS")
print("FADER_REW_FF_LED_SYNC=PASS")
print("TRANSPORT_4_PERSISTENT_LEDS=PASS")
print("PHYSICAL_JKL_AND_SYNTHETIC_GUARD=PASS")
