-- Scene 2 product mode starts silently with Resolve, stops on pause.
local factory = dofile("scene2_session_menu.lua")
local now = 100
local ready, runningApp = false, true
local starts, interrupts, bridgeStarts, bridgeStops = 0, 0, 0, 0
local stored = nil
local timer = nil
local lastArgs, currentTask
local host = {
  printf=function(...) end,
  settings={
    get=function(key) return stored end,
    set=function(key, value) stored=value end,
  },
  timer={doEvery=function(interval, cb)
    assert(interval==1)
    timer={callback=cb,stopped=false,stop=function(self) self.stopped=true end}
    return timer
  end},
  task={new=function(_, finished, streamed, args)
    assert(type(streamed)=="function")
    lastArgs=args
    currentTask={
      running=false, done=finished,
      start=function(self)
        assert(not self.running)
        self.running=true; starts=starts+1
        return self
      end,
      isRunning=function(self) return self.running end,
      interrupt=function(self)
        self.running=false; interrupts=interrupts+1
      end
    }
    return currentTask
  end},
}
local bridge={
  active=false,
  start=function(self)
    self.active=true; bridgeStarts=bridgeStarts+1; return true
  end,
  stop=function(self)
    self.active=false; bridgeStops=bridgeStops+1
  end,
}
local function make(opts)
  opts=opts or {}
  opts.runner="/dev/null"
  opts.python="/dev/null"
  opts.mcuPython="/dev/null"
  opts.logPath="/dev/null"
  opts.ready=function() return ready end
  opts.appRunning=function() return runningApp end
  opts.clock=function() return now end
  return factory(host,bridge,opts)
end

local s=make()
assert(s:isEnabled() and not s:isRunning())
timer.callback()
assert(starts==0, "no launch until Resolve becomes active")
ready=true
timer.callback()
assert(starts==1 and s:isRunning() and bridgeStarts==1)
local cmd=table.concat(lastArgs," ")
assert(cmd:find("--auto-run",1,true))
assert(not cmd:find("--expected-project",1,true))
assert(not cmd:find("--confirmed-backup",1,true))
assert(not cmd:find("--allow-named-project",1,true))
assert(stored==nil, "first-run autostart should not modify settings")
timer.callback()
assert(starts==1, "single Python task owner")
assert(s:pause() and stored==false and interrupts==1)
assert(not bridge.active and bridgeStops==1)
currentTask.done(130, "", "")
timer.callback()
assert(starts==1, "paused session must not restart")
assert(not s:isEnabled())
assert(s:resume() and stored==true and starts==2)
currentTask.running=false
currentTask.done(1,"","")
timer.callback()
assert(starts==2, "unexpected error must back off")
now=111
timer.callback()
assert(starts==3, "bounded automatic recovery")
runningApp=false
timer.callback()
assert(interrupts==2, "quitting Resolve stops workers")
currentTask.done(130,"","")
ready=false
now=113
timer.callback()
assert(starts==3)
runningApp=true
ready=true
now=114
timer.callback()
assert(starts==4, "Resolve reopen automatically reactivates")
s:shutdown()
assert(timer.stopped and interrupts==3)
assert(stored==true, "shutdown does not persist pause")
currentTask.done(130,"","")
local paused=make({timer=false,autoEnabled=false})
assert(not paused:isEnabled())
assert(not paused:ensureRunning())
paused:shutdown()
print("SCENE2_AUTO_SESSION_TEST=PASS")
