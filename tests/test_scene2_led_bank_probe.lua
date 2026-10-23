-- Pure hardware mock: Scene 2 LED bank learns exactly 16 unique button CCs.
local messages, sent, timers = {},{},{}
hs = {
  printf=function(fmt,...) messages[#messages+1]=string.format(fmt,...) end,
  midi={
    devices=function() return {"Other","nanoKONTROL Studio"} end,
    new=function(name)
      assert(name=="nanoKONTROL Studio")
      local dev={}
      function dev:callback(fn) self.fn=fn end
      function dev:sendCommand(kind, meta)
        assert(kind=="controlChange")
        assert(meta.channel==1)
        assert(meta.controllerValue==0 or meta.controllerValue==127)
        sent[#sent+1]={cc=meta.controllerNumber,value=meta.controllerValue}
        return true
      end
      return dev
    end
  },
  timer={
    doAfter=function(seconds, callback)
      local t={seconds=seconds, callback=callback, done=false, stopped=false}
      function t:stop() self.stopped=true end
      timers[#timers+1]=t
      return t
    end
  }
}
local function firePulseTimer()
  for _,t in ipairs(timers) do
    if not t.stopped and not t.done and t.seconds<2 then
      t.done=true
      t.callback()
      return true
    end
  end
  return false
end
local probe=assert(loadfile("scripts/scene2_led_bank_probe.lua"))()
local dev=probe.device
assert(probe.count==0)
assert(not probe.flashAll())
local function cc(ch,num,value)
  dev.fn(dev,"nanoKONTROL Studio","controlChange","",{
    channel=ch,controllerNumber=num,controllerValue=value
  })
end
-- Non-Scene2, rotary, and release do not register buttons.
cc(0,21,127)
cc(1,13,127)
cc(1,21,0)
assert(probe.count==0 and #sent==0)
for i=1,16 do
  local id=i<=8 and i+20 or i+20
  cc(1,id,127)
  assert(probe.count==i and probe.learned[i]==id)
  cc(1,id,127)
  assert(probe.count==i)
end
assert(probe.learned[1]==21 and probe.learned[9]==29)
assert(#sent==0,"learning must be MIDI input only")
probe.show()
assert(probe.flashAll())
assert(not probe.flashAll(),"no overlapping flashes")
assert(sent[1].cc==21 and sent[1].value==127)
for i=1,40 do
  if not firePulseTimer() then break end
end
assert(#sent==32,"exactly 16 on and 16 off expected")
for i=1,16 do
  assert(sent[2*i-1].cc==i+20 and sent[2*i-1].value==127)
  assert(sent[2*i].cc==i+20 and sent[2*i].value==0)
end
assert(probe.flashing==false)
probe.stop()
assert(dev.fn==nil and not probe.active)
assert(_G.nkScene2BankLedProbe==nil)
assert(#sent==48,"cleanup should turn exactly 16 learned LEDs off")
for i=33,48 do assert(sent[i].value==0) end
local sawComplete=false
for _,msg in ipairs(messages) do
  if msg:find("CHASE COMPLETE",1,true) then sawComplete=true end
end
assert(sawComplete)
print("SCENE2_LED_BANK_PROBE_TEST=PASS")
