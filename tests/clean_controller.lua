-- Hardware-free regression test for the one-shot 28-step MIDI wizard.
local menus, queue, keys, outputs = {}, {}, {}, {}
local saved, midiCallback = nil, nil
local alerts, midiLogs = {}, {}
local app = {
  title=function() return "DaVinci Resolve" end,
  bundleID=function() return "com.blackmagic-design.DaVinciResolve" end,
  selectMenuItem=function() return true end,
}
hs = {
  settings = {
    get=function() return {wheel="cc:1:86", buttons={stop="cc:1:59"}} end,
    set=function(_,value) saved=value end,
  },
  alert={show=function(msg) alerts[#alerts+1]=msg end},
  printf=function(fmt,...) midiLogs[#midiLogs+1]=string.format(fmt, ...) end,
  application={frontmostApplication=function() return app end},
  eventtap={keyStroke=function(mods,k) keys[#keys+1]={key=k, mods=mods} end},
  timer={doAfter=function(delay,fn)
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
local function cc(id,v)
  assert(midiCallback)
  midiCallback(nil,"nanoKONTROL Studio","controlChange",nil,
    {channel=0,controllerNumber=id,controllerValue=v, data=string.format('B0 %02X %02X',id,v)})
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
local function allLEDBlanked(startIndex)
  for i=startIndex or 1,#outputs do
    if outputs[i].value~=0 or outputs[i].channel~=1
       or outputs[i].cmd~="controlChange" then return false end
  end
  return true
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
-- 25 unique button CCs. Press only must NOT advance (momentary release required).
for i=1,25 do
  local ccId=29+i -- values 30..54
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
assert(saved.buttons.splitAll=="cc:0:54")
-- At successful 28/28 the External-mode controller receives a fresh OFF
-- on each known LED, and the input channel 0 must map to OUTPUT channel 1.
assert(#outputs==44,"expected 44 known Scene 1 LEDs reset after setup")
assert(allLEDBlanked(1),"initial LED OFF commands need output channel=1")
assert(latestLED(35)==0,"PLAY should start unlit")
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
local n=#keys
cc(82,1)
assert(#keys==n,"wheel should not trim during live fader shuttle")
cc(2,64)
assert(keyCount("k")==2,"center STOP must send K")
-- STOP button disarms fader, must center again.
cc(34,127) -- step 5: STOP
n=#keys
cc(2,127);runPending()
assert(#keys==n,"STOP must disarm fader")
cc(2,64);cc(2,0);runPending()
assert(keyCount("j")==4,"4 reverse JKL gears")
-- A held marker changes wheel to edit-point nudge; release cancels.
cc(2,64);cc(35,127) -- PLAY action stops fader
cc(39,127) -- step 10: editSelect 
cc(82,1)
assert(keyCount(".")==1,"held MARKER SET should trim")
cc(39,0)
cc(82,1)
assert(keyCount("right")>=1,"release restores plain JOG")
-- Wheel SHUTTLE response must be immediate (one tick) and burst-coalesced.
cc(30,127) -- CYCLE after JOG; old full-learn mapping is CC30
assert(menus.title=="NK SHUTTLE","CYCLE should switch to wheel SHUTTLE")
keys={}
cc(82,1)
assert(#keys==0,"one wheel event should queue a short batch, not K spam")
runPending()
assert(keyCount("k")==1 and keyCount("l")==1,
  "one jog tick must trigger one forward shuttle gear")
assert(menus.title=="NK SHUTTLE +1")
cc(82,65)
runPending()
assert(keyCount("k")==2,"one reverse tick at +1 must STOP shuttle")
assert(menus.title=="NK SHUTTLE")
keys={}
for _=1,4 do cc(82,1) end
assert(#keys==0,"fast MIDI burst should not restart Resolve 4 times")
runPending()
assert(keyCount("k")==1 and keyCount("l")==4,
  "four forward ticks must make one K then Lx4 (not four separate restarts)")
assert(menus.title=="NK SHUTTLE +4")
keys={}
cc(82,65)
runPending()
assert(keyCount("k")==1 and keyCount("l")==3,
  "one reverse tick at +4 should reduce to +3")
assert(menus.title=="NK SHUTTLE +3")
keys={}
cc(82,65) -- queue a wheel update
cc(34,127) -- physical STOP must cancel queued wheel changes
runPending()
assert(keyCount("k")==1 and keyCount("l")==0,
  "STOP must cancel a pending wheel batch")
assert(menus.title=="NK SHUTTLE")
cc(30,127) -- CYCLE returns to JOG
assert(menus.title=="NK JOG")
keys={}
cc(82,1)
assert(keyCount("right")==1, "normal JOG must remain 1 frame per tick")

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
cc(35,127);cc(35,0)
assert(keyCount("space")==1 and keyCount("k")==0,
  "PLAY must send Space without a preceding K")
assert(latestLED(35)==127,"first PLAY must latch the local request LED")
cc(35,127);cc(35,0)
assert(keyCount("space")==2 and keyCount("k")==0,
  "second PLAY must pause with Space and no K")
assert(latestLED(35)==0,"second PLAY must clear the LED")

-- STOP sends K, cancels PLAY light, and should flash only while held.
cc(35,127);cc(35,0)
cc(34,127)
assert(latestLED(35)==0 and latestLED(34)==127,
  "STOP should extinguish PLAY, keep its own momentary LED")
cc(34,0)
assert(latestLED(34)==0,"STOP must go OFF on release")

-- CYCLE LED stays ON in SHUTTLE and goes OFF returning to JOG.
cc(30,127);cc(30,0)
assert(latestLED(30)==127,"CYCLE should show SHUTTLE")
cc(30,127);cc(30,0)
assert(latestLED(30)==0,"CYCLE should clear in JOG")

-- MUTE/CAM LED uses the received physical CC, not an inferred camera state.
cc(42,127)
assert(latestLED(42)==127,"MUTE 1 pressed LED")
cc(42,0)
assert(latestLED(42)==0,"MUTE 1 released LED")

-- The one LED menu toggle must turn *all* 44 LEDs off, and suspend feedback.
local after=#outputs
menuAction("LED visszajelzes BE/KI")
assert(#outputs==after+44 and allLEDBlanked(after+1),
  "LED OFF must reset all known buttons on output channel 1")
after=#outputs
cc(42,127);cc(42,0)
assert(#outputs==after,"LED disabled must send no ACK")
menuAction("LED visszajelzes BE/KI")
assert(#outputs>=after+44 and latestLED(35)==0,
  "LED enable should refresh after a clean reset")

print("RAW_MIDI_CONSOLE_ZERO_BASED=PASS")
print("JOG_CC82_DIRECTION_DIAGNOSTIC=PASS")
print("CLEAN_WIZARD_28=PASS")
print("FADER_1_STRICT_CC2=PASS")
print("SHUTTLE_ONE_TICK_AND_BURST=PASS")
print("JOG_SHUTTLE_STOP=PASS")
print("EXTERNAL_LED_CHANNEL1_PLAY_TOGGLE=PASS")
