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
      function dev:sendCommand()
        outputs[#outputs+1]=true
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
assert(#outputs==0,"controller must NEVER send LED output CC")
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
-- Complete one-shot relearn must preserve old saved config if interrupted.
local original=saved
menuAction("TELJES UJRABETANITAS")
cc(82,1)
menuAction("MEGSZAKITASA")
assert(saved==original,"aborted wizard must not overwrite settings")
assert(#outputs==0,"no LED output allowed")
print("RAW_MIDI_CONSOLE_ZERO_BASED=PASS")
print("JOG_CC82_DIRECTION_DIAGNOSTIC=PASS")
print("CLEAN_WIZARD_28=PASS")
print("FADER_1_STRICT_CC2=PASS")
print("JOG_SHUTTLE_STOP=PASS")
print("NO_LED_OUTPUT=PASS")
